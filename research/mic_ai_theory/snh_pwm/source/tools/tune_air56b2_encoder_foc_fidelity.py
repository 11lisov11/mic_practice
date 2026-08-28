from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.foc_svm_key_baseline import FocSvmKeyBaselineConfig
from models.air56b2_fidelity import generate_f2_samples, generate_f3_samples
from models.air56b2_nameplate_ensemble import generate_air56b2_ensemble
from tools.build_air56b2_fidelity_bundle import derived_seed, reference_digest
from tools.run_air56b2_encoder_foc_fidelity_study import _trial


def _evaluate(
    config: FocSvmKeyBaselineConfig,
    *,
    sample_seed: int,
    count: int,
    steps: int,
    target_speed_fraction: float,
    speed_ramp_s: float,
    load_fraction: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    f2_seed = derived_seed(sample_seed, "F2")
    f3_seed = derived_seed(sample_seed, "F3")
    f1_samples = generate_air56b2_ensemble(count, seed=sample_seed)
    f2_samples = generate_f2_samples(f1_samples, seed=f2_seed)
    f3_samples = generate_f3_samples(f1_samples, seed=f3_seed)
    trials = [
        _trial(
            f1,
            f2,
            f3,
            config=config,
            steps=steps,
            target_speed_fraction=target_speed_fraction,
            speed_ramp_s=speed_ramp_s,
            load_fraction=load_fraction,
        )
        for f1, f2, f3 in zip(f1_samples, f2_samples, f3_samples)
    ]
    failed = sum(trial["status"] != "PASS" for trial in trials)
    worst_steady = max(trial["steady_mean_abs_speed_error_rad_s"] for trial in trials)
    worst_final = max(trial["final_abs_speed_error_rad_s"] for trial in trials)
    peak_current = max(trial["peak_true_current_a"] for trial in trials)
    rejected = sum(trial["gateway_rejected_steps"] for trial in trials)
    fault_steps = sum(trial["gateway_fault_steps"] for trial in trials)
    score = (
        1000.0 * failed
        + worst_steady
        + worst_final
        + 0.1 * peak_current
        + 10.0 * rejected
        + 1000.0 * fault_steps
    )
    summary = {
        "score": score,
        "passed": failed == 0,
        "passed_trials": len(trials) - failed,
        "failed_trials": failed,
        "worst_steady_speed_error_rad_s": worst_steady,
        "worst_final_speed_error_rad_s": worst_final,
        "peak_true_current_a": peak_current,
        "gateway_rejected_steps": rejected,
        "gateway_fault_steps": fault_steps,
        "true_state_feedback_steps": sum(
            trial["true_state_feedback_steps"] for trial in trials
        ),
    }
    reference = {
        "sample_seed": int(sample_seed),
        "sample_count": len(f1_samples),
        "sample_reference_sha256": reference_digest(f1_samples),
        "component_seeds": {"F2": f2_seed, "F3": f3_seed},
    }
    return summary, reference


def tune_encoder_foc(
    oracle_tuning: dict[str, Any],
    *,
    oracle_tuning_sha256: str,
    master_seed: int,
    candidate_limit: int,
    train_count: int,
    validation_count: int,
    train_steps: int,
    validation_steps: int,
    top_k: int,
    target_speed_fraction: float,
    speed_ramp_s: float,
    load_fraction: float,
) -> dict[str, Any]:
    if oracle_tuning.get("schema") != "air56b2-foc-ensemble-tuning-v1":
        raise ValueError("unsupported oracle tuning schema")
    candidates = oracle_tuning.get("train_leaderboard")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("oracle tuning has no candidate pool")
    if candidate_limit < 1 or train_count < 1 or validation_count < 1:
        raise ValueError("candidate and sample counts must be positive")
    if train_steps < 1 or validation_steps < 1 or top_k < 1:
        raise ValueError("step counts and top_k must be positive")
    if not 0.0 < target_speed_fraction <= 1.0:
        raise ValueError("target speed fraction must be within (0, 1]")
    if speed_ramp_s <= 0.0 or not 0.0 <= load_fraction <= 1.0:
        raise ValueError("invalid speed ramp or load fraction")

    pool = candidates[: min(candidate_limit, len(candidates))]
    encoder_train_seed = derived_seed(master_seed, "ENCODER_FOC_TRAIN")
    encoder_validation_seed = derived_seed(master_seed, "ENCODER_FOC_VALIDATION")
    train_rows: list[dict[str, Any]] = []
    train_reference: dict[str, Any] | None = None
    for row in pool:
        config = FocSvmKeyBaselineConfig(**row["config"])
        metrics, reference = _evaluate(
            config,
            sample_seed=encoder_train_seed,
            count=train_count,
            steps=train_steps,
            target_speed_fraction=target_speed_fraction,
            speed_ramp_s=speed_ramp_s,
            load_fraction=load_fraction,
        )
        train_reference = reference
        train_rows.append(
            {
                "candidate_index": int(row["candidate_index"]),
                "config": asdict(config),
                "oracle_train_metrics": row.get("metrics"),
                "encoder_train_metrics": metrics,
            }
        )
    train_rows.sort(
        key=lambda row: (row["encoder_train_metrics"]["score"], row["candidate_index"])
    )

    validation_rows: list[dict[str, Any]] = []
    validation_reference: dict[str, Any] | None = None
    for row in train_rows[: min(top_k, len(train_rows))]:
        config = FocSvmKeyBaselineConfig(**row["config"])
        metrics, reference = _evaluate(
            config,
            sample_seed=encoder_validation_seed,
            count=validation_count,
            steps=validation_steps,
            target_speed_fraction=target_speed_fraction,
            speed_ramp_s=speed_ramp_s,
            load_fraction=load_fraction,
        )
        validation_reference = reference
        validation_rows.append(
            {
                "candidate_index": row["candidate_index"],
                "config": row["config"],
                "encoder_train_metrics": row["encoder_train_metrics"],
                "encoder_validation_metrics": metrics,
            }
        )
    validation_rows.sort(
        key=lambda row: (
            row["encoder_validation_metrics"]["score"],
            row["encoder_train_metrics"]["score"],
            row["candidate_index"],
        )
    )
    selected = validation_rows[0]
    selected_passed = bool(selected["encoder_validation_metrics"]["passed"])
    no_true_state = all(
        row["encoder_train_metrics"]["true_state_feedback_steps"] == 0
        for row in train_rows
    ) and all(
        row["encoder_validation_metrics"]["true_state_feedback_steps"] == 0
        for row in validation_rows
    )
    gates = {
        "selected_validation_passed": selected_passed,
        "train_and_validation_are_disjoint": encoder_train_seed != encoder_validation_seed,
        "no_true_state_feedback": no_true_state,
        "hardware_claim_absent": True,
    }
    return {
        "schema": "air56b2-encoder-foc-tuning-v1",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "hardware_claim": False,
        "hardware_identified": False,
        "hardware_release_ready": False,
        "master_seed": int(master_seed),
        "oracle_tuning_sha256": str(oracle_tuning_sha256),
        "oracle_state_feedback_contract": oracle_tuning.get("state_feedback_contract"),
        "candidate_count": len(pool),
        "top_k": min(top_k, len(train_rows)),
        "train_steps": int(train_steps),
        "validation_steps": int(validation_steps),
        "train_reference": train_reference,
        "validation_reference": validation_reference,
        "command": {
            "target_speed_fraction_of_rated": float(target_speed_fraction),
            "speed_ramp_s": float(speed_ramp_s),
            "load_torque_fraction_of_rated": float(load_fraction),
        },
        "feedback_contract": {
            "controller_state": "current_voltage_flux_observer_estimate",
            "speed": "delayed_quantized_as5600_finite_difference",
            "true_flux_speed_angle_to_controller": False,
            "current_offset_handling": "pre_pwm_zero_current_calibration",
        },
        "gates": gates,
        "selected": selected,
        "validation_leaderboard": validation_rows,
        "train_leaderboard": train_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tune AIR56B2 encoder-observer FOC on disjoint F1/F1S/F2/F3 ensembles."
    )
    parser.add_argument("--oracle-tuning", type=Path, required=True)
    parser.add_argument("--master-seed", type=int, default=560225)
    parser.add_argument("--candidate-limit", type=int, default=16)
    parser.add_argument("--train-count", type=int, default=3)
    parser.add_argument("--validation-count", type=int, default=6)
    parser.add_argument("--train-steps", type=int, default=6000)
    parser.add_argument("--validation-steps", type=int, default=10_000)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--target-speed-fraction", type=float, default=0.30)
    parser.add_argument("--speed-ramp-s", type=float, default=0.20)
    parser.add_argument("--load-fraction", type=float, default=0.50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.oracle_tuning.read_bytes()
    payload = tune_encoder_foc(
        json.loads(raw.decode("utf-8")),
        oracle_tuning_sha256=hashlib.sha256(raw).hexdigest(),
        master_seed=args.master_seed,
        candidate_limit=args.candidate_limit,
        train_count=args.train_count,
        validation_count=args.validation_count,
        train_steps=args.train_steps,
        validation_steps=args.validation_steps,
        top_k=args.top_k,
        target_speed_fraction=args.target_speed_fraction,
        speed_ramp_s=args.speed_ramp_s,
        load_fraction=args.load_fraction,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": payload["status"] == "PASS",
                "status": payload["status"],
                "selected_candidate": payload["selected"]["candidate_index"],
                "validation_passed": payload["selected"]["encoder_validation_metrics"][
                    "passed"
                ],
                "output": str(args.output.resolve()),
                "hardware_release_ready": False,
            }
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

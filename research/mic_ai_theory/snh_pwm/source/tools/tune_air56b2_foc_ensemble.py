from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
from random import Random
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.foc_svm_key_baseline import FocSvmKeyBaselineConfig
from models.air56b2_nameplate_ensemble import (
    Air56B2Nameplate,
    derive_nameplate,
    generate_air56b2_ensemble,
    select_nominal_sample,
)
from models.induction_motor_alpha_beta import AlphaBetaMotorParams
from tools.run_air56b2_nameplate_ensemble_study import split_seed
from tools.run_safe_neural_horizon_pwm_study import _make_base_params, run_trial
from tools.build_air56b2_fidelity_bundle import reference_digest


SCENARIOS = ("air56b2_half_load", "air56b2_rated_load")
AIR56B2_NAMEPLATE = Air56B2Nameplate()
RATED_OMEGA_RAD_S = derive_nameplate(AIR56B2_NAMEPLATE).rated_omega_rad_s
CURRENT_PEAK_LIMIT_A = (
    math.sqrt(2.0)
    * AIR56B2_NAMEPLATE.line_current_a
    * AIR56B2_NAMEPLATE.start_current_ratio
    * 1.05
)


def _log_uniform(rng: Random, low: float, high: float) -> float:
    return math.exp(rng.uniform(math.log(low), math.log(high)))


def build_candidates(count: int, *, seed: int, dt_s: float) -> list[FocSvmKeyBaselineConfig]:
    if count < 1:
        raise ValueError("count must be positive")
    rng = Random(seed)
    base = FocSvmKeyBaselineConfig(dt_s=dt_s)
    candidates = [base]
    if count > 1:
        candidates.append(
            replace(
                base,
                speed_kp=0.03,
                speed_ki=0.5,
                current_kp=1.0,
                current_ki=1000.0,
                torque_limit_nm=1.5,
                flux_ref_wb=0.54,
                id_max_fraction=1.0,
                iq_max_fraction=1.0,
                voltage_limit_fraction=1.0,
                switching_tiebreak_weight=0.01,
                preflux_voltage_fraction=0.02,
            )
        )
    while len(candidates) < count:
        candidates.append(
            replace(
                base,
                speed_kp=_log_uniform(rng, 0.015, 0.40),
                speed_ki=_log_uniform(rng, 0.10, 10.0),
                current_kp=_log_uniform(rng, 1.0, 25.0),
                current_ki=_log_uniform(rng, 500.0, 15_000.0),
                torque_limit_nm=rng.uniform(1.1, 4.0),
                flux_ref_wb=rng.uniform(0.34, 0.58),
                id_max_fraction=rng.uniform(0.40, 1.00),
                iq_max_fraction=rng.uniform(0.70, 1.60),
                voltage_limit_fraction=rng.uniform(0.92, 1.00),
                switching_tiebreak_weight=_log_uniform(rng, 0.003, 0.08),
                preflux_voltage_fraction=rng.uniform(0.01, 0.10),
            )
        )
    return candidates


def evaluate_config(
    cfg: FocSvmKeyBaselineConfig,
    *,
    base_motor: AlphaBetaMotorParams,
    plant_samples: list[Any],
    steps: int,
    split: str,
    controller_model_mode: str = "fixed_nominal",
) -> dict[str, Any]:
    if controller_model_mode not in {"fixed_nominal", "matched_plant"}:
        raise ValueError("controller_model_mode must be fixed_nominal or matched_plant")
    _, inverter = _make_base_params()
    rows: list[dict[str, float]] = []
    for scenario in SCENARIOS:
        for sample in plant_samples:
            real_params = AlphaBetaMotorParams.from_motor_params(sample.motor)
            rows.append(
                run_trial(
                    label="foc_svm_key_baseline",
                    base_motor=(
                        real_params if controller_model_mode == "matched_plant" else base_motor
                    ),
                    inverter=inverter,
                    rng=Random(split_seed(sample.seed, split)),
                    steps=steps,
                    horizon=1,
                    feedback_period=1,
                    scenario=scenario,
                    controller_config=cfg,
                    real_params_override=real_params,
                )
            )

    steady_worst = max(row["steady_mean_abs_speed_error"] for row in rows)
    final_worst = max(row["final_abs_speed_error"] for row in rows)
    current_worst = max(row["max_current_abs"] for row in rows)
    safety_worst = max(row["safety_violations"] for row in rows)
    fault_worst = max(row["fault_latch_count"] for row in rows)
    fallback_mean = sum(row["fallback_count"] for row in rows) / len(rows)
    loss_proxy_mean = sum(row["controller_inverter_loss_proxy_mean_w"] for row in rows) / len(rows)
    current_excess = max(0.0, current_worst / CURRENT_PEAK_LIMIT_A - 1.0)
    score = (
        (steady_worst / RATED_OMEGA_RAD_S) ** 2
        + 0.5 * (final_worst / RATED_OMEGA_RAD_S) ** 2
        + 8.0 * current_excess**2
        + 20.0 * float(safety_worst > 0.0)
        + 20.0 * float(fault_worst > 0.0)
        + 0.001 * fallback_mean
        + 1.0e-5 * loss_proxy_mean
    )
    speed_limit = 0.10 * RATED_OMEGA_RAD_S
    return {
        "score": score,
        "passed": bool(
            steady_worst <= speed_limit
            and final_worst <= speed_limit
            and current_worst <= CURRENT_PEAK_LIMIT_A
            and safety_worst == 0.0
            and fault_worst == 0.0
        ),
        "steady_speed_error_worst_rad_s": steady_worst,
        "final_speed_error_worst_rad_s": final_worst,
        "peak_current_worst_a": current_worst,
        "safety_violations_worst": safety_worst,
        "fault_latch_steps_worst": fault_worst,
        "fallback_steps_mean": fallback_mean,
        "inverter_loss_proxy_mean_w": loss_proxy_mean,
        "trial_count": len(rows),
    }


def tune(
    *,
    candidate_count: int,
    train_count: int,
    validation_count: int,
    train_steps: int,
    validation_steps: int,
    top_k: int,
    master_seed: int,
    controller_model_mode: str = "matched_plant",
) -> dict[str, Any]:
    train_seed = split_seed(master_seed, "train")
    validation_seed = split_seed(master_seed, "validation")
    train_samples = generate_air56b2_ensemble(train_count, seed=train_seed)
    validation_samples = generate_air56b2_ensemble(validation_count, seed=validation_seed)
    nominal = select_nominal_sample(train_samples)
    base_motor = AlphaBetaMotorParams.from_motor_params(nominal.motor)
    _, inverter = _make_base_params()
    candidates = build_candidates(
        candidate_count,
        seed=split_seed(master_seed, "ood_stress"),
        dt_s=inverter.t_pwm_s,
    )

    train_rows: list[dict[str, Any]] = []
    for index, cfg in enumerate(candidates):
        train_rows.append(
            {
                "candidate_index": index,
                "config": asdict(cfg),
                "metrics": evaluate_config(
                    cfg,
                    base_motor=base_motor,
                    plant_samples=train_samples,
                    steps=train_steps,
                    split="train",
                    controller_model_mode=controller_model_mode,
                ),
            }
        )
    train_rows.sort(key=lambda row: (row["metrics"]["score"], row["candidate_index"]))

    validation_rows: list[dict[str, Any]] = []
    for row in train_rows[: max(1, min(top_k, len(train_rows)))]:
        cfg = FocSvmKeyBaselineConfig(**row["config"])
        validation_rows.append(
            {
                "candidate_index": row["candidate_index"],
                "config": row["config"],
                "train_metrics": row["metrics"],
                "validation_metrics": evaluate_config(
                    cfg,
                    base_motor=base_motor,
                    plant_samples=validation_samples,
                    steps=validation_steps,
                    split="validation",
                    controller_model_mode=controller_model_mode,
                ),
            }
        )
    validation_rows.sort(
        key=lambda row: (
            row["validation_metrics"]["score"],
            row["train_metrics"]["score"],
            row["candidate_index"],
        )
    )
    selected = validation_rows[0]
    return {
        "schema": "air56b2-foc-ensemble-tuning-v1",
        "status": "host_simulation_tuning_only",
        "hardware_claim": False,
        "blind_holdout_used": False,
        "controller_model_mode": controller_model_mode,
        "master_seed": master_seed,
        "train_seed": train_seed,
        "validation_seed": validation_seed,
        "train_reference": {
            "sample_count": len(train_samples),
            "sample_reference_sha256": reference_digest(train_samples),
        },
        "validation_reference": {
            "sample_count": len(validation_samples),
            "sample_reference_sha256": reference_digest(validation_samples),
        },
        "candidate_count": candidate_count,
        "train_sample_count": train_count,
        "validation_sample_count": validation_count,
        "train_steps": train_steps,
        "validation_steps": validation_steps,
        "controller_model_sample": nominal.index,
        "state_feedback_contract": "oracle_full_simulated_state",
        "hardware_release_ready": False,
        "acceptance_limits": {
            "steady_and_final_speed_error_rad_s": 0.10 * RATED_OMEGA_RAD_S,
            "current_alpha_beta_peak_a": CURRENT_PEAK_LIMIT_A,
        },
        "selected": selected,
        "validation_leaderboard": validation_rows,
        "train_leaderboard": train_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune FOC-SVM on AIR56B2 train/validation ensembles.")
    parser.add_argument("--candidates", type=int, default=32)
    parser.add_argument("--train-count", type=int, default=6)
    parser.add_argument("--validation-count", type=int, default=8)
    parser.add_argument("--train-steps", type=int, default=1200)
    parser.add_argument("--validation-steps", type=int, default=2000)
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--master-seed", type=int, default=560225)
    parser.add_argument(
        "--controller-model-mode",
        choices=("fixed_nominal", "matched_plant"),
        default="matched_plant",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = tune(
        candidate_count=args.candidates,
        train_count=args.train_count,
        validation_count=args.validation_count,
        train_steps=args.train_steps,
        validation_steps=args.validation_steps,
        top_k=args.top_k,
        master_seed=args.master_seed,
        controller_model_mode=args.controller_model_mode,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "selected_candidate": payload["selected"]["candidate_index"],
                "validation_passed": payload["selected"]["validation_metrics"]["passed"],
                "validation_score": payload["selected"]["validation_metrics"]["score"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

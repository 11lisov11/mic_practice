from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.foc_svm_key_baseline import FocSvmKeyBaselineConfig
from models.air56b2_nameplate_ensemble import generate_air56b2_ensemble, select_nominal_sample
from models.induction_motor_alpha_beta import AlphaBetaMotorParams
from tools.run_air56b2_nameplate_ensemble_study import split_seed
from tools.tune_air56b2_foc_ensemble import evaluate_config
from tools.build_air56b2_fidelity_bundle import reference_digest


def validate_holdout(
    tuning_payload: dict[str, Any],
    *,
    count: int,
    steps: int,
) -> dict[str, Any]:
    if tuning_payload.get("schema") != "air56b2-foc-ensemble-tuning-v1":
        raise ValueError("unsupported tuning schema")
    if tuning_payload.get("blind_holdout_used") is not False:
        raise ValueError("tuning payload must prove that blind holdout was unused")
    selected = tuning_payload.get("selected")
    if not isinstance(selected, dict) or not isinstance(selected.get("config"), dict):
        raise ValueError("tuning payload has no selected FOC configuration")
    master_seed = int(tuning_payload["master_seed"])
    holdout_seed = split_seed(master_seed, "blind_holdout")
    holdout = generate_air56b2_ensemble(count, seed=holdout_seed)
    train = generate_air56b2_ensemble(
        int(tuning_payload["train_sample_count"]),
        seed=int(tuning_payload["train_seed"]),
    )
    base_motor = AlphaBetaMotorParams.from_motor_params(select_nominal_sample(train).motor)
    cfg = FocSvmKeyBaselineConfig(**selected["config"])

    matched = evaluate_config(
        cfg,
        base_motor=base_motor,
        plant_samples=holdout,
        steps=steps,
        split="blind_holdout",
        controller_model_mode="matched_plant",
    )
    fixed = evaluate_config(
        cfg,
        base_motor=base_motor,
        plant_samples=holdout,
        steps=steps,
        split="blind_holdout",
        controller_model_mode="fixed_nominal",
    )
    return {
        "schema": "air56b2-foc-blind-holdout-v1",
        "status": "host_simulation_blind_holdout_only",
        "hardware_claim": False,
        "hardware_release_ready": False,
        "master_seed": master_seed,
        "holdout_seed": holdout_seed,
        "holdout_sample_count": count,
        "holdout_reference": {
            "sample_count": len(holdout),
            "sample_reference_sha256": reference_digest(holdout),
        },
        "reconstructed_train_reference": {
            "sample_count": len(train),
            "sample_reference_sha256": reference_digest(train),
        },
        "steps_per_trial": steps,
        "selected_candidate_index": int(selected["candidate_index"]),
        "selected_config": selected["config"],
        "state_feedback_contract": "oracle_full_simulated_state",
        "model_matched_feasibility": matched,
        "frozen_nameplate_only_robustness": fixed,
        "algorithm_feasibility_pass": bool(matched["passed"]),
        "nameplate_only_release_pass": bool(fixed["passed"]),
        "conclusion": (
            "FOC algorithm is simulation-feasible after parameter identification; "
            "nameplate-only hardware release remains forbidden."
            if matched["passed"] and not fixed["passed"]
            else "See individual gates; no hardware release is authorized."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate frozen AIR56B2 FOC tuning on blind holdout.")
    parser.add_argument("--tuning", type=Path, required=True)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.tuning.read_bytes()
    tuning_payload = json.loads(raw.decode("utf-8"))
    payload = validate_holdout(tuning_payload, count=args.count, steps=args.steps)
    payload["tuning_source"] = str(args.tuning.resolve())
    payload["tuning_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "algorithm_feasibility_pass": payload["algorithm_feasibility_pass"],
                "nameplate_only_release_pass": payload["nameplate_only_release_pass"],
                "hardware_release_ready": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

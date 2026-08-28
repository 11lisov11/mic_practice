from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from random import Random
import sys
from typing import Any
import math

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.air56b2_nameplate_ensemble import (
    Air56B2Nameplate,
    derive_nameplate,
    ensemble_manifest,
    generate_air56b2_ensemble,
    select_nominal_sample,
)
from models.induction_motor_alpha_beta import AlphaBetaMotorParams
from tools.run_safe_neural_horizon_pwm_study import (
    _controller_specs,
    _make_base_params,
    _paired_effects,
    _summarize_rows,
    run_trial,
)


SPLITS = ("train", "validation", "blind_holdout", "ood_stress")


def _acceptance(summary: dict[str, Any]) -> dict[str, Any]:
    nameplate = Air56B2Nameplate()
    rated_omega = derive_nameplate(nameplate).rated_omega_rad_s
    current_peak_limit = (
        math.sqrt(2.0)
        * nameplate.line_current_a
        * nameplate.start_current_ratio
        * 1.05
    )
    speed_error_limit = 0.10 * rated_omega
    checks = {
        "no_safety_violation": float(summary["safety_violations"]["worst"]) == 0.0,
        "no_fault_latch": int(summary["failure_count"]) == 0,
        "peak_current_within_nameplate_start_envelope": (
            float(summary["max_current_abs"]["worst"]) <= current_peak_limit
        ),
        "steady_speed_error_within_10pct": (
            float(summary["steady_mean_abs_speed_error"]["worst"]) <= speed_error_limit
        ),
        "final_speed_error_within_10pct": (
            float(summary["final_abs_speed_error"]["worst"]) <= speed_error_limit
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "limits": {
            "current_alpha_beta_peak_a": current_peak_limit,
            "speed_error_rad_s": speed_error_limit,
        },
    }


def split_seed(master_seed: int, split: str) -> int:
    if split not in SPLITS:
        raise ValueError(f"unknown split: {split}")
    digest = hashlib.sha256(f"AIR56B2:{master_seed}:{split}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big")


def run_ensemble_study(
    *,
    count: int,
    steps: int,
    master_seed: int,
    split: str,
    scenarios: list[str],
    quick: bool,
    controller_model_mode: str = "fixed_nominal",
) -> dict[str, Any]:
    if controller_model_mode not in {"fixed_nominal", "matched_plant"}:
        raise ValueError("controller_model_mode must be fixed_nominal or matched_plant")
    seed = split_seed(master_seed, split)
    samples = generate_air56b2_ensemble(count, seed=seed)
    nominal = select_nominal_sample(samples)
    base_motor = AlphaBetaMotorParams.from_motor_params(nominal.motor)
    _, inverter = _make_base_params()
    specs = _controller_specs(quick=quick)

    matrix: dict[str, Any] = {}
    paired_effects: dict[str, Any] = {}
    for scenario in scenarios:
        rows_by_controller: dict[str, list[dict[str, float]]] = {
            label: [] for label, _, _ in specs
        }
        for sample in samples:
            real_params = AlphaBetaMotorParams.from_motor_params(sample.motor)
            trial_controller_motor = (
                real_params if controller_model_mode == "matched_plant" else base_motor
            )
            trial_seed = split_seed(sample.seed, split)
            for label, horizon, feedback_period in specs:
                row = run_trial(
                    label=label,
                    base_motor=trial_controller_motor,
                    inverter=inverter,
                    rng=Random(trial_seed),
                    steps=steps,
                    horizon=horizon,
                    feedback_period=feedback_period,
                    scenario=scenario,
                    real_params_override=real_params,
                )
                row["ensemble_index"] = float(sample.index)
                rows_by_controller[label].append(row)

        scenario_summary = {
            label: _summarize_rows(rows) for label, rows in rows_by_controller.items()
        }
        matrix[scenario] = scenario_summary
        matrix[scenario]["acceptance"] = {
            label: _acceptance(summary) for label, summary in scenario_summary.items()
        }
        baseline_rows = rows_by_controller.get("foc_svm_key_baseline")
        if baseline_rows:
            paired_effects[scenario] = {
                label: _paired_effects(rows, baseline_rows)
                for label, rows in rows_by_controller.items()
                if label != "foc_svm_key_baseline"
            }

    return {
        "schema": "air56b2-nameplate-ensemble-study-v1",
        "status": "host_simulation_only",
        "hardware_claim": False,
        "motor": "IEK AIR56B2 0.25 kW 220 V Delta",
        "master_seed": int(master_seed),
        "split": split,
        "split_seed": seed,
        "sample_count": len(samples),
        "steps_per_trial": int(steps),
        "time_step_s": float(inverter.t_pwm_s),
        "simulated_duration_s": float(steps * inverter.t_pwm_s),
        "dynamic_duration_gate_pass": bool(steps * inverter.t_pwm_s >= 0.2),
        "scenarios": scenarios,
        "controller_model_sample": nominal.index,
        "controller_model_mode": controller_model_mode,
        "controller_model": (
            asdict(nominal.motor) if controller_model_mode == "fixed_nominal" else "matched_per_plant"
        ),
        "ensemble": ensemble_manifest(samples, master_seed=seed),
        "matrix": matrix,
        "paired_effects_vs_foc_svm": paired_effects,
        "all_scenarios_passed_controllers": [
            label
            for label, _, _ in specs
            if all(matrix[scenario]["acceptance"][label]["passed"] for scenario in scenarios)
        ],
        "limitations": [
            "Rs/Rr/Lsigma/Lm/J/B are nameplate-constrained estimates, not measurements.",
            "The plant and controllers are host models; no hardware timing claim is made.",
            "Final acceptance requires a disjoint blind holdout and later hardware validation.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run paired controllers on a deterministic AIR56B2 nameplate ensemble."
    )
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--master-seed", type=int, default=560225)
    parser.add_argument("--split", choices=SPLITS, default="validation")
    parser.add_argument(
        "--scenarios",
        default="air56b2_half_load,air56b2_rated_load",
    )
    parser.add_argument("--quick", action="store_true")
    parser.add_argument(
        "--controller-model-mode",
        choices=("fixed_nominal", "matched_plant"),
        default="fixed_nominal",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    payload = run_ensemble_study(
        count=args.count,
        steps=args.steps,
        master_seed=args.master_seed,
        split=args.split,
        scenarios=scenarios,
        quick=args.quick,
        controller_model_mode=args.controller_model_mode,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "sample_count": payload["sample_count"],
                "split": payload["split"],
                "dynamic_duration_gate_pass": payload["dynamic_duration_gate_pass"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

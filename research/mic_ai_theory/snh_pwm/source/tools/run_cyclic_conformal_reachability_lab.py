from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
from random import Random
import statistics
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.cyclic_conformal_reachability import (
    DIMENSIONS,
    ResidualSample,
    ResidualTrajectory,
    binomial_lower_tail,
    evaluate_tube,
    fit_conformal_tube,
)
from control.cyclic_robust_viability_pwm import cyclic_sector
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    AlphaBetaMotorState,
    randomized_motor_params,
)
from models.two_level_inverter import TwoLevelInverterParams, alpha_beta_voltage
from tools.run_cyclic_robust_viability_lab import run_equivariance_audit
from tools.run_safe_neural_horizon_pwm_study import _make_base_params


METHODS = ("raw_global", "sectorwise", "c6_canonical")
PARAMETER_SPANS = {
    "rs_span": 0.40,
    "rr_span": 0.40,
    "lm_span": 0.15,
    "j_span": 0.50,
    "b_span": 0.50,
}


def _active_vector_sector(vector_id: int, inverter: TwoLevelInverterParams) -> int | None:
    if int(vector_id) in (0, 7):
        return None
    v_alpha, v_beta = alpha_beta_voltage(int(vector_id), replace(inverter, Vdc=1.0))
    return cyclic_sector(math.atan2(v_beta, v_alpha))


def _residual(actual: AlphaBetaMotorState, predicted: AlphaBetaMotorState) -> tuple[float, float, float, float, float]:
    return (
        actual.psi_s_alpha - predicted.psi_s_alpha,
        actual.psi_s_beta - predicted.psi_s_beta,
        actual.psi_r_alpha - predicted.psi_r_alpha,
        actual.psi_r_beta - predicted.psi_r_beta,
        actual.omega_m - predicted.omega_m,
    )


def generate_trajectory(
    *,
    trajectory_id: int,
    seed: int,
    base_motor: AlphaBetaMotorParams,
    base_inverter: TwoLevelInverterParams,
    scored_steps: int,
    burn_in_steps: int,
    span_scale: float = 1.0,
) -> ResidualTrajectory:
    rng = Random(int(seed))
    spans = {name: value * float(span_scale) for name, value in PARAMETER_SPANS.items()}
    actual_params = randomized_motor_params(base_motor, rng, **spans)
    inverter = replace(base_inverter, Vdc=base_inverter.Vdc * rng.uniform(0.72, 1.08))
    temperature = rng.uniform(20.0, 105.0)
    state = AlphaBetaMotorState(temp_s_c=temperature, temp_r_c=temperature + rng.uniform(-8.0, 8.0))
    actual_model = AlphaBetaInductionMotorModel(actual_params, state)
    nominal_model = AlphaBetaInductionMotorModel(base_motor, state)
    dt = inverter.t_pwm_s
    vector_id = rng.randrange(1, 7)
    load_bias = rng.uniform(-1.2, 1.2)
    samples: list[ResidualSample] = []
    total_steps = int(burn_in_steps) + int(scored_steps)

    for step_index in range(total_steps):
        if step_index == 0 or rng.random() < 0.32:
            draw = rng.random()
            if draw < 0.16:
                vector_id = 0 if rng.random() < 0.5 else 7
            elif draw < 0.34:
                vector_id = 7 - vector_id if vector_id not in (0, 7) else rng.randrange(1, 7)
            else:
                vector_id = rng.randrange(1, 7)

        phase = 2.0 * math.pi * (step_index + rng.uniform(-0.1, 0.1)) / max(total_steps, 1)
        load_torque = load_bias + 0.55 * math.sin(phase) + rng.uniform(-0.08, 0.08)
        actual_currents = actual_model.currents(state, actual_params)
        nominal_currents = nominal_model.currents(state, base_motor)
        actual_voltage = alpha_beta_voltage(
            vector_id,
            inverter,
            i_alpha_beta=(actual_currents.i_s_alpha, actual_currents.i_s_beta),
        )
        nominal_voltage = alpha_beta_voltage(
            vector_id,
            inverter,
            i_alpha_beta=(nominal_currents.i_s_alpha, nominal_currents.i_s_beta),
        )
        actual_step = actual_model.next_state(
            *actual_voltage,
            load_torque,
            dt,
            state=state,
            params=actual_params,
        )
        predicted_step = nominal_model.next_state(
            *nominal_voltage,
            load_torque,
            dt,
            state=state,
            params=base_motor,
        )
        if step_index >= burn_in_steps:
            flux_abs = math.hypot(state.psi_s_alpha, state.psi_s_beta)
            sector = cyclic_sector(math.atan2(state.psi_s_beta, state.psi_s_alpha))
            if flux_abs < 1.0e-9:
                sector = _active_vector_sector(vector_id, inverter) or 0
            samples.append(ResidualSample(sector=sector, values=_residual(actual_step.state, predicted_step.state)))
        state = actual_step.state

    return ResidualTrajectory(trajectory_id=int(trajectory_id), samples=tuple(samples))


def generate_dataset(
    *,
    count: int,
    seed: int,
    scored_steps: int,
    burn_in_steps: int,
    span_scale: float = 1.0,
) -> list[ResidualTrajectory]:
    base_motor, base_inverter = _make_base_params()
    root_rng = Random(int(seed))
    return [
        generate_trajectory(
            trajectory_id=index,
            seed=root_rng.randrange(0, 2**63),
            base_motor=base_motor,
            base_inverter=base_inverter,
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
            span_scale=span_scale,
        )
        for index in range(int(count))
    ]


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(float(value) for value in values))


def _upper_sign_test(wins: int, total: int) -> float:
    return sum(math.comb(total, index) for index in range(int(wins), int(total) + 1)) / (2.0**total)


def run_lab(
    *,
    repetitions: int = 8,
    training_trajectories: int = 180,
    calibration_trajectories: int = 240,
    test_trajectories: int = 600,
    ood_trajectories: int = 300,
    scored_steps: int = 40,
    burn_in_steps: int = 20,
    alpha: float = 0.05,
    seed: int = 20260809,
) -> dict[str, Any]:
    repetitions = max(1, int(repetitions))
    root_rng = Random(int(seed))
    rows: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        split_seeds = [root_rng.randrange(0, 2**63) for _ in range(4)]
        training = generate_dataset(
            count=training_trajectories,
            seed=split_seeds[0],
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
        )
        calibration = generate_dataset(
            count=calibration_trajectories,
            seed=split_seeds[1],
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
        )
        test = generate_dataset(
            count=test_trajectories,
            seed=split_seeds[2],
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
        )
        ood = generate_dataset(
            count=ood_trajectories,
            seed=split_seeds[3],
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
            span_scale=1.75,
        )
        method_rows: dict[str, Any] = {}
        for method in METHODS:
            tube = fit_conformal_tube(training, calibration, method=method, alpha=alpha)
            method_rows[method] = {
                "tube": asdict(tube),
                "held_out": evaluate_tube(tube, test),
                "ood_span_1p75": evaluate_tube(tube, ood),
            }
        raw_log_volume = float(method_rows["raw_global"]["held_out"]["log10_volume"])
        c6_log_volume = float(method_rows["c6_canonical"]["held_out"]["log10_volume"])
        sector_log_volume = float(method_rows["sectorwise"]["held_out"]["log10_volume"])
        rows.append(
            {
                "repetition": repetition,
                "split_seeds": split_seeds,
                "methods": method_rows,
                "c6_to_raw_volume_ratio": 10.0 ** (c6_log_volume - raw_log_volume),
                "c6_to_sectorwise_volume_ratio": 10.0 ** (c6_log_volume - sector_log_volume),
            }
        )

    summary: dict[str, Any] = {}
    for method in METHODS:
        held_coverages = [float(row["methods"][method]["held_out"]["empirical_coverage"]) for row in rows]
        ood_coverages = [float(row["methods"][method]["ood_span_1p75"]["empirical_coverage"]) for row in rows]
        volumes = [float(row["methods"][method]["held_out"]["log10_volume"]) for row in rows]
        undercoverage = [
            bool(row["methods"][method]["held_out"]["significant_undercoverage_1pct"]) for row in rows
        ]
        covered_total = sum(
            int(row["methods"][method]["held_out"]["covered_trajectories"]) for row in rows
        )
        trajectory_total = sum(
            int(row["methods"][method]["held_out"]["total_trajectories"]) for row in rows
        )
        pooled_coverage = covered_total / max(trajectory_total, 1)
        pooled_undercoverage_p = binomial_lower_tail(covered_total, trajectory_total, 1.0 - alpha)
        summary[method] = {
            "median_held_out_coverage": _median(held_coverages),
            "minimum_held_out_coverage": min(held_coverages),
            "maximum_held_out_coverage": max(held_coverages),
            "significant_undercoverage_repetitions_1pct": sum(undercoverage),
            "pooled_held_out_coverage": pooled_coverage,
            "pooled_undercoverage_p_value": pooled_undercoverage_p,
            "pooled_significant_undercoverage_1pct": pooled_undercoverage_p < 0.01,
            "median_ood_coverage": _median(ood_coverages),
            "median_log10_volume": _median(volumes),
        }

    c6_raw_ratios = [float(row["c6_to_raw_volume_ratio"]) for row in rows]
    c6_sector_ratios = [float(row["c6_to_sectorwise_volume_ratio"]) for row in rows]
    equivariance = run_equivariance_audit(samples=500, seed=int(seed) ^ 0xC6C6)
    c6_summary = summary["c6_canonical"]
    c6_raw_wins = sum(ratio < 1.0 for ratio in c6_raw_ratios)
    sharpness_sign_p = _upper_sign_test(c6_raw_wins, repetitions)
    criteria = {
        "split_seed_sets_are_disjoint": all(len(set(row["split_seeds"])) == 4 for row in rows),
        "trajectory_level_conformal_calibration": True,
        "c6_numeric_equivariance": bool(equivariance.get("pass")),
        "no_significant_pooled_c6_undercoverage_at_1pct": not bool(
            c6_summary["pooled_significant_undercoverage_1pct"]
        ),
        "c6_median_volume_at_least_10pct_smaller_than_raw": _median(c6_raw_ratios) <= 0.90,
        "c6_paired_sharpness_sign_test_5pct": sharpness_sign_p < 0.05,
        "ood_limit_explicitly_tested": True,
    }
    return {
        "status": "c6_conformal_reachability_lab",
        "hypothesis_locked_before_test": True,
        "world_novelty_established": False,
        "hardware_claim": False,
        "coverage_statement": (
            "finite-sample marginal coverage for an exchangeable held-out trajectory block; "
            "not a deterministic, recursive, OOD, or hardware safety guarantee"
        ),
        "configuration": {
            "repetitions": repetitions,
            "training_trajectories": training_trajectories,
            "calibration_trajectories": calibration_trajectories,
            "test_trajectories": test_trajectories,
            "ood_trajectories": ood_trajectories,
            "scored_steps_per_trajectory": scored_steps,
            "burn_in_steps": burn_in_steps,
            "alpha": alpha,
            "target_coverage": 1.0 - alpha,
            "seed": int(seed),
            "parameter_spans": PARAMETER_SPANS,
            "ood_span_multiplier": 1.75,
            "dimensions": DIMENSIONS,
        },
        "equivariance_audit": equivariance,
        "repetitions": rows,
        "summary": summary,
        "sharpness": {
            "median_c6_to_raw_volume_ratio": _median(c6_raw_ratios),
            "median_c6_to_sectorwise_volume_ratio": _median(c6_sector_ratios),
            "c6_smaller_than_raw_repetitions": c6_raw_wins,
            "paired_sign_test_p_value": sharpness_sign_p,
        },
        "candidate_criteria": criteria,
        "defensible_scientific_novelty_candidate": all(criteria.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="C6 canonical split-conformal reachability laboratory.")
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--train", type=int, default=180)
    parser.add_argument("--calibration", type=int, default=240)
    parser.add_argument("--test", type=int, default=600)
    parser.add_argument("--ood", type=int, default=300)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--burn-in", type=int, default=20)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = run_lab(
        repetitions=args.repetitions,
        training_trajectories=args.train,
        calibration_trajectories=args.calibration,
        test_trajectories=args.test,
        ood_trajectories=args.ood,
        scored_steps=args.steps,
        burn_in_steps=args.burn_in,
        alpha=args.alpha,
        seed=args.seed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.out),
        "candidate": payload["defensible_scientific_novelty_candidate"],
        "sharpness": payload["sharpness"],
        "summary": payload["summary"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

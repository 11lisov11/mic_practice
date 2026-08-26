from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
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
    binomial_lower_confidence_bound,
    binomial_lower_tail,
    evaluate_tube,
    fit_conformal_tube,
    wilson_interval,
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
SHAPE_QUANTILE = 0.80
COVERAGE_NONINFERIORITY_MARGIN = 0.03
COVERAGE_ERROR_PROBABILITY = 0.01
SHARPNESS_RATIO_THRESHOLD = 0.90
PARAMETER_SPANS = {
    "rs_span": 0.40,
    "rr_span": 0.40,
    "lm_span": 0.15,
    "j_span": 0.50,
    "b_span": 0.50,
}
PROTOCOL_SOURCE_FILES = (
    "control/cyclic_conformal_reachability.py",
    "control/cyclic_robust_viability_pwm.py",
    "models/induction_motor_alpha_beta.py",
    "models/two_level_inverter.py",
    "tools/run_cyclic_conformal_reachability_lab.py",
)


def build_protocol_manifest(configuration: dict[str, Any]) -> tuple[dict[str, Any], str]:
    base_motor, base_inverter = _make_base_params()
    source_hashes = {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in PROTOCOL_SOURCE_FILES
    }
    protocol_configuration = {
        key: value
        for key, value in configuration.items()
        if key not in {"seed"}
    }
    manifest = {
        "schema": "c6_bcr_protocol/v2",
        "method": "c6_canonical_block_conformal_reachability",
        "configuration": protocol_configuration,
        "base_motor": asdict(base_motor),
        "base_inverter": asdict(base_inverter),
        "source_files_sha256": source_hashes,
        "prediction_assumption": "one_step_oracle_state_and_stator_flux_sector",
        "estimator_based": False,
        "preregistration_claim": False,
    }
    canonical = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return manifest, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def _draw_unique_seed(rng: Random, used: set[int]) -> int:
    while True:
        seed = rng.randrange(0, 2**63)
        if seed not in used:
            used.add(seed)
            return seed


def _run_independent_coverage_probe(
    *,
    repetitions: int,
    training_trajectories: int,
    calibration_trajectories: int,
    scored_steps: int,
    burn_in_steps: int,
    alpha: float,
    root_rng: Random,
    used_seeds: set[int],
) -> dict[str, Any]:
    """Use one test block per independent calibration fit for exact coverage inference."""

    if repetitions <= 0:
        return {
            "status": "not_run",
            "method": "c6_canonical",
            "probe_repetitions": 0,
            "covered_probes": 0,
            "empirical_coverage": None,
            "target_coverage": 1.0 - float(alpha),
            "wilson95_low": None,
            "wilson95_high": None,
            "undercoverage_p_value": None,
            "significant_undercoverage_1pct": None,
            "lower_confidence_bound_99": None,
            "noninferiority_margin": COVERAGE_NONINFERIORITY_MARGIN,
            "noninferiority_threshold": 1.0 - float(alpha) - COVERAGE_NONINFERIORITY_MARGIN,
            "noninferiority_pass": False,
            "training_seed": None,
            "calibration_test_seed_pairs": [],
            "all_seed_streams_unique": False,
            "all_quantiles_finite": False,
            "rows": [],
        }

    training_seed = _draw_unique_seed(root_rng, used_seeds)
    fixed_training = generate_dataset(
        count=training_trajectories,
        seed=training_seed,
        scored_steps=scored_steps,
        burn_in_steps=burn_in_steps,
    )
    rows: list[dict[str, Any]] = []
    seed_pairs: list[list[int]] = []
    covered = 0
    for probe_index in range(int(repetitions)):
        calibration_seed = _draw_unique_seed(root_rng, used_seeds)
        test_seed = _draw_unique_seed(root_rng, used_seeds)
        seed_pairs.append([calibration_seed, test_seed])
        calibration = generate_dataset(
            count=calibration_trajectories,
            seed=calibration_seed,
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
        )
        test = generate_dataset(
            count=1,
            seed=test_seed,
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
        )[0]
        tube = fit_conformal_tube(
            fixed_training,
            calibration,
            method="c6_canonical",
            alpha=alpha,
            shape_quantile=SHAPE_QUANTILE,
        )
        score = float(tube.trajectory_score(test))
        is_covered = bool(score <= tube.calibration_quantile + 1.0e-15)
        covered += int(is_covered)
        rows.append(
            {
                "probe": probe_index,
                "calibration_seed": calibration_seed,
                "test_seed": test_seed,
                "finite_sample_rank": int(tube.finite_sample_rank),
                "calibration_quantile": float(tube.calibration_quantile),
                "test_score": score,
                "covered": is_covered,
            }
        )

    total = len(rows)
    coverage = covered / total
    low, high = wilson_interval(covered, total)
    target = 1.0 - float(alpha)
    undercoverage_p = binomial_lower_tail(covered, total, target)
    lower_bound = binomial_lower_confidence_bound(
        covered,
        total,
        error_probability=COVERAGE_ERROR_PROBABILITY,
    )
    noninferiority_threshold = target - COVERAGE_NONINFERIORITY_MARGIN
    flattened_seeds = [training_seed] + [seed for pair in seed_pairs for seed in pair]
    return {
        "status": "independent_calibration_test_coverage_probe",
        "method": "c6_canonical",
        "probe_repetitions": total,
        "covered_probes": covered,
        "empirical_coverage": coverage,
        "target_coverage": target,
        "wilson95_low": low,
        "wilson95_high": high,
        "undercoverage_p_value": undercoverage_p,
        "significant_undercoverage_1pct": bool(undercoverage_p < 0.01),
        "lower_confidence_bound_99": lower_bound,
        "noninferiority_margin": COVERAGE_NONINFERIORITY_MARGIN,
        "noninferiority_threshold": noninferiority_threshold,
        "noninferiority_pass": bool(lower_bound >= noninferiority_threshold),
        "training_seed": training_seed,
        "calibration_test_seed_pairs": seed_pairs,
        "all_seed_streams_unique": len(flattened_seeds) == len(set(flattened_seeds)),
        "all_quantiles_finite": all(
            math.isfinite(float(row["calibration_quantile"])) and math.isfinite(float(row["test_score"]))
            for row in rows
        ),
        "rows": rows,
        "inference_unit": "one held-out trajectory from one independent calibration fit",
        "training_split_conditioned_on": True,
    }


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
    coverage_probe_repetitions: int = 0,
) -> dict[str, Any]:
    repetitions = int(repetitions)
    coverage_probe_repetitions = int(coverage_probe_repetitions)
    counts = {
        "repetitions": repetitions,
        "training_trajectories": int(training_trajectories),
        "calibration_trajectories": int(calibration_trajectories),
        "test_trajectories": int(test_trajectories),
        "ood_trajectories": int(ood_trajectories),
        "scored_steps": int(scored_steps),
        "burn_in_steps": int(burn_in_steps),
    }
    if any(value <= 0 for name, value in counts.items() if name != "burn_in_steps"):
        raise ValueError("repetition, trajectory, and scored-step counts must be positive")
    if counts["burn_in_steps"] < 0:
        raise ValueError("burn_in_steps must be non-negative")
    if coverage_probe_repetitions < 0:
        raise ValueError("coverage_probe_repetitions must be non-negative")
    if not math.isfinite(float(alpha)) or not 0.0 < float(alpha) < 1.0:
        raise ValueError("alpha must be finite and in (0, 1)")
    root_rng = Random(int(seed))
    used_seeds: set[int] = set()
    rows: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        split_seeds = [_draw_unique_seed(root_rng, used_seeds) for _ in range(4)]
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
            tube = fit_conformal_tube(
                training,
                calibration,
                method=method,
                alpha=alpha,
                shape_quantile=SHAPE_QUANTILE,
            )
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
        summary[method] = {
            "median_held_out_coverage": _median(held_coverages),
            "minimum_held_out_coverage": min(held_coverages),
            "maximum_held_out_coverage": max(held_coverages),
            "conditional_undercoverage_diagnostic_repetitions_1pct": sum(undercoverage),
            "descriptive_pooled_held_out_coverage": pooled_coverage,
            "median_ood_coverage": _median(ood_coverages),
            "median_log10_volume": _median(volumes),
        }

    independent_probe = _run_independent_coverage_probe(
        repetitions=coverage_probe_repetitions,
        training_trajectories=training_trajectories,
        calibration_trajectories=calibration_trajectories,
        scored_steps=scored_steps,
        burn_in_steps=burn_in_steps,
        alpha=alpha,
        root_rng=root_rng,
        used_seeds=used_seeds,
    )
    c6_raw_ratios = [float(row["c6_to_raw_volume_ratio"]) for row in rows]
    c6_sector_ratios = [float(row["c6_to_sectorwise_volume_ratio"]) for row in rows]
    equivariance = run_equivariance_audit(samples=500, seed=int(seed) ^ 0xC6C6)
    sharpness_non_ties = [
        ratio
        for ratio in c6_raw_ratios
        if not math.isclose(ratio, SHARPNESS_RATIO_THRESHOLD, rel_tol=0.0, abs_tol=1.0e-15)
    ]
    c6_raw_wins = sum(ratio < SHARPNESS_RATIO_THRESHOLD for ratio in sharpness_non_ties)
    sharpness_sign_p = _upper_sign_test(c6_raw_wins, len(sharpness_non_ties))
    criteria = {
        "split_seed_sets_are_globally_disjoint": len(used_seeds)
        == 4 * repetitions + (1 + 2 * coverage_probe_repetitions if coverage_probe_repetitions else 0),
        "trajectory_level_conformal_calibration": True,
        "at_least_24_bulk_repetitions": repetitions >= 24,
        "at_least_200_training_trajectories": training_trajectories >= 200,
        "at_least_400_calibration_trajectories": calibration_trajectories >= 400,
        "at_least_800_descriptive_test_trajectories": test_trajectories >= 800,
        "at_least_40_scored_steps": scored_steps >= 40,
        "c6_numeric_equivariance": bool(equivariance.get("pass")),
        "at_least_400_independent_coverage_probes": coverage_probe_repetitions >= 400,
        "independent_coverage_probe_seed_streams_are_unique": bool(
            independent_probe["all_seed_streams_unique"]
        ),
        "independent_coverage_probe_quantiles_are_finite": bool(independent_probe["all_quantiles_finite"]),
        "independent_c6_coverage_noninferiority_lcb99": bool(independent_probe["noninferiority_pass"]),
        "c6_median_volume_at_least_10pct_smaller_than_raw": _median(c6_raw_ratios) <= 0.90,
        "c6_paired_10pct_sharpness_sign_test_5pct": sharpness_sign_p < 0.05,
    }
    configuration = {
        "repetitions": repetitions,
        "training_trajectories": training_trajectories,
        "calibration_trajectories": calibration_trajectories,
        "test_trajectories": test_trajectories,
        "ood_trajectories": ood_trajectories,
        "scored_steps_per_trajectory": scored_steps,
        "burn_in_steps": burn_in_steps,
        "alpha": alpha,
        "target_coverage": 1.0 - alpha,
        "coverage_noninferiority_margin": COVERAGE_NONINFERIORITY_MARGIN,
        "coverage_error_probability": COVERAGE_ERROR_PROBABILITY,
        "sharpness_ratio_threshold": SHARPNESS_RATIO_THRESHOLD,
        "shape_quantile": SHAPE_QUANTILE,
        "seed": int(seed),
        "coverage_probe_repetitions": coverage_probe_repetitions,
        "parameter_spans": dict(PARAMETER_SPANS),
        "ood_span_multiplier": 1.75,
        "dimensions": DIMENSIONS,
    }
    protocol_manifest, protocol_sha256 = build_protocol_manifest(configuration)
    generator_evidence_pass = all(criteria.values())
    return {
        "status": "c6_conformal_reachability_lab",
        "hypothesis_locked_before_test": False,
        "preregistration_claim": False,
        "world_novelty_established": False,
        "hardware_claim": False,
        "coverage_statement": (
            "finite-sample marginal coverage for one exchangeable held-out trajectory per independent "
            "calibration fit, conditional on the fixed training split; bulk held-out coverage is descriptive only; "
            "not a deterministic, recursive, OOD, or hardware safety guarantee"
        ),
        "configuration": configuration,
        "protocol_manifest": protocol_manifest,
        "protocol_sha256": protocol_sha256,
        "equivariance_audit": equivariance,
        "repetitions": rows,
        "independent_coverage_probe": independent_probe,
        "summary": summary,
        "sharpness": {
            "median_c6_to_raw_volume_ratio": _median(c6_raw_ratios),
            "median_c6_to_sectorwise_volume_ratio": _median(c6_sector_ratios),
            "ratio_threshold": SHARPNESS_RATIO_THRESHOLD,
            "c6_at_least_10pct_smaller_repetitions": c6_raw_wins,
            "non_tied_repetitions": len(sharpness_non_ties),
            "paired_sign_test_p_value": sharpness_sign_p,
        },
        "candidate_criteria": criteria,
        "host_generator_evidence_pass": generator_evidence_pass,
        "defensible_scientific_novelty_candidate": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="C6 canonical split-conformal reachability laboratory.")
    parser.add_argument("--repetitions", type=int, default=24)
    parser.add_argument("--train", type=int, default=200)
    parser.add_argument("--calibration", type=int, default=400)
    parser.add_argument("--test", type=int, default=800)
    parser.add_argument("--ood", type=int, default=300)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--burn-in", type=int, default=20)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument(
        "--coverage-probes",
        type=int,
        default=400,
        help="Independent calibration/test pairs used for the exact coverage test.",
    )
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
        coverage_probe_repetitions=args.coverage_probes,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.out),
        "host_generator_evidence_pass": payload["host_generator_evidence_pass"],
        "scientific_novelty_candidate_auto_claimed": payload["defensible_scientific_novelty_candidate"],
        "sharpness": payload["sharpness"],
        "summary": payload["summary"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

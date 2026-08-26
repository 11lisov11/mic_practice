from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
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
    ResidualSample,
    ResidualTrajectory,
    evaluate_tube,
    fit_conformal_tube,
)
from control.cyclic_robust_viability_pwm import cyclic_sector
from estimation.current_voltage_flux_observer import (
    CurrentVoltageFluxObserver,
    CurrentVoltageFluxObserverConfig,
)
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    AlphaBetaMotorState,
    randomized_motor_params,
)
from models.two_level_inverter import TwoLevelInverterParams, alpha_beta_voltage
from tools.run_safe_neural_horizon_pwm_study import _make_base_params


PARAMETER_SPANS = {
    "rs_span": 0.40,
    "rr_span": 0.40,
    "lm_span": 0.15,
    "j_span": 0.50,
    "b_span": 0.50,
}
SHAPE_QUANTILE = 0.80
PROTOCOL_SOURCE_FILES = (
    "control/cyclic_conformal_reachability.py",
    "control/cyclic_robust_viability_pwm.py",
    "estimation/current_voltage_flux_observer.py",
    "models/induction_motor_alpha_beta.py",
    "models/two_level_inverter.py",
    "tools/run_estimator_fed_conformal_lab.py",
    "tools/run_safe_neural_horizon_pwm_study.py",
)


@dataclass(frozen=True)
class MeasurementNoiseConfig:
    current_noise_fraction: float = 0.004
    current_offset_fraction: float = 0.002
    voltage_gain_sigma: float = 0.005
    voltage_noise_fraction: float = 0.001
    speed_noise_rad_s: float = 0.40
    speed_bias_rad_s: float = 0.20

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True)
class PairedResidualTrajectory:
    oracle: ResidualTrajectory
    estimator: ResidualTrajectory
    sector_matches: int
    sector_comparisons: int
    squared_state_error_sums: tuple[float, float, float, float, float]
    state_error_samples: int
    flux_clip_events: int


def _residual(
    actual: AlphaBetaMotorState,
    predicted: AlphaBetaMotorState,
) -> tuple[float, float, float, float, float]:
    return (
        actual.psi_s_alpha - predicted.psi_s_alpha,
        actual.psi_s_beta - predicted.psi_s_beta,
        actual.psi_r_alpha - predicted.psi_r_alpha,
        actual.psi_r_beta - predicted.psi_r_beta,
        actual.omega_m - predicted.omega_m,
    )


def _state_error(
    actual: AlphaBetaMotorState,
    estimated: AlphaBetaMotorState,
) -> tuple[float, float, float, float, float]:
    return _residual(actual, estimated)


def _active_vector_sector(vector_id: int, inverter: TwoLevelInverterParams) -> int:
    if int(vector_id) in (0, 7):
        return 0
    v_alpha, v_beta = alpha_beta_voltage(int(vector_id), replace(inverter, Vdc=1.0))
    return cyclic_sector(math.atan2(v_beta, v_alpha))


def _flux_sector(state: AlphaBetaMotorState, vector_id: int, inverter: TwoLevelInverterParams) -> int:
    if math.hypot(state.psi_s_alpha, state.psi_s_beta) < 1.0e-9:
        return _active_vector_sector(vector_id, inverter)
    return cyclic_sector(math.atan2(state.psi_s_beta, state.psi_s_alpha))


def _measure_current(
    rng: Random,
    true_alpha: float,
    true_beta: float,
    *,
    offset_alpha: float,
    offset_beta: float,
    noise_sigma: float,
) -> tuple[float, float]:
    return (
        float(true_alpha) + offset_alpha + rng.gauss(0.0, noise_sigma),
        float(true_beta) + offset_beta + rng.gauss(0.0, noise_sigma),
    )


def generate_paired_trajectory(
    *,
    trajectory_id: int,
    seed: int,
    base_motor: AlphaBetaMotorParams,
    base_inverter: TwoLevelInverterParams,
    scored_steps: int,
    burn_in_steps: int,
    measurement_noise: MeasurementNoiseConfig | None = None,
    span_scale: float = 1.0,
) -> PairedResidualTrajectory:
    scored_steps = int(scored_steps)
    burn_in_steps = int(burn_in_steps)
    if scored_steps <= 0 or burn_in_steps < 0:
        raise ValueError("scored_steps must be positive and burn_in_steps non-negative")
    noise = measurement_noise if measurement_noise is not None else MeasurementNoiseConfig()
    rng = Random(int(seed))
    spans = {name: value * float(span_scale) for name, value in PARAMETER_SPANS.items()}
    actual_params = randomized_motor_params(base_motor, rng, **spans)
    inverter = replace(base_inverter, Vdc=base_inverter.Vdc * rng.uniform(0.72, 1.08))
    temperature = rng.uniform(20.0, 105.0)
    state = AlphaBetaMotorState(temp_s_c=temperature, temp_r_c=temperature + rng.uniform(-8.0, 8.0))
    actual_model = AlphaBetaInductionMotorModel(actual_params, state)
    nominal_model = AlphaBetaInductionMotorModel(base_motor)
    observer = CurrentVoltageFluxObserver(
        base_motor,
        CurrentVoltageFluxObserverConfig(
            speed_filter_gain=0.35,
            flux_leak_per_s=0.0,
            max_stator_flux_wb=max(1.0, 4.0 * float(base_motor.Lm) * float(base_motor.i_limit)),
            max_abs_speed_rad_s=1000.0,
        ),
    )
    dt = float(inverter.t_pwm_s)
    current_sigma = float(noise.current_noise_fraction) * float(base_motor.i_limit)
    current_offset_sigma = float(noise.current_offset_fraction) * float(base_motor.i_limit)
    offset_alpha = rng.gauss(0.0, current_offset_sigma)
    offset_beta = rng.gauss(0.0, current_offset_sigma)
    voltage_gain = 1.0 + rng.gauss(0.0, float(noise.voltage_gain_sigma))
    voltage_bias_alpha = rng.gauss(0.0, float(noise.voltage_noise_fraction) * float(inverter.Vdc))
    voltage_bias_beta = rng.gauss(0.0, float(noise.voltage_noise_fraction) * float(inverter.Vdc))
    speed_bias = rng.gauss(0.0, float(noise.speed_bias_rad_s))
    observer.reset(omega_m=state.omega_m + speed_bias)

    initial_currents = actual_model.currents(state, actual_params)
    measured_before = _measure_current(
        rng,
        initial_currents.i_s_alpha,
        initial_currents.i_s_beta,
        offset_alpha=offset_alpha,
        offset_beta=offset_beta,
        noise_sigma=current_sigma,
    )
    vector_id = rng.randrange(1, 7)
    load_bias = rng.uniform(-1.2, 1.2)
    oracle_samples: list[ResidualSample] = []
    estimator_samples: list[ResidualSample] = []
    sector_matches = 0
    sector_comparisons = 0
    squared_errors = [0.0] * 5
    state_error_samples = 0
    flux_clip_events = 0
    total_steps = burn_in_steps + scored_steps

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
        actual_voltage = alpha_beta_voltage(
            vector_id,
            inverter,
            i_alpha_beta=(actual_currents.i_s_alpha, actual_currents.i_s_beta),
        )
        measured_voltage = (
            voltage_gain * actual_voltage[0]
            + voltage_bias_alpha
            + rng.gauss(0.0, float(noise.voltage_noise_fraction) * float(inverter.Vdc)),
            voltage_gain * actual_voltage[1]
            + voltage_bias_beta
            + rng.gauss(0.0, float(noise.voltage_noise_fraction) * float(inverter.Vdc)),
        )
        estimated_state = observer.state
        actual_step = actual_model.next_state(
            *actual_voltage,
            load_torque,
            dt,
            state=state,
            params=actual_params,
        )
        oracle_prediction = nominal_model.next_state(
            *actual_voltage,
            load_torque,
            dt,
            state=state,
            params=base_motor,
        )
        estimator_prediction = nominal_model.next_state(
            *measured_voltage,
            0.0,
            dt,
            state=estimated_state,
            params=base_motor,
        )
        measured_after = _measure_current(
            rng,
            actual_step.currents.i_s_alpha,
            actual_step.currents.i_s_beta,
            offset_alpha=offset_alpha,
            offset_beta=offset_beta,
            noise_sigma=current_sigma,
        )
        measured_speed = (
            actual_step.state.omega_m
            + speed_bias
            + rng.gauss(0.0, float(noise.speed_noise_rad_s))
        )
        observer_update = observer.step(
            v_alpha=measured_voltage[0],
            v_beta=measured_voltage[1],
            i_s_alpha_before=measured_before[0],
            i_s_beta_before=measured_before[1],
            i_s_alpha_after=measured_after[0],
            i_s_beta_after=measured_after[1],
            omega_m_measured=measured_speed,
            dt_s=dt,
        )
        flux_clip_events += int(observer_update.stator_flux_clipped)

        if step_index >= burn_in_steps:
            oracle_sector = _flux_sector(state, vector_id, inverter)
            estimator_sector = _flux_sector(estimated_state, vector_id, inverter)
            oracle_samples.append(
                ResidualSample(
                    sector=oracle_sector,
                    values=_residual(actual_step.state, oracle_prediction.state),
                )
            )
            estimator_samples.append(
                ResidualSample(
                    sector=estimator_sector,
                    values=_residual(actual_step.state, estimator_prediction.state),
                )
            )
            if math.hypot(state.psi_s_alpha, state.psi_s_beta) >= 1.0e-6:
                sector_comparisons += 1
                sector_matches += int(oracle_sector == estimator_sector)
            for index, error in enumerate(_state_error(state, estimated_state)):
                squared_errors[index] += float(error) ** 2
            state_error_samples += 1

        state = actual_step.state
        actual_model.state = state
        measured_before = measured_after

    return PairedResidualTrajectory(
        oracle=ResidualTrajectory(trajectory_id=int(trajectory_id), samples=tuple(oracle_samples)),
        estimator=ResidualTrajectory(trajectory_id=int(trajectory_id), samples=tuple(estimator_samples)),
        sector_matches=sector_matches,
        sector_comparisons=sector_comparisons,
        squared_state_error_sums=tuple(squared_errors),  # type: ignore[arg-type]
        state_error_samples=state_error_samples,
        flux_clip_events=flux_clip_events,
    )


def generate_paired_dataset(
    *,
    count: int,
    seed: int,
    scored_steps: int,
    burn_in_steps: int,
    measurement_noise: MeasurementNoiseConfig | None = None,
    span_scale: float = 1.0,
) -> list[PairedResidualTrajectory]:
    count = int(count)
    if count <= 0:
        raise ValueError("count must be positive")
    base_motor, base_inverter = _make_base_params()
    root_rng = Random(int(seed))
    return [
        generate_paired_trajectory(
            trajectory_id=index,
            seed=root_rng.randrange(0, 2**63),
            base_motor=base_motor,
            base_inverter=base_inverter,
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
            measurement_noise=measurement_noise,
            span_scale=span_scale,
        )
        for index in range(count)
    ]


def _diagnostics(rows: Sequence[PairedResidualTrajectory]) -> dict[str, Any]:
    sector_matches = sum(row.sector_matches for row in rows)
    sector_comparisons = sum(row.sector_comparisons for row in rows)
    state_samples = sum(row.state_error_samples for row in rows)
    squared = [sum(row.squared_state_error_sums[index] for row in rows) for index in range(5)]
    return {
        "sector_matches": sector_matches,
        "sector_comparisons": sector_comparisons,
        "sector_accuracy": sector_matches / sector_comparisons if sector_comparisons else float("nan"),
        "state_rmse": {
            name: math.sqrt(value / state_samples) if state_samples else float("nan")
            for name, value in zip(
                ("psi_s_alpha", "psi_s_beta", "psi_r_alpha", "psi_r_beta", "omega_m"),
                squared,
            )
        },
        "flux_clip_events": sum(row.flux_clip_events for row in rows),
    }


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(float(value) for value in values))


def build_protocol_manifest(configuration: dict[str, Any]) -> tuple[dict[str, Any], str]:
    base_motor, base_inverter = _make_base_params()
    manifest = {
        "schema": "c6_estimator_fed_protocol/v1",
        "method": "current_voltage_encoder_estimator_fed_c6_bcr",
        "configuration": {key: value for key, value in configuration.items() if key != "seed"},
        "base_motor": asdict(base_motor),
        "base_inverter": asdict(base_inverter),
        "source_files_sha256": {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in PROTOCOL_SOURCE_FILES
        },
        "estimator_inputs": [
            "measured_stator_current_alpha_beta",
            "reconstructed_applied_voltage_alpha_beta",
            "processed_encoder_speed",
        ],
        "true_flux_input_to_estimator": False,
        "true_state_use": "simulation_target_and_diagnostics_only",
        "preregistration_claim": False,
    }
    canonical = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return manifest, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_lab(
    *,
    repetitions: int = 8,
    training_trajectories: int = 120,
    calibration_trajectories: int = 200,
    test_trajectories: int = 400,
    ood_trajectories: int = 100,
    scored_steps: int = 40,
    burn_in_steps: int = 20,
    alpha: float = 0.05,
    seed: int = 20260828,
    measurement_noise: MeasurementNoiseConfig | None = None,
) -> dict[str, Any]:
    counts = {
        "repetitions": int(repetitions),
        "training_trajectories": int(training_trajectories),
        "calibration_trajectories": int(calibration_trajectories),
        "test_trajectories": int(test_trajectories),
        "ood_trajectories": int(ood_trajectories),
        "scored_steps": int(scored_steps),
    }
    if any(value <= 0 for value in counts.values()) or int(burn_in_steps) < 0:
        raise ValueError("trajectory counts and scored_steps must be positive; burn_in_steps must be non-negative")
    if not math.isfinite(float(alpha)) or not 0.0 < float(alpha) < 1.0:
        raise ValueError("alpha must be finite and in (0, 1)")
    noise = measurement_noise if measurement_noise is not None else MeasurementNoiseConfig()
    root_rng = Random(int(seed))
    used_seeds: set[int] = set()
    rows: list[dict[str, Any]] = []

    def draw_seed() -> int:
        while True:
            candidate = root_rng.randrange(0, 2**63)
            if candidate not in used_seeds:
                used_seeds.add(candidate)
                return candidate

    for repetition in range(int(repetitions)):
        split_seeds = [draw_seed() for _ in range(4)]
        training = generate_paired_dataset(
            count=training_trajectories,
            seed=split_seeds[0],
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
            measurement_noise=noise,
        )
        calibration = generate_paired_dataset(
            count=calibration_trajectories,
            seed=split_seeds[1],
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
            measurement_noise=noise,
        )
        test = generate_paired_dataset(
            count=test_trajectories,
            seed=split_seeds[2],
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
            measurement_noise=noise,
        )
        ood = generate_paired_dataset(
            count=ood_trajectories,
            seed=split_seeds[3],
            scored_steps=scored_steps,
            burn_in_steps=burn_in_steps,
            measurement_noise=noise,
            span_scale=1.75,
        )
        oracle_tube = fit_conformal_tube(
            [item.oracle for item in training],
            [item.oracle for item in calibration],
            method="c6_canonical",
            alpha=alpha,
            shape_quantile=SHAPE_QUANTILE,
        )
        estimator_tube = fit_conformal_tube(
            [item.estimator for item in training],
            [item.estimator for item in calibration],
            method="c6_canonical",
            alpha=alpha,
            shape_quantile=SHAPE_QUANTILE,
        )
        estimator_raw_tube = fit_conformal_tube(
            [item.estimator for item in training],
            [item.estimator for item in calibration],
            method="raw_global",
            alpha=alpha,
            shape_quantile=SHAPE_QUANTILE,
        )
        oracle_test = evaluate_tube(oracle_tube, [item.oracle for item in test])
        estimator_test = evaluate_tube(estimator_tube, [item.estimator for item in test])
        estimator_ood = evaluate_tube(estimator_tube, [item.estimator for item in ood])
        estimator_raw_test = evaluate_tube(estimator_raw_tube, [item.estimator for item in test])
        estimator_to_oracle = 10.0 ** (estimator_tube.log10_volume() - oracle_tube.log10_volume())
        estimator_c6_to_raw = 10.0 ** (estimator_tube.log10_volume() - estimator_raw_tube.log10_volume())
        rows.append(
            {
                "repetition": repetition,
                "split_seeds": split_seeds,
                "oracle_c6": {"tube": asdict(oracle_tube), "held_out": oracle_test},
                "estimator_c6": {
                    "tube": asdict(estimator_tube),
                    "held_out": estimator_test,
                    "ood_span_1p75": estimator_ood,
                },
                "estimator_raw": {"tube": asdict(estimator_raw_tube), "held_out": estimator_raw_test},
                "estimator_to_oracle_volume_ratio": estimator_to_oracle,
                "estimator_c6_to_raw_volume_ratio": estimator_c6_to_raw,
                "test_estimator_diagnostics": _diagnostics(test),
            }
        )

    estimator_coverages = [float(row["estimator_c6"]["held_out"]["empirical_coverage"]) for row in rows]
    oracle_coverages = [float(row["oracle_c6"]["held_out"]["empirical_coverage"]) for row in rows]
    estimator_ood_coverages = [
        float(row["estimator_c6"]["ood_span_1p75"]["empirical_coverage"]) for row in rows
    ]
    estimator_oracle_ratios = [float(row["estimator_to_oracle_volume_ratio"]) for row in rows]
    estimator_raw_ratios = [float(row["estimator_c6_to_raw_volume_ratio"]) for row in rows]
    sector_accuracies = [float(row["test_estimator_diagnostics"]["sector_accuracy"]) for row in rows]
    flux_clips = sum(int(row["test_estimator_diagnostics"]["flux_clip_events"]) for row in rows)
    configuration = {
        "repetitions": int(repetitions),
        "training_trajectories": int(training_trajectories),
        "calibration_trajectories": int(calibration_trajectories),
        "test_trajectories": int(test_trajectories),
        "ood_trajectories": int(ood_trajectories),
        "scored_steps_per_trajectory": int(scored_steps),
        "burn_in_steps": int(burn_in_steps),
        "alpha": float(alpha),
        "shape_quantile": SHAPE_QUANTILE,
        "seed": int(seed),
        "parameter_spans": dict(PARAMETER_SPANS),
        "ood_span_multiplier": 1.75,
        "measurement_noise": asdict(noise),
    }
    protocol_manifest, protocol_sha256 = build_protocol_manifest(configuration)
    criteria = {
        "at_least_8_repetitions": int(repetitions) >= 8,
        "at_least_100_training_trajectories": int(training_trajectories) >= 100,
        "at_least_200_calibration_trajectories": int(calibration_trajectories) >= 200,
        "at_least_400_test_trajectories": int(test_trajectories) >= 400,
        "at_least_40_scored_steps": int(scored_steps) >= 40,
        "split_seeds_are_unique": len(used_seeds) == 4 * int(repetitions),
        "estimator_uses_no_true_flux_input": protocol_manifest["true_flux_input_to_estimator"] is False,
        "all_reported_metrics_are_finite": all(
            math.isfinite(value)
            for value in estimator_coverages
            + oracle_coverages
            + estimator_ood_coverages
            + estimator_oracle_ratios
            + estimator_raw_ratios
            + sector_accuracies
        ),
        "no_stator_flux_clip_events_in_test": flux_clips == 0,
    }
    return {
        "status": "estimator_fed_c6_bcr_exploratory_lab",
        "host_exploratory_evidence_complete": all(criteria.values()),
        "host_method_evidence_pass": False,
        "coverage_inference_claim": False,
        "scientific_novelty_claim": False,
        "world_novelty_established": False,
        "hardware_ready": False,
        "estimator_based": True,
        "criteria": criteria,
        "configuration": configuration,
        "protocol_manifest": protocol_manifest,
        "protocol_sha256": protocol_sha256,
        "summary": {
            "median_oracle_c6_held_out_coverage_descriptive": _median(oracle_coverages),
            "median_estimator_c6_held_out_coverage_descriptive": _median(estimator_coverages),
            "median_estimator_c6_ood_coverage_descriptive": _median(estimator_ood_coverages),
            "median_estimator_to_oracle_volume_ratio": _median(estimator_oracle_ratios),
            "median_estimator_c6_to_raw_volume_ratio": _median(estimator_raw_ratios),
            "median_estimated_sector_accuracy": _median(sector_accuracies),
            "test_flux_clip_events": flux_clips,
        },
        "repetitions": rows,
        "claim_boundary": (
            "exploratory paired host simulation with current/voltage/processed-encoder inputs; true state is used "
            "only as a simulation target and diagnostic; bulk coverage is descriptive and this result does not "
            "establish independent-probe coverage, estimator validity on hardware, recursive safety, or novelty"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimator-fed C6-BCR exploratory paired laboratory.")
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--train", type=int, default=120)
    parser.add_argument("--calibration", type=int, default=200)
    parser.add_argument("--test", type=int, default=400)
    parser.add_argument("--ood", type=int, default=100)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--burn-in", type=int, default=20)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260828)
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
        "host_exploratory_evidence_complete": payload["host_exploratory_evidence_complete"],
        "host_method_evidence_pass": payload["host_method_evidence_pass"],
        "summary": payload["summary"],
    }, ensure_ascii=False, indent=2))
    return 0 if payload["host_exploratory_evidence_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


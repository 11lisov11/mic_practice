from __future__ import annotations

import argparse
from collections import deque
import hashlib
import inspect
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from estimation.sensorless_flux_slip_observer import (
    SensorlessFluxSlipConfig,
    SensorlessFluxSlipObserver,
)
from models.induction_motor_current_flux_rk4 import (
    CurrentFluxInductionMotorRk4,
    CurrentFluxMotorParams,
)


DEFAULT_INPUT = REPOSITORY_ROOT / "artifacts" / "air56b2_fidelity_bundle.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts" / "air56b2_sensorless_independent_plant_study.json"
TRAIN_SAMPLE_INDICES = (0, 37, 91, 143)
VALIDATION_SAMPLE_INDICES = (11, 53, 107, 199, 253)
TARGET_FREQUENCIES_HZ = (15.0, 30.0, 45.0)
LOW_SPEED_DIAGNOSTIC_HZ = 5.0
DT_S = 1.0e-4
DURATION_S = 1.2
EVALUATION_START_S = 0.70


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plant_params(f2: dict[str, Any], current_limit_a: float) -> CurrentFluxMotorParams:
    motor = f2["transformed_motor"]
    return CurrentFluxMotorParams(
        rs_ohm=float(motor["Rs"]),
        rr_ohm=float(motor["Rr"]),
        ls_h=float(motor["Lm"]) + float(motor["Ls_sigma"]),
        lr_h=float(motor["Lm"]) + float(motor["Lr_sigma"]),
        lm_h=float(motor["Lm"]),
        inertia_kgm2=float(motor["J"]),
        viscous_b_nms=float(motor["B"]),
        pole_pairs=int(motor["p"]),
        coulomb_friction_nm=float(f2["effective_coulomb_friction_torque_nm"]),
        current_limit_a=float(current_limit_a),
    )


def _quantize_signed(value: float, lsb: float, full_scale: float) -> float:
    clipped = max(-full_scale, min(full_scale, float(value)))
    return round(clipped / lsb) * lsb


def _make_trace(
    bundle: dict[str, Any],
    *,
    sample_index: int,
    target_frequency_hz: float,
    load_fraction: float = 0.35,
) -> list[tuple[float, float, float, float, float, bool]]:
    fidelity = bundle["fidelity"]
    f2 = fidelity["f2_samples"][sample_index]
    f3 = fidelity["f3_samples"][sample_index]
    nameplate = fidelity["nameplate"]
    derived = fidelity["derived_nameplate"]
    current_full_scale = float(f3["adc"]["current_full_scale_a"])
    current_lsb = float(f3["adc"]["current_lsb_a"])
    plant = CurrentFluxInductionMotorRk4(
        _plant_params(f2, current_limit_a=max(20.0, current_full_scale * 1.25))
    )
    delay_steps = max(0, int(round(float(f3["adc"]["sample_delay_s"]) / DT_S)))
    delay_a: deque[float] = deque([0.0] * (delay_steps + 1), maxlen=delay_steps + 1)
    delay_b: deque[float] = deque([0.0] * (delay_steps + 1), maxlen=delay_steps + 1)
    theta_e = 0.0
    phase_voltage_rms_rated = float(derived["model_phase_voltage_v"])
    rated_torque = float(derived["rated_torque_nm"])
    ramp_s = 0.35
    load_start_s = 0.55
    trace: list[tuple[float, float, float, float, float, bool]] = []
    steps = int(round(DURATION_S / DT_S))
    previous_i_a = 0.0
    previous_i_b = 0.0
    inverter = f3["inverter"]
    for step in range(steps):
        time_s = step * DT_S
        ramp = min(1.0, time_s / ramp_s)
        frequency_hz = float(target_frequency_hz) * ramp
        theta_e += 2.0 * math.pi * frequency_hz * DT_S
        voltage_peak = math.sqrt(2.0) * phase_voltage_rms_rated * frequency_hz / 50.0
        voltage_peak = min(voltage_peak, 0.95 * float(inverter["nominal_vdc_v"]) / math.sqrt(3.0))
        command_a = voltage_peak * math.cos(theta_e)
        command_b = voltage_peak * math.sin(theta_e)
        current_abs = math.hypot(previous_i_a, previous_i_b)
        if current_abs > 1e-12:
            drop = float(inverter["switch_voltage_drop_v"]) + float(inverter["switch_r_on_ohm"]) * current_abs
            v_alpha = command_a - drop * previous_i_a / current_abs
            v_beta = command_b - drop * previous_i_b / current_abs
        else:
            v_alpha, v_beta = command_a, command_b
        load = rated_torque * load_fraction if time_s >= load_start_s else 0.0
        output = plant.step(v_alpha, v_beta, load, DT_S)
        previous_i_a = output.state.i_s_alpha_a
        previous_i_b = output.state.i_s_beta_a
        delay_a.append(previous_i_a)
        delay_b.append(previous_i_b)
        measured_a = _quantize_signed(delay_a[0], current_lsb, current_full_scale)
        measured_b = _quantize_signed(delay_b[0], current_lsb, current_full_scale)
        trace.append(
            (
                v_alpha,
                v_beta,
                measured_a,
                measured_b,
                output.state.omega_m_rad_s,
                time_s >= EVALUATION_START_S,
            )
        )
    return trace


def _observer_nominal(bundle: dict[str, Any]) -> dict[str, float | int]:
    f2 = bundle["fidelity"]["f2_samples"][128]
    motor = f2["transformed_motor"]
    return {
        "rs_ohm": float(motor["Rs"]),
        "rr_ohm": float(motor["Rr"]),
        "ls_h": float(motor["Lm"]) + float(motor["Ls_sigma"]),
        "lr_h": float(motor["Lm"]) + float(motor["Lr_sigma"]),
        "lm_h": float(motor["Lm"]),
        "pole_pairs": int(motor["p"]),
    }


def _evaluate_trace(
    trace: list[tuple[float, float, float, float, float, bool]],
    config: SensorlessFluxSlipConfig,
) -> dict[str, float]:
    observer = SensorlessFluxSlipObserver(config)
    errors: list[float] = []
    relative_errors: list[float] = []
    valid_count = 0
    evaluation_count = 0
    final_error = 0.0
    for v_a, v_b, i_a, i_b, true_speed, evaluate in trace:
        estimate = observer.step(
            v_alpha_v=v_a,
            v_beta_v=v_b,
            i_s_alpha_a=i_a,
            i_s_beta_a=i_b,
            dt_s=DT_S,
        ).state
        if evaluate:
            evaluation_count += 1
            if estimate.valid:
                valid_count += 1
                final_error = abs(estimate.omega_m_rad_s - true_speed)
                errors.append(final_error)
                relative_errors.append(final_error / max(abs(true_speed), 1.0))
    return {
        "mean_abs_speed_error_rad_s": statistics.fmean(errors) if errors else float("inf"),
        "median_abs_speed_error_rad_s": statistics.median(errors) if errors else float("inf"),
        "final_abs_speed_error_rad_s": final_error if errors else float("inf"),
        "mean_relative_speed_error_pct": 100.0 * statistics.fmean(relative_errors)
        if relative_errors
        else float("inf"),
        "valid_fraction": valid_count / max(evaluation_count, 1),
    }


def _candidate_configs(bundle: dict[str, Any]) -> list[SensorlessFluxSlipConfig]:
    nominal = _observer_nominal(bundle)
    return [
        SensorlessFluxSlipConfig(
            **nominal,
            flux_leak_per_s=leak,
            speed_filter_tau_s=tau,
            slip_gain=slip_gain,
        )
        for leak in (0.5, 1.5, 3.0, 5.0)
        for tau in (0.01, 0.03, 0.06)
        for slip_gain in (0.7, 1.0, 1.3)
    ]


def _score(metrics: list[dict[str, float]]) -> float:
    return statistics.fmean(row["mean_abs_speed_error_rad_s"] for row in metrics) + 20.0 * statistics.fmean(
        1.0 - row["valid_fraction"] for row in metrics
    )


def run_study(input_path: Path, output_path: Path) -> dict[str, Any]:
    bundle = json.loads(input_path.read_text(encoding="utf-8"))
    if bundle.get("status") != "PASS" or bool(bundle.get("hardware_claim", True)):
        raise ValueError("AIR56B2 fidelity input must be a simulation-only PASS bundle")
    if set(TRAIN_SAMPLE_INDICES) & set(VALIDATION_SAMPLE_INDICES):
        raise AssertionError("sensorless train and validation samples must be disjoint")

    train_traces = {
        (index, frequency): _make_trace(bundle, sample_index=index, target_frequency_hz=frequency)
        for index in TRAIN_SAMPLE_INDICES
        for frequency in TARGET_FREQUENCIES_HZ
    }
    candidates = _candidate_configs(bundle)
    leaderboard: list[dict[str, Any]] = []
    for candidate_index, config in enumerate(candidates):
        metrics = [_evaluate_trace(trace, config) for trace in train_traces.values()]
        leaderboard.append(
            {
                "candidate_index": candidate_index,
                "config": config.__dict__,
                "score": _score(metrics),
                "mean_abs_speed_error_rad_s": statistics.fmean(
                    row["mean_abs_speed_error_rad_s"] for row in metrics
                ),
                "worst_mean_abs_speed_error_rad_s": max(
                    row["mean_abs_speed_error_rad_s"] for row in metrics
                ),
                "mean_valid_fraction": statistics.fmean(row["valid_fraction"] for row in metrics),
            }
        )
    leaderboard.sort(key=lambda row: (row["score"], row["candidate_index"]))
    selected_row = leaderboard[0]
    selected_config = SensorlessFluxSlipConfig(**selected_row["config"])

    validation_rows: list[dict[str, Any]] = []
    for index in VALIDATION_SAMPLE_INDICES:
        for frequency in TARGET_FREQUENCIES_HZ:
            trace = _make_trace(bundle, sample_index=index, target_frequency_hz=frequency)
            metrics = _evaluate_trace(trace, selected_config)
            validation_rows.append({"sample_index": index, "frequency_hz": frequency, **metrics})
    low_speed_rows: list[dict[str, Any]] = []
    for index in VALIDATION_SAMPLE_INDICES:
        trace = _make_trace(bundle, sample_index=index, target_frequency_hz=LOW_SPEED_DIAGNOSTIC_HZ)
        low_speed_rows.append(
            {
                "sample_index": index,
                "frequency_hz": LOW_SPEED_DIAGNOSTIC_HZ,
                **_evaluate_trace(trace, selected_config),
            }
        )

    validation_mean = statistics.fmean(row["mean_abs_speed_error_rad_s"] for row in validation_rows)
    validation_worst = max(row["mean_abs_speed_error_rad_s"] for row in validation_rows)
    validation_valid = statistics.fmean(row["valid_fraction"] for row in validation_rows)
    validation_relative = statistics.fmean(
        row["mean_relative_speed_error_pct"] for row in validation_rows
    )
    low_speed_mean = statistics.fmean(row["mean_abs_speed_error_rad_s"] for row in low_speed_rows)
    low_speed_relative = statistics.fmean(
        row["mean_relative_speed_error_pct"] for row in low_speed_rows
    )
    observer_parameters = set(inspect.signature(SensorlessFluxSlipObserver.step).parameters)
    forbidden = {"omega", "speed", "angle", "theta", "true_flux", "rotor_flux"}
    gates = {
        "input_bundle_passed": True,
        "train_validation_disjoint": True,
        "observer_has_no_speed_angle_or_true_flux_input": not any(
            any(token in parameter.lower() for token in forbidden)
            for parameter in observer_parameters
            if parameter != "self"
        ),
        "independent_plant_state_space": True,
        "validation_valid_fraction_at_least_95pct": validation_valid >= 0.95,
        "validation_mean_speed_error_below_35_rad_s": validation_mean < 35.0,
        "validation_worst_speed_error_below_70_rad_s": validation_worst < 70.0,
        "low_speed_limitation_explicit": True,
        "no_hardware_claim": True,
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    payload = {
        "schema": "air56b2-sensorless-independent-plant-study-v1",
        "status": status,
        "hardware_claim": False,
        "hardware_identified": False,
        "hardware_release_ready": False,
        "input": {"path": str(input_path.resolve()), "sha256": _sha256(input_path)},
        "observer_input_contract": "applied_alpha_beta_voltage_and_delayed_quantized_stator_current_only",
        "plant_contract": "independent_i_s_psi_r_state_space_with_rk4",
        "controller_plant_shared_state": False,
        "train_sample_indices": list(TRAIN_SAMPLE_INDICES),
        "validation_sample_indices": list(VALIDATION_SAMPLE_INDICES),
        "target_frequencies_hz": list(TARGET_FREQUENCIES_HZ),
        "candidate_count": len(candidates),
        "selected": selected_row,
        "validation_summary": {
            "mean_abs_speed_error_rad_s": validation_mean,
            "worst_mean_abs_speed_error_rad_s": validation_worst,
            "mean_valid_fraction": validation_valid,
            "mean_relative_speed_error_pct": validation_relative,
        },
        "low_speed_diagnostic": {
            "frequency_hz": LOW_SPEED_DIAGNOSTIC_HZ,
            "mean_abs_speed_error_rad_s": low_speed_mean,
            "mean_relative_speed_error_pct": low_speed_relative,
            "rows": low_speed_rows,
            "release_use": "unsupported_until_hardware_observer_validation",
        },
        "gates": gates,
        "leaderboard": leaderboard,
        "validation_rows": validation_rows,
        "limitations": [
            "This is simulation validation on a structurally independent model, not validation on the AIR56B2 hardware.",
            "The voltage-model observer loses observability and becomes drift-sensitive near zero electrical frequency.",
            "The 5 Hz result is diagnostic only and is excluded from the moderate-speed acceptance gate.",
            "Observer Rs/Rr/Lm must be updated from standstill and run-up identification before sensorless commissioning.",
            "First hardware starts must use scalar V/f or encoder feedback; sensorless takeover requires a supervised transition gate.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AIR56B2 sensorless observer on an independent RK4 plant")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = run_study(args.input.resolve(), args.output.resolve())
    print(json.dumps({"status": payload["status"], **payload["validation_summary"], "low_speed_mean_error_rad_s": payload["low_speed_diagnostic"]["mean_abs_speed_error_rad_s"]}, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

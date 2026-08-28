from __future__ import annotations

import argparse
from collections import deque
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.foc_svm_key_baseline import (
    FocSvmKeyBaselineConfig,
    FocSvmKeyBaselineController,
)
from control.safe_neural_horizon_pwm import effective_vector_schedule
from estimation.current_voltage_flux_observer import CurrentVoltageFluxObserver
from models.air56b2_fidelity import generate_f2_samples, generate_f3_samples
from models.air56b2_nameplate_ensemble import (
    Air56B2Nameplate,
    derive_nameplate,
    generate_air56b2_ensemble,
)
from models.air56b2_starting_regime import starting_torque_scale_for_speed
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    step_inverter_schedule,
)
from models.two_level_inverter import (
    TwoLevelInverterParams,
    alpha_beta_voltage,
)
from safety.ai_pwm_gateway import AIPwmSafetyGateway, GatewayLimits
from tools.build_air56b2_fidelity_bundle import derived_seed, reference_digest


def _finite(values: Sequence[float]) -> bool:
    return all(math.isfinite(float(value)) for value in values)


def _circular_delta(current: float, previous: float) -> float:
    return (float(current) - float(previous) + math.pi) % (2.0 * math.pi) - math.pi


def _delay_buffer(delay_s: float, dt_s: float, initial: float) -> deque[float]:
    delay_steps = max(0, int(round(float(delay_s) / float(dt_s))))
    return deque([float(initial)] * (delay_steps + 1), maxlen=delay_steps + 1)


def _delayed(buffer: deque[float], value: float) -> float:
    buffer.append(float(value))
    return float(buffer[0])


def _average_applied_voltage(
    schedule,
    inverter: TwoLevelInverterParams,
    *,
    current_alpha_a: float,
    current_beta_a: float,
    pwm_enabled: bool,
) -> tuple[float, float]:
    if not pwm_enabled:
        return 0.0, 0.0
    total = sum(float(segment.dwell_s) for segment in schedule)
    if total <= 0.0:
        raise ValueError("applied schedule must have positive duration")
    alpha = 0.0
    beta = 0.0
    for segment in schedule:
        v_alpha, v_beta = alpha_beta_voltage(
            segment.vector_id,
            inverter,
            i_alpha_beta=(current_alpha_a, current_beta_a),
        )
        weight = float(segment.dwell_s) / total
        alpha += weight * v_alpha
        beta += weight * v_beta
    return alpha, beta


def _trial(
    f1,
    f2,
    f3,
    *,
    config: FocSvmKeyBaselineConfig,
    steps: int,
    target_speed_fraction: float,
    speed_ramp_s: float,
    load_fraction: float,
) -> dict[str, Any]:
    nameplate = Air56B2Nameplate()
    derived = derive_nameplate(nameplate)
    controller_motor = AlphaBetaMotorParams.from_motor_params(f1.motor)
    plant_motor = AlphaBetaMotorParams.from_motor_params(f2.transformed_motor)
    initial_vdc = f3.inverter.vdc_at(0.0)
    inverter = TwoLevelInverterParams(
        Vdc=initial_vdc,
        f_pwm=f3.inverter.pwm_frequency_hz,
        dead_time_s=f3.inverter.dead_time_s,
        min_pulse_s=max(2.0e-6, f3.inverter.dead_time_s),
        r_on_ohm=f3.inverter.switch_r_on_ohm,
        v_drop_v=f3.inverter.switch_voltage_drop_v,
    )
    dt_s = inverter.t_pwm_s
    if not math.isclose(config.dt_s, dt_s, rel_tol=0.0, abs_tol=1.0e-15):
        raise ValueError("FOC tuning PWM period does not match F3")
    start_current_peak_a = (
        math.sqrt(2.0) * nameplate.line_current_a * nameplate.start_current_ratio
    )
    current_envelope_a = 1.05 * start_current_peak_a
    gateway = AIPwmSafetyGateway(
        GatewayLimits(
            t_pwm_s=dt_s,
            dead_time_s=inverter.dead_time_s,
            min_pulse_s=inverter.min_pulse_s,
            i_soft_a=current_envelope_a,
            i_trip_a=1.15 * current_envelope_a,
            vdc_min_v=0.70 * f3.inverter.nominal_vdc_v,
            vdc_max_v=1.30 * f3.inverter.nominal_vdc_v,
            confidence_min=0.35,
            risk_max=1.4,
            max_switch_events_per_window=1000,
            switch_window_steps=8,
        )
    )
    controller = FocSvmKeyBaselineController(
        controller_motor,
        inverter,
        gateway,
        config,
    )
    observer = CurrentVoltageFluxObserver(controller_motor)
    observer.reset()
    plant = AlphaBetaInductionMotorModel(plant_motor)

    alpha_delay = _delay_buffer(f3.adc.sample_delay_s, dt_s, 0.0)
    beta_delay = _delay_buffer(f3.adc.sample_delay_s, dt_s, 0.0)
    voltage_delay = _delay_buffer(f3.adc.sample_delay_s, dt_s, initial_vdc)
    angle_delay = _delay_buffer(f3.as5600.sample_delay_s, dt_s, 0.0)
    speed_window_steps = max(20, int(round(0.002 / dt_s)))
    encoder_history = deque([0.0] * (speed_window_steps + 1), maxlen=speed_window_steps + 1)
    current_zero_calibration = f3.adc.quantize_current(0.0)
    measured_i_alpha = 0.0
    measured_i_beta = 0.0
    measured_vdc = f3.adc.quantize_voltage(initial_vdc)
    measured_speed = 0.0

    target_speed = target_speed_fraction * derived.rated_omega_rad_s
    speed_errors: list[float] = []
    peak_current = 0.0
    peak_measured_current = 0.0
    minimum_starting_scale = 1.0
    maximum_observer_speed_error = 0.0
    observer_flux_clipped_steps = 0
    gateway_rejected_steps = 0
    gateway_fault_steps = 0
    current_adc_clipped_steps = 0
    vdc_adc_clipped_steps = 0
    nonfinite_step: int | None = None
    estimated_state_feedback_steps = 0
    true_state_feedback_steps = 0

    for step_index in range(int(steps)):
        time_s = step_index * dt_s
        true_vdc = f3.inverter.vdc_at(time_s)
        ramp_fraction = min(1.0, time_s / max(speed_ramp_s, dt_s))
        omega_ref = target_speed * ramp_fraction
        load_start = 0.40 * steps
        load_ramp = max(0.10 * steps, 1.0)
        load_scale = min(1.0, max(0.0, (step_index - load_start) / load_ramp))
        commanded_load = load_fraction * derived.rated_torque_nm * load_scale
        friction = (
            math.copysign(f2.effective_coulomb_friction_torque_nm, plant.state.omega_m)
            if abs(plant.state.omega_m) > 1.0e-6
            else 0.0
        )
        true_load = commanded_load + friction

        result = controller.step(
            omega_ref=omega_ref,
            load_torque_nm=0.0,
            measured_state=observer.state,
            measured_i_abs=math.hypot(measured_i_alpha, measured_i_beta),
            vdc=measured_vdc,
        )
        estimated_state_feedback_steps += int(result.feedback_requested)
        schedule = effective_vector_schedule(result, dt_s)
        plant_inverter = replace(inverter, Vdc=true_vdc)
        electrical_frequency_hz = abs(controller.omega_e) / (2.0 * math.pi)
        torque_scale = starting_torque_scale_for_speed(
            f1,
            electrical_frequency_hz=electrical_frequency_hz,
            mechanical_speed_rad_s=plant.state.omega_m,
        )
        current_before = plant.currents()
        plant_step = step_inverter_schedule(
            plant,
            schedule,
            plant_inverter,
            true_load,
            pwm_enabled=result.decision.pwm_enabled,
            electromagnetic_torque_scale=torque_scale,
        )

        delayed_alpha = _delayed(alpha_delay, plant_step.currents.i_s_alpha)
        delayed_beta = _delayed(beta_delay, plant_step.currents.i_s_beta)
        delayed_vdc = _delayed(voltage_delay, true_vdc)
        current_alpha_before_clip = (
            delayed_alpha * f3.adc.current_gain_scale + f3.adc.current_offset_a
        )
        current_beta_before_clip = (
            delayed_beta * f3.adc.current_gain_scale + f3.adc.current_offset_a
        )
        voltage_before_clip = (
            delayed_vdc * f3.adc.voltage_gain_scale + f3.adc.voltage_offset_v
        )
        if max(abs(current_alpha_before_clip), abs(current_beta_before_clip)) >= (
            f3.adc.current_full_scale_a
        ):
            current_adc_clipped_steps += 1
        if not 0.0 <= voltage_before_clip <= f3.adc.voltage_full_scale_v:
            vdc_adc_clipped_steps += 1
        next_i_alpha = f3.adc.quantize_current(delayed_alpha) - current_zero_calibration
        next_i_beta = f3.adc.quantize_current(delayed_beta) - current_zero_calibration
        next_vdc = f3.adc.quantize_voltage(delayed_vdc)

        delayed_angle = _delayed(angle_delay, plant_step.state.theta_m)
        encoder_angle = f3.as5600.quantize_angle(delayed_angle)
        encoder_history.append(encoder_angle)
        raw_speed = _circular_delta(encoder_history[-1], encoder_history[0]) / (
            speed_window_steps * dt_s
        )
        measured_speed += 0.20 * (raw_speed - measured_speed)

        observer_inverter = replace(inverter, Vdc=measured_vdc)
        reconstructed_voltage = _average_applied_voltage(
            schedule,
            observer_inverter,
            current_alpha_a=measured_i_alpha,
            current_beta_a=measured_i_beta,
            pwm_enabled=result.decision.pwm_enabled,
        )
        observer_update = observer.step(
            v_alpha=reconstructed_voltage[0],
            v_beta=reconstructed_voltage[1],
            i_s_alpha_before=measured_i_alpha,
            i_s_beta_before=measured_i_beta,
            i_s_alpha_after=next_i_alpha,
            i_s_beta_after=next_i_beta,
            omega_m_measured=measured_speed,
            dt_s=dt_s,
        )
        measured_i_alpha = next_i_alpha
        measured_i_beta = next_i_beta
        measured_vdc = next_vdc

        speed_error = omega_ref - plant_step.state.omega_m
        speed_errors.append(speed_error)
        peak_current = max(peak_current, plant_step.currents.stator_abs)
        peak_measured_current = max(
            peak_measured_current,
            math.hypot(measured_i_alpha, measured_i_beta),
        )
        minimum_starting_scale = min(minimum_starting_scale, torque_scale)
        maximum_observer_speed_error = max(
            maximum_observer_speed_error,
            abs(observer_update.state.omega_m - plant_step.state.omega_m),
        )
        observer_flux_clipped_steps += int(observer_update.stator_flux_clipped)
        gateway_rejected_steps += int(not result.decision.accepted)
        gateway_fault_steps += int(result.decision.fault_latched)
        if not _finite(
            (
                plant_step.state.omega_m,
                plant_step.currents.stator_abs,
                plant_step.torque_nm,
                observer_update.state.omega_m,
                observer_update.state.psi_s_alpha,
                observer_update.state.psi_s_beta,
                measured_i_alpha,
                measured_i_beta,
                measured_vdc,
            )
        ):
            nonfinite_step = step_index
            break

    completed_steps = int(steps) if nonfinite_step is None else nonfinite_step + 1
    steady_count = max(1, len(speed_errors) // 5)
    steady_mean_abs_error = sum(abs(value) for value in speed_errors[-steady_count:]) / (
        steady_count
    )
    final_abs_error = abs(speed_errors[-1]) if speed_errors else float("inf")
    speed_error_limit = 0.15 * max(target_speed, 1.0e-9)
    checks = {
        "completed_all_steps_with_finite_state": nonfinite_step is None,
        "no_gateway_fault_latch": gateway_fault_steps == 0,
        "no_gateway_rejection": gateway_rejected_steps == 0,
        "current_adc_not_clipped": current_adc_clipped_steps == 0,
        "vdc_adc_not_clipped": vdc_adc_clipped_steps == 0,
        "observer_flux_not_clipped": observer_flux_clipped_steps == 0,
        "peak_current_within_nameplate_start_envelope": peak_current <= current_envelope_a,
        "steady_speed_error_within_15pct": steady_mean_abs_error <= speed_error_limit,
        "final_speed_error_within_15pct": final_abs_error <= speed_error_limit,
        "f1s_starting_correction_exercised": minimum_starting_scale < 1.0,
        "estimated_state_feedback_used": estimated_state_feedback_steps == completed_steps,
        "true_state_feedback_not_used": true_state_feedback_steps == 0,
        "encoder_speed_feedback_used": True,
    }
    return {
        "index": f1.index,
        "f1_seed": f1.seed,
        "f2_seed": f2.seed,
        "f3_seed": f3.seed,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "completed_steps": completed_steps,
        "simulated_duration_s": completed_steps * dt_s,
        "target_speed_rad_s": target_speed,
        "final_speed_rad_s": plant.state.omega_m,
        "final_speed_rpm": plant.state.omega_m * 60.0 / (2.0 * math.pi),
        "steady_mean_abs_speed_error_rad_s": steady_mean_abs_error,
        "final_abs_speed_error_rad_s": final_abs_error,
        "speed_error_limit_rad_s": speed_error_limit,
        "peak_true_current_a": peak_current,
        "peak_measured_current_a": peak_measured_current,
        "current_envelope_a": current_envelope_a,
        "minimum_f1s_torque_scale": minimum_starting_scale,
        "maximum_observer_speed_error_rad_s": maximum_observer_speed_error,
        "observer_flux_clipped_steps": observer_flux_clipped_steps,
        "gateway_rejected_steps": gateway_rejected_steps,
        "gateway_fault_steps": gateway_fault_steps,
        "current_adc_clipped_steps": current_adc_clipped_steps,
        "vdc_adc_clipped_steps": vdc_adc_clipped_steps,
        "estimated_state_feedback_steps": estimated_state_feedback_steps,
        "true_state_feedback_steps": true_state_feedback_steps,
        "current_zero_calibration_a": current_zero_calibration,
        "nonfinite_step": nonfinite_step,
    }


def run_study(
    tuning_payload: dict[str, Any],
    *,
    tuning_sha256: str,
    count: int,
    steps: int,
    master_seed: int,
    target_speed_fraction: float,
    speed_ramp_s: float,
    load_fraction: float,
) -> dict[str, Any]:
    if tuning_payload.get("schema") not in {
        "air56b2-foc-ensemble-tuning-v1",
        "air56b2-encoder-foc-tuning-v1",
    }:
        raise ValueError("unsupported tuning schema")
    selected = tuning_payload.get("selected")
    if not isinstance(selected, dict) or not isinstance(selected.get("config"), dict):
        raise ValueError("tuning payload has no selected configuration")
    if count < 1 or steps < 1:
        raise ValueError("count and steps must be positive")
    if not 0.0 < target_speed_fraction <= 1.0:
        raise ValueError("target speed fraction must be within (0, 1]")
    if speed_ramp_s <= 0.0:
        raise ValueError("speed ramp must be positive")
    if not 0.0 <= load_fraction <= 1.0:
        raise ValueError("load fraction must be within [0, 1]")

    f2_seed = derived_seed(master_seed, "F2")
    f3_seed = derived_seed(master_seed, "F3")
    f1_samples = generate_air56b2_ensemble(count, seed=master_seed)
    f2_samples = generate_f2_samples(f1_samples, seed=f2_seed)
    f3_samples = generate_f3_samples(f1_samples, seed=f3_seed)
    config = FocSvmKeyBaselineConfig(**selected["config"])
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
    passed = [trial for trial in trials if trial["status"] == "PASS"]
    gates = {
        "all_trials_passed": len(passed) == len(trials),
        "tuning_master_seed_matches": tuning_payload.get("master_seed") == master_seed,
        "controller_receives_observer_state_only": all(
            trial["checks"]["true_state_feedback_not_used"] for trial in trials
        ),
        "as5600_encoder_feedback_used": all(
            trial["checks"]["encoder_speed_feedback_used"] for trial in trials
        ),
        "hardware_claim_absent": True,
    }
    return {
        "schema": "air56b2-encoder-foc-fidelity-study-v1",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "evidence_level": "host_simulation_only",
        "hardware_claim": False,
        "hardware_identified": False,
        "hardware_release_ready": False,
        "master_seed": int(master_seed),
        "component_seeds": {"F2": f2_seed, "F3": f3_seed},
        "sample_count": len(trials),
        "steps_per_trial": int(steps),
        "tuning_sha256": str(tuning_sha256),
        "selected_candidate_index": int(selected["candidate_index"]),
        "f1_reference": {
            "schema": "air56b2-nameplate-ensemble-v2",
            "master_seed": int(master_seed),
            "sample_count": len(f1_samples),
            "sample_reference_sha256": reference_digest(f1_samples),
        },
        "command": {
            "target_speed_fraction_of_rated": float(target_speed_fraction),
            "speed_ramp_s": float(speed_ramp_s),
            "load_torque_fraction_of_rated": float(load_fraction),
        },
        "feedback_contract": {
            "controller_state": "current_voltage_flux_observer_estimate",
            "current": "delayed_quantized_f3_alpha_beta_adc",
            "current_offset_handling": "pre_pwm_zero_current_calibration",
            "vdc": "delayed_quantized_f3_adc",
            "speed": "delayed_quantized_as5600_finite_difference",
            "true_flux_speed_angle_to_controller": False,
            "controller_load_torque_input": "zero_open_loop_assumption",
        },
        "model_roles": {
            "controller_internal_model": "F1_nameplate_constrained",
            "plant": "F2_temperature_saturation_and_mechanical_losses_without_dynamic_core_loss",
            "starting_torque": "F1S_high_slip_loss_extension",
            "inverter_and_measurements": "F3_nonidealities",
        },
        "gates": gates,
        "summary": {
            "passed_trials": len(passed),
            "failed_trials": len(trials) - len(passed),
            "peak_true_current_a": max(trial["peak_true_current_a"] for trial in trials),
            "worst_steady_speed_error_rad_s": max(
                trial["steady_mean_abs_speed_error_rad_s"] for trial in trials
            ),
            "worst_final_speed_error_rad_s": max(
                trial["final_abs_speed_error_rad_s"] for trial in trials
            ),
            "maximum_observer_speed_error_rad_s": max(
                trial["maximum_observer_speed_error_rad_s"] for trial in trials
            ),
            "total_gateway_rejected_steps": sum(
                trial["gateway_rejected_steps"] for trial in trials
            ),
            "total_true_state_feedback_steps": sum(
                trial["true_state_feedback_steps"] for trial in trials
            ),
        },
        "trials": trials,
        "limitations": [
            "This validates encoder-assisted observer FOC, not sensorless FOC.",
            "The selected PI gains were tuned with oracle-state simulation and are only candidates here.",
            "F2 dynamic core loss and F1S thermal coupling are not implemented.",
            "No host result authorizes hardware energization before identification and low-voltage commissioning.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate AIR56B2 encoder-observer FOC through F1/F1S/F2/F3."
    )
    parser.add_argument("--tuning", type=Path, required=True)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--steps", type=int, default=10_000)
    parser.add_argument("--master-seed", type=int, default=560225)
    parser.add_argument("--target-speed-fraction", type=float, default=0.30)
    parser.add_argument("--speed-ramp-s", type=float, default=0.20)
    parser.add_argument("--load-fraction", type=float, default=0.50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.tuning.read_bytes()
    payload = run_study(
        json.loads(raw.decode("utf-8")),
        tuning_sha256=hashlib.sha256(raw).hexdigest(),
        count=args.count,
        steps=args.steps,
        master_seed=args.master_seed,
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
                "sample_count": payload["sample_count"],
                "passed_trials": payload["summary"]["passed_trials"],
                "output": str(args.output.resolve()),
                "hardware_release_ready": False,
            }
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

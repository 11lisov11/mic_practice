from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.safe_neural_horizon_pwm import effective_vector_schedule
from control.scalar_vf_baseline import (
    Air56B2ScalarVfBaselineController,
    ScalarVfBaselineConfig,
)
from models.air56b2_fidelity import (
    F2Sample,
    F3Sample,
    generate_f2_samples,
    generate_f3_samples,
)
from models.air56b2_nameplate_ensemble import (
    Air56B2EnsembleSample,
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
from models.two_level_inverter import TwoLevelInverterParams
from safety.ai_pwm_gateway import AIPwmSafetyGateway, GatewayLimits
from tools.build_air56b2_fidelity_bundle import derived_seed, reference_digest


def _finite(values: Sequence[float]) -> bool:
    return all(math.isfinite(float(value)) for value in values)


def _circular_error_rad(measured: float, reference: float) -> float:
    return (float(measured) - float(reference) + math.pi) % (2.0 * math.pi) - math.pi


def _delayed_value(buffer: deque[float], value: float) -> float:
    buffer.append(float(value))
    return float(buffer[0])


def _delay_buffer(delay_s: float, dt_s: float, initial: float) -> deque[float]:
    delay_steps = max(0, int(round(float(delay_s) / float(dt_s))))
    return deque([float(initial)] * (delay_steps + 1), maxlen=delay_steps + 1)


def _trial(
    f1: Air56B2EnsembleSample,
    f2: F2Sample,
    f3: F3Sample,
    *,
    steps: int,
    frequency_command_hz: float,
    ramp_hz_per_s: float,
    load_fraction: float,
) -> dict[str, Any]:
    nameplate = Air56B2Nameplate()
    derived = derive_nameplate(nameplate)
    if (f2.f1_index, f2.f1_seed) != (f1.index, f1.seed):
        raise ValueError("F2 sample is not aligned with F1")
    if (f3.f1_index, f3.f1_seed) != (f1.index, f1.seed):
        raise ValueError("F3 sample is not aligned with F1")

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
            max_switch_events_per_window=1000,
            switch_window_steps=8,
        )
    )
    controller = Air56B2ScalarVfBaselineController(
        controller_motor,
        inverter,
        gateway,
        ScalarVfBaselineConfig(
            dt_s=dt_s,
            max_frequency_hz=min(50.0, float(frequency_command_hz)),
            ramp_hz_per_s=float(ramp_hz_per_s),
            current_guard_limit_a=current_envelope_a,
        ),
    )
    plant = AlphaBetaInductionMotorModel(plant_motor)

    current_delay = _delay_buffer(f3.adc.sample_delay_s, dt_s, 0.0)
    voltage_delay = _delay_buffer(f3.adc.sample_delay_s, dt_s, initial_vdc)
    angle_delay = _delay_buffer(f3.as5600.sample_delay_s, dt_s, 0.0)
    current_zero_calibration_a = f3.adc.quantize_current(0.0)
    measured_current_a = abs(
        f3.adc.quantize_current(0.0) - current_zero_calibration_a
    )
    measured_vdc_v = f3.adc.quantize_voltage(initial_vdc)

    peak_current_a = 0.0
    peak_measured_current_a = measured_current_a
    peak_torque_nm = 0.0
    minimum_starting_scale = 1.0
    maximum_angle_error_rad = 0.0
    current_guard_steps = 0
    rejected_steps = 0
    feedback_requested_steps = 0
    current_clipped_steps = 0
    voltage_clipped_steps = 0
    nonfinite_step: int | None = None
    final_load_torque_nm = 0.0

    for step_index in range(int(steps)):
        time_s = step_index * dt_s
        true_vdc_v = f3.inverter.vdc_at(time_s)
        speed_fraction = min(
            1.0,
            abs(plant.state.omega_m) / max(derived.rated_omega_rad_s, 1.0e-12),
        )
        fan_load_torque_nm = (
            float(load_fraction) * derived.rated_torque_nm * speed_fraction**2
        )
        friction_torque_nm = (
            math.copysign(f2.effective_coulomb_friction_torque_nm, plant.state.omega_m)
            if abs(plant.state.omega_m) > 1.0e-6
            else 0.0
        )
        final_load_torque_nm = fan_load_torque_nm + friction_torque_nm
        result = controller.step(
            frequency_command_hz=frequency_command_hz,
            load_torque_nm=0.0,
            measured_state=None,
            measured_i_abs=measured_current_a,
            vdc=measured_vdc_v,
        )
        schedule = effective_vector_schedule(result, dt_s)
        plant_inverter = replace(inverter, Vdc=true_vdc_v)
        torque_scale = starting_torque_scale_for_speed(
            f1,
            electrical_frequency_hz=controller.frequency_hz,
            mechanical_speed_rad_s=plant.state.omega_m,
        )
        plant_step = step_inverter_schedule(
            plant,
            schedule,
            plant_inverter,
            final_load_torque_nm,
            pwm_enabled=result.decision.pwm_enabled,
            electromagnetic_torque_scale=torque_scale,
        )

        true_current_a = plant_step.currents.stator_abs
        delayed_current_a = _delayed_value(current_delay, true_current_a)
        delayed_vdc_v = _delayed_value(voltage_delay, true_vdc_v)
        delayed_angle_rad = _delayed_value(angle_delay, plant_step.state.theta_m)
        current_before_clip = (
            delayed_current_a * f3.adc.current_gain_scale + f3.adc.current_offset_a
        )
        voltage_before_clip = (
            delayed_vdc_v * f3.adc.voltage_gain_scale + f3.adc.voltage_offset_v
        )
        if abs(current_before_clip) >= f3.adc.current_full_scale_a:
            current_clipped_steps += 1
        if not 0.0 <= voltage_before_clip <= f3.adc.voltage_full_scale_v:
            voltage_clipped_steps += 1
        measured_current_a = abs(
            f3.adc.quantize_current(delayed_current_a) - current_zero_calibration_a
        )
        measured_vdc_v = f3.adc.quantize_voltage(delayed_vdc_v)
        measured_angle_rad = f3.as5600.quantize_angle(delayed_angle_rad)
        angle_error_rad = abs(
            _circular_error_rad(measured_angle_rad, plant_step.state.theta_m)
        )

        peak_current_a = max(peak_current_a, true_current_a)
        peak_measured_current_a = max(peak_measured_current_a, measured_current_a)
        peak_torque_nm = max(peak_torque_nm, abs(plant_step.torque_nm))
        minimum_starting_scale = min(minimum_starting_scale, torque_scale)
        maximum_angle_error_rad = max(maximum_angle_error_rad, angle_error_rad)
        current_guard_steps += int(result.metrics["current_guard_active"] > 0.5)
        rejected_steps += int(not result.decision.accepted)
        feedback_requested_steps += int(result.feedback_requested)
        if not _finite(
            (
                plant_step.state.omega_m,
                plant_step.state.theta_m,
                plant_step.currents.stator_abs,
                plant_step.torque_nm,
                measured_current_a,
                measured_vdc_v,
            )
        ):
            nonfinite_step = step_index
            break

    completed_steps = int(steps) if nonfinite_step is None else nonfinite_step + 1
    checks = {
        "completed_all_steps_with_finite_state": nonfinite_step is None,
        "no_gateway_fault_latch": not controller.gateway.fault_latched,
        "no_gateway_rejection": rejected_steps == 0,
        "current_adc_not_clipped": current_clipped_steps == 0,
        "vdc_adc_not_clipped": voltage_clipped_steps == 0,
        "peak_current_within_nameplate_start_envelope": peak_current_a <= current_envelope_a,
        "positive_final_rotation": plant.state.omega_m > 0.0,
        "f1s_starting_correction_exercised": minimum_starting_scale < 1.0,
        "no_true_state_feedback_to_controller": feedback_requested_steps == 0,
        "as5600_not_used_by_controller": True,
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
        "final_frequency_hz": controller.frequency_hz,
        "final_speed_rad_s": plant.state.omega_m,
        "final_speed_rpm": plant.state.omega_m * 60.0 / (2.0 * math.pi),
        "final_load_torque_nm": final_load_torque_nm,
        "peak_true_current_a": peak_current_a,
        "peak_measured_current_a": peak_measured_current_a,
        "current_envelope_a": current_envelope_a,
        "peak_abs_torque_nm": peak_torque_nm,
        "minimum_f1s_torque_scale": minimum_starting_scale,
        "maximum_as5600_angle_error_rad": maximum_angle_error_rad,
        "current_guard_steps": current_guard_steps,
        "gateway_rejected_steps": rejected_steps,
        "controller_feedback_requested_steps": feedback_requested_steps,
        "current_adc_clipped_steps": current_clipped_steps,
        "vdc_adc_clipped_steps": voltage_clipped_steps,
        "current_zero_calibration_a": current_zero_calibration_a,
        "nonfinite_step": nonfinite_step,
        "f2_operating_point": {
            "stator_temperature_c": f2.stator_temperature_c,
            "rotor_temperature_c": f2.rotor_temperature_c,
            "effective_coulomb_friction_torque_nm": (
                f2.effective_coulomb_friction_torque_nm
            ),
        },
        "f3_measurement_chain": {
            "adc_bits": f3.adc.bits,
            "adc_current_full_scale_a": f3.adc.current_full_scale_a,
            "adc_voltage_full_scale_v": f3.adc.voltage_full_scale_v,
            "adc_sample_delay_s": f3.adc.sample_delay_s,
            "as5600_bits": f3.as5600.bits,
            "as5600_sample_delay_s": f3.as5600.sample_delay_s,
        },
    }


def run_study(
    *,
    count: int,
    steps: int,
    master_seed: int,
    frequency_command_hz: float,
    ramp_hz_per_s: float,
    load_fraction: float,
) -> dict[str, Any]:
    if count < 1 or steps < 1:
        raise ValueError("count and steps must be positive")
    if not 0.0 < frequency_command_hz <= 50.0:
        raise ValueError("frequency command must be within (0, 50] Hz")
    if ramp_hz_per_s <= 0.0:
        raise ValueError("frequency ramp must be positive")
    if not 0.0 <= load_fraction <= 1.0:
        raise ValueError("load fraction must be within [0, 1]")

    f2_seed = derived_seed(master_seed, "F2")
    f3_seed = derived_seed(master_seed, "F3")
    f1_samples = generate_air56b2_ensemble(count, seed=master_seed)
    f2_samples = generate_f2_samples(f1_samples, seed=f2_seed)
    f3_samples = generate_f3_samples(f1_samples, seed=f3_seed)
    trials = [
        _trial(
            f1,
            f2,
            f3,
            steps=steps,
            frequency_command_hz=frequency_command_hz,
            ramp_hz_per_s=ramp_hz_per_s,
            load_fraction=load_fraction,
        )
        for f1, f2, f3 in zip(f1_samples, f2_samples, f3_samples)
    ]
    passed = [trial for trial in trials if trial["status"] == "PASS"]
    gates = {
        "all_trials_passed": len(passed) == len(trials),
        "f1_f2_f3_references_aligned": all(
            (f2.f1_index, f2.f1_seed) == (f1.index, f1.seed)
            and (f3.f1_index, f3.f1_seed) == (f1.index, f1.seed)
            for f1, f2, f3 in zip(f1_samples, f2_samples, f3_samples)
        ),
        "controller_uses_no_true_state_feedback": all(
            trial["checks"]["no_true_state_feedback_to_controller"] for trial in trials
        ),
        "as5600_is_teacher_only": all(
            trial["checks"]["as5600_not_used_by_controller"] for trial in trials
        ),
        "hardware_claim_absent": True,
    }
    return {
        "schema": "air56b2-vf-fidelity-study-v1",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "evidence_level": "host_simulation_only",
        "hardware_claim": False,
        "hardware_identified": False,
        "parameters_measured": False,
        "motor": "IEK AIR56B2 0.25 kW 220 V Delta",
        "master_seed": int(master_seed),
        "component_seeds": {"F2": f2_seed, "F3": f3_seed},
        "sample_count": len(trials),
        "steps_per_trial": int(steps),
        "command": {
            "frequency_hz": float(frequency_command_hz),
            "ramp_hz_per_s": float(ramp_hz_per_s),
            "fan_load_fraction_at_rated_speed": float(load_fraction),
        },
        "model_roles": {
            "controller_internal_model": "F1_nameplate_constrained",
            "controller_load_torque_input": "zero_open_loop_assumption",
            "plant": "F2_temperature_saturation_and_mechanical_losses_without_dynamic_core_loss",
            "dynamic_core_loss_applied": False,
            "starting_torque": "F1S_high_slip_loss_extension",
            "inverter_and_measurements": "F3_nonidealities",
            "controller_feedback": ["delayed_quantized_current_magnitude", "delayed_quantized_vdc"],
            "current_offset_handling": "pre_pwm_zero_current_calibration",
            "as5600": "recorded_teacher_channel_not_used_for_vf_control",
        },
        "f1_reference": {
            "schema": "air56b2-nameplate-ensemble-v2",
            "master_seed": int(master_seed),
            "sample_count": len(f1_samples),
            "sample_reference_sha256": reference_digest(f1_samples),
        },
        "gates": gates,
        "summary": {
            "passed_trials": len(passed),
            "failed_trials": len(trials) - len(passed),
            "peak_true_current_a": max(trial["peak_true_current_a"] for trial in trials),
            "minimum_final_speed_rpm": min(trial["final_speed_rpm"] for trial in trials),
            "maximum_final_speed_rpm": max(trial["final_speed_rpm"] for trial in trials),
            "minimum_f1s_torque_scale": min(
                trial["minimum_f1s_torque_scale"] for trial in trials
            ),
            "maximum_as5600_angle_error_rad": max(
                trial["maximum_as5600_angle_error_rad"] for trial in trials
            ),
            "total_gateway_rejected_steps": sum(
                trial["gateway_rejected_steps"] for trial in trials
            ),
            "total_current_adc_clipped_steps": sum(
                trial["current_adc_clipped_steps"] for trial in trials
            ),
            "total_vdc_adc_clipped_steps": sum(
                trial["vdc_adc_clipped_steps"] for trial in trials
            ),
        },
        "trials": trials,
        "limitations": [
            "This is deterministic host simulation, not bench or hardware validation.",
            "F1/F2/F3 parameters absent from the nameplate remain bounded priors, not measurements.",
            "The F1S high-slip loss law is phenomenological and must be updated after locked-rotor tests.",
            "F2 core-loss scaling is recorded but is not yet coupled to the alpha-beta dynamic power balance.",
            "F1S additional high-slip loss scales torque but is not yet coupled to a thermal state.",
            "Passing this gate proves software integration and finite safe simulation only; it does not authorize energizing the inverter.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the AIR56B2 sensorless scalar V/f baseline through F1/F1S/F2/F3."
    )
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--steps", type=int, default=4000)
    parser.add_argument("--master-seed", type=int, default=560225)
    parser.add_argument("--frequency-hz", type=float, default=15.0)
    parser.add_argument("--ramp-hz-per-s", type=float, default=100.0)
    parser.add_argument("--load-fraction", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run_study(
        count=args.count,
        steps=args.steps,
        master_seed=args.master_seed,
        frequency_command_hz=args.frequency_hz,
        ramp_hz_per_s=args.ramp_hz_per_s,
        load_fraction=args.load_fraction,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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

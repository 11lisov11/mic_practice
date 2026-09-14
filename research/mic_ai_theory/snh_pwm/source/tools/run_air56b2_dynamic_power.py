"""Averaged FOC/probe experiment; terminal energy, not inverter DC energy.

This deliberately reuses the baseline PI/antiwindup/dq methods, but does not
claim to exercise its PWM gateway, switching losses or firmware timing.
"""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
REPO = SOURCE.parents[3]
sys.path.insert(0, str(SOURCE))

from control.foc_svm_key_baseline import FocSvmKeyBaselineConfig, FocSvmKeyBaselineController
from estimation.current_voltage_flux_observer import CurrentVoltageFluxObserver
from estimation.encoder_current_flux_observer import EncoderCurrentFluxObserver
from models.air56b2_fidelity import generate_f2_samples
from models.air56b2_nameplate_ensemble import Air56B2Nameplate, derive_nameplate, generate_air56b2_ensemble
from models.induction_motor_alpha_beta import AlphaBetaMotorParams
from models.induction_motor_energy_core import EnergyCoreMotor, EnergyCoreParams
from models.transformations import alpha_beta_to_dq
from models.two_level_inverter import TwoLevelInverterParams
from safety.ai_pwm_gateway import AIPwmSafetyGateway, GatewayLimits


def source_hashes():
    files = sorted(p for p in SOURCE.rglob("*.py") if "tests" not in p.parts)
    files += [REPO / "artifacts/air56b2_encoder_foc_tuning.json"]
    return {str(path.relative_to(REPO)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files}


def build_cases(count, seed):
    f1 = generate_air56b2_ensemble(count, seed=seed)
    f2 = generate_f2_samples(f1, seed=seed+1)
    result = []
    for i, (cold, hot) in enumerate(zip(f1, f2)):
        motor = hot.transformed_motor
        for kappa in (0., .4):
            plant = EnergyCoreParams(
                motor.Rs, motor.Rr, motor.Ls_sigma, motor.Lr_sigma, motor.Lm,
                cold.core_resistance_ohm / hot.core_loss_scale,
                motor.J, motor.B, motor.p, hot.effective_coulomb_friction_torque_nm,
                saturation_kappa=kappa, saturation_knee_wb=.5)
            # One frozen cold controller for all plants; no online temperature/parameter truth.
            controller = replace(AlphaBetaMotorParams.from_motor_params(f1[0].motor), psi_sat=0.)
            result.append((f"motor{i}_k{kappa:g}", plant, controller))
    return result


def averaged_foc_voltage(controller, state, current, speed_ref, id_ref):
    controller.cfg = replace(controller.cfg, flux_ref_wb=controller.motor_params.Lm * id_ref)
    torque_ref = controller._torque_ref(speed_ref, state.omega_m)
    d_ref, q_ref = controller._dq_references(torque_ref)
    omega_e = controller._update_angle(state, d_ref, q_ref)
    d, q = alpha_beta_to_dq(*current, controller.theta_e)
    return controller._voltage_reference(
        id_ref=d_ref, iq_ref=q_ref, i_d=d, i_q=q, omega_e=omega_e,
        inverter=controller.inverter_params,
        rotor_flux_abs=math.hypot(state.psi_r_alpha, state.psi_r_beta), preflux_v=0.)


def run_trial(plant_params, control_params, *, method, duration_s=6., dt_s=1e-4,
              disturbance=False, noise_seed=730, trace_stride=50, observer_kind="current",
              speed_fraction=.3, plant_substeps=1, supervisor=None,
              initial_load_fraction=.25, final_load_fraction=.5, load_step_s=2.6):
    from control.air56b2_dynamic_probe import DynamicProbeConfig, DynamicProbeSupervisor
    if method not in ("fixed", "fit") or observer_kind not in ("current", "voltage"):
        raise ValueError("unknown method or observer")
    if (not isinstance(plant_substeps, int) or isinstance(plant_substeps, bool)
            or plant_substeps < 1 or not math.isfinite(duration_s) or duration_s <= 0
            or not math.isfinite(dt_s) or dt_s <= 0 or duration_s < dt_s
            or not math.isfinite(speed_fraction) or not 0 < speed_fraction <= 1
            or trace_stride < 1):
        raise ValueError("invalid experiment timing, substeps, speed or trace stride")
    if (any(not math.isfinite(v) or v < 0 for v in
            (initial_load_fraction,final_load_fraction,load_step_s))
            or max(initial_load_fraction,final_load_fraction) > 1.):
        raise ValueError("load fractions must lie in [0,1]; finite nonnegative step time required")
    derived = derive_nameplate()
    tuning = json.loads((REPO / "artifacts/air56b2_encoder_foc_tuning.json").read_text())
    config_data = tuning["selected"]["config"]
    cfg = FocSvmKeyBaselineConfig(**{**config_data, "dt_s": dt_s})
    inverter = TwoLevelInverterParams(Vdc=310., f_pwm=1/dt_s)
    control = FocSvmKeyBaselineController(control_params, inverter,
        AIPwmSafetyGateway(GatewayLimits(t_pwm_s=dt_s)), cfg)
    observer = (EncoderCurrentFluxObserver(control_params) if observer_kind == "current"
                else CurrentVoltageFluxObserver(control_params))
    plant = EnergyCoreMotor(plant_params)
    probe_cfg = DynamicProbeConfig(dt_s=dt_s, start_after_s=1.6)
    if supervisor is not None and method == "fixed":
        raise ValueError("fixed reference must not receive a supervisor")
    if supervisor is not None and supervisor.config.dt_s != dt_s:
        raise ValueError("supervisor and controller periods must match")
    probe = supervisor if supervisor is not None else (DynamicProbeSupervisor(probe_cfg) if method != "fixed" else None)
    rng = np.random.default_rng(noise_seed)
    encoder_span = max(1, round(.004/dt_s))
    history = deque([0.]*(encoder_span+1), maxlen=encoder_span+1)
    current = np.zeros(2)
    voltage = np.zeros(2)
    measured_power, measured_speed = 0., 0.
    energy = {key: 0. for key in ("input_j", "stator_copper_j", "rotor_copper_j", "core_j",
                                  "friction_j", "shaft_work_j", "stored_change_j")}
    trace, errors = [], []
    peak_current = 0.
    max_balance = 0.
    absolute_balance = 0.
    clipped_steps = 0
    current_violations = 0
    fault = None
    max_power_measurement_error_w = 0.
    id_ref, phase = .83, "fixed"
    action = None
    steps = round(duration_s/dt_s)
    for n in range(steps):
        t = n*dt_s
        speed_ref = speed_fraction * derived.rated_omega_rad_s * min(1., t/.6)
        load_fraction = initial_load_fraction
        if disturbance and t >= load_step_s:
            load_fraction = final_load_fraction
        load = load_fraction * derived.rated_torque_nm * min(1., max(0., (t-.65)/.25))
        if probe is not None:
            action = probe.step(time_s=t, measured_power_w=measured_power,
                measured_current_peak_a=float(np.linalg.norm(current)),
                measured_voltage_peak_v=float(np.linalg.norm(voltage)),
                measured_speed_rad_s=measured_speed, reference_speed_rad_s=speed_ref)
            id_ref, phase = action.id_ref_a, action.phase
        voltage = np.array(averaged_foc_voltage(control, observer.state, current, speed_ref, id_ref))
        violated_this_tick = False
        interval_input_j = 0.
        try:
            for _ in range(plant_substeps):
                step = plant.step(voltage, load, dt_s/plant_substeps)
                interval_input_j += step.input_j
                for key in energy:
                    energy[key] += getattr(step, key)
                max_balance = max(max_balance, abs(step.balance_error_j))
                absolute_balance += abs(step.balance_error_j)
                instantaneous_peak = float(np.linalg.norm(plant.currents()[0]))
                peak_current = max(peak_current, instantaneous_peak)
                violated_this_tick |= instantaneous_peak > 3.1
        except ArithmeticError as exc:
            fault = str(exc)
            break
        actual_current = plant.currents()[0]
        current_violations += int(violated_this_tick)
        # Explicit simulation sensor assumptions, not a claim about board ADC accuracy.
        next_current = np.round((actual_current + rng.normal(0., .002, 2))/.002)*.002
        angle = round((plant.angle_rad % (2*math.pi))*4096/(2*math.pi))*2*math.pi/4096
        history.append(angle)
        delta = (history[-1]-history[0]+math.pi) % (2*math.pi)-math.pi
        raw_speed = delta/(encoder_span*dt_s)
        measured_speed += .1*(raw_speed-measured_speed)
        midpoint_current = (current+next_current)/2
        measured_power = 1.5 * float(voltage @ midpoint_current)
        true_interval_power = interval_input_j / dt_s
        if t >= probe_cfg.start_after_s:
            max_power_measurement_error_w = max(max_power_measurement_error_w,
                                                abs(measured_power-true_interval_power))
        if observer_kind == "current":
            observer.step(i_alpha_a=midpoint_current[0], i_beta_a=midpoint_current[1],
                          speed_rad_s=measured_speed, dt_s=dt_s)
        else:
            update = observer.step(v_alpha=voltage[0], v_beta=voltage[1],
                i_s_alpha_before=midpoint_current[0], i_s_beta_before=midpoint_current[1],
                i_s_alpha_after=next_current[0], i_s_beta_after=next_current[1],
                omega_m_measured=measured_speed, dt_s=dt_s)
            clipped_steps += int(update.stator_flux_clipped)
        current = next_current
        error = speed_ref-plant.state[6]
        if t >= 1.2:
            errors.append(error)
        if n % trace_stride == 0:
            trace.append([t+dt_s, speed_ref, plant.state[6], measured_power, id_ref,
                          np.linalg.norm(actual_current), energy["input_j"],
                          energy["shaft_work_j"], plant.stored_energy_j(), phase, true_interval_power])
        if np.linalg.norm(actual_current) > 9.8 or abs(plant.state[6]) > 450:
            fault = "research_abort_envelope"
            break
    completed = n+1 if fault is None or fault == "research_abort_envelope" else n
    loss = sum(energy[key] for key in ("stator_copper_j", "rotor_copper_j", "core_j", "friction_j"))
    mean_error = float(np.mean(np.abs(errors))) if errors else None
    checks = {"complete": completed == steps and fault is None,
              "observer_not_clipped": clipped_steps == 0,
              "current_within_3p1a": current_violations == 0,
              "settled_speed_mae_below_3rad_s": mean_error is not None and mean_error < 3.,
              "energy_balance": max_balance < 1e-8}
    checks = {key: bool(value) for key, value in checks.items()}
    return {"method": method, "observer": observer_kind, "disturbance": disturbance, "duration_s": duration_s,
            "initial_load_fraction": initial_load_fraction, "final_load_fraction": final_load_fraction,
            "load_step_s": load_step_s,
            "speed_fraction": speed_fraction, "noise_seed": noise_seed,
            "plant_substeps": plant_substeps,
            "probe_complete": action.completed if action else True,
            "probe_reason": action.reason if action else None,
            "completed_steps": completed, "dt_s": dt_s, "checks": checks,
            "status": "PASS" if all(checks.values()) else "FAIL", "fault": fault,
            "energy": {**energy, "loss_j": loss}, "peak_current_a": peak_current,
            "current_violation_steps": current_violations, "speed_mae_rad_s": mean_error,
            "max_step_balance_error_j": max_balance, "sum_abs_balance_error_j": absolute_balance,
            "final_id_a": id_ref, "final_phase": phase,
            "evaluation_final_state": plant.state.tolist(),
            "probe_events": probe.events if probe else [],
            "max_power_measurement_error_after_1p6s_w": max_power_measurement_error_w,
            "trace_columns": ["time_s", "speed_ref_rad_s", "speed_rad_s", "measured_power_w",
                              "id_ref_a", "current_peak_a", "input_j", "shaft_work_j", "stored_j", "phase",
                              "true_interval_terminal_power_w"],
            "trace": trace}


def paired_comparison(rows):
    pairs = []
    def key(row):
        return tuple(row[k] for k in ("case", "disturbance", "speed_fraction", "observer", "dt_s", "duration_s", "noise_seed")) + (row.get("plant_substeps", 1),)
    for case in sorted(set(key(row) for row in rows)):
        group = [r for r in rows if key(r) == case]
        selected = {r["method"]: r for r in group}
        if len(group) != len(selected):
            raise ValueError("duplicate method for paired trial")
        if set(selected) != {"fixed", "fit"}:
            continue
        base, adaptive = selected["fixed"], selected["fit"]
        work_delta = adaptive["energy"]["shaft_work_j"] - base["energy"]["shaft_work_j"]
        eligible = (all(r["status"] == "PASS" and r["probe_complete"] for r in selected.values())
                    and abs(work_delta) <= .01*max(abs(base["energy"]["shaft_work_j"]), 1.))
        pairs.append({"case": case[0], "disturbance": case[1], "speed_fraction": case[2],
            "observer": case[3], "eligible": bool(eligible),
            "work_delta_j": work_delta,
            "input_saving_j": base["energy"]["input_j"]-adaptive["energy"]["input_j"],
            "loss_saving_j": base["energy"]["loss_j"]-adaptive["energy"]["loss_j"],
            "stored_delta_j": adaptive["energy"]["stored_change_j"]-base["energy"]["stored_change_j"]})
    return pairs


def _run_job(job):
    name, plant, control, method, disturbance, duration, dt, observer, speed, substeps = job
    row = run_trial(plant, control, method=method, disturbance=disturbance,
                    duration_s=duration, dt_s=dt, observer_kind=observer, speed_fraction=speed,
                    plant_substeps=substeps)
    row["case"] = name
    return row


def _json_scalar(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"unsupported JSON type {type(value).__name__}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", type=int, default=3)
    parser.add_argument("--seed", type=int, default=92061)
    parser.add_argument("--duration", type=float, default=6.)
    parser.add_argument("--dt", type=float, default=1e-4)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--observer", choices=["current", "voltage"], default="current")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--speeds", type=float, nargs="+", default=[.3, .7])
    parser.add_argument("--plant-substeps", type=int, default=1)
    args = parser.parse_args()
    if (args.models < 1 or not math.isfinite(args.duration) or args.duration <= 0
            or not math.isfinite(args.dt) or args.dt <= 0 or args.duration < args.dt
            or args.workers < 1 or args.plant_substeps < 1
            or any(not math.isfinite(s) or not 0 < s <= 1 for s in args.speeds)):
        parser.error("models, duration, dt, workers must be positive")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/"manifest.json").unlink(missing_ok=True)
    hashes = source_hashes()
    cases = build_cases(args.models, args.seed)
    if args.smoke:
        cases = cases[:1]
    protocol = {"schema": 1, "nameplate": asdict(Air56B2Nameplate()),
        "seed": args.seed, "dt_s": args.dt, "duration_s": args.duration,
        "boundary": "averaged_motor_terminals_no_inverter_loss_no_switching_gateway",
        "sensor_assumptions": {"current_noise_std_a": .002, "current_lsb_a": .002,
            "current_delay_steps": 0, "encoder_bits": 12, "speed_window_s": .004},
        "observer": args.observer,
        "controller_information": "one frozen cold F1 model; measured current/voltage/encoder speed; no true torque/flux/temperature",
        "thermal_assumption": "constant hot resistances per trial; no online thermal state",
        "core_model": "Rc=F1.core_resistance/F2.core_loss_scale; nonlinear kappa explicit prior, knee=.5Wb peak",
        "not_validated": ["hardware", "sensorless", "neural_dynamic_transfer", "startup_nameplate_ratios", "PWM_switching", "whole_drive_efficiency"],
        "cases": [{"case": name, "plant": asdict(p), "controller": asdict(c)} for name, p, c in cases]}
    from control.air56b2_dynamic_probe import DynamicProbeConfig
    protocol["probe"] = asdict(DynamicProbeConfig(dt_s=args.dt, start_after_s=1.6))
    protocol["plant_substeps"] = args.plant_substeps
    protocol["speeds"] = args.speeds[:1] if args.smoke else args.speeds
    (args.out/"protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    rows = []
    start = time.monotonic()
    jobs = [(name, plant, control, method, disturbance, args.duration, args.dt, args.observer, speed, args.plant_substeps)
            for name, plant, control in cases
            for speed in protocol["speeds"]
            for disturbance in ([False] if args.smoke else [False, True])
            for method in ("fixed", "fit")]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_run_job, job) for job in jobs]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(row["case"], row["speed_fraction"], row["disturbance"], row["method"], row["status"], row["final_phase"],
                  row["speed_mae_rad_s"], row["energy"]["input_j"], flush=True)
    rows.sort(key=lambda r: (r["case"], r["speed_fraction"], r["disturbance"], r["method"]))
    result = {"rows": rows, "pairs": paired_comparison(rows), "elapsed_s": time.monotonic()-start}
    if source_hashes() != hashes:
        raise RuntimeError("source/input changed during run; results not published")
    path = args.out/"study.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False, default=_json_scalar), encoding="utf-8")
    manifest = {"sources": hashes, "outputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (path, args.out/"protocol.json")}}
    (args.out/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"pairs": result["pairs"], "elapsed_s": result["elapsed_s"]}), flush=True)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import hashlib
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

from models.air56b2_loss_thermal import (
    Air56B2LossModelParams,
    MotorThermalParams,
    MotorThermalState,
    evaluate_operating_point,
    losses_to_dict,
    optimize_id_reference,
    simulate_constant_thermal_load,
)


DEFAULT_INPUT = REPOSITORY_ROOT / "artifacts" / "air56b2_fidelity_bundle.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts" / "air56b2_loss_optimization_study.json"
SAMPLE_INDICES = tuple(range(0, 256, 11))
SPEED_FRACTIONS = (0.20, 0.40, 0.60, 0.80, 1.00)
TORQUE_FRACTIONS = (0.25, 0.50, 0.75, 1.00)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _params_from_rows(bundle: dict[str, Any], index: int) -> tuple[Air56B2LossModelParams, float]:
    fidelity = bundle["fidelity"]
    f2 = fidelity["f2_samples"][index]
    f3 = fidelity["f3_samples"][index]
    motor = f2["transformed_motor"]
    inverter = f3["inverter"]
    derived = fidelity["derived_nameplate"]
    nameplate = fidelity["nameplate"]
    rs_ref = float(motor["Rs"]) / float(f2["stator_resistance_scale"])
    rr_ref = float(motor["Rr"]) / float(f2["rotor_resistance_scale"])
    rated_flux = float(f2["saturation_knee_flux_wb"]) / float(f2["saturation_knee_flux_scale"])
    params = Air56B2LossModelParams(
        rs_ref_ohm=rs_ref,
        rr_ref_ohm=rr_ref,
        lm_h=float(motor["Lm"]),
        lls_h=float(motor["Ls_sigma"]),
        llr_h=float(motor["Lr_sigma"]),
        pole_pairs=int(motor["p"]),
        rated_frequency_hz=float(nameplate["frequency_hz"]),
        rated_omega_rad_s=float(derived["rated_omega_rad_s"]),
        rated_flux_wb=rated_flux,
        rated_core_loss_w=float(f2["effective_core_loss_w"]),
        viscous_b_nms=float(f2["effective_viscous_coefficient_nms"]),
        coulomb_friction_nm=float(f2["effective_coulomb_friction_torque_nm"]),
        stator_temp_coeff_per_c=float(f2["stator_copper_alpha_per_c"]),
        rotor_temp_coeff_per_c=float(f2["rotor_copper_alpha_per_c"]),
        reference_temp_c=20.0,
        saturation_knee_flux_wb=float(f2["saturation_knee_flux_wb"]),
        saturation_exponent=float(f2["saturation_exponent"]),
        minimum_lm_scale=float(f2["minimum_magnetizing_inductance_scale"]),
        vdc_v=float(inverter["nominal_vdc_v"]),
        pwm_frequency_hz=float(inverter["pwm_frequency_hz"]),
        switch_r_on_ohm=float(inverter["switch_r_on_ohm"]),
        switch_voltage_drop_v=float(inverter["switch_voltage_drop_v"]),
        phase_voltage_limit_v=0.95 * float(inverter["nominal_vdc_v"]) / math.sqrt(3.0),
        phase_current_peak_limit_a=2.5 * float(nameplate["line_current_a"]),
    )
    fixed_id = rated_flux / max(float(motor["Lm"]), 1e-12)
    return params, fixed_id


def run_study(input_path: Path, output_path: Path) -> dict[str, Any]:
    bundle = _read(input_path)
    if bundle.get("schema") != "air56b2-fidelity-bundle-v1" or bundle.get("status") != "PASS":
        raise ValueError("AIR56B2 fidelity bundle is missing or invalid")
    if bool(bundle.get("hardware_claim", True)) or bool(bundle.get("hardware_identified", True)):
        raise ValueError("Loss study input must remain simulation-only")

    derived = bundle["fidelity"]["derived_nameplate"]
    rated_speed = float(derived["rated_omega_rad_s"])
    rated_torque = float(derived["rated_torque_nm"])
    rows: list[dict[str, Any]] = []
    infeasible: list[dict[str, Any]] = []
    for sample_index in SAMPLE_INDICES:
        params, fixed_id = _params_from_rows(bundle, sample_index)
        for speed_fraction in SPEED_FRACTIONS:
            for torque_fraction in TORQUE_FRACTIONS:
                speed = rated_speed * speed_fraction
                torque = rated_torque * torque_fraction
                fixed = evaluate_operating_point(
                    params,
                    speed_rad_s=speed,
                    torque_nm=torque,
                    id_a=fixed_id,
                )
                try:
                    optimized = optimize_id_reference(
                        params,
                        speed_rad_s=speed,
                        torque_nm=torque,
                        id_lower_a=0.12,
                        id_upper_a=1.50 * 1.24,
                        grid_points=801,
                        candidate_id_values=(fixed_id,),
                    )
                except ValueError as exc:
                    infeasible.append(
                        {
                            "sample_index": sample_index,
                            "speed_fraction": speed_fraction,
                            "torque_fraction": torque_fraction,
                            "reason": str(exc),
                        }
                    )
                    continue
                optimum = optimized.optimum
                if not fixed.feasible:
                    infeasible.append(
                        {
                            "sample_index": sample_index,
                            "speed_fraction": speed_fraction,
                            "torque_fraction": torque_fraction,
                            "reason": "fixed-rated-flux baseline violates current or voltage limit",
                        }
                    )
                    continue
                saving = 100.0 * (fixed.total_loss_w - optimum.total_loss_w) / max(fixed.total_loss_w, 1e-12)
                rows.append(
                    {
                        "sample_index": sample_index,
                        "speed_fraction": speed_fraction,
                        "torque_fraction": torque_fraction,
                        "speed_rad_s": speed,
                        "torque_nm": torque,
                        "fixed": losses_to_dict(fixed),
                        "optimized": losses_to_dict(optimum),
                        "loss_saving_pct": saving,
                        "evaluated_points": optimized.evaluated_points,
                        "feasible_points": optimized.feasible_points,
                    }
                )

    if not rows:
        raise RuntimeError("Loss optimization study produced no comparable operating points")
    savings = [float(row["loss_saving_pct"]) for row in rows]
    worse_count = sum(1 for value in savings if value < -1e-9)

    central_params, central_fixed_id = _params_from_rows(bundle, 128)
    rated_losses = evaluate_operating_point(
        central_params,
        speed_rad_s=rated_speed,
        torque_nm=rated_torque,
        id_a=central_fixed_id,
    )
    thermal_params = MotorThermalParams()
    thermal_initial = MotorThermalState(
        stator_temp_c=thermal_params.ambient_temp_c,
        rotor_temp_c=thermal_params.ambient_temp_c,
    )
    thermal_600s = simulate_constant_thermal_load(
        thermal_initial,
        rated_losses,
        thermal_params,
        duration_s=600.0,
        dt_s=0.1,
    )

    expected_cases = len(SAMPLE_INDICES) * len(SPEED_FRACTIONS) * len(TORQUE_FRACTIONS)
    comparable_fraction = len(rows) / expected_cases
    gates = {
        "input_bundle_passed": True,
        "no_hardware_claim": True,
        "comparable_fraction_at_least_90pct": comparable_fraction >= 0.90,
        "optimizer_never_worse_on_comparable_points": worse_count == 0,
        "median_loss_saving_positive": statistics.median(savings) > 0.0,
        "thermal_state_is_finite_and_heats": (
            math.isfinite(thermal_600s.stator_temp_c)
            and math.isfinite(thermal_600s.rotor_temp_c)
            and thermal_600s.stator_temp_c > thermal_initial.stator_temp_c
            and thermal_600s.rotor_temp_c > thermal_initial.rotor_temp_c
        ),
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    payload = {
        "schema": "air56b2-loss-optimization-study-v1",
        "status": status,
        "hardware_claim": False,
        "hardware_identified": False,
        "hardware_release_ready": False,
        "input": {"path": str(input_path.resolve()), "sha256": _sha256(input_path)},
        "sample_indices": list(SAMPLE_INDICES),
        "speed_fractions": list(SPEED_FRACTIONS),
        "torque_fractions": list(TORQUE_FRACTIONS),
        "case_count_expected": expected_cases,
        "case_count_comparable": len(rows),
        "case_count_infeasible": len(infeasible),
        "comparable_fraction": comparable_fraction,
        "summary": {
            "loss_saving_pct_min": min(savings),
            "loss_saving_pct_median": statistics.median(savings),
            "loss_saving_pct_mean": statistics.fmean(savings),
            "loss_saving_pct_max": max(savings),
            "worse_case_count": worse_count,
        },
        "thermal_prior": {
            "parameters": thermal_params.__dict__,
            "initial": thermal_initial.__dict__,
            "after_600s_at_central_rated_point": thermal_600s.__dict__,
        },
        "gates": gates,
        "limitations": [
            "The loss model is an analytical F1/F2/F3 prior and is not fitted to hardware calorimetry.",
            "Core-loss exponents, switching-time equivalent, and two-node thermal constants are explicit simulation assumptions.",
            "The classical optimum is an offline reference baseline, not an approved real-time current command.",
            "Every current/voltage/temperature limit must be replaced by measured board and motor limits before commissioning.",
        ],
        "infeasible_cases": infeasible,
        "cases": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AIR56B2 analytical loss and id-reference optimization study")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = run_study(args.input.resolve(), args.output.resolve())
    print(json.dumps({"status": payload["status"], **payload["summary"]}, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

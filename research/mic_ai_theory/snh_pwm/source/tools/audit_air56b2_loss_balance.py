from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.air56b2_loss_thermal import (
    Air56B2LossModelParams,
    LossBreakdown,
    MotorThermalState,
    evaluate_operating_point,
    loss_params_from_fidelity_bundle,
)
from tools.run_air56b2_measurement_adaptation import evaluate_shaft_point


DEFAULT_OUTPUT_DIR = REPO / "artifacts/measurement_adaptation_20260908"
COMMON_ID_A = 0.83
TOLERANCE_W = 1e-9
METHODS = ("legacy_fixed", "legacy_neural", "common_fixed_083")
SOURCE_PATHS = (
    Path(__file__).resolve(),
    ROOT / "models/air56b2_loss_thermal.py",
    ROOT / "tools/run_air56b2_measurement_adaptation.py",
    ROOT / "models/air56b2_measurement_context.py",
    ROOT / "control/air56b2_measured_loss_fit.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_input(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    data = path.read_bytes()
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    if payload.get("status") != "PASS" or payload.get("hardware_claim") is not False:
        raise ValueError(f"Expected a simulation-only PASS input: {path}")
    return payload, {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def _stats(values: list[float]) -> dict[str, float | int]:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("Audit statistics require nonempty finite values")
    return {
        "count": len(values),
        "minimum": min(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "maximum_absolute": max(abs(value) for value in values),
    }


def _balance(
    params: Air56B2LossModelParams,
    point: LossBreakdown,
    thermal: MotorThermalState,
    speed: float,
    electromagnetic_torque: float,
    shaft_power: float,
) -> dict[str, float | bool]:
    rs = params.rs_ref_ohm * (
        1.0 + params.stator_temp_coeff_per_c * (thermal.stator_temp_c - params.reference_temp_c)
    )
    lm = point.effective_lm_h
    lr = lm + params.llr_h
    omega_e = 2.0 * math.pi * point.electrical_frequency_hz
    original_vd = rs * point.id_a - omega_e * params.lls_h * point.iq_a
    original_vq = rs * point.iq_a + omega_e * (point.flux_wb + params.lls_h * point.id_a)
    leakage = params.lls_h + lm * params.llr_h / lr
    corrected_vd = rs * point.id_a - omega_e * leakage * point.iq_a
    corrected_vq = rs * point.iq_a + omega_e * (leakage * point.id_a + lm / lr * point.flux_wb)
    original_power = 1.5 * (original_vd * point.id_a + original_vq * point.iq_a)
    corrected_power = 1.5 * (corrected_vd * point.id_a + corrected_vq * point.iq_a)
    core_free_expected = (
        electromagnetic_torque * speed + point.stator_copper_w + point.rotor_copper_w
    )
    # This is an additive modeled wattmeter, not power reconstructed from dq channels.
    virtual_input = shaft_power + point.total_loss_w
    return {
        "total_loss_w": point.total_loss_w,
        "iq_a": point.iq_a,
        "feasible": point.feasible,
        "electromagnetic_torque_nm": electromagnetic_torque,
        "stator_copper_w": point.stator_copper_w,
        "rotor_copper_w": point.rotor_copper_w,
        "core_prior_w": point.core_w,
        "mechanical_w": point.mechanical_w,
        "inverter_prior_w": point.inverter_loss_w,
        "original_vd_v": original_vd,
        "original_vq_v": original_vq,
        "corrected_vd_v": corrected_vd,
        "corrected_vq_v": corrected_vq,
        "original_voltage_peak_v": math.hypot(original_vd, original_vq),
        "corrected_voltage_peak_v": math.hypot(corrected_vd, corrected_vq),
        "returned_voltage_peak_v": point.phase_voltage_peak_v,
        "original_dq_power_w": original_power,
        "corrected_dq_power_w": corrected_power,
        "core_free_expected_power_w": core_free_expected,
        "original_core_free_residual_w": original_power - core_free_expected,
        "corrected_core_free_residual_w": corrected_power - core_free_expected,
        "predicted_original_leakage_residual_w": (
            electromagnetic_torque * omega_e / params.pole_pairs * params.llr_h / lm
        ),
        "rotor_slip_residual_w": (
            point.rotor_copper_w - electromagnetic_torque * point.slip_omega_rad_s / params.pole_pairs
        ),
        "virtual_input_power_w": virtual_input,
        "virtual_minus_original_dq_plus_inverter_w": virtual_input - original_power - point.inverter_loss_w,
        "virtual_minus_corrected_dq_plus_inverter_w": virtual_input - corrected_power - point.inverter_loss_w,
    }


def _summary(rows: list[dict[str, Any]], method: str) -> dict[str, Any]:
    points = [row["evaluations"][method] for row in rows]
    result: dict[str, Any] = {
        "shaft_minus_legacy_loss_w": _stats([point["shaft_minus_legacy_loss_w"] for point in points]),
    }
    for interpretation in ("legacy", "shaft_corrected"):
        balances = [point[interpretation] for point in points]
        result[interpretation] = {
            "infeasible_count": sum(not point["feasible"] for point in balances),
            **{
                key: _stats([point[key] for point in balances])
                for key in (
                    "original_core_free_residual_w", "corrected_core_free_residual_w",
                    "rotor_slip_residual_w", "virtual_minus_original_dq_plus_inverter_w",
                    "virtual_minus_corrected_dq_plus_inverter_w",
                )
            },
        }
    return result


def audit(fidelity_path: Path, policy_path: Path) -> dict[str, Any]:
    sources = [{"path": str(path), "sha256": _sha256(path)} for path in SOURCE_PATHS]
    fidelity, fidelity_record = _read_input(fidelity_path)
    policy, policy_record = _read_input(policy_path)
    if policy.get("input", {}).get("sha256") != fidelity_record["sha256"]:
        raise ValueError("Policy provenance does not match the supplied fidelity bundle")
    source_rows = policy["holdout_rows"]
    splits = policy["splits"]
    if len(source_rows) != 600 or splits["holdout_case_count"] != 600:
        raise ValueError("This bounded audit requires the existing 600-row holdout")
    counts = Counter(row["sample_index"] for row in source_rows)
    if len(counts) != 12 or set(counts.values()) != {50}:
        raise ValueError("Expected 12 parameter samples with 50 cases each")
    if set(counts) != set(splits["holdout_sample_indices"]):
        raise ValueError("Holdout sample identifiers do not match the split record")
    if set(counts) & (set(splits["train_sample_indices"]) | set(splits["validation_sample_indices"])):
        raise ValueError("Holdout overlaps training or validation")
    context_keys = ("sample_index", "speed_pu", "torque_pu", "stator_temp_c", "rotor_temp_c")
    if len({tuple(row[key] for key in context_keys) for row in source_rows}) != 600:
        raise ValueError("Duplicate holdout contexts")

    derived = fidelity["fidelity"]["derived_nameplate"]
    rows: list[dict[str, Any]] = []
    checks: dict[str, list[float]] = {
        key: [] for key in (
            "saved_loss_replay_error_w", "saved_fixed_id_replay_error_a",
            "corrected_core_free_residual_w", "rotor_slip_residual_w",
            "leakage_formula_error_w", "original_voltage_replay_error_v",
            "wrapper_voltage_replay_error_v", "mechanical_power_identity_error_w",
            "shaft_virtual_core_accounting_error_w", "legacy_virtual_core_mechanical_accounting_error_w",
        )
    }
    for source in source_rows:
        params, fixed_id = loss_params_from_fidelity_bundle(fidelity, int(source["sample_index"]))
        checks["saved_fixed_id_replay_error_a"].append(fixed_id - float(source["fixed_id_a"]))
        speed = float(derived["rated_omega_rad_s"]) * float(source["speed_pu"])
        torque = float(derived["rated_torque_nm"]) * float(source["torque_pu"])
        thermal = MotorThermalState(float(source["stator_temp_c"]), float(source["rotor_temp_c"]))
        electromagnetic_torque = torque + params.viscous_b_nms * speed + params.coulomb_friction_nm
        shaft_power = torque * speed
        row = {
            **{key: source[key] for key in context_keys},
            "speed_rad_s": speed, "shaft_torque_nm": torque,
            "shaft_power_w": shaft_power, "corrected_electromagnetic_torque_nm": electromagnetic_torque,
            "evaluations": {},
        }
        actions = (
            ("legacy_fixed", float(source["fixed_id_a"]), float(source["fixed_loss_w"])),
            ("legacy_neural", float(source["policy_id_a"]), float(source["policy_loss_w"])),
            ("common_fixed_083", COMMON_ID_A, None),
        )
        for method, id_a, saved_loss in actions:
            legacy_point = evaluate_operating_point(
                params, speed_rad_s=speed, torque_nm=torque, id_a=id_a, thermal_state=thermal,
            )
            shaft_point = evaluate_shaft_point(params, speed, torque, id_a, thermal)
            legacy = _balance(params, legacy_point, thermal, speed, torque, shaft_power)
            corrected = _balance(params, shaft_point, thermal, speed, electromagnetic_torque, shaft_power)
            replay_error = None if saved_loss is None else legacy_point.total_loss_w - saved_loss
            if replay_error is not None:
                checks["saved_loss_replay_error_w"].append(replay_error)
            for point in (legacy, corrected):
                for key in ("corrected_core_free_residual_w", "rotor_slip_residual_w"):
                    checks[key].append(point[key])
                checks["leakage_formula_error_w"].append(
                    point["original_core_free_residual_w"] - point["predicted_original_leakage_residual_w"]
                )
            checks["original_voltage_replay_error_v"].append(
                legacy["original_voltage_peak_v"] - legacy_point.phase_voltage_peak_v
            )
            checks["wrapper_voltage_replay_error_v"].append(
                corrected["corrected_voltage_peak_v"] - shaft_point.phase_voltage_peak_v
            )
            checks["mechanical_power_identity_error_w"].append(
                (electromagnetic_torque - torque) * speed - shaft_point.mechanical_w
            )
            checks["shaft_virtual_core_accounting_error_w"].append(
                corrected["virtual_minus_corrected_dq_plus_inverter_w"] - shaft_point.core_w
            )
            checks["legacy_virtual_core_mechanical_accounting_error_w"].append(
                legacy["virtual_minus_corrected_dq_plus_inverter_w"]
                - legacy_point.core_w - legacy_point.mechanical_w
            )
            row["evaluations"][method] = {
                "id_a": id_a, "saved_loss_w": saved_loss, "saved_loss_replay_error_w": replay_error,
                "shaft_minus_legacy_loss_w": shaft_point.total_loss_w - legacy_point.total_loss_w,
                "legacy": legacy, "shaft_corrected": corrected,
            }
        rows.append(row)

    protected = [fidelity_record, policy_record, *sources]
    integrity = {
        "inputs_and_sources_unchanged": all(_sha256(Path(item["path"])) == item["sha256"] for item in protected),
        **{key + "_within_tolerance": max(map(abs, values)) <= TOLERANCE_W for key, values in checks.items()},
    }
    return {
        "schema": "air56b2-legacy-loss-balance-audit-v1",
        "status": "PASS" if all(integrity.values()) else "FAIL",
        "status_meaning": "Audit replay and algebraic checks only; legacy scientific conclusions remain provisional.",
        "hardware_claim": False, "hardware_release_ready": False,
        "case_count": len(rows), "parameter_sample_count": len(counts),
        "common_fixed_id_a": COMMON_ID_A,
        "python_executable": sys.executable,
        "python_version": sys.version,
        "inputs": {"fidelity": fidelity_record, "legacy_policy": policy_record},
        "sources": sources,
        "contracts": {
            "scope": "600 saved contexts; replay fixed/neural actions and 0.83 A only; no training or optimization",
            "loss_difference": "shaft-corrected total loss minus legacy total loss at identical id, speed and temperatures",
            "torque": "Te = Tshaft + B*omega_m + Tc; positive-speed steady motoring",
            "core_free_identity": "P_dq = Te*omega_m + P_stator_copper + P_rotor_copper",
            "dq_comparison": "Original and corrected voltages evaluated at the same current and Te within each interpretation",
            "original_residual": "Te*omega_e/p * Llr/Lm_eff",
            "virtual_wattmeter": "P_virtual = Tshaft*omega_m + total_loss; not an implemented electrical estimator",
            "corrected_virtual_gap": "P_virtual - (P_dq_corrected + P_inverter_prior) = P_core_prior",
            "legacy_virtual_gap": "P_virtual_legacy - (P_dq_corrected + P_inverter_prior) = P_core_prior + P_mechanical",
        },
        "absolute_tolerances": {"power_w": TOLERANCE_W, "voltage_v": TOLERANCE_W, "current_a": TOLERANCE_W},
        "integrity_checks": integrity,
        "check_maximum_absolute_errors": {key: max(map(abs, values)) for key, values in checks.items()},
        "summary": {method: _summary(rows, method) for method in METHODS},
        "limitations": [
            "Core-free identity excludes the additive core-loss prior and inverter-loss prior; it does not validate either.",
            "No current-carrying core-loss branch is implemented; voltage/current amplitudes are approximate proxies.",
            "Virtual watts are synthetic shaft power plus modeled losses, not measured or reconstructed terminal/DC watts.",
            "This is a frozen-action replay, not a corrected policy benchmark or a re-optimization of historical actions.",
            "All 600 cases are retained irrespective of feasibility; parameter priors are not physical motor measurements.",
            "No study, settling dynamics, transient energy, thermal safety test or hardware experiment is run.",
        ],
        "rows": rows,
    }


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Legacy AIR56B2 Loss-Balance Audit", "",
        f"Status: **{result['status']}**. {result['status_meaning']}", "",
        "600 existing holdout contexts, 12 simulated parameter samples. No training, optimization, or historical artifact edits.",
        "All cases retained, including any infeasible points. Common fixed current: 0.83 A.", "",
        "## Shaft-Torque Correction", "",
        "At fixed current/speed/temperature, add friction torque before evaluating losses:",
        "`Te = Tshaft + B*omega_m + Tc`. Positive differences below mean the legacy evaluation understated loss.", "",
        "| Current choice | Minimum delta W | Median delta W | Maximum delta W | Corrected infeasible |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for method in METHODS:
        summary = result["summary"][method]
        delta = summary["shaft_minus_legacy_loss_w"]
        lines.append(f"| {method} | {delta['minimum']:.6f} | {delta['median']:.6f} | {delta['maximum']:.6f} | {summary['shaft_corrected']['infeasible_count']} |")
    lines += [
        "", "## Core-Free dq Identity", "",
        "Residual: `1.5*(vd*id + vq*iq) - Te*omega_m - P_stator_copper - P_rotor_copper`.",
        "Original/corrected voltages use identical currents and electromagnetic torque within each interpretation.",
        "The corrected leakage is `Lls + Lm_eff*Llr/(Lm_eff + Llr)`.", "",
        "| Current choice / torque interpretation | Original median W | Original max abs W | Corrected max abs W |",
        "| --- | ---: | ---: | ---: |",
    ]
    for method in METHODS:
        for interpretation in ("legacy", "shaft_corrected"):
            summary = result["summary"][method][interpretation]
            original = summary["original_core_free_residual_w"]
            corrected = summary["corrected_core_free_residual_w"]
            lines.append(f"| {method} / {interpretation} | {original['median']:.6f} | {original['maximum_absolute']:.6f} | {corrected['maximum_absolute']:.3e} |")
    lines += [
        "", "## Virtual Wattmeter Limitation", "",
        "`P_virtual = Tshaft*omega_m + total_loss` is synthetic, not an implemented power estimator.",
        "After both corrections, `P_virtual - (P_dq_corrected + P_inverter_prior) = P_core_prior`.",
        "With legacy torque semantics, that gap is `P_core_prior + P_mechanical` instead.",
        "Core and inverter priors are NOT validated by the core-free identity. No current-carrying iron-loss branch exists.",
        "Voltage/current amplitudes remain approximate proxies, not a complete power-consistent measurement circuit.",
        "Saved actions are not re-optimized; all historical efficiency/policy conclusions remain provisional.", "",
        "## Reproduction and Provenance", "",
        "Run with the environment used for this audit (the imported wrapper requires PyTorch):",
        "```powershell",
        f'& "{result["python_executable"]}" -B "{Path(__file__).resolve()}"',
        "```", "",
        f"All audit checks passed: `{all(result['integrity_checks'].values())}`. Absolute numerical tolerance: 1e-9 in W/V/A.",
        "JSON contains every row, input/source SHA-256 hashes, residuals, feasibility counts and integrity checks.", "",
    ]
    for record in [*result["inputs"].values(), *result["sources"]]:
        lines.append(f"- `{Path(record['path']).name}`: `{record['sha256']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the legacy 600-case AIR56B2 loss-balance audit only")
    parser.add_argument("--fidelity", type=Path, default=REPO / "artifacts/air56b2_fidelity_bundle.json")
    parser.add_argument("--policy", type=Path, default=REPO / "artifacts/air56b2_policy_benchmark.json")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    fidelity_path, policy_path = args.fidelity.resolve(), args.policy.resolve()
    output_dir = args.output_dir.resolve()
    output_paths = [output_dir / "legacy_loss_audit.json", output_dir / "legacy_loss_audit.md"]
    if any(path.resolve() in {fidelity_path, policy_path, *SOURCE_PATHS} for path in output_paths):
        raise ValueError("Audit outputs must not overwrite inputs or sources")
    result = audit(fidelity_path, policy_path)
    json_text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    markdown_text = _markdown(result)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths[0].write_text(json_text, encoding="utf-8")
    output_paths[1].write_text(markdown_text, encoding="ascii")
    print(json.dumps({
        "status": result["status"], "case_count": result["case_count"],
        "outputs": [str(path) for path in output_paths],
        "common_083_shaft_minus_legacy_loss_w": result["summary"]["common_fixed_083"]["shaft_minus_legacy_loss_w"],
        "legacy_neural_dq_residuals": result["summary"]["legacy_neural"]["legacy"],
        "integrity_checks": result["integrity_checks"],
    }, indent=2, allow_nan=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

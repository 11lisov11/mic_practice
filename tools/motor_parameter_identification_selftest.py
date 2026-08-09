#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from motor_identification.schema import CAPTURE_SCHEMA, load_capture, validate_capture  # noqa: E402
from motor_identification.service import identify_motor  # noqa: E402
from motor_identification.synthetic import make_synthetic_bundle  # noqa: E402
from motor_parameter_api import dispatch  # noqa: E402


def _case(name: str, function: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"name": name, "pass": True, "evidence": function()}
    except Exception as exc:
        return {"name": name, "pass": False, "error": f"{type(exc).__name__}: {exc}"}


def _contract_accepts_complete_independent_bundle() -> dict[str, Any]:
    capture, _ = make_synthetic_bundle(seed=101, steps_per_electrical_experiment=96)
    report = validate_capture(capture)
    if not report.passed:
        raise RuntimeError(report.as_dict())
    return report.as_dict()


def _contract_rejects_hardware_without_provenance_and_reused_run() -> dict[str, Any]:
    capture, _ = make_synthetic_bundle(seed=102, steps_per_electrical_experiment=96)
    broken = deepcopy(capture)
    broken["source"] = {"kind": "hardware"}
    fit_run = next(item["run_id"] for item in broken["experiments"] if item["role"] == "fit")
    for experiment in broken["experiments"]:
        if experiment["role"] == "validation":
            experiment["run_id"] = fit_run
    report = validate_capture(broken)
    codes = {item["code"] for item in report.as_dict()["errors"]}
    required = {"hardware_provenance", "calibration_provenance", "truth_leakage", "validation_leakage"}
    if report.passed or not required.issubset(codes):
        raise RuntimeError({"codes": sorted(codes), "required": sorted(required)})
    return {"codes": sorted(codes)}


def _csv_manifest_imports_abc_and_rpm_with_explicit_units() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "run.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            fields = [
                "t_s",
                "v_a_v",
                "v_b_v",
                "v_c_v",
                "i_a_a",
                "i_b_a",
                "i_c_a",
                "omega_rpm",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index in range(64):
                writer.writerow(
                    {
                        "t_s": (index + 1) * 0.001,
                        "v_a_v": 3.0,
                        "v_b_v": -1.5,
                        "v_c_v": -1.5,
                        "i_a_a": 1.0,
                        "i_b_a": -0.5,
                        "i_c_a": -0.5,
                        "omega_rpm": 60.0,
                    }
                )
        manifest = {
            "schema": CAPTURE_SCHEMA,
            "motor_id": "csv-import",
            "experiments": [{"id": "csv", "samples_csv": "run.csv"}],
        }
        manifest_path = root / "capture.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        loaded = load_capture(manifest_path)
        samples = loaded["experiments"][0]["samples"]
        if not math.isclose(samples["v_alpha_v"][0], 3.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise RuntimeError(samples["v_alpha_v"][0])
        if not math.isclose(samples["i_alpha_a"][0], 1.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise RuntimeError(samples["i_alpha_a"][0])
        if not math.isclose(samples["omega_rad_s"][0], 2.0 * math.pi, rel_tol=0.0, abs_tol=1.0e-12):
            raise RuntimeError(samples["omega_rad_s"][0])
        return {"rows": len(samples["t_s"]), "omega_rad_s": samples["omega_rad_s"][0]}


def _rank_gate_blocks_uninformative_excitation() -> dict[str, Any]:
    capture, prior = make_synthetic_bundle(seed=103, steps_per_electrical_experiment=96)
    broken = deepcopy(capture)
    for experiment in broken["experiments"]:
        if experiment["kind"] != "coast":
            count = len(experiment["samples"]["v_alpha_v"])
            experiment["samples"]["v_alpha_v"] = [8.0] * count
            experiment["samples"]["v_beta_v"] = [0.0] * count
    result = identify_motor(broken, prior, starts=1, max_nfev=10)
    if result.get("accepted") is not False or "rank_gate_failed" not in result.get("blockers", []):
        raise RuntimeError({"accepted": result.get("accepted"), "blockers": result.get("blockers")})
    return {"blockers": result["blockers"], "rank": result["rank_gate_prior"]["numerical_rank"]}


def _contract_rejects_reused_validation_samples() -> dict[str, Any]:
    capture, _ = make_synthetic_bundle(seed=105, steps_per_electrical_experiment=96)
    broken = deepcopy(capture)
    fit_by_kind = {
        item["kind"]: item for item in broken["experiments"] if item["role"] == "fit"
    }
    for experiment in broken["experiments"]:
        if experiment["role"] == "validation":
            experiment["samples"] = deepcopy(fit_by_kind[experiment["kind"]]["samples"])
    report = validate_capture(broken)
    codes = {item["code"] for item in report.as_dict()["errors"]}
    if "validation_data_reuse" not in codes:
        raise RuntimeError(sorted(codes))
    return {"codes": sorted(codes)}


def _contract_checks_alpha_beta_current_magnitude() -> dict[str, Any]:
    capture, _ = make_synthetic_bundle(seed=106, steps_per_electrical_experiment=96)
    broken = deepcopy(capture)
    sample = broken["experiments"][0]["samples"]
    sample["i_alpha_a"][0] = 1.3
    sample["i_beta_a"][0] = 1.3
    report = validate_capture(broken)
    codes = {item["code"] for item in report.as_dict()["errors"]}
    if "current_limit" not in codes:
        raise RuntimeError(sorted(codes))
    return {"vector_magnitude_a": math.hypot(1.3, 1.3), "codes": sorted(codes)}


def _end_to_end_recovers_parameters_and_validates_independently() -> dict[str, Any]:
    capture, prior = make_synthetic_bundle(seed=104, steps_per_electrical_experiment=360)
    result = identify_motor(capture, prior, starts=2, seed=55, max_nfev=120)
    if result.get("accepted") is not True:
        raise RuntimeError(result.get("blockers"))
    truth = capture["true_params"]
    estimated = result["estimated_params_si"]
    names = ("Rs_ohm", "Rr_ohm", "Lsigma_h", "Lm_h", "J_kg_m2", "B_nm_s")
    errors = {name: abs(estimated[name] - truth[name]) / truth[name] for name in names}
    if max(errors.values()) >= 0.05:
        raise RuntimeError(errors)
    if result["dataset"]["fit_experiments"] == result["dataset"]["validation_experiments"]:
        raise RuntimeError("validation experiments are not independent")
    if set(result["dataset"]["fit_run_ids"]) & set(result["dataset"]["validation_run_ids"]):
        raise RuntimeError("fit and validation run ids overlap")
    if result["claims"]["hardware_dataset_accepted"] is not False:
        raise RuntimeError("synthetic run was mislabeled as hardware")
    if result["acceptance"]["checks"].get("confidence_interval_width") is not True:
        raise RuntimeError(result.get("confidence_interval_audit"))
    legacy = result["estimated_params"]
    if not math.isclose(legacy["Ls"], estimated["Lm_h"] + estimated["Lsigma_h"], rel_tol=1.0e-12):
        raise RuntimeError("MIC AI legacy inductance mapping is inconsistent")
    return {
        "max_relative_error": max(errors.values()),
        "fit_nrmse": result["fit_metrics"]["normalized_rmse"],
        "validation_nrmse": result["validation_metrics"]["normalized_rmse"],
        "rank": result["rank_gate_fitted"]["numerical_rank"],
        "max_relative_ci_half_width": result["confidence_interval_audit"]["max_relative_half_width"],
    }


def _api_is_analysis_only() -> dict[str, Any]:
    status, payload = dispatch("health", {})
    if status != 200 or payload.get("hardware_commands_enabled") is not False:
        raise RuntimeError(payload)
    status, payload = dispatch("identify", {"capture": {}})
    if status != 400 or payload.get("ok") is not False:
        raise RuntimeError(payload)
    return {"health": "ok", "hardware_commands_enabled": False}


def main() -> int:
    cases = [
        _case("contract_accepts_complete_independent_bundle", _contract_accepts_complete_independent_bundle),
        _case(
            "contract_rejects_hardware_without_provenance_and_reused_run",
            _contract_rejects_hardware_without_provenance_and_reused_run,
        ),
        _case("csv_manifest_imports_abc_and_rpm_with_explicit_units", _csv_manifest_imports_abc_and_rpm_with_explicit_units),
        _case("rank_gate_blocks_uninformative_excitation", _rank_gate_blocks_uninformative_excitation),
        _case("contract_rejects_reused_validation_samples", _contract_rejects_reused_validation_samples),
        _case("contract_checks_alpha_beta_current_magnitude", _contract_checks_alpha_beta_current_magnitude),
        _case(
            "end_to_end_recovers_parameters_and_validates_independently",
            _end_to_end_recovers_parameters_and_validates_independently,
        ),
        _case("api_is_analysis_only", _api_is_analysis_only),
    ]
    failed = [case for case in cases if not case["pass"]]
    summary = {
        "tool": "motor_parameter_identification_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": cases,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

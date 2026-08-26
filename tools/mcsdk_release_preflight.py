#!/usr/bin/env python3
"""Fail-closed release gate for a generated STM32 Motor Control SDK project."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


REQUIRED_PROFILE_FIELDS = (
    "pole_pairs",
    "rated_line_voltage_v",
    "rated_phase_voltage_v",
    "rated_current_a",
    "rated_frequency_hz",
    "rated_speed_rpm",
)
REQUIRED_ARTIFACT_SUFFIXES = (".elf", ".bin", ".hex")
REQUIRED_PROFILE_SOURCE_KIND = "nameplate_and_measurement"
STEVAL_IPM15B_MAX_INPUT_DC_V = 400.0
MEASURED_MODEL_FIELDS = (
    "stator_resistance_ohm",
    "rotor_resistance_ohm",
    "stator_leakage_inductance_h",
    "rotor_leakage_inductance_h",
    "magnetizing_inductance_h",
    "rotor_inertia_kg_m2",
)
MEASURED_MODEL_IOC_KEYS = {
    "stator_resistance_ohm": "M1_RS",
    "rotor_resistance_ohm": "RR",
    "stator_leakage_inductance_h": "LLS",
    "rotor_leakage_inductance_h": "LLR",
    # In Workbench ACIM projects, LMS is the entered magnetizing inductance;
    # LM is a generated 3/2-scaled value used by the control implementation.
    "magnetizing_inductance_h": "LMS",
    "rotor_inertia_kg_m2": "WB_UI_INERTIA",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def find_ioc(project: Path) -> list[Path]:
    return sorted(project.rglob("*.ioc"))


def matching_artifacts(root: Path, suffix: str) -> list[Path]:
    return sorted(path for path in root.rglob(f"*{suffix}") if path.is_file() and path.stat().st_size > 1024)


def coherent_artifact_stems(artifact_map: dict[str, list[Path]]) -> list[str]:
    stem_sets = [{path.stem for path in artifact_map[suffix]} for suffix in REQUIRED_ARTIFACT_SUFFIXES]
    return sorted(set.intersection(*stem_sets)) if stem_sets else []


def profile_errors(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if profile.get("schema") != "mic_ai.mcsdk.acim_motor_profile.v1":
        errors.append("profile_schema")
    if str(profile.get("source_kind", "")).lower() != REQUIRED_PROFILE_SOURCE_KIND:
        errors.append("profile_provenance")
    if str(profile.get("motor_type", "")).lower() not in {"acim", "induction", "asynchronous"}:
        errors.append("motor_type_not_acim")
    motor_label = str(profile.get("motor_label", "")).strip()
    if not motor_label or motor_label.upper().startswith("FILL_"):
        errors.append("profile_motor_label")

    connection = str(profile.get("connection", "")).strip().lower()
    if connection not in {"delta", "d", "star", "y"}:
        errors.append("profile_connection")
    for field in REQUIRED_PROFILE_FIELDS:
        value = profile.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            errors.append(f"profile_{field}")

    if not errors:
        line_voltage = float(profile["rated_line_voltage_v"])
        phase_voltage = float(profile["rated_phase_voltage_v"])
        expected_phase_voltage = line_voltage if connection in {"delta", "d"} else line_voltage / math.sqrt(3.0)
        if abs(phase_voltage - expected_phase_voltage) > max(1.0, expected_phase_voltage * 0.03):
            errors.append("profile_phase_line_connection_inconsistent")

    controller_phase_voltage = profile.get("controller_equivalent_phase_voltage_v")
    if controller_phase_voltage is not None:
        if isinstance(controller_phase_voltage, bool) or not isinstance(controller_phase_voltage, (int, float)) or controller_phase_voltage <= 0:
            errors.append("profile_controller_equivalent_phase_voltage_v")
        elif not errors:
            # MCSDK ACIM V/F uses phase-to-neutral quantities. A physical delta
            # motor is therefore represented by its star-equivalent phase value.
            expected_controller_phase = float(profile["rated_line_voltage_v"]) / math.sqrt(3.0)
            if abs(float(controller_phase_voltage) - expected_controller_phase) > max(1.0, expected_controller_phase * 0.03):
                errors.append("profile_controller_phase_voltage_inconsistent")

    if str(profile.get("source_kind", "")).lower() == REQUIRED_PROFILE_SOURCE_KIND:
        for field in MEASURED_MODEL_FIELDS:
            value = profile.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"profile_measured_{field}")
        evidence = profile.get("measurement_evidence")
        if not isinstance(evidence, dict) or not str(evidence.get("method", "")).strip() or not str(evidence.get("date", "")).strip():
            errors.append("profile_measurement_evidence")
    return errors


def parse_numeric_define(path: Path, macro: str) -> float | None:
    if not path.is_file():
        return None
    match = re.search(
        rf"^\s*#define\s+{re.escape(macro)}\s+([0-9]+(?:\.[0-9]+)?)",
        path.read_text(encoding="utf-8", errors="replace"),
        flags=re.MULTILINE,
    )
    return float(match.group(1)) if match else None


def first_project_file(project: Path, filename: str) -> Path | None:
    return next(iter(sorted(project.rglob(filename))), None)


def parse_ioc_numeric_value(path: Path | None, key: str) -> float | None:
    if path is None or not path.is_file():
        return None
    match = re.search(
        rf"^\s*MotorControl\.{re.escape(key)}=([0-9]+(?:\.[0-9]+)?)\s*$",
        path.read_text(encoding="utf-8", errors="replace"),
        flags=re.MULTILINE,
    )
    return float(match.group(1)) if match else None


def generated_motor_configuration_errors(project: Path, profile: dict[str, Any]) -> dict[str, Any]:
    """Compare the declared real motor to the generated MCSDK constants.

    The profile is intentionally separate from MCSDK generation. Without this
    comparison, a valid nameplate JSON could incorrectly approve an old
    Siemens binary.
    """
    acim_path = first_project_file(project, "acim_motor_parameters.h")
    drive_path = first_project_file(project, "drive_parameters.h")
    power_path = first_project_file(project, "power_stage_parameters.h")
    ioc_path = next(iter(find_ioc(project)), None)
    measured_values = {
        field: parse_ioc_numeric_value(ioc_path, ioc_key)
        for field, ioc_key in MEASURED_MODEL_IOC_KEYS.items()
    }
    values = {
        "pole_pairs": parse_numeric_define(acim_path, "POLE_PAIR_NUM") if acim_path else None,
        "rated_phase_voltage_v": parse_numeric_define(acim_path, "NOMINAL_PHASE_VOLTAGE") if acim_path else None,
        "max_speed_rpm": parse_numeric_define(drive_path, "MAX_APPLICATION_SPEED_RPM") if drive_path else None,
        "nominal_bus_voltage_v": parse_numeric_define(power_path, "NOMINAL_BUS_VOLTAGE_V") if power_path else None,
        "files": {
            "acim_motor_parameters": str(acim_path) if acim_path else "",
            "drive_parameters": str(drive_path) if drive_path else "",
            "power_stage_parameters": str(power_path) if power_path else "",
            "ioc": str(ioc_path) if ioc_path else "",
        },
        "measured_model": measured_values,
    }
    errors: list[str] = []
    if any(values[key] is None for key in ("pole_pairs", "rated_phase_voltage_v", "max_speed_rpm", "nominal_bus_voltage_v")):
        errors.append("config_motor_constants_missing")
        return {"errors": errors, "values": values, "required_dc_bus_v": None}

    profile_pole_pairs = float(profile["pole_pairs"])
    profile_phase_voltage = float(profile.get("controller_equivalent_phase_voltage_v", profile["rated_phase_voltage_v"]))
    profile_speed = float(profile["rated_speed_rpm"])
    connection = str(profile["connection"]).strip().lower()
    line_voltage = float(profile["rated_line_voltage_v"])
    required_dc_bus_v = math.sqrt(2.0) * line_voltage

    if abs(float(values["pole_pairs"]) - profile_pole_pairs) > 0.01:
        errors.append("config_pole_pairs")
    if abs(float(values["rated_phase_voltage_v"]) - profile_phase_voltage) > 1.0:
        errors.append("config_winding_voltage")
    if float(values["max_speed_rpm"]) < profile_speed or float(values["max_speed_rpm"]) > profile_speed * 1.10:
        errors.append("config_speed_limit")
    if float(values["nominal_bus_voltage_v"]) + 2.0 < required_dc_bus_v:
        errors.append("config_dc_bus_too_low")
    if required_dc_bus_v > STEVAL_IPM15B_MAX_INPUT_DC_V:
        errors.append("profile_dc_bus_exceeds_steval_ipm15b")

    if str(profile.get("source_kind", "")).lower() == REQUIRED_PROFILE_SOURCE_KIND:
        missing_measured = [field for field, value in measured_values.items() if value is None]
        if missing_measured:
            errors.append("config_measured_motor_parameters_missing")
        mismatches = {
            field: {
                "profile": float(profile[field]),
                "ioc": value,
            }
            for field, value in measured_values.items()
            if value is not None
            and abs(float(value) - float(profile[field])) > max(1e-6, abs(float(profile[field])) * 0.03)
        }
        if mismatches:
            errors.append("config_measured_motor_parameters_mismatch")
            values["measured_model_mismatches"] = mismatches

    values["profile_connection"] = connection
    return {"errors": errors, "values": values, "required_dc_bus_v": required_dc_bus_v}


def inspect(project: Path, profile_path: Path, artifacts: Path) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}

    def record(name: str, ok: bool, evidence: Any) -> None:
        checks[name] = {"pass": bool(ok), "evidence": evidence}

    record("project_directory", project.is_dir(), str(project))
    ioc_files = find_ioc(project) if project.is_dir() else []
    record("cube_ioc_present", bool(ioc_files), [str(path) for path in ioc_files])

    ioc_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in ioc_files)
    expected_mcu = "STM32G431RB" in ioc_text.upper()
    record("target_is_nucleo_g431rb", expected_mcu, "STM32G431RB" if expected_mcu else "not found")

    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in project.rglob("*")
        if path.is_file() and path.suffix.lower() in {".c", ".cpp", ".h", ".ioc", ".xml", ".json", ".ftl"}
    ) if project.is_dir() else ""
    source_upper = source_text.upper()
    topology_markers = {
        # The official IPM15B examples name the Nucleo control board, but do
        # not embed the IHM09M2 adapter designation in generated sources.
        "IHM09M2_or_NUCLEO_G431RB": (
            "IHM09M2" in source_upper or "NUCLEO-G431RB" in source_upper
        ),
        "IPM15B": "IPM15B" in source_upper,
        "ACIM": "ACIM" in source_upper,
    }
    record("mcsdk_topology_markers", all(topology_markers.values()), topology_markers)

    # The supplied MIC_AI.pdf includes an external precharge relay. Do not allow
    # a motor-release result until the Nucleo application explicitly declares
    # an implemented interlock; a UART command or a relay driver on an obsolete
    # Blue Pill is not an interlock for this target.
    precharge_interlock = bool(re.search(
        r"^\s*#define\s+MIC_PRECHARGE_INTERLOCK_IMPLEMENTED\s+1\b",
        source_text,
        flags=re.MULTILINE,
    ))
    record("precharge_interlock_implemented", precharge_interlock, {
        "required_define": "#define MIC_PRECHARGE_INTERLOCK_IMPLEMENTED 1",
        "note": "Must be added only with a real Nucleo relay output, bus-ready threshold, fault/E-stop opening path, and HIL evidence.",
    })

    record("motor_profile_present", profile_path.is_file(), str(profile_path))
    profile: dict[str, Any] = {}
    profile_error = ""
    if profile_path.is_file():
        try:
            profile = read_json(profile_path)
        except (OSError, json.JSONDecodeError) as exc:
            profile_error = str(exc)
    errors = profile_errors(profile) if not profile_error and profile else ["profile_unreadable"]
    record("motor_profile_is_real_acim", not errors, {"errors": errors, "source_kind": profile.get("source_kind", "") if profile else profile_error})

    configuration = generated_motor_configuration_errors(project, profile) if not errors else {
        "errors": ["profile_invalid"],
        "values": {},
        "required_dc_bus_v": None,
    }
    record(
        "generated_motor_configuration_matches_profile",
        not configuration["errors"],
        configuration,
    )

    artifact_paths = {suffix: matching_artifacts(artifacts, suffix) for suffix in REQUIRED_ARTIFACT_SUFFIXES}
    artifact_map = {
        suffix: [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in paths
        ]
        for suffix, paths in artifact_paths.items()
    }
    record("release_artifacts", all(artifact_map.values()), artifact_map)
    release_stems = coherent_artifact_stems(artifact_paths)
    record("release_artifacts_are_one_build", bool(release_stems), release_stems)

    failures = [name for name, check in checks.items() if not check["pass"]]
    return {
        "tool": "mcsdk_release_preflight",
        "pass": not failures,
        "project": str(project),
        "artifacts": str(artifacts),
        "motor_profile": str(profile_path),
        "motor_profile_sha256": sha256(profile_path) if profile_path.is_file() else "",
        "failed_checks": failures,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an MCSDK ACIM release before treating it as a flashable firmware package.")
    parser.add_argument("--project", required=True, type=Path, help="Root of the generated STM32CubeIDE/MCSDK project")
    parser.add_argument("--motor-profile", required=True, type=Path, help="Measured/nameplate ACIM profile JSON")
    parser.add_argument("--artifacts", type=Path, help="Directory containing the generated ELF/BIN/HEX files; defaults to project root")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    project = args.project.resolve()
    artifacts = (args.artifacts or args.project).resolve()
    report = inspect(project, args.motor_profile.resolve(), artifacts)
    try:
        artifacts.relative_to(project)
        artifacts_inside_project = True
    except ValueError:
        artifacts_inside_project = False
    report["checks"]["artifacts_inside_project"] = {
        "pass": artifacts_inside_project,
        "evidence": {"project": str(project), "artifacts": str(artifacts)},
    }
    if not artifacts_inside_project:
        report["failed_checks"].append("artifacts_inside_project")
        report["pass"] = False
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

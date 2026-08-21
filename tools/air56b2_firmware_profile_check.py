#!/usr/bin/env python3
"""Check that the AIR56B2 profile stays coherent across both firmware projects."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


EXPECTED_PROFILE_KIND = "nameplate_verified_vf_open_loop_pending_identification"
EXPECTED_LINE_VOLTAGE_V = 220.0
EXPECTED_CURRENT_A = 1.24
EXPECTED_FREQUENCY_HZ = 50.0
EXPECTED_POLE_PAIRS = 1.0
EXPECTED_RATED_SPEED_RPM = 2720.0
EXPECTED_COMMAND_SPEED_RPM = 3000.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_text(path: Path, errors: list[str], label: str) -> str:
    if not path.is_file():
        errors.append(f"missing:{label}:{path}")
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    text = read_text(path, errors, label)
    if not text:
        return {}
    try:
        value = json.loads(text.lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid_json:{label}:{exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"invalid_json_object:{label}")
        return {}
    return value


def ioc_value(text: str, key: str, errors: list[str]) -> str:
    match = re.search(rf"(?m)^MotorControl\.{re.escape(key)}=(.+?)\s*$", text)
    if match is None:
        errors.append(f"ioc_missing:{key}")
        return ""
    return match.group(1).strip()


def define_number(text: str, name: str, errors: list[str]) -> float | None:
    match = re.search(
        rf"(?m)^#define\s+{re.escape(name)}\s+.*?(-?[0-9]+(?:\.[0-9]+)?)",
        text,
    )
    if match is None:
        errors.append(f"header_missing:{name}")
        return None
    return float(match.group(1))


def number(value: Any, label: str, errors: list[str]) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"not_numeric:{label}:{value!r}")
        return None


def close(actual: float | None, expected: float, label: str, errors: list[str], tolerance: float = 1e-3) -> None:
    if actual is None:
        return
    if abs(actual - expected) > tolerance:
        errors.append(f"mismatch:{label}:expected={expected}:actual={actual}")


def check_profile(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = str(profile.get("motor_label", ""))
    if "AIR56B2" not in label.upper():
        errors.append("profile_motor_not_air56b2")
    if str(profile.get("source_kind", "")) != EXPECTED_PROFILE_KIND:
        errors.append("profile_kind_not_nameplate_vf_candidate")
    if str(profile.get("connection", "")).lower() != "delta":
        errors.append("profile_connection_not_delta")

    line_voltage = number(profile.get("rated_line_voltage_v"), "rated_line_voltage_v", errors)
    winding_voltage = number(profile.get("rated_phase_voltage_v"), "rated_phase_voltage_v", errors)
    controller_voltage = number(
        profile.get("controller_equivalent_phase_voltage_v"),
        "controller_equivalent_phase_voltage_v",
        errors,
    )
    close(line_voltage, EXPECTED_LINE_VOLTAGE_V, "profile_line_voltage_v", errors)
    close(winding_voltage, EXPECTED_LINE_VOLTAGE_V, "profile_delta_winding_voltage_v", errors)
    close(
        controller_voltage,
        EXPECTED_LINE_VOLTAGE_V / math.sqrt(3.0),
        "profile_controller_phase_voltage_v",
        errors,
    )
    close(number(profile.get("rated_current_a"), "rated_current_a", errors), EXPECTED_CURRENT_A, "profile_current_a", errors)
    close(number(profile.get("rated_frequency_hz"), "rated_frequency_hz", errors), EXPECTED_FREQUENCY_HZ, "profile_frequency_hz", errors)
    close(number(profile.get("pole_pairs"), "pole_pairs", errors), EXPECTED_POLE_PAIRS, "profile_pole_pairs", errors)
    close(number(profile.get("rated_speed_rpm"), "rated_speed_rpm", errors), EXPECTED_RATED_SPEED_RPM, "profile_rated_speed_rpm", errors)
    return errors


def check_project(project: Path, profile: dict[str, Any]) -> tuple[list[str], dict[str, float]]:
    errors: list[str] = []
    ioc_files = list(project.glob("*.ioc"))
    if len(ioc_files) != 1:
        return [f"ioc_count:expected=1:actual={len(ioc_files)}"], {}
    ioc_text = read_text(ioc_files[0], errors, "ioc")
    header_text = read_text(project / "Inc" / "acim_motor_parameters.h", errors, "acim_motor_parameters")
    values: dict[str, float] = {}

    name = ioc_value(ioc_text, "M1_MOTOR_NAME", errors)
    if "AIR56B2" not in name.upper():
        errors.append(f"ioc_motor_not_air56b2:{name}")

    ioc_pairs = number(ioc_value(ioc_text, "ACIM_POLE_PAIR_NUM", errors), "ioc_pole_pairs", errors)
    ioc_current = number(ioc_value(ioc_text, "ACIM_NOMINAL_CURRENT", errors), "ioc_nominal_current", errors)
    ioc_phase_voltage = number(ioc_value(ioc_text, "NOMINAL_PHASE_VOLTAGE", errors), "ioc_nominal_phase_voltage", errors)
    ioc_frequency = number(ioc_value(ioc_text, "NOMINAL_FREQ", errors), "ioc_nominal_frequency", errors)
    ioc_flux_k = number(ioc_value(ioc_text, "FLUX_K", errors), "ioc_flux_k", errors)
    ioc_max_speed = number(ioc_value(ioc_text, "ACIM_MAX_APPLICATION_SPEED", errors), "ioc_max_speed", errors)
    ioc_motor_max_speed = number(ioc_value(ioc_text, "M1_MOTOR_MAX_SPEED_RPM", errors), "ioc_motor_max_speed", errors)
    for actual, expected, label in (
        (ioc_pairs, EXPECTED_POLE_PAIRS, "ioc_pole_pairs"),
        (ioc_current, EXPECTED_CURRENT_A, "ioc_current_a"),
        (ioc_phase_voltage, EXPECTED_LINE_VOLTAGE_V / math.sqrt(3.0), "ioc_controller_phase_voltage_v"),
        (ioc_frequency, EXPECTED_FREQUENCY_HZ, "ioc_frequency_hz"),
        (ioc_max_speed, EXPECTED_COMMAND_SPEED_RPM, "ioc_max_speed_rpm"),
        (ioc_motor_max_speed, EXPECTED_COMMAND_SPEED_RPM, "ioc_motor_max_speed_rpm"),
    ):
        close(actual, expected, label, errors, tolerance=1.0 if "voltage" in label else 1e-3)
    if ioc_phase_voltage is not None and ioc_frequency is not None:
        close(
            ioc_flux_k,
            ioc_phase_voltage * math.sqrt(2.0) / (2.0 * math.pi * ioc_frequency),
            "ioc_flux_k",
            errors,
            tolerance=1e-6,
        )

    generated_pairs = define_number(header_text, "POLE_PAIR_NUM", errors)
    generated_current = define_number(header_text, "NOMINAL_CURRENT", errors)
    generated_phase_voltage = define_number(header_text, "NOMINAL_PHASE_VOLTAGE", errors)
    generated_flux_k = define_number(header_text, "FLUX_K", errors)
    generated_frequency = define_number(header_text, "NOMINAL_FREQ", errors)
    generated_max_speed = define_number(header_text, "MOTOR_MAX_SPEED_RPM", errors)
    for actual, expected, label in (
        (generated_pairs, EXPECTED_POLE_PAIRS, "generated_pole_pairs"),
        (generated_current, EXPECTED_CURRENT_A, "generated_current_a"),
        (generated_phase_voltage, EXPECTED_LINE_VOLTAGE_V / math.sqrt(3.0), "generated_controller_phase_voltage_v"),
        (generated_frequency, EXPECTED_FREQUENCY_HZ, "generated_frequency_hz"),
        (generated_max_speed, EXPECTED_COMMAND_SPEED_RPM, "generated_max_speed_rpm"),
    ):
        close(actual, expected, label, errors, tolerance=1.0 if "voltage" in label else 1e-3)
    if generated_phase_voltage is not None and generated_frequency is not None:
        close(
            generated_flux_k,
            generated_phase_voltage * math.sqrt(2.0) / (2.0 * math.pi * generated_frequency),
            "generated_flux_k",
            errors,
            tolerance=1e-6,
        )
    if generated_pairs is not None and generated_max_speed is not None:
        values["nucleo_max_frequency_millihz"] = generated_max_speed * generated_pairs * 1000.0 / 60.0

    profile_phase = number(profile.get("controller_equivalent_phase_voltage_v"), "profile_controller_voltage", errors)
    close(ioc_phase_voltage, profile_phase or 0.0, "ioc_matches_profile_phase_voltage", errors, tolerance=1.0)
    return errors, values


def check_uno_and_adapter(uno_path: Path, nucleo_main: Path) -> list[str]:
    errors: list[str] = []
    uno = read_text(uno_path, errors, "uno_source")
    nucleo = read_text(nucleo_main, errors, "nucleo_adapter")
    if not re.search(r"POLE_PAIRS\s*=\s*1\.0f\s*;", uno):
        errors.append("uno_pole_pairs_not_one")
    if not re.search(r"AIR56B2_RATED_ELECTRICAL_FREQ_HZ\s*=\s*50\.0f\s*;", uno):
        errors.append("uno_rated_frequency_not_50hz")
    if len(re.findall(r"clampf\(f,\s*0\.0f,\s*AIR56B2_MAX_ELECTRICAL_FREQ_HZ\)", uno)) != 2:
        errors.append("uno_set_freq_not_limited_in_both_command_paths")
    if not re.search(r"bp_freq_millihz.*?clampf\(freq_hz,\s*0\.0f,\s*AIR56B2_MAX_ELECTRICAL_FREQ_HZ\)", uno, flags=re.DOTALL):
        errors.append("uno_transport_frequency_not_limited")
    if not re.search(r"MOTOR_MAX_SPEED_RPM.*?POLE_PAIR_NUM.*?1000U.*?/\s*60U", nucleo, flags=re.DOTALL):
        errors.append("nucleo_frequency_limit_not_derived_from_motor_profile")
    if not re.search(r"frequency_millihz\s*>\s*max_frequency_millihz", nucleo):
        errors.append("nucleo_does_not_reject_overfrequency")
    if not re.search(r"MC_ProgramSpeedRampMotor1", nucleo):
        errors.append("nucleo_does_not_apply_scalar_speed")
    return errors


def check_manifest(artifacts: Path) -> list[str]:
    errors: list[str] = []
    manifest = read_json(artifacts / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json", errors, "nucleo_manifest")
    if "AIR56B2" not in str(manifest.get("reference_motor", "")).upper():
        errors.append("manifest_motor_not_air56b2")
    if str(manifest.get("ioc_motor_name", "")).upper() != "IEK_AIR56B2_D":
        errors.append("manifest_ioc_motor_name")
    for key, expected in (
        ("ioc_nominal_phase_voltage_v", 127.0),
        ("ioc_nominal_current_a", EXPECTED_CURRENT_A),
        ("ioc_pole_pairs", EXPECTED_POLE_PAIRS),
    ):
        close(number(manifest.get(key), f"manifest_{key}", errors), expected, f"manifest_{key}", errors)
    entries = manifest.get("artifacts")
    if not isinstance(entries, list):
        return errors + ["manifest_artifacts_missing"]
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            errors.append("manifest_artifact_entry_invalid")
            continue
        path = artifacts / entry["file"]
        if not path.is_file() or entry.get("bytes") != path.stat().st_size or entry.get("sha256") != sha256(path):
            errors.append(f"manifest_artifact_mismatch:{entry['file']}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Validate AIR56B2 values across MCSDK, UNO Q and built artifacts.")
    parser.add_argument("--project", type=Path, default=root / "mcsdk_reference" / "AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV")
    parser.add_argument("--profile", type=Path, default=root / "docs" / "mcsdk_acim_motor_profile.iek_air56b2_nameplate_verified_vf.json")
    parser.add_argument("--uno", type=Path, default=root / "UNOQ_MOTOR" / "UNOQ_MOTOR.ino")
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()

    project = args.project.resolve()
    artifacts = (args.artifacts or project / "STM32CubeIDE" / "Debug").resolve()
    profile_errors: list[str] = []
    profile = read_json(args.profile.resolve(), profile_errors, "profile")
    project_errors, derived = check_project(project, profile)
    checks = {
        "profile": profile_errors + check_profile(profile),
        "mcsdk_project": project_errors,
        "uno_and_uart_adapter": check_uno_and_adapter(args.uno.resolve(), project / "Src" / "main.c"),
        "build_manifest": check_manifest(artifacts),
    }
    failed = [name for name, errors in checks.items() if errors]
    report = {
        "tool": "air56b2_firmware_profile_check",
        "pass": not failed,
        "project": str(project),
        "profile": str(args.profile.resolve()),
        "uno": str(args.uno.resolve()),
        "artifacts": str(artifacts),
        "derived": derived,
        "checks": checks,
        "failed_checks": failed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

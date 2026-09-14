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
IPM_SD_BKIN_EVIDENCE_SCHEMA = "mic_ai.ipm_sd_bkin_hil.v1"
IPM_SD_BKIN_REQUIRED_CHECKS = (
    "sd_normal_high",
    "sd_forced_low",
    "all_six_pwm_inactive_on_trip",
    "mc_fault_latched",
    "pwm_stays_inactive_after_sd_release",
    "explicit_clear_and_rearm_required",
)
PROFILE_NUMERIC_LIMITS = {
    "pole_pairs": (1.0, 32.0),
    "rated_line_voltage_v": (10.0, 1000.0),
    "rated_phase_voltage_v": (5.0, 1000.0),
    "rated_current_a": (0.01, 1000.0),
    "rated_frequency_hz": (1.0, 1000.0),
    "rated_speed_rpm": (1.0, 100000.0),
}
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


def ipm_sd_bkin_evidence_errors(
    evidence_path: Path | None,
    artifact_paths: dict[str, list[Path]],
) -> dict[str, Any]:
    """Validate a low-voltage physical trip report against this exact build."""
    evidence: dict[str, Any] = {}
    errors: list[str] = []
    if evidence_path is None or not evidence_path.is_file():
        return {
            "errors": ["evidence_missing"],
            "path": str(evidence_path) if evidence_path else "",
        }
    try:
        evidence = read_json(evidence_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"errors": ["evidence_unreadable"], "path": str(evidence_path), "detail": str(exc)}

    if evidence.get("schema") != IPM_SD_BKIN_EVIDENCE_SCHEMA:
        errors.append("evidence_schema")
    if evidence.get("pass") is not True:
        errors.append("evidence_not_passing")
    if evidence.get("power_stage") != "STEVAL-IPM15B":
        errors.append("evidence_power_stage")
    if evidence.get("adapter") != "X-NUCLEO-IHM09M2":
        errors.append("evidence_adapter")
    if evidence.get("mcu") != "STM32G431RBT6":
        errors.append("evidence_mcu")
    if not str(evidence.get("tested_at", "")).strip():
        errors.append("evidence_tested_at")
    if not str(evidence.get("operator", "")).strip():
        errors.append("evidence_operator")

    conditions = evidence.get("conditions")
    required_conditions = (
        "mains_disconnected",
        "dc_bus_below_2v",
        "j7_disconnected",
        "motor_disconnected",
        "auxiliary_vcc_only",
    )
    if not isinstance(conditions, dict):
        errors.append("evidence_conditions")
    else:
        for condition in required_conditions:
            if conditions.get(condition) is not True:
                errors.append(f"evidence_condition_{condition}")

    checks = evidence.get("checks")
    if not isinstance(checks, dict):
        errors.append("evidence_checks")
    else:
        for check in IPM_SD_BKIN_REQUIRED_CHECKS:
            if checks.get(check) is not True:
                errors.append(f"evidence_check_{check}")

    expected_hex_hashes = {sha256(path) for path in artifact_paths.get(".hex", [])}
    reported_hex_hash = str(evidence.get("nucleo_hex_sha256", "")).strip().upper()
    if not reported_hex_hash or reported_hex_hash not in expected_hex_hashes:
        errors.append("evidence_nucleo_hex_hash")

    capture = evidence.get("capture")
    capture_result: dict[str, Any] = {}
    if not isinstance(capture, dict) or not str(capture.get("path", "")).strip():
        errors.append("evidence_capture")
    else:
        capture_path = Path(str(capture["path"]))
        if capture_path.is_absolute():
            errors.append("evidence_capture_must_be_relative")
        capture_root = evidence_path.parent.resolve()
        capture_path = (capture_root / capture_path).resolve()
        try:
            capture_path.relative_to(capture_root)
        except ValueError:
            errors.append("evidence_capture_outside_report_directory")
        reported_capture_hash = str(capture.get("sha256", "")).strip().upper()
        capture_result = {"path": str(capture_path), "sha256": reported_capture_hash}
        if not capture_path.is_file() or capture_path.stat().st_size == 0:
            errors.append("evidence_capture_missing")
        elif sha256(capture_path) != reported_capture_hash:
            errors.append("evidence_capture_hash")

    return {
        "errors": errors,
        "path": str(evidence_path),
        "nucleo_hex_sha256": reported_hex_hash,
        "capture": capture_result,
    }


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
        limits = PROFILE_NUMERIC_LIMITS[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not limits[0] <= float(value) <= limits[1]
        ):
            errors.append(f"profile_{field}")
    pole_pairs = profile.get("pole_pairs")
    if (
        isinstance(pole_pairs, (int, float))
        and not isinstance(pole_pairs, bool)
        and math.isfinite(float(pole_pairs))
        and not float(pole_pairs).is_integer()
    ):
        errors.append("profile_pole_pairs_integer")

    if not errors:
        line_voltage = float(profile["rated_line_voltage_v"])
        phase_voltage = float(profile["rated_phase_voltage_v"])
        expected_phase_voltage = line_voltage if connection in {"delta", "d"} else line_voltage / math.sqrt(3.0)
        if abs(phase_voltage - expected_phase_voltage) > max(1.0, expected_phase_voltage * 0.03):
            errors.append("profile_phase_line_connection_inconsistent")

    controller_phase_voltage = profile.get("controller_equivalent_phase_voltage_v")
    if controller_phase_voltage is not None:
        if (
            isinstance(controller_phase_voltage, bool)
            or not isinstance(controller_phase_voltage, (int, float))
            or not math.isfinite(float(controller_phase_voltage))
            or not 5.0 <= float(controller_phase_voltage) <= 1000.0
        ):
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
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 1.0e-12 <= float(value) <= 1.0e6
            ):
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


def inspect(
    project: Path,
    profile_path: Path,
    artifacts: Path,
    ipm_sd_bkin_evidence: Path | None = None,
) -> dict[str, Any]:
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
    control_source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in project.rglob("*")
        if path.is_file() and path.suffix.lower() in {".c", ".cpp", ".h"}
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

    main_path = project / "Src" / "main.c"
    msp_path = project / "Src" / "stm32g4xx_hal_msp.c"
    irq_path = project / "Src" / "stm32g4xx_mc_it.c"
    main_text = main_path.read_text(encoding="utf-8", errors="replace") if main_path.is_file() else ""
    msp_text = msp_path.read_text(encoding="utf-8", errors="replace") if msp_path.is_file() else ""
    irq_text = irq_path.read_text(encoding="utf-8", errors="replace") if irq_path.is_file() else ""
    bkin_static = {
        "pa6_is_tim1_bkin": "PA6.Signal=TIM1_BKIN" in ioc_text,
        "break_enabled": "TIM1.BreakState=TIM_BREAK_ENABLE" in ioc_text,
        "external_break_source_enabled": "TIM1.SourceBRKDigInput=TIM_BREAKINPUTSOURCE_ENABLE" in ioc_text,
        "external_sd_is_active_low": "TIM1.SourceBRKDigInputPolarity=TIM_BREAKINPUTSOURCE_POLARITY_LOW" in ioc_text,
        "automatic_output_disabled": (
            "TIM1.AutomaticOutput=TIM_AUTOMATICOUTPUT_DISABLE" in ioc_text
            and "sBreakDeadTimeConfig.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;" in main_text
        ),
        "pa6_open_drain_pullup": (
            "PA6.GPIO_PuPd=GPIO_PULLUP" in ioc_text
            and "GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;" in msp_text
            and "GPIO_InitStruct.Pull = GPIO_PULLUP;" in msp_text
        ),
        "break_irq_present": (
            "void TIMx_BRK_M1_IRQHandler(void)" in irq_text
            and "LL_TIM_IsActiveFlag_BRK(TIM1)" in irq_text
        ),
    }
    record("ipm_sd_bkin_static_configuration", all(bkin_static.values()), bkin_static)

    uart_separation = {
        "uno_link_usart1_pb6_pb7": all(marker in main_text for marker in (
            "USART1 PB6/PB7 at 115200 8N1",
            "gpio.Pin = GPIO_PIN_6 | GPIO_PIN_7;",
            "gpio.Alternate = GPIO_AF7_USART1;",
            "huart1.Instance = USART1;",
        )),
        "mcsdk_transport_usart2_pa2_pa3": all(marker in source_text for marker in (
            "huart2.Instance = USART2;",
            "PA2     ------> USART2_TX",
            "PA3     ------> USART2_RX",
        )),
    }
    record("uno_and_mcsdk_uart_are_separate", all(uart_separation.values()), uart_separation)

    softstart_configured = bool(re.search(
        r"^\s*#define\s+MIC_EXTERNAL_SOFTSTART_CONFIGURED\s+1\b",
        control_source_text,
        flags=re.MULTILINE,
    ))
    softstart_gpio_disabled = bool(re.search(
        r"^\s*#define\s+MIC_SOFTSTART_GPIO_CONTROLLED\s+0\b",
        control_source_text,
        flags=re.MULTILINE,
    )) and not any(marker in control_source_text for marker in (
        "UNO_PRECHARGE_GPIO",
        "uno_precharge_set",
        "MIC_PRECHARGE_INTERLOCK_IMPLEMENTED",
    ))
    settle_match = re.search(
        r"^\s*#define\s+MIC_EXTERNAL_SOFTSTART_SETTLE_MS\s+(\d+)U?\b",
        control_source_text,
        flags=re.MULTILINE,
    )
    settle_ms = int(settle_match.group(1)) if settle_match else 0
    record("external_softstart_configured", softstart_configured, {
        "required_define": "#define MIC_EXTERNAL_SOFTSTART_CONFIGURED 1",
        "note": "The mains soft-start is autonomous and installed ahead of the rectifier.",
    })
    record("external_softstart_has_no_mcu_control", softstart_gpio_disabled, {
        "required_define": "#define MIC_SOFTSTART_GPIO_CONTROLLED 0",
        "forbidden_markers": ["UNO_PRECHARGE_GPIO", "uno_precharge_set"],
    })
    record("external_softstart_bus_settle_guard", settle_ms >= 3000, {
        "settle_ms": settle_ms,
        "minimum_ms": 3000,
    })
    softstart_hil = bool(re.search(
        r"^\s*#define\s+MIC_EXTERNAL_SOFTSTART_HIL_VALIDATED\s+1\b",
        control_source_text,
        flags=re.MULTILINE,
    ))
    record("external_softstart_hil_validated", softstart_hil, {
        "required_define": "#define MIC_EXTERNAL_SOFTSTART_HIL_VALIDATED 1",
        "note": "Set to 1 only after checking NTC limiting, autonomous bypass timing, DC-bus stability, and restart behavior on the assembled power path.",
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

    bkin_evidence = ipm_sd_bkin_evidence_errors(ipm_sd_bkin_evidence, artifact_paths)
    record(
        "ipm_sd_bkin_hardware_trip_validated",
        not bkin_evidence["errors"],
        bkin_evidence,
    )

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
    parser.add_argument(
        "--ipm-sd-bkin-evidence",
        type=Path,
        help="Passing mic_ai.ipm_sd_bkin_hil.v1 report tied to this HEX and its capture file",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    project = args.project.resolve()
    artifacts = (args.artifacts or args.project).resolve()
    evidence_path = args.ipm_sd_bkin_evidence.resolve() if args.ipm_sd_bkin_evidence else None
    report = inspect(project, args.motor_profile.resolve(), artifacts, evidence_path)
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

#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import mcsdk_release_preflight as gate


def profile(source_kind: str) -> dict:
    return {
        "schema": "mic_ai.mcsdk.acim_motor_profile.v1",
        "source_kind": source_kind,
        "motor_type": "acim",
        "motor_label": "TEST-MOTOR-230V-DELTA",
        "pole_pairs": 2,
        "rated_line_voltage_v": 230.0,
        "rated_phase_voltage_v": 230.0,
        "rated_current_a": 1.0,
        "rated_frequency_hz": 50.0,
        "rated_speed_rpm": 1400.0,
        "connection": "delta",
        "stator_resistance_ohm": 2.85,
        "rotor_resistance_ohm": 0.7,
        "stator_leakage_inductance_h": 0.003,
        "rotor_leakage_inductance_h": 0.003,
        "magnetizing_inductance_h": 0.099,
        "rotor_inertia_kg_m2": 0.001,
        "measurement_evidence": {
            "date": "2026-08-21",
            "method": "test fixture",
            "report_path": "measurement.csv",
        },
    }


def make_project(root: Path) -> None:
    (root / "motor.ioc").write_text(
        "Mcu.Name=STM32G431RBTx\n"
        "Board=NUCLEO-G431RB\n"
        "MotorControl.M1_RS=2.85\n"
        "MotorControl.RR=0.7\n"
        "MotorControl.LLS=0.003\n"
        "MotorControl.LLR=0.003\n"
        "MotorControl.LMS=0.099\n"
        "MotorControl.WB_UI_INERTIA=0.001\n",
        encoding="utf-8",
    )
    (root / "Core").mkdir()
    (root / "Core" / "mcsdk_config.h").write_text(
        "X-NUCLEO-IHM09M2 STEVAL-IPM15B ACIM\n#define MIC_PRECHARGE_INTERLOCK_IMPLEMENTED 1\n",
        encoding="utf-8",
    )
    (root / "acim_motor_parameters.h").write_text(
        "#define POLE_PAIR_NUM 2\n#define NOMINAL_PHASE_VOLTAGE 230\n", encoding="utf-8"
    )
    (root / "drive_parameters.h").write_text("#define MAX_APPLICATION_SPEED_RPM 1500\n", encoding="utf-8")
    (root / "power_stage_parameters.h").write_text("#define NOMINAL_BUS_VOLTAGE_V 325U\n", encoding="utf-8")
    (root / "Release").mkdir()
    for suffix in gate.REQUIRED_ARTIFACT_SUFFIXES:
        (root / "Release" / f"motor{suffix}").write_bytes(b"x" * 2048)


def make_official_style_project(root: Path) -> None:
    (root / "motor.ioc").write_text(
        "Mcu.Name=STM32G431RBTx\n"
        "Board=NUCLEO-G431RB\n"
        "MotorControl.M1_RS=2.85\n"
        "MotorControl.RR=0.7\n"
        "MotorControl.LLS=0.003\n"
        "MotorControl.LLR=0.003\n"
        "MotorControl.LMS=0.099\n"
        "MotorControl.WB_UI_INERTIA=0.001\n",
        encoding="utf-8",
    )
    (root / "Core").mkdir()
    (root / "Core" / "mcsdk_config.h").write_text(
        "STEVAL-IPM15B ACIM\n#define MIC_PRECHARGE_INTERLOCK_IMPLEMENTED 1\n",
        encoding="utf-8",
    )
    (root / "acim_motor_parameters.h").write_text(
        "#define POLE_PAIR_NUM 2\n#define NOMINAL_PHASE_VOLTAGE 230\n", encoding="utf-8"
    )
    (root / "drive_parameters.h").write_text("#define MAX_APPLICATION_SPEED_RPM 1500\n", encoding="utf-8")
    (root / "power_stage_parameters.h").write_text("#define NOMINAL_BUS_VOLTAGE_V 325U\n", encoding="utf-8")
    (root / "Release").mkdir()
    for suffix in gate.REQUIRED_ARTIFACT_SUFFIXES:
        (root / "Release" / f"motor{suffix}").write_bytes(b"x" * 2048)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_project(root)
        profile_path = root / "motor.json"
        profile_path.write_text(json.dumps(profile("nameplate_and_measurement")), encoding="utf-8")
        accepted = gate.inspect(root, profile_path, root / "Release")

        (root / "Release" / "motor.hex").rename(root / "Release" / "other.hex")
        incoherent = gate.inspect(root, profile_path, root / "Release")
        (root / "Release" / "other.hex").rename(root / "Release" / "motor.hex")

        profile_path.write_text(json.dumps(profile("synthetic")), encoding="utf-8")
        rejected = gate.inspect(root, profile_path, root / "Release")

        profile_path.write_text(json.dumps(profile("catalog_reference_unverified")), encoding="utf-8")
        catalog_rejected = gate.inspect(root, profile_path, root / "Release")

        bad_configuration_profile = profile("nameplate_and_measurement")
        bad_configuration_profile["pole_pairs"] = 1
        profile_path.write_text(json.dumps(bad_configuration_profile), encoding="utf-8")
        stale_firmware_rejected = gate.inspect(root, profile_path, root / "Release")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_official_style_project(root)
        profile_path = root / "motor.json"
        profile_path.write_text(json.dumps(profile("nameplate_and_measurement")), encoding="utf-8")
        official_style = gate.inspect(root, profile_path, root / "Release")

    summary = {
        "tool": "mcsdk_release_preflight_selftest",
        "pass": (
            accepted["pass"]
            and not incoherent["pass"]
            and "release_artifacts_are_one_build" in incoherent["failed_checks"]
            and not rejected["pass"]
            and "motor_profile_is_real_acim" in rejected["failed_checks"]
            and not catalog_rejected["pass"]
            and "motor_profile_is_real_acim" in catalog_rejected["failed_checks"]
            and not stale_firmware_rejected["pass"]
            and "generated_motor_configuration_matches_profile" in stale_firmware_rejected["failed_checks"]
            and official_style["pass"]
        ),
        "accepted_project": accepted["pass"],
        "mixed_artifacts_rejected": "release_artifacts_are_one_build" in incoherent["failed_checks"],
        "synthetic_profile_rejected": "motor_profile_is_real_acim" in rejected["failed_checks"],
        "catalog_profile_rejected": "motor_profile_is_real_acim" in catalog_rejected["failed_checks"],
        "stale_firmware_rejected": "generated_motor_configuration_matches_profile" in stale_firmware_rejected["failed_checks"],
        "official_nucleo_ipm15b_topology_accepted": official_style["pass"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

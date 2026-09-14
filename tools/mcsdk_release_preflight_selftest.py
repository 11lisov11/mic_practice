#!/usr/bin/env python3
from __future__ import annotations

import json
import math
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


def make_static_safety_sources(root: Path) -> None:
    source = root / "Src"
    source.mkdir()
    (source / "main.c").write_text(
        "USART1 PB6/PB7 at 115200 8N1\n"
        "gpio.Pin = GPIO_PIN_6 | GPIO_PIN_7;\n"
        "gpio.Alternate = GPIO_AF7_USART1;\n"
        "huart1.Instance = USART1;\n"
        "huart2.Instance = USART2;\n"
        "PA2     ------> USART2_TX\n"
        "PA3     ------> USART2_RX\n"
        "sBreakDeadTimeConfig.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;\n",
        encoding="utf-8",
    )
    (source / "stm32g4xx_hal_msp.c").write_text(
        "GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;\n"
        "GPIO_InitStruct.Pull = GPIO_PULLUP;\n",
        encoding="utf-8",
    )
    (source / "stm32g4xx_mc_it.c").write_text(
        "void TIMx_BRK_M1_IRQHandler(void) {\n"
        "  if (LL_TIM_IsActiveFlag_BRK(TIM1)) {}\n"
        "}\n",
        encoding="utf-8",
    )


def make_project(root: Path) -> None:
    (root / "motor.ioc").write_text(
        "Mcu.Name=STM32G431RBTx\n"
        "Board=NUCLEO-G431RB\n"
        "MotorControl.M1_RS=2.85\n"
        "MotorControl.RR=0.7\n"
        "MotorControl.LLS=0.003\n"
        "MotorControl.LLR=0.003\n"
        "MotorControl.LMS=0.099\n"
        "MotorControl.WB_UI_INERTIA=0.001\n"
        "PA6.Signal=TIM1_BKIN\n"
        "PA6.GPIO_PuPd=GPIO_PULLUP\n"
        "TIM1.BreakState=TIM_BREAK_ENABLE\n"
        "TIM1.SourceBRKDigInput=TIM_BREAKINPUTSOURCE_ENABLE\n"
        "TIM1.SourceBRKDigInputPolarity=TIM_BREAKINPUTSOURCE_POLARITY_LOW\n"
        "TIM1.AutomaticOutput=TIM_AUTOMATICOUTPUT_DISABLE\n",
        encoding="utf-8",
    )
    make_static_safety_sources(root)
    (root / "Core").mkdir()
    (root / "Core" / "mcsdk_config.h").write_text(
        "X-NUCLEO-IHM09M2 STEVAL-IPM15B ACIM\n"
        "#define MIC_EXTERNAL_SOFTSTART_CONFIGURED 1\n"
        "#define MIC_SOFTSTART_GPIO_CONTROLLED 0\n"
        "#define MIC_EXTERNAL_SOFTSTART_HIL_VALIDATED 1\n"
        "#define MIC_EXTERNAL_SOFTSTART_SETTLE_MS 3500U\n",
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
        "MotorControl.WB_UI_INERTIA=0.001\n"
        "PA6.Signal=TIM1_BKIN\n"
        "PA6.GPIO_PuPd=GPIO_PULLUP\n"
        "TIM1.BreakState=TIM_BREAK_ENABLE\n"
        "TIM1.SourceBRKDigInput=TIM_BREAKINPUTSOURCE_ENABLE\n"
        "TIM1.SourceBRKDigInputPolarity=TIM_BREAKINPUTSOURCE_POLARITY_LOW\n"
        "TIM1.AutomaticOutput=TIM_AUTOMATICOUTPUT_DISABLE\n",
        encoding="utf-8",
    )
    make_static_safety_sources(root)
    (root / "Core").mkdir()
    (root / "Core" / "mcsdk_config.h").write_text(
        "STEVAL-IPM15B ACIM\n"
        "#define MIC_EXTERNAL_SOFTSTART_CONFIGURED 1\n"
        "#define MIC_SOFTSTART_GPIO_CONTROLLED 0\n"
        "#define MIC_EXTERNAL_SOFTSTART_HIL_VALIDATED 1\n"
        "#define MIC_EXTERNAL_SOFTSTART_SETTLE_MS 3500U\n",
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


def make_bkin_evidence(root: Path) -> Path:
    capture_dir = root / "captures"
    capture_dir.mkdir(exist_ok=True)
    capture_path = capture_dir / "sd_bkin_trip.csv"
    capture_path.write_bytes(b"time,sd,pwm1h,pwm1l,pwm2h,pwm2l,pwm3h,pwm3l\n" + b"0,1,0,0,0,0,0,0\n" * 80)
    evidence_path = root / "ipm_sd_bkin_hil.json"
    evidence = {
        "schema": gate.IPM_SD_BKIN_EVIDENCE_SCHEMA,
        "pass": True,
        "tested_at": "2026-09-14T00:00:00Z",
        "operator": "selftest",
        "power_stage": "STEVAL-IPM15B",
        "adapter": "X-NUCLEO-IHM09M2",
        "mcu": "STM32G431RBT6",
        "conditions": {
            "mains_disconnected": True,
            "dc_bus_below_2v": True,
            "j7_disconnected": True,
            "motor_disconnected": True,
            "auxiliary_vcc_only": True,
        },
        "checks": {name: True for name in gate.IPM_SD_BKIN_REQUIRED_CHECKS},
        "nucleo_hex_sha256": gate.sha256(root / "Release" / "motor.hex"),
        "capture": {
            "path": "captures/sd_bkin_trip.csv",
            "sha256": gate.sha256(capture_path),
        },
    }
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    return evidence_path


def main() -> int:
    nonfinite_profile = profile("nameplate_and_measurement")
    nonfinite_profile["rated_current_a"] = math.nan
    nonfinite_rejected = "profile_rated_current_a" in gate.profile_errors(nonfinite_profile)
    fractional_profile = profile("nameplate_and_measurement")
    fractional_profile["pole_pairs"] = 1.9
    fractional_rejected = "profile_pole_pairs_integer" in gate.profile_errors(fractional_profile)
    infinite_model_profile = profile("nameplate_and_measurement")
    infinite_model_profile["magnetizing_inductance_h"] = math.inf
    infinite_model_rejected = (
        "profile_measured_magnetizing_inductance_h" in gate.profile_errors(infinite_model_profile)
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_project(root)
        profile_path = root / "motor.json"
        profile_path.write_text(json.dumps(profile("nameplate_and_measurement")), encoding="utf-8")
        evidence_path = make_bkin_evidence(root)
        accepted = gate.inspect(root, profile_path, root / "Release", evidence_path)
        artifact_evidence = accepted["checks"]["release_artifacts"]["evidence"]
        artifacts_are_hashed = all(
            entry["bytes"] == 2048 and len(entry["sha256"]) == 64
            for entries in artifact_evidence.values()
            for entry in entries
        )
        profile_is_hashed = len(accepted["motor_profile_sha256"]) == 64

        missing_bkin_evidence = gate.inspect(root, profile_path, root / "Release")

        capture_path = root / "captures" / "sd_bkin_trip.csv"
        capture_path.write_bytes(capture_path.read_bytes() + b"tampered\n")
        tampered_capture = gate.inspect(root, profile_path, root / "Release", evidence_path)
        evidence_path = make_bkin_evidence(root)

        wrong_hash_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        wrong_hash_payload["nucleo_hex_sha256"] = "0" * 64
        evidence_path.write_text(json.dumps(wrong_hash_payload), encoding="utf-8")
        wrong_firmware_hash = gate.inspect(root, profile_path, root / "Release", evidence_path)
        evidence_path = make_bkin_evidence(root)

        (root / "Release" / "motor.hex").rename(root / "Release" / "other.hex")
        incoherent = gate.inspect(root, profile_path, root / "Release", evidence_path)
        (root / "Release" / "other.hex").rename(root / "Release" / "motor.hex")

        profile_path.write_text(json.dumps(profile("synthetic")), encoding="utf-8")
        rejected = gate.inspect(root, profile_path, root / "Release", evidence_path)

        profile_path.write_text(json.dumps(profile("catalog_reference_unverified")), encoding="utf-8")
        catalog_rejected = gate.inspect(root, profile_path, root / "Release", evidence_path)

        bad_configuration_profile = profile("nameplate_and_measurement")
        bad_configuration_profile["pole_pairs"] = 1
        profile_path.write_text(json.dumps(bad_configuration_profile), encoding="utf-8")
        stale_firmware_rejected = gate.inspect(root, profile_path, root / "Release", evidence_path)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_official_style_project(root)
        profile_path = root / "motor.json"
        profile_path.write_text(json.dumps(profile("nameplate_and_measurement")), encoding="utf-8")
        evidence_path = make_bkin_evidence(root)
        official_style = gate.inspect(root, profile_path, root / "Release", evidence_path)

    summary = {
        "tool": "mcsdk_release_preflight_selftest",
        "pass": (
            accepted["pass"]
            and artifacts_are_hashed
            and profile_is_hashed
            and not incoherent["pass"]
            and "release_artifacts_are_one_build" in incoherent["failed_checks"]
            and not rejected["pass"]
            and "motor_profile_is_real_acim" in rejected["failed_checks"]
            and not catalog_rejected["pass"]
            and "motor_profile_is_real_acim" in catalog_rejected["failed_checks"]
            and not stale_firmware_rejected["pass"]
            and "generated_motor_configuration_matches_profile" in stale_firmware_rejected["failed_checks"]
            and official_style["pass"]
            and not missing_bkin_evidence["pass"]
            and "ipm_sd_bkin_hardware_trip_validated" in missing_bkin_evidence["failed_checks"]
            and not tampered_capture["pass"]
            and "evidence_capture_hash" in tampered_capture["checks"]["ipm_sd_bkin_hardware_trip_validated"]["evidence"]["errors"]
            and not wrong_firmware_hash["pass"]
            and "evidence_nucleo_hex_hash" in wrong_firmware_hash["checks"]["ipm_sd_bkin_hardware_trip_validated"]["evidence"]["errors"]
            and nonfinite_rejected
            and fractional_rejected
            and infinite_model_rejected
        ),
        "accepted_project": accepted["pass"],
        "artifacts_are_hashed": artifacts_are_hashed,
        "profile_is_hashed": profile_is_hashed,
        "mixed_artifacts_rejected": "release_artifacts_are_one_build" in incoherent["failed_checks"],
        "synthetic_profile_rejected": "motor_profile_is_real_acim" in rejected["failed_checks"],
        "catalog_profile_rejected": "motor_profile_is_real_acim" in catalog_rejected["failed_checks"],
        "stale_firmware_rejected": "generated_motor_configuration_matches_profile" in stale_firmware_rejected["failed_checks"],
        "official_nucleo_ipm15b_topology_accepted": official_style["pass"],
        "missing_bkin_hil_rejected": "ipm_sd_bkin_hardware_trip_validated" in missing_bkin_evidence["failed_checks"],
        "tampered_bkin_capture_rejected": "evidence_capture_hash" in tampered_capture["checks"]["ipm_sd_bkin_hardware_trip_validated"]["evidence"]["errors"],
        "wrong_bkin_firmware_hash_rejected": "evidence_nucleo_hex_hash" in wrong_firmware_hash["checks"]["ipm_sd_bkin_hardware_trip_validated"]["evidence"]["errors"],
        "nonfinite_profile_rejected": nonfinite_rejected,
        "fractional_pole_pairs_rejected": fractional_rejected,
        "infinite_measured_model_rejected": infinite_model_rejected,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

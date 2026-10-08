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
        "sBreakInputConfig.Enable = TIM_BREAKINPUTSOURCE_ENABLE;\n"
        "sBreakInputConfig.Polarity = TIM_BREAKINPUTSOURCE_POLARITY_LOW;\n"
        "sBreakDeadTimeConfig.BreakState = TIM_BREAK_ENABLE;\n"
        "sBreakDeadTimeConfig.BreakPolarity = TIM_BREAKPOLARITY_HIGH;\n"
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
        "  if (LL_TIM_IsActiveFlag_BRK(TIM1)) { PWMC_DP_Handler(&PWM_Handle_M1._Super); }\n"
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
        "TIM1.BreakPolarity=TIM_BREAKPOLARITY_HIGH\n"
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
        "TIM1.BreakPolarity=TIM_BREAKPOLARITY_HIGH\n"
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
    lines = ["Time [s],Channel 0,Channel 1,Channel 2,Channel 3,Channel 4,Channel 5,Channel 6",
             "0.000000,0,0,0,0,0,0,1"]
    for cycle in range(5):
        base = cycle * 0.0001
        lines.extend((
            f"{base + 0.000001:.6f},1,0,1,0,1,0,1",
            f"{base + 0.000020:.6f},0,0,0,0,0,0,1",
            f"{base + 0.000025:.6f},0,1,0,1,0,1,1",
            f"{base + 0.000050:.6f},0,0,0,0,0,0,1",
        ))
    lines.extend(("0.000600,0,0,0,0,0,0,0",
                  "0.002000,0,0,0,0,0,0,1",
                  "0.022000,0,0,0,0,0,0,1"))
    capture_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    evidence_path = root / "ipm_sd_bkin_hil.json"
    evidence = {
        "schema": gate.IPM_SD_BKIN_EVIDENCE_SCHEMA,
        "pass": True,
        "tested_at": "2026-09-14T00:00:00Z",
        "operator": "selftest",
        "power_stage": "STEVAL-IPM15B",
        "adapter": "X-NUCLEO-IHM09M2",
        "mcu": "STM32G431RBT6",
        "trip_source": "external_sd_pin",
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

        vf_catalog = profile(gate.VF_CATALOG_SOURCE_KIND)
        for field in gate.MEASURED_MODEL_FIELDS:
            vf_catalog.pop(field)
        vf_catalog.pop("measurement_evidence")
        vf_catalog["source_url"] = "https://cdn-01.iek.ru/media/original/air56b2.pdf"
        vf_catalog["operator_confirmed_model"] = True
        profile_path.write_text(json.dumps(vf_catalog), encoding="utf-8")
        vf_accepted = gate.inspect(root, profile_path, root / "Release", evidence_path, "vf")
        foc_catalog_rejected = gate.inspect(root, profile_path, root / "Release", evidence_path, "foc")
        unconfirmed_vf = dict(vf_catalog, operator_confirmed_model=False)
        profile_path.write_text(json.dumps(unconfirmed_vf), encoding="utf-8")
        vf_unconfirmed_rejected = gate.inspect(root, profile_path, root / "Release", evidence_path, "vf")
        forged_source_vf = dict(vf_catalog, source_url="https://example.com/air56b2.pdf")
        profile_path.write_text(json.dumps(forged_source_vf), encoding="utf-8")
        vf_source_rejected = gate.inspect(root, profile_path, root / "Release", evidence_path, "vf")
        malformed_source_vf = dict(vf_catalog, source_url="https://[invalid/air56b2.pdf")
        profile_path.write_text(json.dumps(malformed_source_vf), encoding="utf-8")
        vf_malformed_source_rejected = gate.inspect(root, profile_path, root / "Release", evidence_path, "vf")
        profile_path.write_text(json.dumps(profile("nameplate_and_measurement")), encoding="utf-8")

        false_capture_path = root / "captures" / "sd_bkin_trip.csv"
        false_capture_path.write_text(
            "Time [s]," + ",".join(f"Channel {index}" for index in range(7)) + "\n"
            + "".join(f"{index * 0.001:.3f},0,0,0,0,0,0,1\n" for index in range(80)),
            encoding="utf-8",
        )
        false_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        false_evidence["capture"]["sha256"] = gate.sha256(false_capture_path)
        evidence_path.write_text(json.dumps(false_evidence), encoding="utf-8")
        all_low_capture_rejected = gate.inspect(root, profile_path, root / "Release", evidence_path)
        evidence_path = make_bkin_evidence(root)

        internal_trip_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        internal_trip_evidence["trip_source"] = "timer_software_bg"
        evidence_path.write_text(json.dumps(internal_trip_evidence), encoding="utf-8")
        internal_trip_rejected = gate.inspect(root, profile_path, root / "Release", evidence_path)
        evidence_path = make_bkin_evidence(root)

        ioc_path = root / "motor.ioc"
        original_ioc = ioc_path.read_text(encoding="utf-8")
        ioc_path.write_text(original_ioc.replace(
            "TIM1.BreakPolarity=TIM_BREAKPOLARITY_HIGH",
            "TIM1.BreakPolarity=TIM_BREAKPOLARITY_LOW"), encoding="utf-8")
        wrong_break_polarity = gate.inspect(root, profile_path, root / "Release", evidence_path)
        ioc_path.write_text(original_ioc, encoding="utf-8")

        irq_path = root / "Src" / "stm32g4xx_mc_it.c"
        original_irq = irq_path.read_text(encoding="utf-8")
        irq_path.write_text(original_irq.replace("PWMC_DP_Handler(", "PWMC_OVP_Handler("), encoding="utf-8")
        wrong_sd_handler = gate.inspect(root, profile_path, root / "Release", evidence_path)
        irq_path.write_text(original_irq, encoding="utf-8")

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
            and vf_accepted["pass"]
            and vf_accepted["control_mode"] == "vf"
            and not foc_catalog_rejected["pass"]
            and "motor_profile_is_real_acim" in foc_catalog_rejected["failed_checks"]
            and "motor_profile_is_catalog_confirmed_acim" in vf_unconfirmed_rejected["failed_checks"]
            and "motor_profile_is_catalog_confirmed_acim" in vf_source_rejected["failed_checks"]
            and "motor_profile_is_catalog_confirmed_acim" in vf_malformed_source_rejected["failed_checks"]
            and not all_low_capture_rejected["pass"]
            and "evidence_capture_no_verified_trip" in all_low_capture_rejected["checks"]["ipm_sd_bkin_hardware_trip_validated"]["evidence"]["errors"]
            and not internal_trip_rejected["pass"]
            and "evidence_trip_source" in internal_trip_rejected["checks"]["ipm_sd_bkin_hardware_trip_validated"]["evidence"]["errors"]
            and not wrong_break_polarity["pass"]
            and not wrong_break_polarity["checks"]["ipm_sd_bkin_static_configuration"]["evidence"]["break_output_polarity_matches_inverted_source"]
            and not wrong_sd_handler["checks"]["ipm_sd_bkin_static_configuration"]["pass"]
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
        "operator_confirmed_catalog_accepted_for_vf_only": vf_accepted["pass"] and not foc_catalog_rejected["pass"],
        "unconfirmed_vf_catalog_rejected": "motor_profile_is_catalog_confirmed_acim" in vf_unconfirmed_rejected["failed_checks"],
        "nonmanufacturer_vf_source_rejected": "motor_profile_is_catalog_confirmed_acim" in vf_source_rejected["failed_checks"],
        "malformed_vf_source_rejected": "motor_profile_is_catalog_confirmed_acim" in vf_malformed_source_rejected["failed_checks"],
        "all_low_capture_rejected": not all_low_capture_rejected["pass"],
        "internal_software_trip_rejected_as_physical_evidence": not internal_trip_rejected["pass"],
        "wrong_break_polarity_rejected": not wrong_break_polarity["pass"],
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

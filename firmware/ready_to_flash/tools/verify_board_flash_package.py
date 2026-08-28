#!/usr/bin/env python3
"""Verify integrity and identity of the MIC_AI board flash package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_FILES = {
    "nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex",
    "nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin",
    "nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf",
    "nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json",
    "uno_q_mcu/UNOQ_MOTOR.ino.elf-zsk.bin",
    "uno_q_mcu/UNOQ_MOTOR.ino.bin",
    "uno_q_mcu/UNOQ_MOTOR.ino.elf",
    "uno_q_mcu/UNOQ_MOTOR.ino.hex",
    "uno_q_mcu/unoq_mcsdk_scalar.build-manifest.json",
    "linux/web_hmi/server.py",
    "linux/web_hmi/requirements.txt",
    "linux/web_hmi/static/index.html",
    "linux/web_hmi/static/app.js",
    "linux/web_hmi/static/style.css",
    "linux/tools/adb_deploy_web_hmi.py",
    "linux/tools/configure_unoq_autonomous_wifi.py",
    "linux/tools/capture_as5600_teacher_dataset.py",
    "tools/flash_mic_ai_boards.ps1",
    "tools/verify_board_flash_package.py",
    "reports/mcsdk_release_preflight.json",
    "FLASHING_RU.md",
    "FIRMWARE_STAGES_RU.md",
    "AUTONOMOUS_WIFI_OPERATION_RU.md",
    "firmware_stages.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    failures: list[str] = []
    manifest_path = root / "flash-package-manifest.json"
    try:
        manifest = load_json(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        manifest = {}
        failures.append(f"manifest_unreadable:{exc}")

    if manifest.get("schema") != "mic_ai.board_flash_package.v1":
        failures.append("manifest_schema")
    identity = manifest.get("identity", {})
    if identity.get("nucleo_mcu") != "STM32G431RBT6":
        failures.append("wrong_nucleo_mcu")
    if identity.get("uno_board") != "Arduino UNO Q":
        failures.append("wrong_uno_board")
    if identity.get("motor_connection") != "220 V delta":
        failures.append("wrong_motor_connection")
    if identity.get("protocol") != "UART v0x02, 115200 8N1":
        failures.append("wrong_protocol")
    if identity.get("rpc_schema") != "UNO Q get-array v2, 78 append-only elements":
        failures.append("wrong_rpc_schema")
    if identity.get("telemetry_api") != "mc_* canonical; bp_* deprecated compatibility aliases":
        failures.append("wrong_telemetry_api")
    if identity.get("supported_motor_modes") != ["VF"]:
        failures.append("wrong_supported_motor_modes")
    if identity.get("uart_topology") != "direct 3.3 V UART; UNO Q GND and Nucleo GND are common HOT_GND = STEVAL J7 DC-":
        failures.append("wrong_uart_topology")
    if identity.get("external_interface_in_hv") != "Wi-Fi only; no USB/ST-Link/Ethernet/HDMI/UART cables":
        failures.append("wrong_hv_external_interface")
    if manifest.get("hardware_validated") is not False:
        failures.append("hardware_validation_must_remain_explicit")
    if manifest.get("active_stage") != "S1_VF_SENSORLESS_FIRST_SPIN":
        failures.append("wrong_active_stage")
    if manifest.get("mcu_controlled_precharge_relay") is not False:
        failures.append("mcu_precharge_relay_must_be_absent")

    entries = manifest.get("artifacts")
    seen: set[str] = set()
    if not isinstance(entries, list):
        failures.append("artifact_list_missing")
        entries = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            failures.append("invalid_artifact_entry")
            continue
        relative = entry["path"].replace("\\", "/")
        seen.add(relative)
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            failures.append(f"artifact_outside_package:{relative}")
            continue
        if not candidate.is_file():
            failures.append(f"artifact_missing:{relative}")
            continue
        if candidate.stat().st_size != entry.get("bytes"):
            failures.append(f"artifact_size:{relative}")
        if sha256(candidate) != entry.get("sha256"):
            failures.append(f"artifact_hash:{relative}")

    for relative in sorted(REQUIRED_FILES - seen):
        failures.append(f"required_artifact_unlisted:{relative}")

    release_path = root / "reports" / "mcsdk_release_preflight.json"
    try:
        release = load_json(release_path)
        expected_open = {
            "external_softstart_hil_validated",
            "motor_profile_is_real_acim",
            "generated_motor_configuration_matches_profile",
        }
        failed_checks = set(release.get("failed_checks", []))
        if release.get("pass") is not False or failed_checks != expected_open:
            failures.append("release_gate_state_is_not_explicit")
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"release_report_unreadable:{exc}")

    report = {
        "tool": "verify_board_flash_package",
        "pass": not failures,
        "package": str(root),
        "artifacts": len(entries),
        "hardware_validated": False,
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

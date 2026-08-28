#!/usr/bin/env python3
"""Static safety checks for the active UNO Q + Nucleo release only."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNO = ROOT / "UNOQ_MOTOR" / "UNOQ_MOTOR.ino"
NUCLEO_MAIN = (
    ROOT
    / "mcsdk_reference"
    / "AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
    / "Src"
    / "main.c"
)
NUCLEO_CONFIG = ROOT / "nucleo_g431_uart_bridge_pio" / "include" / "config.h"
NUCLEO_PROTO = ROOT / "nucleo_g431_uart_bridge_pio" / "include" / "proto.h"
PACKAGE = ROOT / "firmware" / "ready_to_flash"
PACKAGE_MANIFEST = PACKAGE / "flash-package-manifest.json"


def has(source: str, pattern: str) -> bool:
    return re.search(pattern, source, flags=re.MULTILINE | re.DOTALL) is not None


def main() -> int:
    cases: list[dict] = []

    def check(name: str, ok: bool, detail: object = None) -> None:
        cases.append({"name": name, "ok": bool(ok), "detail": detail})

    required = (UNO, NUCLEO_MAIN, NUCLEO_CONFIG, NUCLEO_PROTO, PACKAGE_MANIFEST)
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    check("active_inputs_present", not missing, missing)
    if missing:
        report = {"tool": "nucleo_firmware_safety_check", "pass": False, "cases": cases}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    uno = UNO.read_text(encoding="utf-8", errors="replace")
    main_c = NUCLEO_MAIN.read_text(encoding="utf-8", errors="replace")
    config = NUCLEO_CONFIG.read_text(encoding="utf-8", errors="replace")
    proto = NUCLEO_PROTO.read_text(encoding="utf-8", errors="replace")
    manifest = json.loads(PACKAGE_MANIFEST.read_text(encoding="utf-8-sig"))

    check(
        "active_backend_is_nucleo_mcsdk",
        "static const bool NUCLEO_MCSDK_ACIM_BACKEND = true;" in uno
        and "static const bool USE_EXTERNAL_PWM = true;" in uno
        and "static const bool USE_NUCLEO_UART_FALLBACK = true;" in uno,
    )
    check(
        "uart_contract_matches",
        "static const uint32_t NUCLEO_UART_BAUD = 115200;" in uno
        and "#define UART_BAUD 115200U" in config
        and "static const uint8_t BP_VER = 0x02;" in uno
        and "#define MIC_PROTOCOL_VERSION 0x02U" in config
        and "#define FRAME_LEN 32" in proto,
    )
    check(
        "rpc_v2_is_append_only_and_vf_only",
        "static const uint8_t RPC_SCHEMA_VERSION = 2U;" in uno
        and "mp_tx_array(78);" in uno
        and "mp_tx_int(0);  // RPC index 74: legacy precharge_managed, always false." in uno
        and "mp_tx_int((int32_t)RPC_SCHEMA_VERSION);" in uno
        and "mp_tx_int((int32_t)MC_CAP_VF);" in uno,
    )
    check(
        "mcu_precharge_output_is_disabled",
        "static const bool BP_PRECHARGE_RELAY_PRESENT = false;" in uno
        and "#define MIC_SOFTSTART_GPIO_CONTROLLED 0" in main_c
        and "#define MIC_EXTERNAL_SOFTSTART_CONFIGURED 1" in main_c,
    )
    check(
        "unsupported_foc_fails_closed",
        has(
            uno,
            r"static bool handle_mcfoc_command\(const char \*arg\).*?"
            r"if \(NUCLEO_MCSDK_ACIM_BACKEND\) \{\s*return false;\s*\}",
        ),
    )
    check(
        "telemetry_flags_have_canonical_names",
        "#define RSP_OFF_TELEMETRY_FLAGS 29" in proto
        and "#define TELEMETRY_FLAG_SOFTSTART_READY 0x20" in proto
        and "#define TELEMETRY_FLAG_VBUS_VALID 0x40" in proto
        and "#define TELEMETRY_FLAG_MCSDK_UNITS 0x80" in proto,
    )

    identity = manifest.get("identity", {})
    check(
        "package_identity_is_active_nucleo",
        identity.get("nucleo_mcu") == "STM32G431RBT6"
        and identity.get("supported_motor_modes") == ["VF"]
        and identity.get("rpc_schema") == "UNO Q get-array v2, 78 append-only elements",
        identity,
    )
    legacy_paths = [
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*")
        if path.is_file() and "bluepill" in str(path).lower()
    ]
    check("package_has_no_bluepill_artifacts", not legacy_paths, legacy_paths)
    check(
        "hardware_validation_remains_explicit",
        manifest.get("software_verified") is True and manifest.get("hardware_validated") is False,
        {
            "software_verified": manifest.get("software_verified"),
            "hardware_validated": manifest.get("hardware_validated"),
        },
    )

    report = {
        "tool": "nucleo_firmware_safety_check",
        "profile": "active-nucleo-only",
        "pass": all(case["ok"] for case in cases),
        "cases": cases,
        "legacy_bluepill_sources_read": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

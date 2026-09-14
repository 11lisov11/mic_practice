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
NUCLEO_ROOT = NUCLEO_MAIN.parents[1]
NUCLEO_IOC = NUCLEO_ROOT / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.ioc"
NUCLEO_MSP = NUCLEO_ROOT / "Src" / "stm32g4xx_hal_msp.c"
NUCLEO_IRQ = NUCLEO_ROOT / "Src" / "stm32g4xx_mc_it.c"
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

    required = (
        UNO,
        NUCLEO_MAIN,
        NUCLEO_IOC,
        NUCLEO_MSP,
        NUCLEO_IRQ,
        NUCLEO_CONFIG,
        NUCLEO_PROTO,
        PACKAGE_MANIFEST,
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    check("active_inputs_present", not missing, missing)
    if missing:
        report = {"tool": "nucleo_firmware_safety_check", "pass": False, "cases": cases}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    uno = UNO.read_text(encoding="utf-8", errors="replace")
    main_c = NUCLEO_MAIN.read_text(encoding="utf-8", errors="replace")
    ioc = NUCLEO_IOC.read_text(encoding="utf-8", errors="replace")
    msp = NUCLEO_MSP.read_text(encoding="utf-8", errors="replace")
    irq = NUCLEO_IRQ.read_text(encoding="utf-8", errors="replace")
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
        "uno_uart_is_separate_from_mcsdk_uart",
        all(marker in main_c for marker in (
            "USART1 PB6/PB7 at 115200 8N1",
            "gpio.Pin = GPIO_PIN_6 | GPIO_PIN_7;",
            "gpio.Alternate = GPIO_AF7_USART1;",
            "huart1.Instance = USART1;",
            "huart2.Instance = USART2;",
        ))
        and "PA2     ------> USART2_TX" in msp
        and "PA3     ------> USART2_RX" in msp,
        {
            "uno_link": "USART1 PB6/PB7",
            "mcsdk_transport": "USART2 PA2/PA3",
        },
    )
    check(
        "ipm_sd_bkin_is_fail_closed",
        all(marker in ioc for marker in (
            "PA6.Signal=TIM1_BKIN",
            "PA6.GPIO_PuPd=GPIO_PULLUP",
            "TIM1.BreakState=TIM_BREAK_ENABLE",
            "TIM1.SourceBRKDigInput=TIM_BREAKINPUTSOURCE_ENABLE",
            "TIM1.SourceBRKDigInputPolarity=TIM_BREAKINPUTSOURCE_POLARITY_LOW",
            "TIM1.AutomaticOutput=TIM_AUTOMATICOUTPUT_DISABLE",
        ))
        and "GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;" in msp
        and "void TIMx_BRK_M1_IRQHandler(void)" in irq
        and "LL_TIM_IsActiveFlag_BRK(TIM1)" in irq,
    )
    check(
        "rpc_v3_is_append_only_and_vf_only",
        "static const uint8_t RPC_SCHEMA_VERSION = 3U;" in uno
        and "mp_tx_array(79);" in uno
        and "mp_tx_int(0);  // RPC index 74: legacy precharge_managed, always false." in uno
        and "mp_tx_int((int32_t)RPC_SCHEMA_VERSION);" in uno
        and "mp_tx_int((int32_t)MC_CAP_VF);" in uno
        and "RPC index 78: Nucleo firmware identity" in uno,
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
        and "#define TELEMETRY_FLAG_MCSDK_UNITS 0x80" in proto
        and "#define TELEMETRY_FLAG_FW_BUILD_VALID 0x10" in proto
        and "#define MIC_NUCLEO_FW_BUILD_ID 2026091401UL" in main_c
        and "UNO_TELEMETRY_FW_BUILD_VALID" in main_c,
    )
    check(
        "clear_handshake_is_uart_rate_limited",
        has(
            uno,
            r"if \(!force && \(enable \|\| g_clear_fault_req\).*?"
            r"g_nucleo_waiting_rsp.*?NUCLEO_RUN_REPLY_GUARD_US.*?"
            r"if \(!force && \(enable \|\| g_clear_fault_req\).*?min_send_us",
        ),
    )

    identity = manifest.get("identity", {})
    check(
        "package_identity_is_active_nucleo",
        identity.get("nucleo_mcu") == "STM32G431RBT6"
        and identity.get("supported_motor_modes") == ["VF"]
        and identity.get("rpc_schema") == "UNO Q get-array v3, 79 append-only elements",
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
        manifest.get("software_verified") is True
        and manifest.get("hardware_validated") is False
        and set(manifest.get("open_release_checks", [])).issubset({
                "external_softstart_hil_validated",
                "ipm_sd_bkin_hardware_trip_validated",
                "motor_profile_is_real_acim",
                "generated_motor_configuration_matches_profile",
            }),
        {
            "software_verified": manifest.get("software_verified"),
            "hardware_validated": manifest.get("hardware_validated"),
            "ipm_sd_bkin_hardware_trip_validated": manifest.get("ipm_sd_bkin_hardware_trip_validated"),
            "open_release_checks": manifest.get("open_release_checks"),
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

#!/usr/bin/env python3
"""Static and protocol-vector checks for the UNO Q to Nucleo MCSDK adapter."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FRAME_LEN = 32
PROTOCOL_VERSION = 0x02
FLAG_ENABLE = 0x01
FLAG_ESTOP = 0x02
FLAG_CLEAR = 0x08
MODE_OFF = 0
MODE_SCALAR = 3


def _xor(frame: bytes | bytearray) -> int:
    value = 0
    for byte in frame[: FRAME_LEN - 1]:
        value ^= byte
    return value


def classify_frame(frame: bytes | bytearray) -> str:
    if len(frame) != FRAME_LEN:
        return "invalid_length"
    if frame[0:2] != b"\xAA\x55":
        return "invalid_header"
    if frame[2] != PROTOCOL_VERSION:
        return "invalid_version"
    if frame[FRAME_LEN - 1] != _xor(frame):
        return "invalid_crc"
    if frame[3] == FLAG_CLEAR and frame[4] == MODE_OFF:
        return "clear" if all(byte == 0 for byte in frame[6:31]) else "invalid_clear"
    if frame[3] & FLAG_ESTOP:
        return "estop"
    if any(byte != 0 for byte in frame[14:31]):
        return "invalid_service"
    if frame[3] == 0 and frame[4] == MODE_OFF:
        return "stop"
    if frame[3] != FLAG_ENABLE or frame[4] != MODE_SCALAR:
        return "invalid_mode"
    if int.from_bytes(frame[6:10], "little") == 0:
        return "invalid_frequency"
    return "scalar"


def make_frame(*, flags: int, mode: int, frequency_millihz: int = 0, service: bool = False) -> bytearray:
    frame = bytearray(FRAME_LEN)
    frame[0:2] = b"\xAA\x55"
    frame[2] = PROTOCOL_VERSION
    frame[3] = flags
    frame[4] = mode
    frame[5] = 0x2A
    frame[6:10] = frequency_millihz.to_bytes(4, "little")
    # This is the historic amplitude field. The Nucleo adapter intentionally ignores it.
    frame[10:14] = (0x1234).to_bytes(4, "little")
    if service:
        frame[14] = 1
    frame[-1] = _xor(frame)
    return frame


def vector_errors() -> list[str]:
    cases: list[tuple[str, bytearray, str]] = [
        ("scalar", make_frame(flags=FLAG_ENABLE, mode=MODE_SCALAR, frequency_millihz=5000), "scalar"),
        ("stop", make_frame(flags=0, mode=MODE_OFF), "stop"),
        ("estop", make_frame(flags=FLAG_ESTOP, mode=MODE_OFF), "estop"),
        ("service", make_frame(flags=FLAG_ENABLE, mode=MODE_SCALAR, frequency_millihz=5000, service=True), "invalid_service"),
        ("duty", make_frame(flags=FLAG_ENABLE, mode=2, frequency_millihz=5000), "invalid_mode"),
        ("zero_frequency", make_frame(flags=FLAG_ENABLE, mode=MODE_SCALAR), "invalid_frequency"),
    ]
    clear = make_frame(flags=FLAG_CLEAR, mode=MODE_OFF)
    clear[10:14] = b"\0\0\0\0"
    clear[-1] = _xor(clear)
    cases.append(("clear", clear, "clear"))
    bad_crc = make_frame(flags=FLAG_ENABLE, mode=MODE_SCALAR, frequency_millihz=5000)
    bad_crc[-1] ^= 0xFF
    cases.append(("bad_crc", bad_crc, "invalid_crc"))
    wrong_version = make_frame(flags=FLAG_ENABLE, mode=MODE_SCALAR, frequency_millihz=5000)
    wrong_version[2] = 0x01
    wrong_version[-1] = _xor(wrong_version)
    cases.append(("wrong_version", wrong_version, "invalid_version"))
    return [f"vector:{name}:{classify_frame(frame)}" for name, frame, expected in cases if classify_frame(frame) != expected]


def require(text: str, pattern: str, name: str, errors: list[str]) -> None:
    if not re.search(pattern, text, flags=re.MULTILINE | re.DOTALL):
        errors.append(name)


def user_code_section(text: str) -> str:
    match = re.search(r"/\* USER CODE BEGIN 0 \*/(.*?)/\* USER CODE END 0 \*/", text, flags=re.DOTALL)
    return match.group(1) if match else ""


def source_errors(
    uno_path: Path, nucleo_path: Path, expected_pole_pairs: float | None = None
) -> list[str]:
    errors: list[str] = []
    if not uno_path.is_file():
        return [f"missing_uno_source:{uno_path}"]
    if not nucleo_path.is_file():
        return [f"missing_nucleo_source:{nucleo_path}"]

    uno = uno_path.read_text(encoding="utf-8", errors="replace")
    nucleo = nucleo_path.read_text(encoding="utf-8", errors="replace")
    user_code = user_code_section(nucleo)

    for pattern, name in (
        (r"NUCLEO_MCSDK_ACIM_BACKEND\s*=\s*true", "uno_mcsdk_backend_disabled"),
        (r"USE_EXTERNAL_PWM\s*=\s*true", "uno_external_uart_bridge_disabled"),
        (r"USE_NUCLEO_SPI\s*=\s*false", "uno_spi_must_be_disabled"),
        (r"USE_NUCLEO_UART_FALLBACK\s*=\s*true", "uno_uart_bridge_disabled"),
        (r"BP_VER\s*=\s*0x02", "uno_protocol_version_not_v2"),
        (r"if\s*\(rx\[2\]\s*!=\s*BP_VER\)\s*return false", "uno_does_not_validate_reply_version"),
        (r"if\s*\(g_io_test_mode\)\s*\{\s*enable_eff\s*=\s*false", "uno_io_test_can_drive_mcsdk"),
        (r"if\s*\(USE_EXTERNAL_PWM\)\s*\{\s*g_pwm_outputs_active\s*=\s*true;\s*nucleo_send_pwm\(d_u, d_v, d_w, true\);\s*return", "uno_pwm_not_routed_only_to_nucleo"),
    ):
        require(uno, pattern, name, errors)

    for pattern, name in (
        (r"UNO_FRAME_LEN\s*=\s*32U", "nucleo_frame_length_not_32"),
        (r"UNO_PROTOCOL_VERSION\s*=\s*0x02U", "nucleo_protocol_version_not_v2"),
        (r"UNO_LINK_TIMEOUT_MS\s*=\s*300U", "nucleo_timeout_not_300ms"),
        (r"GPIO_PIN_6\s*\|\s*GPIO_PIN_7", "nucleo_usart1_pins_missing"),
        (r"GPIO_AF7_USART1", "nucleo_usart1_af_missing"),
        (
            r"/\* USER CODE BEGIN 2 \*/\s*/\* Keep the external UNO Q transport outside generated peripheral lists\. \*/\s*MX_USART1_UART_Init\(\);\s*uno_link_init\(\);",
            "nucleo_usart1_init_not_regeneration_safe",
        ),
        (r"if\s*\(!uno_service_fields_are_zero\(frame\)\)", "nucleo_service_fields_not_rejected"),
        (r"flags\s*!=\s*UNO_FLAG_ENABLE\s*\|\|\s*mode\s*!=\s*UNO_MODE_SCALAR", "nucleo_legacy_modes_not_rejected"),
        (r"MC_ProgramSpeedRampMotor1", "nucleo_does_not_apply_speed_api"),
        (r"MC_StartMotor1", "nucleo_does_not_start_with_mcsdk_api"),
        (r"MC_StopMotor1", "nucleo_does_not_stop_with_mcsdk_api"),
        (r"MC_AcknowledgeFaultMotor1", "nucleo_does_not_ack_mcsdk_fault"),
    ):
        require(nucleo, pattern, name, errors)

    for forbidden in ("HAL_TIM_", "HAL_ADC_", "HAL_GPIO_WritePin"):
        if forbidden in user_code:
            errors.append(f"nucleo_adapter_uses_forbidden_direct_control:{forbidden}")
    if expected_pole_pairs is not None:
        pole_pair_match = re.search(
            r"static\s+const\s+float\s+POLE_PAIRS\s*=\s*([0-9]+(?:\.[0-9]+)?)f\s*;",
            uno,
        )
        if pole_pair_match is None:
            errors.append("uno_pole_pairs_not_declared")
        elif abs(float(pole_pair_match.group(1)) - expected_pole_pairs) > 1e-6:
            errors.append(
                f"uno_pole_pairs_mismatch:expected={expected_pole_pairs}:actual={pole_pair_match.group(1)}"
            )
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Verify UNO Q to Nucleo MCSDK UART contract.")
    parser.add_argument("--uno", type=Path, default=root / "UNOQ_MOTOR" / "UNOQ_MOTOR.ino")
    parser.add_argument(
        "--nucleo",
        type=Path,
        default=root / "mcsdk_reference" / "ACIM_IPM15B_SIEMENS_REFERENCE_NOT_AIR56" / "CubeIDE_V1.6.3" / "Src" / "main.c",
    )
    parser.add_argument("--expected-pole-pairs", type=float)
    args = parser.parse_args()
    errors = vector_errors() + source_errors(args.uno, args.nucleo, args.expected_pole_pairs)
    report = {
        "tool": "uno_nucleo_mcsdk_contract_check",
        "pass": not errors,
        "uno": str(args.uno),
        "nucleo": str(args.nucleo),
        "expected_pole_pairs": args.expected_pole_pairs,
        "checks": ["protocol_vectors", "source_contract", "no_direct_motor_control_in_adapter"],
        "failures": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

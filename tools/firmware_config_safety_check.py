#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFINE_RE = re.compile(r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+?)(?://.*)?$")
IF_RE = re.compile(r"^\s*#if\s+(.+?)(?://.*)?$")
IFDEF_RE = re.compile(r"^\s*#ifdef\s+([A-Za-z_][A-Za-z0-9_]*)\b")
IFNDEF_RE = re.compile(r"^\s*#ifndef\s+([A-Za-z_][A-Za-z0-9_]*)\b")
ELSE_RE = re.compile(r"^\s*#else\b")
ENDIF_RE = re.compile(r"^\s*#endif\b")
ERROR_RE = re.compile(r"^\s*#error\s+(.+)")
POLE_PAIRS_RE = re.compile(r"\bPOLE_PAIRS\s*=\s*([0-9]+(?:\.[0-9]+)?)f?\s*;")


class CheckError(RuntimeError):
    pass


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "fail"
    evidence: Any = None


@dataclass
class IfFrame:
    parent_active: bool
    condition_true: bool
    active: bool


def clean_value(raw: str) -> str:
    return raw.strip().rstrip()


def numeric_token(raw: str) -> float | int | None:
    token = clean_value(raw)
    token = token.strip("()")
    token = re.sub(r"(?i)([0-9])([ulf]+)\b", r"\1", token)
    try:
        if re.fullmatch(r"[-+]?0x[0-9a-fA-F]+", token):
            return int(token, 16)
        if re.fullmatch(r"[-+]?[0-9]+", token):
            return int(token, 10)
        if re.fullmatch(r"[-+]?[0-9]*\.[0-9]+", token):
            return float(token)
    except Exception:
        return None
    return None


def macro_num(defs: dict[str, str], name: str) -> float | int:
    if name not in defs:
        raise CheckError(f"missing macro {name}")
    return resolve_num(defs, defs[name], (name,))


def resolve_num(defs: dict[str, str], raw: str, stack: tuple[str, ...] = ()) -> float | int:
    token = clean_value(raw)
    num = numeric_token(token)
    if num is not None:
        return num
    if token in defs:
        if token in stack:
            raise CheckError(f"macro alias cycle: {' -> '.join((*stack, token))}")
        return resolve_num(defs, defs[token], (*stack, token))
    raise CheckError(f"macro value is not numeric: {token!r}")


def macro_str(defs: dict[str, str], name: str) -> str:
    if name not in defs:
        raise CheckError(f"missing macro {name}")
    token = clean_value(defs[name])
    while token in defs and token != defs[token]:
        next_token = clean_value(defs[token])
        if next_token == token:
            break
        token = next_token
    return token


def eval_if(expr: str, defs: dict[str, str]) -> bool:
    text = expr.strip()
    text = text.replace("&&", " and ").replace("||", " or ")
    text = re.sub(r"!\s*", " not ", text)

    def repl(match: re.Match[str]) -> str:
        name = match.group(0)
        if name in {"and", "or", "not"}:
            return name
        try:
            return str(int(macro_num(defs, name)))
        except Exception:
            return "0"

    text = re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\b", repl, text)
    try:
        return bool(eval(text, {"__builtins__": {}}, {}))
    except Exception as exc:
        raise CheckError(f"cannot evaluate #if {expr!r}: {exc}") from exc


def parse_active_defines(path: Path) -> tuple[dict[str, str], list[str]]:
    defs: dict[str, str] = {}
    errors: list[str] = []
    stack: list[IfFrame] = []

    def active() -> bool:
        return all(frame.active for frame in stack)

    for line in path.read_text(encoding="utf-8").splitlines():
        ifdef_match = IFDEF_RE.match(line)
        if ifdef_match:
            parent = active()
            cond = ifdef_match.group(1) in defs if parent else False
            stack.append(IfFrame(parent_active=parent, condition_true=cond, active=parent and cond))
            continue
        ifndef_match = IFNDEF_RE.match(line)
        if ifndef_match:
            parent = active()
            cond = ifndef_match.group(1) not in defs if parent else False
            stack.append(IfFrame(parent_active=parent, condition_true=cond, active=parent and cond))
            continue
        if_match = IF_RE.match(line)
        if if_match:
            parent = active()
            cond = eval_if(if_match.group(1), defs) if parent else False
            stack.append(IfFrame(parent_active=parent, condition_true=cond, active=parent and cond))
            continue
        if ELSE_RE.match(line):
            if not stack:
                raise CheckError("unexpected #else")
            top = stack[-1]
            top.active = top.parent_active and not top.condition_true
            continue
        if ENDIF_RE.match(line):
            if not stack:
                raise CheckError("unexpected #endif")
            stack.pop()
            continue
        if not active():
            continue
        err = ERROR_RE.match(line)
        if err:
            errors.append(err.group(1).strip())
            continue
        match = DEFINE_RE.match(line)
        if match:
            defs[match.group(1)] = clean_value(match.group(2))
    if stack:
        raise CheckError("unclosed #if block in config.h")
    return defs, errors


def ok_case(name: str, evidence: Any = None, detail: str = "") -> CaseResult:
    return CaseResult(name=name, ok=True, detail=detail, evidence=evidence)


def fail_case(name: str, detail: str, evidence: Any = None) -> CaseResult:
    return CaseResult(name=name, ok=False, detail=detail, evidence=evidence)


def warn_case(name: str, detail: str, evidence: Any = None) -> CaseResult:
    return CaseResult(name=name, ok=True, detail=detail, severity="warn", evidence=evidence)


def check_range(name: str, value: float, lo: float, hi: float, unit: str = "") -> CaseResult:
    if lo <= value <= hi:
        return ok_case(name, evidence=value, detail=f"{value:g}{unit}")
    return fail_case(name, detail=f"{value:g}{unit} outside [{lo:g}, {hi:g}]{unit}", evidence=value)


def same_pin(defs: dict[str, str], port_a: str, pin_a: str, port_b: str, pin_b: str) -> bool:
    return macro_str(defs, port_a) == macro_str(defs, port_b) and macro_str(defs, pin_a) == macro_str(defs, pin_b)


def unoq_pole_pairs(path: Path) -> float:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = POLE_PAIRS_RE.search(text)
    if not match:
        raise CheckError("UNOQ_MOTOR POLE_PAIRS not found")
    return float(match.group(1))


def unoq_uses_nucleo_mcsdk(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"\bNUCLEO_MCSDK_ACIM_BACKEND\s*=\s*(true|false)\s*;", text)
    if not match:
        raise CheckError("UNOQ_MOTOR NUCLEO_MCSDK_ACIM_BACKEND not found")
    return match.group(1) == "true"


def nucleo_mcsdk_pole_pairs(repo: Path) -> float:
    project = repo / "mcsdk_reference" / "AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
    ioc_files = list(project.glob("*.ioc"))
    if len(ioc_files) != 1:
        raise CheckError(f"expected one Nucleo MCSDK IOC, found {len(ioc_files)}")
    text = ioc_files[0].read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?m)^MotorControl\.ACIM_POLE_PAIR_NUM=([0-9]+(?:\.[0-9]+)?)\s*$", text)
    if not match:
        raise CheckError("Nucleo MCSDK ACIM_POLE_PAIR_NUM not found")
    return float(match.group(1))


def source_contains(path: Path, needle: str) -> bool:
    return needle in path.read_text(encoding="utf-8", errors="replace")


def function_body(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        return ""
    brace = text.find("{", start)
    if brace < 0:
        return ""
    depth = 0
    for pos in range(brace, len(text)):
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth == 0:
                return text[brace : pos + 1]
    return ""


def run_checks(repo: Path) -> list[CaseResult]:
    config_path = repo / "bluepill_uart_pwm_pio" / "include" / "config.h"
    defs, preprocessor_errors = parse_active_defines(config_path)
    cases: list[CaseResult] = []

    if preprocessor_errors:
        cases.append(fail_case("config_preprocessor_errors", "; ".join(preprocessor_errors)))
    else:
        cases.append(ok_case("config_preprocessor_errors", "none"))

    cases.append(check_range("uart_baud", float(macro_num(defs, "UART_BAUD")), 115200, 921600, " baud"))
    cases.append(check_range("pwm_frequency", float(macro_num(defs, "PWM_FREQ_HZ")), 8000, 25000, " Hz"))
    cases.append(check_range("pwm_deadtime", float(macro_num(defs, "PWM_DEADTIME_NS")), 600, 2000, " ns"))
    cases.append(check_range("command_timeout", float(macro_num(defs, "TIMEOUT_MS")), 100, 500, " ms"))

    enable_confirm_frames = int(macro_num(defs, "ENABLE_CONFIRM_FRAMES"))
    safety_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "safety.cpp"
    enable_confirm_ok = (
        2 <= enable_confirm_frames <= 8
        and source_contains(safety_cpp, "s_enable_confirm_count < ENABLE_CONFIRM_FRAMES")
        and source_contains(safety_cpp, "seq != s_enable_last_seq")
        and source_contains(safety_cpp, "reset_enable_confirmation();")
    )
    if enable_confirm_ok:
        cases.append(
            ok_case(
                "enable_requires_consecutive_fresh_frames",
                {"frames": enable_confirm_frames, "distinct_sequence_required": True},
            )
        )
    else:
        cases.append(
            fail_case(
                "enable_requires_consecutive_fresh_frames",
                "PWM enable must reject a single stale frame and require distinct sequence numbers",
                {"frames": enable_confirm_frames},
            )
        )

    link_use_spi = int(macro_num(defs, "LINK_USE_SPI"))
    cases.append(ok_case("link_mode", {"LINK_USE_SPI": link_use_spi}) if link_use_spi == 0 else fail_case("link_mode", "PC-direct runtime expects UART LINK_USE_SPI=0", link_use_spi))

    pwm_min = float(macro_num(defs, "PWM_MIN_PERCENT"))
    pwm_max = float(macro_num(defs, "PWM_MAX_PERCENT"))
    if 0.0 <= pwm_min < pwm_max <= 100.0:
        cases.append(ok_case("pwm_duty_limits", {"min": pwm_min, "max": pwm_max}))
    else:
        cases.append(fail_case("pwm_duty_limits", "invalid min/max duty clamp", {"min": pwm_min, "max": pwm_max}))

    use_bkin = int(macro_num(defs, "USE_TIM1_BKIN"))
    em_stop_pb12 = int(macro_num(defs, "EM_STOP_IS_PB12"))
    if use_bkin and em_stop_pb12:
        cases.append(fail_case("bkin_em_stop_conflict", "TIM1_BKIN and EM_STOP both use PB12"))
    else:
        cases.append(ok_case("bkin_em_stop_conflict", {"USE_TIM1_BKIN": use_bkin, "EM_STOP_IS_PB12": em_stop_pb12}))

    if macro_str(defs, "EM_STOP_GPIO_PORT") == "GPIOB" and macro_str(defs, "EM_STOP_GPIO_PIN") == "GPIO_PIN_12":
        cases.append(ok_case("em_stop_pin", "GPIOB/GPIO_PIN_12"))
    else:
        cases.append(fail_case("em_stop_pin", "current wiring expects EM_STOP on PB12", {"port": macro_str(defs, "EM_STOP_GPIO_PORT"), "pin": macro_str(defs, "EM_STOP_GPIO_PIN")}))

    zero = float(macro_num(defs, "ADC_VBUS_ZERO_RAW"))
    cal_raw = float(macro_num(defs, "ADC_VBUS_CAL_RAW"))
    cal_v = float(macro_num(defs, "ADC_VBUS_CAL_V"))
    hv_cal_valid = int(macro_num(defs, "ADC_VBUS_HV_CALIBRATION_VALID"))
    if 0 <= zero < cal_raw <= 4095 and 250.0 <= cal_v <= 400.0 and math.isfinite(cal_v / (cal_raw - zero)):
        cases.append(ok_case("vbus_calibration", {"zero_raw": zero, "cal_raw": cal_raw, "cal_v": cal_v}))
    else:
        cases.append(fail_case("vbus_calibration", "invalid Vbus calibration constants", {"zero_raw": zero, "cal_raw": cal_raw, "cal_v": cal_v}))

    hmi_source = (repo / "web_hmi" / "server.py").read_text(encoding="utf-8")
    hmi_values: dict[str, float] = {}
    for name in ("VBUS_RAW_ZERO_CAL", "VBUS_RAW_CAL", "VBUS_RAW_CAL_V"):
        match = re.search(rf"^\s*{name}\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*$", hmi_source, re.MULTILINE)
        if match:
            hmi_values[name] = float(match.group(1))
    calibration_mirror_ok = (
        hmi_values.get("VBUS_RAW_ZERO_CAL") == zero
        and hmi_values.get("VBUS_RAW_CAL") == cal_raw
        and hmi_values.get("VBUS_RAW_CAL_V") == cal_v
    )
    if calibration_mirror_ok:
        cases.append(ok_case("vbus_hmi_raw_gate_matches_firmware", hmi_values))
    else:
        cases.append(
            fail_case(
                "vbus_hmi_raw_gate_matches_firmware",
                "HMI raw Vbus gate must mirror Blue Pill calibration points",
                {"firmware": {"zero_raw": zero, "cal_raw": cal_raw, "cal_v": cal_v}, "hmi": hmi_values},
            )
        )

    hmi_hv_cal_match = re.search(
        r"^\s*VBUS_HV_CALIBRATION_VALID\s*=\s*(True|False)\s*$",
        hmi_source,
        re.MULTILINE,
    )
    hmi_hv_cal_valid = hmi_hv_cal_match is not None and hmi_hv_cal_match.group(1) == "True"
    if hv_cal_valid in (0, 1) and hmi_hv_cal_valid == bool(hv_cal_valid):
        cases.append(ok_case("vbus_hv_calibration_gate_matches_firmware", {"valid": hv_cal_valid}))
    else:
        cases.append(
            fail_case(
                "vbus_hv_calibration_gate_matches_firmware",
                "HMI and Blue Pill must agree whether the known-HV calibration point is valid",
                {"firmware": hv_cal_valid, "hmi": hmi_hv_cal_valid},
            )
        )

    mirror_files = {
        "unoq": repo / "UNOQ_MOTOR" / "UNOQ_MOTOR.ino",
        "pc_direct": repo / "tools" / "unoq_web_server.py",
    }
    mirror_evidence: dict[str, dict[str, float]] = {}
    mirror_ok = True
    for label, path in mirror_files.items():
        source = path.read_text(encoding="utf-8")
        values: dict[str, float] = {}
        for name in ("BP_VBUS_ZERO_RAW", "BP_VBUS_CAL_RAW", "BP_VBUS_CAL_V"):
            match = re.search(rf"\b{name}\s*=\s*([0-9]+(?:\.[0-9]+)?)", source)
            if match:
                values[name] = float(match.group(1))
        mirror_evidence[label] = values
        mirror_ok = mirror_ok and (
            values.get("BP_VBUS_ZERO_RAW") == zero
            and values.get("BP_VBUS_CAL_RAW") == cal_raw
            and values.get("BP_VBUS_CAL_V") == cal_v
        )
    if mirror_ok:
        cases.append(ok_case("vbus_all_consumers_match_firmware", mirror_evidence))
    else:
        cases.append(
            fail_case(
                "vbus_all_consumers_match_firmware",
                "UNO Q and PC-direct Vbus conversion must mirror Blue Pill calibration points",
                mirror_evidence,
            )
        )

    vbus_oversamples = int(macro_num(defs, "ADC_VBUS_IDLE_OVERSAMPLES"))
    vbus_iir_shift = int(macro_num(defs, "ADC_VBUS_IIR_SHIFT"))
    if 16 <= vbus_oversamples <= 256 and 1 <= vbus_iir_shift <= 8:
        cases.append(ok_case("vbus_adc_filter", {"idle_oversamples": vbus_oversamples, "iir_shift": vbus_iir_shift}))
    else:
        cases.append(fail_case("vbus_adc_filter", "unsafe or ineffective Vbus ADC filter settings", {"idle_oversamples": vbus_oversamples, "iir_shift": vbus_iir_shift}))

    use_temp = int(macro_num(defs, "USE_HEATSINK_TEMP"))
    temp_protect = int(macro_num(defs, "HEATSINK_TEMP_PROTECTION_ENABLE"))
    temp_mode = macro_str(defs, "HEATSINK_TEMP_SENSOR_MODE")
    temp_oversamples = int(macro_num(defs, "HEATSINK_TEMP_OVERSAMPLES"))
    if use_temp == 1 and temp_protect == 1 and temp_mode == "1":
        cases.append(
            ok_case(
                "heatsink_temperature_protection",
                {"mode": "TSO", "protection": temp_protect},
            )
        )
    else:
        cases.append(fail_case("heatsink_temperature_protection", "current bench expects TSO temperature protection enabled", {"USE_HEATSINK_TEMP": use_temp, "HEATSINK_TEMP_PROTECTION_ENABLE": temp_protect, "HEATSINK_TEMP_SENSOR_MODE": temp_mode}))

    adc_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "adc_currents.cpp"
    temp_adc_settling_ok = (
        4 <= temp_oversamples <= 256
        and source_contains(adc_cpp, "i <= HEATSINK_TEMP_OVERSAMPLES")
        and source_contains(adc_cpp, "if (i != 0U)")
    )
    if temp_adc_settling_ok:
        cases.append(ok_case("heatsink_temperature_adc_settling", {"oversamples": temp_oversamples, "discard_first": True}))
    else:
        cases.append(
            fail_case(
                "heatsink_temperature_adc_settling",
                "TSO sampling must discard the first post-switch ADC conversion and average a bounded burst",
                {"oversamples": temp_oversamples},
            )
        )

    phase_c_conflict = same_pin(defs, "HEATSINK_TEMP_PORT", "HEATSINK_TEMP_PIN", "PHASE_MEAS_C_PORT", "PHASE_MEAS_C_PIN")
    safety_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "safety.cpp"
    virtual_c_ok = source_contains(safety_cpp, "PHASE_FLAG_C_VIRTUAL") and source_contains(adc_cpp, "PHASE_MEAS_CENTER_RAW")
    if phase_c_conflict and virtual_c_ok:
        cases.append(ok_case("phase_c_virtual_due_pb0_temp", {"PB0_conflict": True, "virtual_c": True}))
    elif phase_c_conflict:
        cases.append(fail_case("phase_c_virtual_due_pb0_temp", "PB0 is shared but virtual phase C implementation was not found"))
    else:
        cases.append(warn_case("phase_c_virtual_due_pb0_temp", "phase C no longer shares heat-sink pin; verify wiring/docs", {"PB0_conflict": False}))

    ipm_io_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "ipm15_io.cpp"
    ipm_io_h = repo / "bluepill_uart_pwm_pio" / "include" / "ipm15_io.h"
    safety_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "safety.cpp"
    main_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "main.cpp"
    pb1_unused_ok = (
        macro_str(defs, "UNUSED_STEVAL_J2_21_PORT") == "GPIOB"
        and macro_str(defs, "UNUSED_STEVAL_J2_21_PIN") == "GPIO_PIN_1"
        and source_contains(ipm_io_cpp, "gpio_analog_init(UNUSED_STEVAL_J2_21_PORT, UNUSED_STEVAL_J2_21_PIN)")
        and not source_contains(ipm_io_cpp, "ipm15_set_ntc")
        and not source_contains(ipm_io_h, "ipm15_set_ntc")
        and not source_contains(safety_cpp, "EXT_NTC_RELAY")
    )
    pb4_relay_disabled_ok = (
        int(macro_num(defs, "USE_PRECHARGE_RELAY")) == 0
        and macro_str(defs, "PRECHARGE_RELAY_PORT") == "GPIOB"
        and macro_str(defs, "PRECHARGE_RELAY_PIN") == "GPIO_PIN_4"
        and source_contains(ipm_io_cpp, "gpio_analog_init(PRECHARGE_RELAY_PORT, PRECHARGE_RELAY_PIN)")
    )
    if pb1_unused_ok and pb4_relay_disabled_ok:
        cases.append(ok_case("pb4_precharge_disabled_pb1_unused", {"PB4": "analog/high-impedance", "PB1": "analog/high-impedance"}))
    else:
        cases.append(fail_case("pb4_precharge_disabled_pb1_unused", "PB4 and PB1/J2-21 must stay high-impedance when K1 is absent"))

    relay_reply_forced_off_ok = (
        source_contains(ipm_io_h, "ipm15_precharge_relay_pin_active")
        and source_contains(ipm_io_cpp, "return false;")
        and source_contains(safety_cpp, "ext_reply &= (uint8_t)(~EXT_PRECHARGE_RELAY)")
        and source_contains(safety_cpp, "#if USE_PRECHARGE_RELAY")
    )
    if relay_reply_forced_off_ok:
        cases.append(ok_case("precharge_reply_forced_off", {"reply_bit_0x08": 0, "relay_present": False}))
    else:
        cases.append(fail_case("precharge_reply_forced_off", "precharge status bit must stay cleared when K1 is absent"))

    fan_control_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "fan_control.cpp"
    fan_control_text = fan_control_cpp.read_text(encoding="utf-8", errors="replace")
    fan_pwm = int(macro_num(defs, "USE_FAN_PWM"))
    tim2_remap_pos = fan_control_text.find("__HAL_AFIO_REMAP_TIM2_PARTIAL_1();")
    fan_swj_nojtag_pos = fan_control_text.find("__HAL_AFIO_REMAP_SWJ_NOJTAG();", tim2_remap_pos)
    fan_pb3_jtag_ok = (
        fan_pwm == 1
        and macro_str(defs, "FAN_PWM_PORT") == "GPIOB"
        and macro_str(defs, "FAN_PWM_PIN") == "GPIO_PIN_3"
        and source_contains(main_cpp, "__HAL_AFIO_REMAP_SWJ_NOJTAG")
        and tim2_remap_pos >= 0
        and fan_swj_nojtag_pos > tim2_remap_pos
    )
    if fan_pwm == 0:
        cases.append(ok_case("fan_pwm_pb3_jtag_disabled", {"USE_FAN_PWM": 0, "PB3": "analog/high-impedance"}))
    elif fan_pb3_jtag_ok:
        cases.append(ok_case("fan_pwm_pb3_jtag_disabled", {"FAN_PWM": "PB3", "SWJ_NOJTAG": "main_and_after_TIM2_remap"}))
    else:
        cases.append(
            fail_case(
                "fan_pwm_pb3_jtag_disabled",
                "fan PWM expects PB3 with JTAG disabled; re-assert SWJ_NOJTAG after TIM2 remap to keep PB3/PB4 released from JTAG",
                {"TIM2_remap": tim2_remap_pos, "fan_SWJ_NOJTAG_after_TIM2": fan_swj_nojtag_pos},
            )
        )

    fan_pwm_hz = int(macro_num(defs, "FAN_PWM_FREQ_HZ"))
    fan_pwm_active_high = int(macro_num(defs, "FAN_PWM_ACTIVE_HIGH"))
    fan_4wire_ok = (
        21000 <= fan_pwm_hz <= 28000
        and fan_pwm_active_high == 0
        and "FAN_PWM_ACTIVE_HIGH ? TIM_OCPOLARITY_HIGH : TIM_OCPOLARITY_LOW" in fan_control_text
    )
    if fan_pwm == 0:
        cases.append(ok_case("fan_4wire_open_collector_timing", {"USE_FAN_PWM": 0, "status": "disabled"}))
    elif fan_4wire_ok:
        cases.append(ok_case("fan_4wire_open_collector_timing", {"frequency_hz": fan_pwm_hz, "timer_active_high": fan_pwm_active_high}))
    else:
        cases.append(
            fail_case(
                "fan_4wire_open_collector_timing",
                "4-wire fan expects 21..28 kHz and active-low timer output for the inverting NPN open collector",
                {"frequency_hz": fan_pwm_hz, "timer_active_high": fan_pwm_active_high},
            )
        )

    fan_tach = int(macro_num(defs, "USE_FAN_TACH"))
    if fan_tach == 1 and macro_str(defs, "FAN_TACH_PORT") == "GPIOA" and macro_str(defs, "FAN_TACH_PIN") == "GPIO_PIN_11":
        cases.append(warn_case("fan_tach_pa11_usb_conflict", "PA11 tach is OK only when Blue Pill USB is not used", {"FAN_TACH": "PA11"}))
    else:
        cases.append(ok_case("fan_tach_pa11_usb_conflict", {"USE_FAN_TACH": fan_tach}))

    unoq_path = repo / "UNOQ_MOTOR" / "UNOQ_MOTOR.ino"
    unoq_text = unoq_path.read_text(encoding="utf-8", errors="replace")
    matrix_feedback_ok = all(
        token in unoq_text
        for token in (
            "float freq = g_pwm_enabled ? g_freq_ref : g_freq_cmd;",
            "bool show_rpm = g_pwm_enabled",
            "(freq * 60.0f) / POLE_PAIRS",
            "if (g_bp_softstart_ready)",
            "g_bp_status & BP_STATUS_PWM_ACTIVE",
        )
    )
    if matrix_feedback_ok:
        cases.append(ok_case("unoq_matrix_shows_command_and_pwm", {"digits": "frequency/RPM", "left": "external soft-start ready", "right": "MCSDK PWM"}))
    else:
        cases.append(fail_case("unoq_matrix_shows_command_and_pwm", "UNO Q matrix must expose frequency/RPM, external soft-start readiness, and actual MCSDK PWM feedback"))
    hard_stop_body = unoq_text.split("static void hard_stop(bool clear_cmd, bool force_link) {", 1)
    hard_stop_releases_relay = bool(
        len(hard_stop_body) == 2
        and hard_stop_body[1].split("static void request_normal_stop()", 1)[0].find("BP_EXT_PRECHARGE_RELAY") >= 0
    )
    if hard_stop_releases_relay:
        cases.append(ok_case("unoq_every_hard_stop_clears_legacy_precharge_bit"))
    else:
        cases.append(fail_case("unoq_every_hard_stop_clears_legacy_precharge_bit", "hard_stop must clear the reserved precharge bit"))
    ext_flag_body = unoq_text.split("static void ext_flag_set(uint8_t flag, bool on) {", 1)
    ext_flag_immediate = bool(
        len(ext_flag_body) == 2
        and "USE_EXTERNAL_PWM && !g_pwm_enabled" in ext_flag_body[1].split("static void ext_brake_set", 1)[0]
        and "nucleo_send_stop(true);" in ext_flag_body[1].split("static void ext_brake_set", 1)[0]
    )
    if ext_flag_immediate:
        cases.append(ok_case("unoq_service_outputs_send_immediate_safe_frame"))
    else:
        cases.append(fail_case("unoq_service_outputs_send_immediate_safe_frame", "PFC/service-output changes must immediately reach Blue Pill while PWM is off"))
    unoq_uart_match = re.search(r"\bNUCLEO_UART_BAUD\s*=\s*([0-9]+)\s*;", unoq_text)
    bluepill_uart_baud = int(macro_num(defs, "UART_BAUD"))
    if unoq_uart_match is None:
        cases.append(fail_case("uart_baud_match", "UNOQ NUCLEO_UART_BAUD not found"))
    else:
        unoq_uart_baud = int(unoq_uart_match.group(1))
        evidence = {"unoq": unoq_uart_baud, "bluepill": bluepill_uart_baud}
        if unoq_uart_baud == bluepill_uart_baud:
            cases.append(ok_case("uart_baud_match", evidence))
        else:
            cases.append(fail_case("uart_baud_match", "UNO Q and Blue Pill UART baud differ", evidence))
    scalar_offload_ok = all(
        token in unoq_text
        for token in (
            "NUCLEO_SCALAR_MIN_SEND_US = 50000",
            "mode = BP_MODE_SCALAR;",
            "else if (mode == BP_MODE_SCALAR)",
            "bp_freq_millihz(g_freq_ref)",
            "bp_scalar_vmag_q15()",
        )
    )
    if scalar_offload_ok:
        cases.append(
            ok_case(
                "unoq_scalar_generation_offloaded_to_bluepill",
                {"backend": "MODE_SCALAR", "setpoint_period_us": 50000},
            )
        )
    else:
        cases.append(
            fail_case(
                "unoq_scalar_generation_offloaded_to_bluepill",
                "scalar/VF must send frequency and magnitude to the Blue Pill instead of streaming duty at 100 Hz",
            )
        )
    estop_heartbeat_limited = all(
        token in unoq_text
        for token in (
            "static void pwm_force_off(bool force_link)",
            "nucleo_send_stop(force_link);",
            "pwm_force_off(force_link || outputs_were_active);",
            "hard_stop(false, true);",
        )
    ) and "static void pwm_force_off(bool force_link = false);" in unoq_text
    if estop_heartbeat_limited:
        cases.append(
            ok_case(
                "unoq_repeated_estop_uses_uart_heartbeat_limit",
                {"first_shutdown": "forced", "repeated_safe_ticks": "heartbeat-limited"},
            )
        )
    else:
        cases.append(
            fail_case(
                "unoq_repeated_estop_uses_uart_heartbeat_limit",
                "repeated SAFE/ESTOP ticks must not force unthrottled Blue Pill UART frames",
            )
        )
    io_test_branch = unoq_text.split("} else if (io_test_eff && !estop_eff) {", 1)
    if len(io_test_branch) == 2:
        io_test_branch = io_test_branch[1].split("} else if", 1)[0]
    else:
        io_test_branch = ""
    io_test_service_frame_safe = all(
        token in io_test_branch
        for token in (
            "enable_eff = false;",
            "diag_eff = false;",
            "mode = BP_MODE_OFF;",
            "du_eff = 0.0f;",
            "dv_eff = 0.0f;",
            "dw_eff = 0.0f;",
        )
    )
    if io_test_service_frame_safe:
        cases.append(ok_case("unoq_iotest_uses_disabled_service_frame", {"mode": "OFF", "enable": False, "pwm": "zero"}))
    else:
        cases.append(
            fail_case(
                "unoq_iotest_uses_disabled_service_frame",
                "UNO Q IOTEST must carry relay flags in MODE_OFF with ENABLE=0 and zero PWM duties",
            )
        )

    mcfoc_body = function_body(unoq_text, "static bool handle_mcfoc_command")
    mcfoc_on_requires_safe_state = all(
        token in mcfoc_body
        for token in (
            "NUCLEO_MCSDK_ACIM_BACKEND",
            "g_pwm_enabled",
            "g_state != STATE_SAFE",
            "g_estop_latched",
            "g_fault != 0",
            "g_bp_foc_backend = true",
            "g_bp_foc_backend = false",
            "nucleo_send_stop(true);",
        )
    )
    mcfoc_off_is_fail_safe = (
        "g_bp_foc_backend = false" in mcfoc_body
        and "request_normal_stop();" in mcfoc_body
        and "nucleo_send_stop(true);" in mcfoc_body
    )
    if mcfoc_on_requires_safe_state and mcfoc_off_is_fail_safe:
        cases.append(ok_case("unoq_mcfoc_backend_command_safety", {"nucleo_scalar": "reject_on", "on_guards": "pwm_off,state_safe,estop_clear,fault_clear", "off": "stop_if_active"}))
    else:
        cases.append(
            fail_case(
                "unoq_mcfoc_backend_command_safety",
                "MCFOC ON must be rejected by the scalar Nucleo backend and guarded for future backends; OFF must stop if active",
                {"on_safe": mcfoc_on_requires_safe_state, "off_fail_safe": mcfoc_off_is_fail_safe},
            )
        )

    pc_hmi_path = repo / "tools" / "unoq_web_server.py"
    pc_hmi_text = pc_hmi_path.read_text(encoding="utf-8", errors="replace")
    pc_bpfoc_explicit_only = (
        "state.bp_foc_backend = next_mode == MODE_FOC" not in pc_hmi_text
        and "if next_mode != MODE_FOC:" in pc_hmi_text
        and "state.bp_foc_backend = False" in pc_hmi_text
        and 'if head == "BPFOC":' in pc_hmi_text
        and 'output_permitted_locked(state, "BPFOC")' in pc_hmi_text
        and "state.bp_foc_backend = True" in pc_hmi_text
    )
    if pc_bpfoc_explicit_only:
        cases.append(ok_case("pc_direct_bpfoc_backend_explicit_only", {"MODE_FOC": "passive", "enable": "BPFOC ON guarded"}))
    else:
        cases.append(
            fail_case(
                "pc_direct_bpfoc_backend_explicit_only",
                "PC-direct MODE FOC must not auto-enable BPFOC backend; only guarded BPFOC ON may set bp_foc_backend=true",
            )
        )

    pwm_tim1_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "pwm_tim1.cpp"
    pwm_tim1_text = pwm_tim1_cpp.read_text(encoding="utf-8", errors="replace")
    safe_disable_ok = all(
        token in pwm_tim1_text
        for token in (
            "pwm_gpio_force_low",
            "pwm_force_safe_gpio",
            "pwm_force_safe_gpio_hard",
            "pwm_safe_idle",
            "pwm_tim1_force_peripheral_off",
            "TIM1->BDTR &= ~TIM_BDTR_MOE;",
            "TIM1->CCER &= ~PWM_CCER_ENABLE_MASK;",
            "TIM1->CR1 &= ~TIM_CR1_CEN;",
            "GPIO_MODE_OUTPUT_PP",
            "__HAL_TIM_MOE_DISABLE(&htim1);",
            "pwm_gpio_force_low();",
            "pwm_gpio_config_af();",
            "__HAL_TIM_MOE_ENABLE(&htim1);",
        )
    )
    if safe_disable_ok:
        cases.append(ok_case("pwm_safe_disable_forces_gpio_low", {"pins": "PA8/PA9/PA10/PB13/PB14/PB15"}))
    else:
        cases.append(fail_case("pwm_safe_disable_forces_gpio_low", "PWM disable must force all six TIM1 pins to GPIO-low before relying on EM_STOP"))

    tim1_gpio_prepare_ok = (
        "pwm_prepare_tim1_gpio_pins" in pwm_tim1_text
        and "__HAL_RCC_AFIO_CLK_ENABLE();" in pwm_tim1_text
        and function_body(pwm_tim1_text, "static void pwm_gpio_force_low").find("pwm_prepare_tim1_gpio_pins();") >= 0
        and function_body(pwm_tim1_text, "static void pwm_gpio_config_af").find("pwm_prepare_tim1_gpio_pins();") >= 0
        and function_body(pwm_tim1_text, "static void pwm_gpio_force_low").find("GPIO_MODE_OUTPUT_PP") >= 0
    )
    if tim1_gpio_prepare_ok:
        cases.append(ok_case("pwm_driver_prepares_tim1_gpio_low_side_pins", {"pins": "PA8/PA9/PA10/PB13/PB14/PB15", "note": "PB13/PB14/PB15 are TIM1_CHxN, not JTAG"}))
    else:
        cases.append(
            fail_case(
                "pwm_driver_prepares_tim1_gpio_low_side_pins",
                "pwm_tim1.cpp must prepare TIM1 GPIO and force PA8/PA9/PA10/PB13/PB14/PB15 LOW before switching to AF or enabling outputs",
            )
        )

    force_low_body = function_body(pwm_tim1_text, "static void pwm_gpio_force_low")
    force_peripheral_off_body = function_body(pwm_tim1_text, "static void pwm_tim1_force_peripheral_off")
    force_low_turns_tim1_off_ok = (
        "pwm_tim1_force_peripheral_off();" in force_low_body
        and "TIM1->BDTR &= ~TIM_BDTR_MOE;" in force_peripheral_off_body
        and "TIM1->CCER &= ~PWM_CCER_ENABLE_MASK;" in force_peripheral_off_body
        and "TIM1->CR1 &= ~TIM_CR1_CEN;" in force_peripheral_off_body
        and "s_pwm_outputs_started = false;" in force_peripheral_off_body
    )
    if force_low_turns_tim1_off_ok:
        cases.append(ok_case("pwm_force_safe_gpio_turns_tim1_peripheral_off", {"registers": "BDTR.MOE, CCER, CR1.CEN"}))
    else:
        cases.append(
            fail_case(
                "pwm_force_safe_gpio_turns_tim1_peripheral_off",
                "pwm_force_safe_gpio paths must turn TIM1 hardware outputs off before forcing GPIO-low",
            )
        )

    main_text = main_cpp.read_text(encoding="utf-8", errors="replace")
    hal_init_pos = main_text.find("HAL_Init();")
    clock_config_pos = main_text.find("SystemClock_Config();")
    mx_gpio_init_pos = main_text.find("MX_GPIO_Init();")
    early_force_pos = main_text.find("pwm_force_safe_gpio_hard();")
    uart_init_pos = main_text.find("MX_USART2_UART_Init();")
    tim1_init_pos = main_text.find("pwm_tim1_init();")
    reset_window_force_low_ok = (
        hal_init_pos >= 0
        and early_force_pos > hal_init_pos
        and (clock_config_pos < 0 or early_force_pos < clock_config_pos)
        and (mx_gpio_init_pos < 0 or early_force_pos < mx_gpio_init_pos)
    )
    if reset_window_force_low_ok:
        cases.append(ok_case("pwm_gpio_forced_low_immediately_after_hal_init", {"order": "HAL_Init -> hard PWM GPIO-low -> clocks/GPIO"}))
    else:
        cases.append(
            fail_case(
                "pwm_gpio_forced_low_immediately_after_hal_init",
                "main() must force all six PWM GPIOs low immediately after HAL_Init(), before clock and generic GPIO init",
                {
                    "HAL_Init": hal_init_pos,
                    "pwm_force_safe_gpio_hard": early_force_pos,
                    "SystemClock_Config": clock_config_pos,
                    "MX_GPIO_Init": mx_gpio_init_pos,
                },
            )
        )

    early_force_low_ok = early_force_pos >= 0 and (
        (uart_init_pos < 0 or early_force_pos < uart_init_pos)
        and (tim1_init_pos < 0 or early_force_pos < tim1_init_pos)
    )
    if early_force_low_ok:
        cases.append(ok_case("pwm_gpio_forced_low_before_link_and_tim1_init", {"call": "pwm_force_safe_gpio_hard"}))
    else:
        cases.append(
            fail_case(
                "pwm_gpio_forced_low_before_link_and_tim1_init",
                "main() must force PA8/PA9/PA10/PB13/PB14/PB15 GPIO-low before UART/SPI link and TIM1 init",
                {"pwm_force_safe_gpio_hard": early_force_pos, "uart_init": uart_init_pos, "tim1_init": tim1_init_pos},
            )
        )

    prelink_force_low_ok = (
        "safety_state()->good_cnt == 0" in main_text
        and "pwm_force_safe_gpio_hard();" in function_body(main_text, "int main")
        and "last_prelink_force_ms" in function_body(main_text, "int main")
        and main_text.find("safety_state()->good_cnt == 0") < main_text.rfind("pwm_force_safe_gpio_hard();")
    )
    if prelink_force_low_ok:
        cases.append(ok_case("pwm_gpio_reasserted_low_until_first_valid_frame", {"condition": "good_cnt == 0"}))
    else:
        cases.append(
            fail_case(
                "pwm_gpio_reasserted_low_until_first_valid_frame",
                "main loop must keep PWM GPIOs forced low until the first valid Blue Pill command frame",
            )
        )

    selftest_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "pwm_selftest.cpp"
    selftest_text = selftest_cpp.read_text(encoding="utf-8", errors="replace")
    selftest_hal_init_pos = selftest_text.find("HAL_Init();")
    selftest_clock_config_pos = selftest_text.find("SystemClock_Config();")
    selftest_force_pos = selftest_text.find("pwm_force_safe_gpio();")
    selftest_tim1_pos = selftest_text.find("pwm_tim1_init();")
    selftest_reset_window_ok = (
        selftest_hal_init_pos >= 0
        and selftest_force_pos > selftest_hal_init_pos
        and (selftest_clock_config_pos < 0 or selftest_force_pos < selftest_clock_config_pos)
    )
    if selftest_reset_window_ok:
        cases.append(ok_case("pwm_selftest_gpio_forced_low_immediately_after_hal_init", {"order": "HAL_Init -> PWM GPIO-low -> clocks"}))
    else:
        cases.append(
            fail_case(
                "pwm_selftest_gpio_forced_low_immediately_after_hal_init",
                "pwm_selftest firmware must force all six PWM GPIOs low immediately after HAL_Init(), before clock init",
                {
                    "HAL_Init": selftest_hal_init_pos,
                    "pwm_force_safe_gpio": selftest_force_pos,
                    "SystemClock_Config": selftest_clock_config_pos,
                },
            )
        )

    selftest_force_low_ok = selftest_force_pos >= 0 and (
        selftest_tim1_pos < 0 or selftest_force_pos < selftest_tim1_pos
    )
    if selftest_force_low_ok:
        cases.append(ok_case("pwm_selftest_forces_gpio_low_before_tim1_init", {"call": "pwm_force_safe_gpio"}))
    else:
        cases.append(
            fail_case(
                "pwm_selftest_forces_gpio_low_before_tim1_init",
                "pwm_selftest firmware must force PA8/PA9/PA10/PB13/PB14/PB15 GPIO-low before TIM1 init",
                {"pwm_force_safe_gpio": selftest_force_pos, "tim1_init": selftest_tim1_pos},
            )
        )

    static_low_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "pwm_static_low_test.cpp"
    static_low_text = static_low_cpp.read_text(encoding="utf-8", errors="replace")
    static_low_main = function_body(static_low_text, "int main")
    static_low_force_body = function_body(static_low_text, "static void force_all_static_low")
    static_low_hal_init_pos = static_low_main.find("HAL_Init();")
    static_low_first_force_pos = static_low_main.find("force_all_static_low();")
    static_low_clock_pos = static_low_main.find("SystemClock_Config();")
    static_low_loop_pos = static_low_main.find("while (1)")
    static_low_loop_force_pos = static_low_main.rfind("force_all_static_low();")
    static_low_force_order_ok = (
        static_low_hal_init_pos >= 0
        and static_low_first_force_pos > static_low_hal_init_pos
        and (static_low_clock_pos < 0 or static_low_first_force_pos < static_low_clock_pos)
        and static_low_loop_pos >= 0
        and static_low_loop_force_pos > static_low_loop_pos
        and "GPIO_MODE_OUTPUT_PP" in static_low_force_body
        and "HAL_GPIO_WritePin(GPIOB, PWM_B_PINS, GPIO_PIN_RESET);" in static_low_force_body
    )
    if static_low_force_order_ok:
        cases.append(ok_case("pwm_static_low_test_hard_forces_gpio_low", {"pins": "PA8/PA9/PA10/PB13/PB14/PB15", "loop": True}))
    else:
        cases.append(
            fail_case(
                "pwm_static_low_test_hard_forces_gpio_low",
                "static-low diagnostic firmware must force all PWM pins LOW immediately and continuously",
                {
                    "HAL_Init": static_low_hal_init_pos,
                    "first_force_all_static_low": static_low_first_force_pos,
                    "SystemClock_Config": static_low_clock_pos,
                    "loop": static_low_loop_pos,
                    "loop_force_all_static_low": static_low_loop_force_pos,
                },
            )
        )

    static_low_is_gpio_only = not any(
        token in static_low_text
        for token in (
            "pwm_tim1_init(",
            "HAL_TIM_PWM_Init",
            "HAL_TIM_PWM_Start",
            "HAL_TIMEx_PWMN_Start",
            "uart_link",
            "spi_link",
            "control_update",
        )
    )
    platformio_text = (repo / "bluepill_uart_pwm_pio" / "platformio.ini").read_text(encoding="utf-8", errors="replace")
    static_low_env_ok = (
        "[env:bluepill_static_low_test]" in platformio_text
        and "build_src_filter = +<pwm_static_low_test.cpp>" in platformio_text
    )
    if static_low_is_gpio_only and static_low_env_ok:
        cases.append(ok_case("pwm_static_low_test_excludes_tim1_and_protocol", {"env": "bluepill_static_low_test"}))
    else:
        cases.append(
            fail_case(
                "pwm_static_low_test_excludes_tim1_and_protocol",
                "static-low diagnostic firmware must build only the GPIO-low test, without TIM1 PWM or command protocol code",
                {"gpio_only": static_low_is_gpio_only, "env_ok": static_low_env_ok},
            )
        )

    pwm_init_body = function_body(pwm_tim1_text, "void pwm_tim1_init")
    pwm_enable_body = function_body(pwm_tim1_text, "void pwm_outputs_enable")
    pwm_safe_idle_body = function_body(pwm_tim1_text, "void pwm_safe_idle")
    pwm_start_outputs_body = function_body(pwm_tim1_text, "static void pwm_start_outputs")
    safety_text = safety_cpp.read_text(encoding="utf-8", errors="replace")
    control_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "control.cpp"
    control_text = control_cpp.read_text(encoding="utf-8", errors="replace")
    init_force_low_pos = pwm_init_body.find("pwm_gpio_force_low();")
    init_config_af_pos = pwm_init_body.find("pwm_gpio_config_af();")
    init_hal_pwm_pos = pwm_init_body.find("HAL_TIM_PWM_Init")
    init_holds_low_ok = (
        init_force_low_pos >= 0
        and init_config_af_pos < 0
        and (init_hal_pwm_pos < 0 or init_force_low_pos < init_hal_pwm_pos)
    )
    if init_holds_low_ok:
        cases.append(ok_case("pwm_tim1_init_keeps_gpio_low_until_enable", {"order": "GPIO-low during TIM1 init"}))
    else:
        cases.append(
            fail_case(
                "pwm_tim1_init_keeps_gpio_low_until_enable",
                "pwm_tim1_init() must keep all six PWM pins as GPIO-low; switch to AF only inside pwm_outputs_enable(true)",
                {
                    "pwm_gpio_force_low": init_force_low_pos,
                    "pwm_gpio_config_af": init_config_af_pos,
                    "HAL_TIM_PWM_Init": init_hal_pwm_pos,
                },
            )
        )

    enable_if_pos = pwm_enable_body.find("if (enable)")
    enable_af_pos = pwm_enable_body.find("pwm_gpio_config_af();")
    enable_start_pos = pwm_enable_body.find("pwm_start_outputs();")
    enable_moe_pos = pwm_enable_body.find("__HAL_TIM_MOE_ENABLE(&htim1);")
    enable_af_order_ok = (
        enable_if_pos >= 0
        and enable_af_pos > enable_if_pos
        and enable_start_pos > enable_af_pos
        and enable_moe_pos > enable_start_pos
    )
    if enable_af_order_ok:
        cases.append(ok_case("pwm_outputs_enable_switches_af_only_on_start", {"order": "AF -> start -> MOE"}))
    else:
        cases.append(
            fail_case(
                "pwm_outputs_enable_switches_af_only_on_start",
                "PWM pins must switch from GPIO-low to alternate-function only when outputs are explicitly enabled",
                {
                    "if_enable": enable_if_pos,
                    "pwm_gpio_config_af": enable_af_pos,
                    "pwm_start_outputs": enable_start_pos,
                    "MOE_ENABLE": enable_moe_pos,
                },
            )
        )

    safe_idle_disable_pos = pwm_safe_idle_body.find("pwm_outputs_enable(false);")
    safe_idle_all_off_pos = pwm_safe_idle_body.find("pwm_all_off();")
    safe_idle_force_low_pos = pwm_safe_idle_body.find("pwm_gpio_force_low();")
    safe_idle_order_ok = (
        safe_idle_disable_pos >= 0
        and safe_idle_all_off_pos > safe_idle_disable_pos
        and safe_idle_force_low_pos > safe_idle_all_off_pos
    )
    if safe_idle_order_ok:
        cases.append(ok_case("pwm_safe_idle_disables_before_ccr_zero", {"order": "disable -> CCR=0 -> GPIO-low"}))
    else:
        cases.append(
            fail_case(
                "pwm_safe_idle_disables_before_ccr_zero",
                "pwm_safe_idle() must disable TIM1 outputs before pwm_all_off(), because CCR=0 can drive complementary N outputs high while MOE is set",
                {
                    "pwm_outputs_enable_false": safe_idle_disable_pos,
                    "pwm_all_off": safe_idle_all_off_pos,
                    "pwm_gpio_force_low": safe_idle_force_low_pos,
                },
            )
        )

    q15_to_ccr_body = function_body(pwm_tim1_text, "static uint32_t q15_to_ccr")
    active_zero_duty_clamped_ok = (
        "if (q15 == 0U)" not in q15_to_ccr_body
        and "clamp_percent(pct)" in q15_to_ccr_body
        and "PWM_MIN_PERCENT" in pwm_tim1_text
        and "pwm_all_off" in pwm_safe_idle_body
        and safe_idle_order_ok
    )
    if active_zero_duty_clamped_ok:
        cases.append(
            ok_case(
                "pwm_active_zero_duty_clamped_above_complementary_full_on",
                {"active_zero": "clamped_by_PWM_MIN_PERCENT", "true_off": "pwm_all_off_after_MOE_CCER_disable"},
            )
        )
    else:
        cases.append(
            fail_case(
                "pwm_active_zero_duty_clamped_above_complementary_full_on",
                "Active q15 duty conversion must not return CCR=0, because complementary TIM1 N outputs become full-on while MOE is set",
            )
        )

    lazy_pwm_start_ok = (
        "static bool s_pwm_outputs_started" in pwm_tim1_text
        and "static void pwm_start_outputs" in pwm_tim1_text
        and "static void pwm_stop_outputs" in pwm_tim1_text
        and "HAL_TIM_PWM_Start" not in pwm_init_body
        and "HAL_TIMEx_PWMN_Start" not in pwm_init_body
        and "pwm_start_outputs();" in pwm_enable_body
        and "pwm_stop_outputs();" in pwm_enable_body
    )
    if lazy_pwm_start_ok:
        cases.append(ok_case("pwm_lazy_start_avoids_init_complementary_glitch", {"start": "pwm_outputs_enable(true)", "stop": "pwm_outputs_enable(false)"}))
    else:
        cases.append(fail_case("pwm_lazy_start_avoids_init_complementary_glitch", "TIM1 PWM/N outputs must not be started inside pwm_tim1_init()"))

    hal_start_not_used_for_tim1_ok = (
        "HAL_TIM_PWM_Start" not in pwm_start_outputs_body
        and "HAL_TIMEx_PWMN_Start" not in pwm_start_outputs_body
        and "PWM_CCER_ENABLE_MASK" in pwm_start_outputs_body
        and "TIM1->EGR = TIM_EVENTSOURCE_UPDATE;" in pwm_start_outputs_body
    )
    if hal_start_not_used_for_tim1_ok:
        cases.append(ok_case("pwm_start_outputs_avoids_hal_moe_side_effect", {"start": "direct CCER staging"}))
    else:
        cases.append(
            fail_case(
                "pwm_start_outputs_avoids_hal_moe_side_effect",
                "HAL_TIM_PWM_Start/HAL_TIMEx_PWMN_Start enable MOE internally; TIM1 startup must stage all CCER bits with MOE disabled",
            )
        )

    start_moe_disable_pos = pwm_start_outputs_body.find("__HAL_TIM_MOE_DISABLE(&htim1);")
    start_ccer_off_pos = pwm_start_outputs_body.find("TIM1->CCER &= ~PWM_CCER_ENABLE_MASK;")
    start_update_pos = pwm_start_outputs_body.find("TIM1->EGR = TIM_EVENTSOURCE_UPDATE;")
    start_counter_pos = pwm_start_outputs_body.find("__HAL_TIM_ENABLE(&htim1);")
    start_ccer_on_pos = pwm_start_outputs_body.find("TIM1->CCER |= PWM_CCER_ENABLE_MASK;")
    start_order_ok = (
        start_moe_disable_pos >= 0
        and start_ccer_off_pos > start_moe_disable_pos
        and start_update_pos > start_ccer_off_pos
        and start_counter_pos > start_update_pos
        and start_ccer_on_pos > start_counter_pos
    )
    if start_order_ok:
        cases.append(ok_case("pwm_start_outputs_stages_all_channels_before_moe", {"order": "MOE off -> CCER off -> UPDATE -> CEN -> CCER all"}))
    else:
        cases.append(
            fail_case(
                "pwm_start_outputs_stages_all_channels_before_moe",
                "TIM1 startup must load compare registers and enable all six CCER outputs before pwm_outputs_enable(true) raises MOE",
                {
                    "MOE_DISABLE": start_moe_disable_pos,
                    "CCER_OFF": start_ccer_off_pos,
                    "UPDATE": start_update_pos,
                    "COUNTER_ENABLE": start_counter_pos,
                    "CCER_ON": start_ccer_on_pos,
                },
            )
        )

    control_body = function_body(control_text, "void control_tick")
    disabled_branch_ok = (
        "if (!st->enabled || st->fault_latched || st->timeout_active)" in control_body
        and "pwm_safe_idle();" in control_body
        and "safety_set_pwm_active(false);" in control_body
    )
    if disabled_branch_ok:
        cases.append(ok_case("control_tick_holds_pwm_gpio_low_when_not_enabled", {"path": "!enabled/fault/timeout"}))
    else:
        cases.append(
            fail_case(
                "control_tick_holds_pwm_gpio_low_when_not_enabled",
                "control_tick() must continuously force TIM1 pins off while disabled, faulted, or timed out",
            )
        )

    control_update_body = function_body(control_text, "void control_update_from_cmd")
    protocol_decode_uses_named_offsets = (
        "u16le(cmd, CMD_OFF_DU)" in control_update_body
        and "u16le(cmd, CMD_OFF_DV)" in control_update_body
        and "u16le(cmd, CMD_OFF_DW)" in control_update_body
        and "u32le(cmd, CMD_OFF_DU)" in control_update_body
        and "u32le(cmd, CMD_OFF_DW)" in control_update_body
        and "i16le(cmd, CMD_OFF_DU)" in control_update_body
        and "i16le(cmd, CMD_OFF_DV)" in control_update_body
        and all(f"cmd[{idx}]" not in control_update_body for idx in range(6, 14))
    )
    if protocol_decode_uses_named_offsets:
        cases.append(ok_case("control_protocol_decode_uses_named_offsets", {"offsets": "CMD_OFF_DU/DV/DW"}))
    else:
        cases.append(
            fail_case(
                "control_protocol_decode_uses_named_offsets",
                "control_update_from_cmd() must decode motion payload via CMD_OFF_* helpers, not raw byte indexes",
            )
        )

    safety_set_pwm_active_body = function_body(safety_text, "void safety_set_pwm_active")
    safety_without_control_ack = safety_text.replace(safety_set_pwm_active_body, "")
    pwm_active_owned_by_control = (
        "mode_can_drive_pwm" in safety_text
        and "s_state.pwm_active = true" not in safety_without_control_ack
        and "s_state.pwm_active = true" in safety_set_pwm_active_body
        and "can_release_shutdown" in safety_set_pwm_active_body
        and "safety_set_pwm_active(true)" in control_text
        and "control_tick() is the only place" in safety_text
    )
    if pwm_active_owned_by_control:
        cases.append(ok_case("pwm_active_report_owned_by_control_tick", {"active_setter": "safety_set_pwm_active"}))
    else:
        cases.append(
            fail_case(
                "pwm_active_report_owned_by_control_tick",
                "safety layer must not report STATUS_PWM_ACTIVE until control_tick has applied duty and enabled TIM1",
            )
        )

    release_pos = safety_text.find("brake_set(false);")
    setter_pos = safety_text.find("void safety_set_pwm_active")
    shutdown_release_owned_by_control_ack = (
        setter_pos >= 0
        and release_pos > setter_pos
        and "can_release_shutdown" in safety_text
        and "s_state.enabled && !s_state.fault_latched && !s_state.timeout_active && !s_state.estop" in safety_text
    )
    if shutdown_release_owned_by_control_ack:
        cases.append(ok_case("em_stop_release_owned_by_control_ack", {"release_in": "safety_set_pwm_active(true)"}))
    else:
        cases.append(fail_case("em_stop_release_owned_by_control_ack", "EM_STOP must be released only after control_tick applies duty and enables TIM1"))

    fan_disabled = fan_pwm == 0 and fan_tach == 0
    fan_failsafe_ok = (
        "static void force_safe_outputs" in safety_text
        and "fan_control_set_pwm_q15(0);" in safety_text
        and "FAULT_OVERTEMP" in safety_text
        and "fan_control_set_pwm_q15(32767U);" in safety_text
    )
    if fan_disabled:
        cases.append(ok_case("fan_safe_output_and_overtemp_full_speed", {"USE_FAN_PWM": 0, "USE_FAN_TACH": 0, "status": "disabled"}))
    elif fan_failsafe_ok:
        cases.append(ok_case("fan_safe_output_and_overtemp_full_speed", {"safe_output": "fan=0", "overtemp": "fan=100%"}))
    else:
        cases.append(fail_case("fan_safe_output_and_overtemp_full_speed", "force_safe_outputs must clear fan unless OVERTEMP explicitly drives it full speed"))

    shared_safe_paths_ok = (
        safety_text.count("force_safe_outputs();") >= 5
        and "void safety_on_bad_frame" in safety_text
        and "FAULT_TIMEOUT" in safety_text
    )
    if shared_safe_paths_ok:
        cases.append(ok_case("fault_timeout_paths_share_force_safe_outputs", {"force_safe_outputs_calls": safety_text.count("force_safe_outputs();")}))
    else:
        cases.append(fail_case("fault_timeout_paths_share_force_safe_outputs", "fault, bad-frame and timeout paths must share force_safe_outputs()"))

    uart_cpp = repo / "bluepill_uart_pwm_pio" / "src" / "uart_link.cpp"
    uart_text = uart_cpp.read_text(encoding="utf-8", errors="replace")
    adc_text = adc_cpp.read_text(encoding="utf-8", errors="replace")
    uart_tx_timeout_ok = (
        "UART_TX_TIMEOUT_MS" in defs
        and "static bool wait_for_uart_flag" in uart_text
        and "HAL_GetTick() - started_ms" in uart_text
        and "bool uart_link_send" in uart_text
        and main_text.count("if (!uart_link_send") >= 4
        and "safety_on_bad_frame(FAULT_INTERNAL);" in main_text
    )
    if uart_tx_timeout_ok:
        cases.append(ok_case("uart_tx_timeout_forces_safe_fault", {"timeout_ms": int(macro_num(defs, "UART_TX_TIMEOUT_MS"))}))
    else:
        cases.append(fail_case("uart_tx_timeout_forces_safe_fault", "UART transmit must be bounded and force FAULT_INTERNAL instead of freezing active PWM"))

    uart_rx_errors_reported = (
        "s_rx_error_count" in uart_text
        and "uart_link_take_rx_error_count" in uart_text
        and "safety_note_bad_frames(uart_rx_errors);" in main_text
        and "saturating_add_u16" in safety_text
    )
    if uart_rx_errors_reported:
        cases.append(ok_case("uart_hardware_errors_are_saturated_and_reported", {"counter": "bad_cnt"}))
    else:
        cases.append(fail_case("uart_hardware_errors_are_saturated_and_reported", "UART framing/overrun and ring overflow errors must reach the saturated protocol bad counter"))

    proto_text = (repo / "bluepill_uart_pwm_pio" / "include" / "proto.h").read_text(encoding="utf-8", errors="replace")
    shutdown_readback_ok = (
        "STATUS_SHUTDOWN_RELEASED" in proto_text
        and "HAL_GPIO_ReadPin(EM_STOP_GPIO_PORT, EM_STOP_GPIO_PIN)" in safety_text
        and "status |= STATUS_SHUTDOWN_RELEASED;" in safety_text
    )
    if shutdown_readback_ok:
        cases.append(ok_case("shutdown_release_pin_readback_reported", {"status_bit": "0x40", "pin": "PB12"}))
    else:
        cases.append(fail_case("shutdown_release_pin_readback_reported", "Blue Pill reply must report the actual PB12 input level"))

    temp_fail_closed = (
        "s_state.heatsink_temp_fault = !sample_ok || adc_heatsink_fault_active();" in safety_text
        and "if (s_state.heatsink_temp_fault) return false;" in safety_text
        and "update_heatsink_temperature();" in safety_text
        and "if (!adc_heatsink_get(nullptr, &temp_c))" in adc_text
    )
    if temp_fail_closed:
        cases.append(ok_case("heatsink_sensor_failure_is_fail_closed", {"fault": "FAULT_OVERTEMP"}))
    else:
        cases.append(fail_case("heatsink_sensor_failure_is_fail_closed", "Temperature ADC failure must latch a fault and block CLEAR while the failure remains live"))

    bp_poles = float(macro_num(defs, "AS5600_POLE_PAIRS"))
    uno_path = repo / "UNOQ_MOTOR" / "UNOQ_MOTOR.ino"
    uq_poles = unoq_pole_pairs(uno_path)
    if unoq_uses_nucleo_mcsdk(uno_path):
        active_poles = nucleo_mcsdk_pole_pairs(repo)
        evidence = {"active_backend": "nucleo_mcsdk", "nucleo": active_poles, "unoq": uq_poles}
        if abs(active_poles - uq_poles) < 0.001:
            cases.append(ok_case("pole_pairs_match_active_backend", evidence))
        else:
            cases.append(fail_case("pole_pairs_match_active_backend", "Nucleo MCSDK and UNO Q pole-pair constants differ", evidence))
        if abs(bp_poles - uq_poles) >= 0.001:
            cases.append(
                warn_case(
                    "inactive_bluepill_pole_pairs_differ",
                    "Blue Pill is not the active motor backend; update its motor profile before enabling it again",
                    {"bluepill": bp_poles, "unoq": uq_poles},
                )
            )
    elif abs(bp_poles - uq_poles) < 0.001:
        cases.append(ok_case("pole_pairs_match_active_backend", {"active_backend": "bluepill", "bluepill": bp_poles, "unoq": uq_poles}))
    else:
        cases.append(fail_case("pole_pairs_match_active_backend", "Blue Pill and UNO Q pole-pair constants differ", {"bluepill": bp_poles, "unoq": uq_poles}))

    foc_require_hall = int(macro_num(defs, "FOC_REQUIRE_HALL"))
    cases.append(ok_case("foc_requires_sensor", {"FOC_REQUIRE_HALL": foc_require_hall}) if foc_require_hall == 1 else fail_case("foc_requires_sensor", "FOC open-loop fallback is enabled by config"))

    return cases


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    cases = run_checks(repo)
    failed = [c for c in cases if not c.ok and c.severity == "fail"]
    warnings = [c for c in cases if c.severity == "warn"]
    summary = {
        "tool": "firmware_config_safety_check",
        "pass": len(failed) == 0,
        "failed": len(failed),
        "warnings": len(warnings),
        "cases": [c.__dict__ for c in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if len(failed) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import serial

from active_pwm_guard import start_allowed_by_bench_gate

FRAME_LEN = 32
CRC_OFF = FRAME_LEN - 1
CMD_HDR0 = 0xAA
CMD_HDR1 = 0x55
RSP_HDR0 = 0x55
RSP_HDR1 = 0xAA

FLAG_ENABLE = 0x01
FLAG_ESTOP = 0x02
FLAG_DIAG_PWM = 0x04
FLAG_CLEAR_FAULT = 0x08
FLAG_VECTOR_ROTATE = 0x10

EXT_RESERVED_0 = 0x01
EXT_PFC_SYNC = 0x02
EXT_BRAKE_PWM = 0x04
EXT_PRECHARGE_RELAY = 0x08
PRECHARGE_RELAY_PRESENT = False

MODE_OFF = 0
MODE_DIAG = 1
MODE_DUTY = 2
MODE_SCALAR = 3
MODE_VECTOR = 4
MODE_FOC = 5

MAX_FREQ_HZ = 50.0
BP_VBUS_ZERO_RAW = 1966
BP_VBUS_CAL_RAW = 3459
BP_VBUS_CAL_V = 315.0
BP_TEMP_VREF = 3.3
BP_TEMP_SENSOR_NTC = 0
BP_TEMP_SENSOR_TSO = 1
BP_TEMP_SENSOR_MODE = BP_TEMP_SENSOR_TSO
BP_TEMP_PULLUP_OHM = 12000.0
BP_TEMP_NTC_R25_OHM = 85000.0
BP_TEMP_NTC_BETA_K = 4092.0
BP_TEMP_TSO_V25 = 1.16
BP_TEMP_TSO_MV_PER_C = 18.0
BP_TEMP_FLAG_VALID = 0x01
BP_TEMP_FLAG_FAULT = 0x02
BP_PHASE_VREF = 3.3
BP_PHASE_FLAG_VALID = 0x01
BP_PHASE_FLAG_C_VIRTUAL = 0x02

STATUS_LINK_OK = 0x01
STATUS_ENABLED = 0x02
STATUS_ESTOP = 0x04
STATUS_FAULT = 0x08
STATUS_TIMEOUT = 0x10
STATUS_PWM_ACTIVE = 0x20
START_LINK_MAX_AGE_S = 0.5
DEFAULT_CMD_GUARD_MAX_VDC = 60.0
VBUS_RAW_MIN_VALID = 1
VBUS_RAW_MAX_VALID = 4094
VBUS_RAW_WINDOW_MARGIN_V = 5.0
VBUS_RAW_ZERO_LOW_MARGIN = 128

FAULT_MAP = {
    0: "OK",
    1: "ESTOP",
    2: "TIMEOUT",
    3: "BAD_CRC",
    4: "BAD_HDR",
    5: "INTERNAL",
    6: "OVERTEMP",
}


def log(msg: str) -> None:
    print(msg, flush=True)


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def crc_xor(buf: bytes) -> int:
    c = 0
    for i in range(CRC_OFF):
        c ^= buf[i]
    return c & 0xFF


def temp_voltage(raw: int) -> float:
    return float(max(0, min(4095, raw))) * BP_TEMP_VREF / 4095.0


def vbus_voltage(raw: int) -> float:
    raw = max(0, min(4095, raw))
    if raw <= BP_VBUS_ZERO_RAW:
        return 0.0
    denom = float(BP_VBUS_CAL_RAW - BP_VBUS_ZERO_RAW)
    if denom <= 1.0:
        return 0.0
    return float(raw - BP_VBUS_ZERO_RAW) * (BP_VBUS_CAL_V / denom)


def vbus_raw_for_voltage(vdc: float) -> float:
    span = float(BP_VBUS_CAL_RAW - BP_VBUS_ZERO_RAW)
    return float(BP_VBUS_ZERO_RAW) + max(0.0, float(vdc)) * span / BP_VBUS_CAL_V


def phase_voltage(raw: int) -> float:
    return float(max(0, min(4095, raw))) * BP_PHASE_VREF / 4095.0


def temp_c(raw: int) -> float:
    raw = max(0, min(4095, raw))
    v = temp_voltage(raw)
    if raw <= 0 or raw >= 4095 or v <= 0.001 or v >= (BP_TEMP_VREF - 0.001):
        return 0.0
    if BP_TEMP_SENSOR_MODE == BP_TEMP_SENSOR_TSO:
        return 25.0 + ((v - BP_TEMP_TSO_V25) * 1000.0) / BP_TEMP_TSO_MV_PER_C
    r_ntc = BP_TEMP_PULLUP_OHM * v / (BP_TEMP_VREF - v)
    if not math.isfinite(r_ntc) or r_ntc <= 0:
        return 0.0
    inv_t = (1.0 / 298.15) + (math.log(r_ntc / BP_TEMP_NTC_R25_OHM) / BP_TEMP_NTC_BETA_K)
    if not math.isfinite(inv_t) or inv_t <= 0:
        return 0.0
    return (1.0 / inv_t) - 273.15


def read_frame(ser: serial.Serial, timeout_s: float) -> bytes | None:
    state = 0
    idx = 0
    buf = bytearray(FRAME_LEN)
    start = time.monotonic()
    while (time.monotonic() - start) < timeout_s:
        b = ser.read(1)
        if not b:
            continue
        val = b[0]
        if state == 0:
            if val == RSP_HDR0:
                buf[0] = val
                state = 1
        elif state == 1:
            if val == RSP_HDR1:
                buf[1] = val
                idx = 2
                state = 2
            elif val == RSP_HDR0:
                buf[0] = val
                state = 1
            else:
                state = 0
        else:
            buf[idx] = val
            idx += 1
            if idx >= FRAME_LEN:
                return bytes(buf)
    return None


def clamp01(x: float) -> float:
    if not math.isfinite(x):
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def clamp11(x: float) -> float:
    if not math.isfinite(x):
        return 0.0
    if x < -1.0:
        return -1.0
    if x > 1.0:
        return 1.0
    return x


def q15_from_unit(x: float) -> int:
    return int(clamp01(x) * 32767.0) & 0xFFFF


def q15_from_signed(x: float) -> int:
    return int(clamp11(x) * 32767.0) & 0xFFFF


def clamp_range(x: float, lo: float, hi: float) -> float:
    if not math.isfinite(x):
        raise ValueError("non-finite")
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def parse_bounded_float(raw: str, lo: float, hi: float) -> float:
    return clamp_range(float(raw), lo, hi)


def parse_on_off(raw: str) -> bool:
    val = raw.strip().upper()
    if val in ("1", "ON", "TRUE", "YES"):
        return True
    if val in ("0", "OFF", "FALSE", "NO"):
        return False
    raise ValueError(raw)


def clamp_freq_hz(x: float) -> float:
    return clamp_range(x, 0.0, MAX_FREQ_HZ)


class SharedState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.enable = False
        self.estop = False
        self.mode = MODE_OFF
        self.diag = False
        self.vector_rotate = False
        self.freq_hz = 5.0
        self.foc_freq_hz = 5.0
        self.mag = 0.30
        self.alpha = 0.3
        self.beta = 0.0
        self.id_ref = 0.0
        self.iq_ref = 0.3
        self.bp_foc_backend = False
        self.duty_u = 0.2
        self.duty_v = 0.2
        self.duty_w = 0.2
        self.ntc = False
        self.pfc = False
        self.precharge = False
        self.brake_pwm = False
        self.brake_duty = 0.0
        self.fan_duty = 0.0
        self.iotest = False
        self.clear_pending = False

        self.link_ok = False
        self.last_rsp = None  # type: bytes | None
        self.last_seq = 0
        self.last_rtt_ms = None  # type: float | None
        self.last_rx_time = 0.0
        self.miss_count = 0
        self.uart_port = ""
        self.uart_baud = 0
        self.uart_open = False
        self.uart_last_error = ""
        self.uart_error_count = 0
        self.uart_last_error_time = 0.0
        self.cmd_guard_max_vdc = DEFAULT_CMD_GUARD_MAX_VDC
        self.cmd_guard_allow_hv = False
        self.cmd_guard_disabled = False
        self.bench_gate_url = ""
        self.bench_gate_runner = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "enable": self.enable,
                "estop": self.estop,
                "mode": self.mode,
                "diag": self.diag,
                "vector_rotate": self.vector_rotate,
                "freq_hz": self.freq_hz,
                "foc_freq_hz": self.foc_freq_hz,
                "mag": self.mag,
                "alpha": self.alpha,
                "beta": self.beta,
                "id_ref": self.id_ref,
                "iq_ref": self.iq_ref,
                "bp_foc_backend": self.bp_foc_backend,
                "duty_u": self.duty_u,
                "duty_v": self.duty_v,
                "duty_w": self.duty_w,
                "ntc": self.ntc,
                "pfc": self.pfc,
                "precharge": self.precharge,
                "brake_pwm": self.brake_pwm,
                "brake_duty": self.brake_duty,
                "fan_duty": self.fan_duty,
                "iotest": self.iotest,
            }


def force_local_safe_outputs_locked(state: SharedState) -> None:
    # Called with state.lock held. Drop every output request that could be
    # replayed when a broken UART link recovers.
    state.enable = False
    state.mode = MODE_OFF
    state.diag = False
    state.vector_rotate = False
    state.bp_foc_backend = False
    state.ntc = False
    state.pfc = False
    state.precharge = False
    state.brake_pwm = False
    state.brake_duty = 0.0
    state.fan_duty = 0.0
    state.iotest = False
    state.clear_pending = False


def build_frame(state: SharedState, seq: int) -> bytes:
    frame = bytearray(FRAME_LEN)
    frame[0] = CMD_HDR0
    frame[1] = CMD_HDR1
    frame[2] = 0x02

    with state.lock:
        enable = state.enable
        estop = state.estop
        mode = state.mode
        diag = state.diag
        vector_rotate = state.vector_rotate
        freq_hz = state.freq_hz
        foc_freq_hz = state.foc_freq_hz
        mag = state.mag
        alpha = state.alpha
        beta = state.beta
        id_ref = state.id_ref
        iq_ref = state.iq_ref
        duty_u = state.duty_u
        duty_v = state.duty_v
        duty_w = state.duty_w
        pfc = state.pfc
        precharge = state.precharge
        brake_pwm = state.brake_pwm
        brake_duty = state.brake_duty
        fan_duty = state.fan_duty
        clear_pending = state.clear_pending
        if clear_pending:
            state.clear_pending = False

    flags = 0
    if clear_pending:
        flags |= FLAG_CLEAR_FAULT
        enable = False
        estop = False
        mode = MODE_OFF
        diag = False
        pfc = False
        precharge = False
        brake_pwm = False
        brake_duty = 0.0
        fan_duty = 0.0
    if enable:
        flags |= FLAG_ENABLE
    if estop:
        flags |= FLAG_ESTOP
    if diag:
        flags |= FLAG_DIAG_PWM
    if vector_rotate:
        flags |= FLAG_VECTOR_ROTATE

    frame[3] = flags
    frame[4] = mode & 0xFF
    frame[5] = seq & 0xFF

    if mode == MODE_OFF:
        pass
    elif mode == MODE_DIAG:
        pass
    elif mode == MODE_DUTY:
        du = q15_from_unit(duty_u)
        dv = q15_from_unit(duty_v)
        dw = q15_from_unit(duty_w)
        frame[6] = du & 0xFF
        frame[7] = (du >> 8) & 0xFF
        frame[8] = dv & 0xFF
        frame[9] = (dv >> 8) & 0xFF
        frame[10] = dw & 0xFF
        frame[11] = (dw >> 8) & 0xFF
    elif mode == MODE_VECTOR and not vector_rotate:
        a = q15_from_signed(alpha)
        b = q15_from_signed(beta)
        frame[6] = a & 0xFF
        frame[7] = (a >> 8) & 0xFF
        frame[8] = b & 0xFF
        frame[9] = (b >> 8) & 0xFF
    elif mode == MODE_FOC:
        id_q15 = q15_from_signed(id_ref)
        iq_q15 = q15_from_signed(iq_ref)
        frame[6] = id_q15 & 0xFF
        frame[7] = (id_q15 >> 8) & 0xFF
        frame[8] = iq_q15 & 0xFF
        frame[9] = (iq_q15 >> 8) & 0xFF
        foc_mhz = int(max(0.0, foc_freq_hz) * 1000.0)
        frame[10] = foc_mhz & 0xFF
        frame[11] = (foc_mhz >> 8) & 0xFF
        frame[12] = (foc_mhz >> 16) & 0xFF
        frame[13] = (foc_mhz >> 24) & 0xFF
    else:
        freq_mhz = int(max(0.0, freq_hz) * 1000.0)
        frame[6] = freq_mhz & 0xFF
        frame[7] = (freq_mhz >> 8) & 0xFF
        frame[8] = (freq_mhz >> 16) & 0xFF
        frame[9] = (freq_mhz >> 24) & 0xFF
        mag_q15 = q15_from_unit(mag)
        frame[10] = mag_q15 & 0xFF
        frame[11] = (mag_q15 >> 8) & 0xFF

    ext_flags = 0
    if pfc:
        ext_flags |= EXT_PFC_SYNC
    if brake_pwm and brake_duty > 0.0:
        ext_flags |= EXT_BRAKE_PWM
    if PRECHARGE_RELAY_PRESENT and precharge:
        ext_flags |= EXT_PRECHARGE_RELAY
    frame[14] = ext_flags & 0xFF
    brake_q15 = q15_from_unit(brake_duty if brake_pwm else 0.0)
    frame[15] = brake_q15 & 0xFF
    frame[16] = (brake_q15 >> 8) & 0xFF
    fan_q15 = q15_from_unit(fan_duty)
    frame[17] = fan_q15 & 0xFF
    frame[18] = (fan_q15 >> 8) & 0xFF

    frame[CRC_OFF] = crc_xor(frame)
    return bytes(frame)


def parse_rsp(state: SharedState, rsp: bytes, rtt_ms: float) -> None:
    if len(rsp) != FRAME_LEN:
        return
    if rsp[0] != RSP_HDR0 or rsp[1] != RSP_HDR1:
        return
    if rsp[CRC_OFF] != crc_xor(rsp):
        return

    status = rsp[3]
    with state.lock:
        state.link_ok = (status & STATUS_LINK_OK) != 0
        state.last_rsp = rsp
        state.last_seq = rsp[4]
        state.last_rtt_ms = rtt_ms
        state.last_rx_time = time.monotonic()
        state.miss_count = 0


def output_permitted_locked(state: SharedState, what: str) -> tuple[bool, str]:
    if state.estop:
        return False, "estop latched"
    if not state.link_ok or state.last_rsp is None:
        return False, "bluepill link not ready"
    if state.last_rx_time <= 0.0 or (time.monotonic() - state.last_rx_time) > START_LINK_MAX_AGE_S:
        return False, "bluepill link stale"
    rsp = state.last_rsp
    status = int(rsp[3])
    bad = int(rsp[7] | (rsp[8] << 8))
    fault = int(rsp[9])
    vbus_raw = min(4095, int(rsp[17] | (rsp[18] << 8)))
    vdc = vbus_voltage(vbus_raw)
    if (status & STATUS_ESTOP) != 0:
        return False, "bluepill estop active"
    if (status & STATUS_TIMEOUT) != 0:
        return False, "bluepill timeout active"
    if (status & STATUS_FAULT) != 0 or fault != 0:
        return False, f"bluepill fault active: {FAULT_MAP.get(fault, fault)}"
    if (status & STATUS_PWM_ACTIVE) != 0:
        return False, f"bluepill PWM active before {what}"
    if bad != 0:
        return False, f"bluepill bad counter non-zero: {bad}"
    if not (state.cmd_guard_allow_hv or state.cmd_guard_disabled):
        if vdc > state.cmd_guard_max_vdc:
            return False, f"DC bus too high for {what}: {vdc:.1f} V"
        if vbus_raw < VBUS_RAW_MIN_VALID or vbus_raw > VBUS_RAW_MAX_VALID:
            return False, f"raw DC bus telemetry invalid before {what}: raw={vbus_raw}"
        if state.cmd_guard_max_vdc <= DEFAULT_CMD_GUARD_MAX_VDC:
            raw_min = BP_VBUS_ZERO_RAW - VBUS_RAW_ZERO_LOW_MARGIN
            raw_max = math.ceil(vbus_raw_for_voltage(state.cmd_guard_max_vdc + VBUS_RAW_WINDOW_MARGIN_V))
            if vbus_raw < raw_min or vbus_raw > raw_max:
                return False, f"raw DC bus outside calibrated low-voltage window before {what}: raw={vbus_raw} expected={raw_min}..{raw_max}"
    return True, "ok"


def start_permitted_locked(state: SharedState) -> tuple[bool, str]:
    if state.mode == MODE_OFF:
        return False, "mode off"
    if state.mode == MODE_FOC and not state.bp_foc_backend:
        return False, "bpfoc backend off"
    return output_permitted_locked(state, "START")


def start_bench_gate_permitted(state: SharedState) -> tuple[bool, str]:
    logs: list[str] = []
    runner = state.bench_gate_runner
    if runner is not None:
        ok = bool(runner(logs.append, state.bench_gate_url or None))
    else:
        ok = bool(start_allowed_by_bench_gate(logs.append, url=state.bench_gate_url or None))
    if ok:
        return True, "ok"
    detail = "; ".join(logs) if logs else "bench gate refused START"
    return False, f"bench gate blocked START: {detail}"


def status_payload(state: SharedState) -> dict[str, Any]:
    with state.lock:
        rsp = state.last_rsp
        link_ok = state.link_ok
        last_rtt = state.last_rtt_ms
        last_rx = state.last_rx_time
        miss_count = state.miss_count
        uart_port = state.uart_port
        uart_baud = state.uart_baud
        uart_open = state.uart_open
        uart_last_error = state.uart_last_error
        uart_error_count = state.uart_error_count
        uart_last_error_time = state.uart_last_error_time
        mode = state.mode
        enable = state.enable
        estop = state.estop
        freq_hz = state.freq_hz
        foc_freq_hz = state.foc_freq_hz
        bp_foc_backend_cmd = state.bp_foc_backend
        ntc_cmd = state.ntc
        pfc_cmd = state.pfc
        precharge_cmd = state.precharge
        brake_pwm_cmd = state.brake_pwm
        brake_duty_cmd = state.brake_duty
        fan_duty_cmd = state.fan_duty
        iotest_cmd = state.iotest
    data: dict[str, Any] = {
        "link": bool(link_ok),
        "enable": bool(enable),
        "estop": bool(estop),
        "freq_cmd": float(freq_hz),
        "foc_freq_cmd": float(foc_freq_hz),
        "mode_cmd": mode,
        "bp_foc_backend": int(1 if bp_foc_backend_cmd else 0),
        "ntc_cmd": bool(ntc_cmd),
        "pfc_cmd": bool(pfc_cmd),
        "precharge_cmd": bool(precharge_cmd),
        "brake_pwm_cmd": bool(brake_pwm_cmd),
        "brake_duty_cmd": float(brake_duty_cmd),
        "fan_duty_cmd": float(fan_duty_cmd),
        "iotest": int(1 if iotest_cmd else 0),
        "ntc": int(1 if ntc_cmd else 0),
        "pfc": int(1 if pfc_cmd else 0),
        "precharge": int(1 if precharge_cmd else 0),
        "brake": int(1 if brake_pwm_cmd else 0),
        "brake_pwm": int(1 if brake_pwm_cmd else 0),
        "brake_duty": float(brake_duty_cmd),
        "fan_duty": float(fan_duty_cmd),
        "last_rtt_ms": last_rtt,
        "last_rx_age_s": (time.monotonic() - last_rx) if last_rx > 0 else None,
        "miss_count": int(miss_count),
        "uart_port": uart_port,
        "uart_baud": int(uart_baud),
        "uart_open": bool(uart_open),
        "uart_last_error": uart_last_error,
        "uart_error_count": int(uart_error_count),
        "uart_last_error_age_s": (time.monotonic() - uart_last_error_time) if uart_last_error_time > 0 else None,
        "state": "NO_LINK",
        "status_flags": 0,
        "bp_status": 0,
        "pwm": 0,
        "timeout": 1,
        "fault": 255,
        "bp_fault": 255,
        "fault_text": "NO_RSP",
        "good": 0,
        "bad": 999999,
        "bp_good": 0,
        "bp_bad": 999999,
        "bp_bad_cnt": 999999,
        "bp_age_ms": 999999,
        "bp_rsp_age_ms": 999999,
        "bp_vbus_raw": 0,
        "bp_vdc": 0.0,
        "bp_vbus_age_ms": 999999,
        "bp_temp_raw": 0,
        "bp_temp_v": 0.0,
        "bp_temp_c": 0.0,
        "bp_temp_flags": 0,
        "bp_temp_valid": 0,
        "bp_temp_fault": 0,
        "bp_temp_age_ms": 999999,
        "bp_ext_flags": 0,
        "bp_ext": 0,
        "bp_ntc": 0,
        "bp_pfc": 0,
        "bp_precharge": 0,
        "bp_brake_pwm": 0,
        "bp_brake_duty": 0.0,
        "bp_fan_duty": 0.0,
        "bp_fan_rpm": 0,
        "bp_phase_a_raw": 0,
        "bp_phase_b_raw": 0,
        "bp_phase_c_raw": 0,
        "bp_phase_a_v": 0.0,
        "bp_phase_b_v": 0.0,
        "bp_phase_c_v": 0.0,
        "bp_phase_flags": 0,
        "bp_phase_valid": 0,
        "bp_phase_c_virtual": 0,
        "bp_phase_age_ms": 999999,
        "vdc": 0.0,
        "last_mode": MODE_OFF,
        "bp_mode": MODE_OFF,
        "bp_cmd_mode": MODE_OFF,
    }
    if rsp:
        rx_age_ms = int((time.monotonic() - last_rx) * 1000.0) if last_rx > 0 else 999999
        status = rsp[3]
        good = rsp[5] | (rsp[6] << 8)
        bad = rsp[7] | (rsp[8] << 8)
        fault = rsp[9]
        last_mode = rsp[10]
        vbus_raw = min(4095, rsp[17] | (rsp[18] << 8))
        bp_vdc = vbus_voltage(vbus_raw)
        temp_raw = min(4095, rsp[19] | (rsp[20] << 8))
        temp_flags = rsp[21]
        ext_flags = rsp[14]
        brake_q15 = rsp[15] | (rsp[16] << 8)
        fan_duty_q8 = rsp[22]
        fan_tach_x30 = rsp[30]
        bp_temp_v = temp_voltage(temp_raw)
        bp_temp_c = temp_c(temp_raw) if (temp_flags & BP_TEMP_FLAG_VALID) else 0.0
        phase_a_raw = min(4095, rsp[23] | (rsp[24] << 8))
        phase_b_raw = min(4095, rsp[25] | (rsp[26] << 8))
        phase_c_raw = min(4095, rsp[27] | (rsp[28] << 8))
        phase_flags = rsp[29]
        state_text = "FAULT" if (status & STATUS_FAULT) else ("RUN" if (status & STATUS_PWM_ACTIVE) else "SAFE")
        data.update(
            {
                "state": state_text,
                "status_flags": status,
                "bp_status": status,
                "pwm": int(1 if (status & STATUS_PWM_ACTIVE) else 0),
                "timeout": int(1 if (status & STATUS_TIMEOUT) else 0),
                "estop": int(1 if (status & STATUS_ESTOP) else 0),
                "fault": int(fault),
                "bp_fault": int(fault),
                "fault_text": FAULT_MAP.get(int(fault), "UNKNOWN"),
                "good": int(good),
                "bad": int(bad),
                "bp_good": int(good),
                "bp_bad": int(bad),
                "bp_bad_cnt": int(bad),
                "bp_age_ms": rx_age_ms,
                "bp_rsp_age_ms": rx_age_ms,
                "bp_vbus_raw": int(vbus_raw),
                "bp_vdc": bp_vdc,
                "bp_vbus_age_ms": rx_age_ms,
                "bp_temp_raw": int(temp_raw),
                "bp_temp_v": bp_temp_v,
                "bp_temp_c": bp_temp_c,
                "bp_temp_flags": int(temp_flags),
                "bp_temp_valid": int(1 if (temp_flags & BP_TEMP_FLAG_VALID) else 0),
                "bp_temp_fault": int(1 if (temp_flags & BP_TEMP_FLAG_FAULT) else 0),
                "bp_temp_age_ms": rx_age_ms,
                "bp_ext_flags": int(ext_flags),
                "bp_ext": int(ext_flags),
                "bp_ntc": 0,
                "bp_pfc": int(1 if (ext_flags & EXT_PFC_SYNC) else 0),
                "bp_precharge": int(1 if (ext_flags & EXT_PRECHARGE_RELAY) else 0),
                "bp_brake_pwm": int(1 if (ext_flags & EXT_BRAKE_PWM) else 0),
                "bp_brake_duty": float(min(brake_q15, 32767) / 32767.0),
                "bp_fan_duty": float(fan_duty_q8 / 255.0),
                "bp_fan_rpm": int(fan_tach_x30 * 30),
                "bp_phase_a_raw": int(phase_a_raw),
                "bp_phase_b_raw": int(phase_b_raw),
                "bp_phase_c_raw": int(phase_c_raw),
                "bp_phase_a_v": phase_voltage(phase_a_raw),
                "bp_phase_b_v": phase_voltage(phase_b_raw),
                "bp_phase_c_v": phase_voltage(phase_c_raw),
                "bp_phase_flags": int(phase_flags),
                "bp_phase_valid": int(1 if (phase_flags & BP_PHASE_FLAG_VALID) else 0),
                "bp_phase_c_virtual": int(1 if (phase_flags & BP_PHASE_FLAG_C_VIRTUAL) else 0),
                "bp_phase_age_ms": rx_age_ms,
                "vdc": bp_vdc,
                "last_mode": int(last_mode),
                "bp_mode": int(last_mode),
                "bp_cmd_mode": int(mode),
                "bp_foc_backend": int(1 if bp_foc_backend_cmd else 0),
            }
        )
    return data


def apply_cmd(state: SharedState, cmd: str) -> tuple[bool, str]:
    cmd = cmd.strip()
    if not cmd:
        return False, "empty cmd"
    parts = cmd.split()
    head = parts[0].upper()

    if head == "START":
        if len(parts) != 1:
            return False, "bad start args"
        with state.lock:
            ok, msg = start_permitted_locked(state)
        if not ok:
            return False, msg
        ok, msg = start_bench_gate_permitted(state)
        if not ok:
            return False, msg
        with state.lock:
            ok, msg = start_permitted_locked(state)
            if not ok:
                return False, msg
            state.enable = True
            return True, "ok"

    with state.lock:
        if head == "STOP":
            if len(parts) != 1:
                return False, "bad stop args"
            state.enable = False
            return True, "ok"
        if head == "ESTOP":
            if len(parts) == 2 and parts[1].upper() == "CLEAR":
                state.estop = False
                state.enable = False
                state.ntc = False
                state.pfc = False
                state.precharge = False
                state.brake_pwm = False
                state.brake_duty = 0.0
                state.fan_duty = 0.0
                state.bp_foc_backend = False
                state.iotest = False
                state.clear_pending = True
                return True, "ok"
            if len(parts) != 1:
                return False, "bad estop args"
            state.estop = True
            state.enable = False
            state.ntc = False
            state.pfc = False
            state.precharge = False
            state.brake_pwm = False
            state.brake_duty = 0.0
            state.fan_duty = 0.0
            state.bp_foc_backend = False
            state.iotest = False
            state.clear_pending = False
            return True, "ok"
        if head == "CLEAR":
            if len(parts) != 1:
                return False, "bad clear args"
            state.enable = False
            state.estop = False
            state.ntc = False
            state.pfc = False
            state.precharge = False
            state.brake_pwm = False
            state.brake_duty = 0.0
            state.fan_duty = 0.0
            state.bp_foc_backend = False
            state.iotest = False
            state.clear_pending = True
            return True, "ok"
        if head == "IOTEST":
            if len(parts) != 2:
                return False, "bad iotest args"
            try:
                next_iotest = parse_on_off(parts[1])
            except ValueError:
                return False, "bad iotest"
            if next_iotest:
                ok, msg = output_permitted_locked(state, "IOTEST")
                if not ok:
                    return False, msg
            state.iotest = next_iotest
            if not next_iotest:
                state.ntc = False
                state.pfc = False
                state.precharge = False
                state.brake_pwm = False
                state.brake_duty = 0.0
                state.fan_duty = 0.0
            state.enable = False
            state.mode = MODE_OFF
            state.bp_foc_backend = False
            state.diag = False
            return True, "ok"
        if head == "BPFOC":
            if len(parts) != 2:
                return False, "bad bpfoc args"
            try:
                next_bpfoc = parse_on_off(parts[1])
            except ValueError:
                return False, "bad bpfoc"
            if next_bpfoc:
                ok, msg = output_permitted_locked(state, "BPFOC")
                if not ok:
                    return False, msg
                state.enable = False
                state.mode = MODE_FOC
                state.diag = False
                state.vector_rotate = False
                state.bp_foc_backend = True
                return True, "ok"
            state.enable = False
            state.bp_foc_backend = False
            if state.mode == MODE_FOC:
                state.mode = MODE_OFF
            state.diag = False
            state.vector_rotate = False
            return True, "ok"
        if head == "MODE":
            if len(parts) != 2:
                return False, "bad mode args"
            mode = parts[1].upper()
            next_mode = state.mode
            next_diag = False
            next_vector_rotate = state.vector_rotate
            if mode in ("VF", "SCALAR"):
                next_mode = MODE_SCALAR
                next_vector_rotate = False
            elif mode in ("VECTOR", "VEC"):
                next_mode = MODE_VECTOR
            elif mode in ("FOC",):
                next_mode = MODE_FOC
            elif mode in ("DUTY",):
                next_mode = MODE_DUTY
            elif mode in ("DIAG",):
                next_mode = MODE_DIAG
                next_diag = True
            elif mode in ("OFF",):
                next_mode = MODE_OFF
            else:
                return False, f"unknown mode {mode}"
            if state.enable and next_mode != state.mode:
                state.enable = False
            state.mode = next_mode
            if next_mode != MODE_FOC:
                state.bp_foc_backend = False
            state.vector_rotate = next_vector_rotate
            state.diag = next_diag
            return True, "ok"
        if head == "DIAG":
            if len(parts) != 2:
                return False, "bad diag args"
            try:
                diag_on = parse_on_off(parts[1])
            except ValueError:
                return False, "bad diag"
            if state.enable and ((diag_on and state.mode != MODE_DIAG) or (not diag_on and state.mode == MODE_DIAG)):
                state.enable = False
            state.diag = diag_on
            state.mode = MODE_DIAG if diag_on else MODE_OFF
            state.bp_foc_backend = False
            state.vector_rotate = False
            return True, "ok"
        if head == "FREQ":
            if len(parts) != 2:
                return False, "bad freq args"
            try:
                f = clamp_freq_hz(float(parts[1]))
            except ValueError:
                return False, "bad freq"
            state.freq_hz = f
            state.foc_freq_hz = f
            return True, "ok"
        if head == "FOC_FREQ":
            if len(parts) != 2:
                return False, "bad foc_freq args"
            try:
                f = clamp_freq_hz(float(parts[1]))
            except ValueError:
                return False, "bad foc_freq"
            state.foc_freq_hz = f
            return True, "ok"
        if head == "MAG":
            if len(parts) != 2:
                return False, "bad mag args"
            try:
                state.mag = parse_bounded_float(parts[1], 0.0, 1.0)
            except ValueError:
                return False, "bad mag"
            return True, "ok"
        if head == "ALPHA":
            if len(parts) != 2:
                return False, "bad alpha args"
            try:
                state.alpha = parse_bounded_float(parts[1], -1.0, 1.0)
            except ValueError:
                return False, "bad alpha"
            return True, "ok"
        if head == "BETA":
            if len(parts) != 2:
                return False, "bad beta args"
            try:
                state.beta = parse_bounded_float(parts[1], -1.0, 1.0)
            except ValueError:
                return False, "bad beta"
            return True, "ok"
        if head == "ID":
            if len(parts) != 2:
                return False, "bad id args"
            try:
                state.id_ref = parse_bounded_float(parts[1], -1.0, 1.0)
            except ValueError:
                return False, "bad id"
            return True, "ok"
        if head == "IQ":
            if len(parts) != 2:
                return False, "bad iq args"
            try:
                state.iq_ref = parse_bounded_float(parts[1], -1.0, 1.0)
            except ValueError:
                return False, "bad iq"
            return True, "ok"
        if head == "DUTY":
            vals = parts[1:]
            if not vals:
                return False, "missing duty"
            try:
                flt = [parse_bounded_float(v, 0.0, 1.0) for v in vals]
            except ValueError:
                return False, "bad duty"
            if len(flt) == 1:
                state.duty_u = flt[0]
                state.duty_v = flt[0]
                state.duty_w = flt[0]
            elif len(flt) == 3:
                state.duty_u = flt[0]
                state.duty_v = flt[1]
                state.duty_w = flt[2]
            else:
                return False, "need 1 or 3 duty values"
            if state.enable and state.mode != MODE_DUTY:
                state.enable = False
            state.mode = MODE_DUTY
            return True, "ok"
        if head == "FAN":
            if len(parts) == 2:
                val = parts[1].upper()
                if val == "ON":
                    ok, msg = output_permitted_locked(state, "FAN")
                    if not ok:
                        return False, msg
                    state.fan_duty = 1.0
                    return True, "ok"
                if val == "OFF":
                    state.fan_duty = 0.0
                    return True, "ok"
                try:
                    next_fan_duty = parse_bounded_float(parts[1], 0.0, 1.0)
                except ValueError:
                    return False, "bad fan"
                if next_fan_duty > 0.0:
                    ok, msg = output_permitted_locked(state, "FAN")
                    if not ok:
                        return False, msg
                state.fan_duty = next_fan_duty
                return True, "ok"
            if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
                try:
                    next_fan_duty = parse_bounded_float(parts[2], 0.0, 1.0)
                except ValueError:
                    return False, "bad fan duty"
                if next_fan_duty > 0.0:
                    ok, msg = output_permitted_locked(state, "FAN")
                    if not ok:
                        return False, msg
                state.fan_duty = next_fan_duty
                return True, "ok"
            return False, "bad fan args"
        if head == "PRECHARGE":
            if not PRECHARGE_RELAY_PRESENT:
                state.precharge = False
                return False, "unsupported: precharge relay is not installed"
            if len(parts) != 2:
                return False, "bad precharge args"
            try:
                next_precharge = parse_on_off(parts[1])
            except ValueError:
                return False, "bad precharge"
            if next_precharge:
                ok, msg = output_permitted_locked(state, "PRECHARGE")
                if not ok:
                    return False, msg
            state.precharge = next_precharge
            return True, "ok"
        if head == "NTC":
            state.ntc = False
            return False, "unsupported: STEVAL J2-21 is not connected"
        if head == "PFC":
            if len(parts) != 2:
                return False, "bad pfc args"
            try:
                next_pfc = parse_on_off(parts[1])
            except ValueError:
                return False, "bad pfc"
            if next_pfc:
                ok, msg = output_permitted_locked(state, "PFC")
                if not ok:
                    return False, msg
            state.pfc = next_pfc
            return True, "ok"
        if head == "BRAKE":
            if len(parts) == 2:
                val = parts[1].upper()
                if val == "OFF":
                    state.brake_pwm = False
                    state.brake_duty = 0.0
                    return True, "ok"
                try:
                    next_brake_duty = parse_bounded_float(parts[1], 0.0, 1.0)
                except ValueError:
                    return False, "bad brake"
                if next_brake_duty > 0.0:
                    ok, msg = output_permitted_locked(state, "BRAKE")
                    if not ok:
                        return False, msg
                state.brake_duty = next_brake_duty
                state.brake_pwm = state.brake_duty > 0.0
                return True, "ok"
            if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
                try:
                    next_brake_duty = parse_bounded_float(parts[2], 0.0, 1.0)
                except ValueError:
                    return False, "bad brake duty"
                if next_brake_duty > 0.0:
                    ok, msg = output_permitted_locked(state, "BRAKE")
                    if not ok:
                        return False, msg
                state.brake_duty = next_brake_duty
                state.brake_pwm = state.brake_duty > 0.0
                return True, "ok"
            return False, "bad brake args"
        if head == "VROT":
            if len(parts) != 2:
                return False, "bad vrot args"
            val = parts[1].upper()
            try:
                next_vector_rotate = parse_on_off(val)
            except ValueError:
                return False, "bad vrot"
            if state.enable and state.mode == MODE_VECTOR and next_vector_rotate != state.vector_rotate:
                state.enable = False
            state.vector_rotate = next_vector_rotate
            return True, "ok"
        if head == "SET":
            if len(parts) != 3:
                return False, "bad set args"
            key = parts[1].upper()
            val = parts[2]
            if key == "FREQ":
                try:
                    f = clamp_freq_hz(float(val))
                except ValueError:
                    return False, "bad freq"
                state.freq_hz = f
                state.foc_freq_hz = f
                return True, "ok"
            if key == "MAG":
                try:
                    state.mag = parse_bounded_float(val, 0.0, 1.0)
                except ValueError:
                    return False, "bad mag"
                return True, "ok"
            return False, f"unknown set {key}"
    return False, f"unknown cmd: {cmd}"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send(code, body)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            data = status_payload(self.server.state)  # type: ignore[attr-defined]
            self._send_json(200, {"ok": True, "data": data})
            return
        if self.path in ("/", "/index.html"):
            html = self.server.html  # type: ignore[attr-defined]
            self._send(200, html, "text/html; charset=utf-8")
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path.startswith("/api/cmd"):
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                self._send_json(400, {"ok": False, "error": "bad json"})
                return
            cmd = body.get("cmd", "")
            ok, msg = apply_cmd(self.server.state, str(cmd))  # type: ignore[attr-defined]
            if ok:
                self._send_json(200, {"ok": True})
            else:
                self._send_json(400, {"ok": False, "error": msg})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        return


HTML_UI = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Blue Pill Direct Control</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #0f1115; color: #e6e9ef; }
    .wrap { max-width: 980px; margin: 0 auto; padding: 16px; }
    .card { background: #171a21; border-radius: 12px; padding: 12px 16px; margin-bottom: 12px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .btn { padding: 10px 14px; border: 0; border-radius: 8px; background: #2b6cb0; color: #fff; cursor: pointer; }
    .btn.warn { background: #f59e0b; }
    .btn.danger { background: #d64545; }
    .btn.ghost { background: #1f2430; color: #e6e9ef; }
    label { font-size: 12px; color: #aab1c2; display: block; margin-bottom: 4px; }
    input, select { padding: 8px; border-radius: 8px; border: 1px solid #2a2f3a; background: #0f1115; color: #e6e9ef; }
    .k { color: #aab1c2; }
    .v { font-weight: 600; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <h2>Blue Pill Direct PWM Control</h2>
    <div class="card">
      <div class="row">
        <button class="btn" onclick="sendCmd('START')">START</button>
        <button class="btn ghost" onclick="sendCmd('STOP')">STOP</button>
        <button class="btn danger" onclick="sendCmd('ESTOP')">ESTOP</button>
        <button class="btn warn" onclick="sendCmd('ESTOP CLEAR')">CLEAR</button>
      </div>
    </div>

    <div class="card grid">
      <div>
        <label>Mode</label>
        <select id="mode" onchange="onMode()">
          <option value="VF">VF (Scalar)</option>
          <option value="FOC">FOC</option>
          <option value="VECTOR">Vector</option>
          <option value="DUTY">Duty</option>
          <option value="DIAG">Diag</option>
          <option value="OFF">Off</option>
        </select>
      </div>
      <div>
        <label>Freq (Hz)</label>
        <input id="freq" type="number" step="0.1" min="0" max="50" value="5.0" oninput="onFreq()">
      </div>
      <div>
        <label>Mag (0..1)</label>
        <input id="mag" type="number" step="0.01" min="0" max="1" value="0.30" oninput="onMag()">
      </div>
      <div>
        <label>Vector Alpha/Beta (-1..1)</label>
        <div class="row">
          <input id="alpha" type="number" step="0.01" min="-1" max="1" value="0.30" oninput="onAlpha()">
          <input id="beta" type="number" step="0.01" min="-1" max="1" value="0.00" oninput="onBeta()">
        </div>
      </div>
      <div>
        <label>FOC Id/Iq (-1..1)</label>
        <div class="row">
          <input id="id" type="number" step="0.01" min="-1" max="1" value="0.00" oninput="onId()">
          <input id="iq" type="number" step="0.01" min="-1" max="1" value="0.30" oninput="onIq()">
        </div>
      </div>
      <div>
        <label>Duty U/V/W (0..1)</label>
        <div class="row">
          <input id="du" type="number" step="0.01" min="0" max="1" value="0.20" oninput="onDuty()">
          <input id="dv" type="number" step="0.01" min="0" max="1" value="0.20" oninput="onDuty()">
          <input id="dw" type="number" step="0.01" min="0" max="1" value="0.20" oninput="onDuty()">
        </div>
      </div>
    </div>

    <div class="card">
      <h3>Service IO (no motor START required)</h3>
      <div class="row">
        <span>Precharge relay: not installed (PB4 disabled)</span>
        <button class="btn ghost" onclick="sendCmd('PFC ON')">PFC ON</button>
        <button class="btn ghost" onclick="sendCmd('PFC OFF')">PFC OFF</button>
        <button class="btn ghost" onclick="sendCmd('BPFOC ON')">BPFOC ON</button>
        <button class="btn ghost" onclick="sendCmd('BPFOC OFF')">BPFOC OFF</button>
      </div>
      <div class="row" style="margin-top:12px">
        <div>
          <label>Fan duty (0..1)</label>
          <input id="fan" type="number" step="0.05" min="0" max="1" value="0.00" oninput="onFan()">
        </div>
        <div>
          <label>Brake PWM duty (0..1)</label>
          <input id="brake" type="number" step="0.05" min="0" max="1" value="0.00" oninput="onBrake()">
        </div>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <div><span class="k">Link:</span> <span id="link" class="v">-</span></div>
        <div><span class="k">UART:</span> <span id="uart" class="v">-</span></div>
        <div><span class="k">UART err:</span> <span id="uart_err" class="v">-</span></div>
        <div><span class="k">PWM:</span> <span id="pwm" class="v">-</span></div>
        <div><span class="k">Fault:</span> <span id="fault" class="v">-</span></div>
        <div><span class="k">Timeout:</span> <span id="timeout" class="v">-</span></div>
        <div><span class="k">RTT ms:</span> <span id="rtt" class="v">-</span></div>
        <div><span class="k">PRE:</span> <span id="precharge" class="v">-</span></div>
        <div><span class="k">PFC:</span> <span id="pfc" class="v">-</span></div>
        <div><span class="k">Fan:</span> <span id="fan_state" class="v">-</span></div>
        <div><span class="k">Tach rpm:</span> <span id="tach" class="v">-</span></div>
        <div><span class="k">Brake:</span> <span id="brake_state" class="v">-</span></div>
        <div><span class="k">BPFOC:</span> <span id="bpfoc_state" class="v">-</span></div>
      </div>
    </div>
  </div>
  <script>
    async function sendCmd(cmd) {
      await fetch('/api/cmd', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({cmd})
      });
    }
    function onMode(){ sendCmd('MODE ' + document.getElementById('mode').value); }
    function onFreq(){ sendCmd('FREQ ' + document.getElementById('freq').value); }
    function onMag(){ sendCmd('MAG ' + document.getElementById('mag').value); }
    function onAlpha(){ sendCmd('ALPHA ' + document.getElementById('alpha').value); }
    function onBeta(){ sendCmd('BETA ' + document.getElementById('beta').value); }
    function onId(){ sendCmd('ID ' + document.getElementById('id').value); }
    function onIq(){ sendCmd('IQ ' + document.getElementById('iq').value); }
    function onFan(){ sendCmd('FAN PWM ' + document.getElementById('fan').value); }
    function onBrake(){ sendCmd('BRAKE PWM ' + document.getElementById('brake').value); }
    function onDuty(){
      const u = document.getElementById('du').value;
      const v = document.getElementById('dv').value;
      const w = document.getElementById('dw').value;
      sendCmd('DUTY ' + u + ' ' + v + ' ' + w);
    }
    async function poll() {
      try {
        const r = await fetch('/api/status');
        const j = await r.json();
        if (j.ok) {
          const d = j.data;
          document.getElementById('link').textContent = d.link ? 'OK' : 'NO';
          document.getElementById('uart').textContent = (d.uart_port || '-') + (d.uart_open ? ' open' : ' closed');
          document.getElementById('uart_err').textContent = d.uart_last_error || '-';
          document.getElementById('pwm').textContent = d.pwm ? 'ON' : 'OFF';
          document.getElementById('fault').textContent = d.fault_text || d.fault || '-';
          document.getElementById('timeout').textContent = d.timeout ? 'YES' : 'NO';
          document.getElementById('rtt').textContent = d.last_rtt_ms ? d.last_rtt_ms.toFixed(1) : '-';
          document.getElementById('precharge').textContent = d.bp_precharge ? 'ON' : 'OFF';
          document.getElementById('pfc').textContent = d.bp_pfc ? 'ON' : 'OFF';
          document.getElementById('fan_state').textContent = (d.bp_fan_duty || 0).toFixed(2);
          document.getElementById('tach').textContent = d.bp_fan_rpm || 0;
          document.getElementById('brake_state').textContent = (d.bp_brake_duty || 0).toFixed(2);
          document.getElementById('bpfoc_state').textContent = d.bp_foc_backend ? 'ON' : 'OFF';
        }
      } catch (e) {}
      setTimeout(poll, 250);
    }
    poll();
  </script>
</body>
</html>
"""


def uart_worker(state: SharedState, port: str, baud: int, rate_hz: float, rx_timeout: float) -> None:
    period = 1.0 / max(5.0, rate_hz)
    seq = 1
    while True:
        try:
            ser = serial.Serial(port, baud, timeout=0.01, write_timeout=max(0.05, rx_timeout))
        except Exception as exc:
            msg = f"open failed {port}: {exc}"
            log(f"UART {msg}")
            with state.lock:
                state.uart_open = False
                state.link_ok = False
                state.uart_last_error = msg
                state.uart_error_count += 1
                state.uart_last_error_time = time.monotonic()
                force_local_safe_outputs_locked(state)
            time.sleep(1.0)
            continue

        ser.dtr = False
        ser.rts = False
        log(f"UART ready on {port} @ {baud}")
        with state.lock:
            state.uart_open = True
        try:
            next_t = time.monotonic()
            while True:
                frame = build_frame(state, seq)
                t0 = time.monotonic()
                written = ser.write(frame)
                if written != len(frame):
                    raise serial.SerialTimeoutException(f"short UART write: {written}/{len(frame)}")
                rsp = read_frame(ser, rx_timeout)
                if rsp and rsp[CRC_OFF] == crc_xor(rsp):
                    rtt = (time.monotonic() - t0) * 1000.0
                    parse_rsp(state, rsp, rtt)
                    with state.lock:
                        state.uart_last_error = ""
                else:
                    with state.lock:
                        state.link_ok = False
                        state.miss_count += 1
                        if state.miss_count >= 3:
                            force_local_safe_outputs_locked(state)
                seq = (seq + 1) & 0xFF
                next_t += period
                sleep = next_t - time.monotonic()
                if sleep > 0:
                    time.sleep(sleep)
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            log(f"UART error: {exc}")
            with state.lock:
                state.uart_open = False
                state.link_ok = False
                state.uart_last_error = msg
                state.uart_error_count += 1
                state.uart_last_error_time = time.monotonic()
                force_local_safe_outputs_locked(state)
                state.miss_count += 1
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(0.5)


def main() -> int:
    ap = argparse.ArgumentParser(description="PC-direct HMI for Blue Pill UART PWM firmware.")
    ap.add_argument("--serial", required=True, help="Serial port to Blue Pill, e.g. /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--rate", type=float, default=50.0, help="UART command rate (Hz)")
    ap.add_argument("--rx-timeout", type=float, default=0.08)
    ap.add_argument("--cmd-guard-max-vdc", type=float, default=float(os.environ.get("UNOQ_CMD_GUARD_MAX_VDC", DEFAULT_CMD_GUARD_MAX_VDC)))
    ap.add_argument("--cmd-guard-allow-hv", action="store_true", default=truthy_env("UNOQ_CMD_GUARD_ALLOW_HV"))
    ap.add_argument(
        "--cmd-guard-disable",
        action="store_true",
        default=truthy_env("UNOQ_CMD_GUARD_DISABLE"),
        help="Bypass only the DC bus voltage command guard; link, ESTOP, fault, PWM-active and bad-counter interlocks stay enforced.",
    )
    ap.add_argument(
        "--bench-gate-url",
        default=os.environ.get("UNOQ_BENCH_GATE_URL", ""),
        help="Live HMI URL used by bench_gate_report.py before accepting START. Defaults to this server on 127.0.0.1.",
    )
    args = ap.parse_args()

    state = SharedState()
    state.cmd_guard_max_vdc = float(args.cmd_guard_max_vdc)
    state.cmd_guard_allow_hv = bool(args.cmd_guard_allow_hv)
    state.cmd_guard_disabled = bool(args.cmd_guard_disable)
    state.bench_gate_url = args.bench_gate_url.strip() or f"http://127.0.0.1:{int(args.port)}"
    state.uart_port = str(args.serial)
    state.uart_baud = int(args.baud)
    th = threading.Thread(
        target=uart_worker,
        args=(state, args.serial, args.baud, args.rate, args.rx_timeout),
        daemon=True,
    )
    th.start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.state = state  # type: ignore[attr-defined]
    server.html = HTML_UI.encode("utf-8")  # type: ignore[attr-defined]

    log(f"HTTP server on http://{args.host}:{args.port}")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

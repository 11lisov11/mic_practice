#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import select
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Deque, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

try:
    import termios
except Exception:  # pragma: no cover - Windows/local dev without POSIX TTY
    termios = None

try:
    import msgpack
except Exception:  # pragma: no cover - allow text-only mode without msgpack
    msgpack = None

STATE_NAMES = {
    0: "SAFE",
    1: "VF_RUN",
    2: "FOC_ALIGN",
    3: "FOC_RUN",
    4: "FAULT",
}
MODE_NAMES = {
    0: "VF",
    1: "FOC",
    2: "MIC",
    3: "DIAG",
    4: "DUTY",
}
STATE_CODES = {v: k for k, v in STATE_NAMES.items()}
MODE_CODES = {v: k for k, v in MODE_NAMES.items()}
BP_MODE_DIAG = 1
BP_MODE_DUTY = 2
DEFAULT_REMOTEOCD = "/home/arduino/.arduino15/packages/arduino/tools/remoteocd/0.0.4-rc.4/remoteocd"
DEFAULT_REMOTEOCD_CFG = os.path.join(os.path.dirname(__file__), "flash_unoq_sketch_090.cfg")
DEFAULT_CMD_GUARD_MAX_VDC = 60.0
CMD_GUARD_MAX_AGE_MS = 1000.0
# Independent raw-ADC gate mirrored from Blue Pill config.h. The raw check does
# not trust the scaled Vbus field, but its calibration points must stay in sync
# with the firmware and are enforced by firmware_config_safety_check.py.
VBUS_RAW_MIN_VALID = 1
VBUS_RAW_MAX_VALID = 4094
VBUS_RAW_ZERO_CAL = 1966
VBUS_RAW_CAL = 3459
VBUS_RAW_CAL_V = 315.0
VBUS_HV_CALIBRATION_VALID = False
VBUS_RAW_WINDOW_MARGIN_V = 5.0
VBUS_RAW_ZERO_LOW_MARGIN = 128
DEFAULT_START_RUNLIMIT_SEC = 15.0
DEFAULT_HV_ARM_TTL_SEC = 30.0
DEFAULT_HV_ARM_MIN_VDC = 100.0
DEFAULT_HV_ARM_MAX_VDC = 400.0
DEFAULT_HV_ARM_CONFIRM = "ARM 310V"
DEFAULT_HV_ARM_MIN_TEMP_C = -20.0
DEFAULT_HV_ARM_MAX_TEMP_C = 90.0
DEFAULT_LV_ARM_TTL_SEC = 30.0
DEFAULT_LV_ARM_MIN_VDC = 0.0
DEFAULT_LV_ARM_MAX_VDC = 10.0
DEFAULT_LV_ARM_CONFIRM = "ARM LV HV OFF"
DEFAULT_LV_START_RUNLIMIT_SEC = 3.0
DEFAULT_RELAY_CONFIRM_TIMEOUT_SEC = 1.5
DEFAULT_RELAY_SETTLE_SEC = 0.35
DEFAULT_RUN_CONFIRM_TIMEOUT_SEC = 1.0
ARM_PROFILE_HV = "hv"
ARM_PROFILE_LV = "lv"
HV_RUNTIME_BAD_BURST_LIMIT = 3
HV_RUNTIME_BAD_WINDOW_SEC = 1.0

TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

try:
    from active_pwm_guard import start_allowed_by_bench_gate
except Exception:  # pragma: no cover - fail closed if tooling import is broken
    start_allowed_by_bench_gate = None  # type: ignore[assignment]

def effective_mode(
    mode_code: int,
    bp_mode: int,
    diag_mode: Optional[int] = None,
    duty_mode: Optional[int] = None,
) -> tuple[int, str]:
    if diag_mode is not None:
        if int(diag_mode) != 0:
            return 3, MODE_NAMES[3]
    elif bp_mode == BP_MODE_DIAG:
        return 3, MODE_NAMES[3]
    if duty_mode is not None:
        if int(duty_mode) != 0:
            return 4, MODE_NAMES[4]
    elif bp_mode == BP_MODE_DUTY:
        return 4, MODE_NAMES[4]
    return mode_code, MODE_NAMES.get(mode_code, str(mode_code))


def _now_ts() -> float:
    return time.time()


def _fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def termios_baud_constant(baud: int) -> int:
    if termios is None:
        raise RuntimeError("termios not available on this platform")
    name = f"B{int(baud)}"
    if not hasattr(termios, name):
        raise RuntimeError(f"termios baud {baud} is not supported by this platform")
    return int(getattr(termios, name))


class LogStore:
    def __init__(self, max_bytes: int, log_path: Optional[str], file_max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._total_bytes = 0
        self._items: Deque[Tuple[float, str]] = deque()
        self._lock = threading.Lock()
        self._log_path = log_path
        self._file_max_bytes = file_max_bytes
        if self._log_path:
            log_dir = os.path.dirname(self._log_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

    def add(self, line: str) -> None:
        ts = _now_ts()
        entry = f"{_fmt_ts(ts)} {line}"
        size = len(entry) + 1
        with self._lock:
            self._items.append((ts, entry))
            self._total_bytes += size
            while self._total_bytes > self._max_bytes and self._items:
                _, old = self._items.popleft()
                self._total_bytes -= (len(old) + 1)
            if self._log_path:
                self._append_to_file(entry)

    def _append_to_file(self, entry: str) -> None:
        if not self._log_path:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
            if self._file_max_bytes <= 0:
                return
            size = os.path.getsize(self._log_path)
            if size <= self._file_max_bytes:
                return
            self._truncate_file_tail()
        except Exception:
            pass

    def _truncate_file_tail(self) -> None:
        if not self._log_path:
            return
        try:
            with open(self._log_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                keep = min(size, self._file_max_bytes)
                f.seek(max(size - keep, 0))
                data = f.read()
            # Drop partial line at start
            nl = data.find(b"\n")
            if nl != -1:
                data = data[nl + 1 :]
            with open(self._log_path, "wb") as f:
                f.write(data)
        except Exception:
            pass

    @staticmethod
    def _parse_ts(entry: str) -> Optional[float]:
        try:
            ts_str = entry[:19]
            return time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
        except Exception:
            return None

    def dump_since(self, since_ts: float) -> List[str]:
        if self._log_path and os.path.exists(self._log_path):
            try:
                with open(self._log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
                out: List[str] = []
                for raw_line in lines:
                    # Concurrent legacy writers could leave sparse NUL bytes in
                    # the persistent log. Never expose them through /api/logs.
                    line = raw_line.replace("\x00", "").strip()
                    if not line:
                        continue
                    ts = self._parse_ts(line)
                    if ts is None or ts >= since_ts:
                        out.append(line)
                return out
            except Exception:
                pass
        with self._lock:
            return [entry for ts, entry in self._items if ts >= since_ts]


def _tail_text(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _as_float(data: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(data.get(key, default))
    except (TypeError, ValueError):
        return default


def _as_int(data: dict, key: str, default: int = 0) -> int:
    try:
        return int(float(data.get(key, default)))
    except (TypeError, ValueError):
        return default


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _cmd_tokens(cmd: str) -> list[str]:
    return cmd.strip().split()


def _cmd_head(cmd: str) -> str:
    parts = _cmd_tokens(cmd)
    return parts[0].upper() if parts else ""


def _on_off_arg(parts: list[str], index: int = 1) -> Optional[bool]:
    if len(parts) <= index:
        return None
    val = parts[index].strip().upper()
    if val in ("1", "ON", "TRUE", "YES"):
        return True
    if val in ("0", "OFF", "FALSE", "NO"):
        return False
    return None


def _positive_arg(parts: list[str], index: int) -> bool:
    if len(parts) <= index:
        return False
    try:
        return float(parts[index]) > 0.0001
    except (TypeError, ValueError):
        return False


def command_requests_start(cmd: str) -> bool:
    parts = _cmd_tokens(cmd)
    return len(parts) == 1 and parts[0].upper() == "START"


def command_requests_service_output(cmd: str) -> bool:
    parts = _cmd_tokens(cmd)
    if not parts:
        return False
    head = parts[0].upper()
    if head == "IOTEST":
        return _on_off_arg(parts) is True
    if head == "BPFOC":
        return _on_off_arg(parts) is True
    if head in ("PFC", "PRECHARGE"):
        return _on_off_arg(parts) is True
    if head == "FAN":
        if len(parts) == 2:
            arg = parts[1].upper()
            if arg == "ON":
                return True
            if arg == "OFF":
                return False
            return _positive_arg(parts, 1)
        if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
            return _positive_arg(parts, 2)
        return False
    if head == "BRAKE":
        if len(parts) == 2:
            if parts[1].upper() == "OFF":
                return False
            return _positive_arg(parts, 1)
        if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
            return _positive_arg(parts, 2)
        return False
    return False


def command_releases_service_output(cmd: str) -> bool:
    parts = _cmd_tokens(cmd)
    if not parts:
        return False
    head = parts[0].upper()
    if head in ("IOTEST", "BPFOC", "PFC", "PRECHARGE"):
        return _on_off_arg(parts) is False
    if head == "FAN":
        if len(parts) == 2:
            return parts[1].upper() == "OFF" or not _positive_arg(parts, 1)
        if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
            return not _positive_arg(parts, 2)
    if head == "BRAKE":
        if len(parts) == 2:
            return parts[1].upper() == "OFF" or not _positive_arg(parts, 1)
        if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
            return not _positive_arg(parts, 2)
    return False


def status_has_active_outputs(data: Optional[dict]) -> bool:
    if data is None:
        return True
    return bool(
        _as_int(data, "pwm", 1) != 0
        or _as_int(data, "precharge", 1) != 0
        or (_as_int(data, "bp_ext", 0xFF) & 0x0E) != 0
        or _as_int(data, "pfc", 1) != 0
        or _as_int(data, "brake", 1) != 0
        or _as_float(data, "brake_duty", 1.0) > 0.0001
        or _as_float(data, "fan_duty", 1.0) > 0.0001
        or _as_float(data, "bp_fan_duty", 1.0) > 0.0001
    )


class CommandGuardConfig:
    def __init__(
        self,
        max_vdc: float,
        allow_hv: bool = False,
        disabled: bool = False,
        bench_gate_url: str = "",
        bench_gate_runner: Optional[Callable[[Callable[[str], None], Optional[str]], bool]] = None,
        local_bench_gate: bool = False,
    ) -> None:
        self.max_vdc = max_vdc
        self.allow_hv = allow_hv
        self.disabled = disabled
        self.bench_gate_url = bench_gate_url
        self.bench_gate_runner = bench_gate_runner
        self.local_bench_gate = local_bench_gate


def start_bench_gate_check(cfg: CommandGuardConfig) -> tuple[bool, str]:
    if cfg.local_bench_gate:
        return True, "standalone live safety gate"
    logs: list[str] = []
    if cfg.bench_gate_runner is not None:
        ok = bool(cfg.bench_gate_runner(logs.append, cfg.bench_gate_url or None))
    elif start_allowed_by_bench_gate is not None:
        ok = bool(start_allowed_by_bench_gate(logs.append, url=cfg.bench_gate_url or None))
    else:
        ok = False
        logs.append("active_pwm_guard import failed")
    if ok:
        return True, "ok"
    detail = "; ".join(logs) if logs else "bench gate refused START"
    return False, f"bench gate blocked START: {detail}"


def validate_bench_gate_attestation(payload: object, now: Optional[float] = None) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "attestation payload is not an object"
    if payload.get("ready_for_active_pwm") is not True:
        return False, "attestation is not green"
    current = time.time() if now is None else float(now)
    try:
        issued_at = float(payload.get("issued_at"))
        expires_at = float(payload.get("expires_at"))
    except (TypeError, ValueError):
        return False, "attestation timestamps are missing"
    if not (math.isfinite(issued_at) and math.isfinite(expires_at)):
        return False, "attestation timestamps are invalid"
    if issued_at > current + 1.0:
        return False, "attestation was issued in the future"
    if current - issued_at > 10.0:
        return False, "attestation is stale"
    if expires_at < current:
        return False, "attestation has expired"
    if expires_at - issued_at > 10.0:
        return False, "attestation validity window is too long"
    return True, "ok"


def attested_bench_gate_runner(log_fn: Callable[[str], None], url: Optional[str]) -> bool:
    target = str(url or "").strip()
    if not target:
        log_fn("bench-gate attestation URL is missing")
        return False
    try:
        request = urllib.request.Request(target, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=12.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        log_fn(f"bench-gate attestation request failed: {type(exc).__name__}: {exc}")
        return False
    ok, detail = validate_bench_gate_attestation(payload)
    if not ok:
        log_fn(f"bench-gate attestation rejected: {detail}")
    return ok


def _status_bp_bad(data: dict) -> int:
    values = [_as_int(data, key, 999999) for key in ("bp_bad_cnt", "bp_bad") if key in data]
    if not values:
        return 999999
    return max(values)


def _status_vdc(data: dict) -> float:
    values: list[float] = []
    for key in ("vdc", "bp_vdc"):
        if key not in data:
            continue
        value = _as_float(data, key, float("nan"))
        if math.isfinite(value) and value >= 0.0:
            values.append(value)
    return max(values) if values else float("nan")


def _vbus_raw_for_voltage(vdc: float) -> float:
    span = float(VBUS_RAW_CAL - VBUS_RAW_ZERO_CAL)
    return float(VBUS_RAW_ZERO_CAL) + max(0.0, float(vdc)) * span / float(VBUS_RAW_CAL_V)


def raw_vbus_window_check(data: dict, min_vdc: float, max_vdc: float) -> tuple[bool, str]:
    if _as_float(data, "bp_vbus_age_ms", 999999.0) > CMD_GUARD_MAX_AGE_MS:
        return False, "raw DC bus telemetry is stale"
    if "bp_vbus_raw" not in data:
        return False, "raw DC bus telemetry is missing"
    raw = _as_int(data, "bp_vbus_raw", -1)
    if _as_int(data, "bp_mcsdk_telemetry", 0) == 1:
        if _as_int(data, "bp_vbus_valid", 0) != 1:
            return False, "MCSDK DC bus telemetry is not valid"
        if raw < 0 or raw > 5000:
            return False, f"MCSDK DC bus telemetry is invalid: decivolts={raw}"
        direct_vdc = float(raw) * 0.1
        scaled_vdc = _status_vdc(data)
        if not math.isfinite(scaled_vdc) or abs(scaled_vdc - direct_vdc) > 1.0:
            return False, "MCSDK DC bus telemetry fields disagree"
        if direct_vdc < min_vdc or direct_vdc > max_vdc:
            return False, f"MCSDK DC bus is outside window: vdc={direct_vdc:.1f} V"
        return True, "ok"
    if raw < VBUS_RAW_MIN_VALID or raw > VBUS_RAW_MAX_VALID:
        return False, f"raw DC bus telemetry is invalid: raw={raw}"

    if max_vdc <= DEFAULT_CMD_GUARD_MAX_VDC:
        raw_min = VBUS_RAW_ZERO_CAL - VBUS_RAW_ZERO_LOW_MARGIN
        raw_max = math.ceil(_vbus_raw_for_voltage(max_vdc + VBUS_RAW_WINDOW_MARGIN_V))
        if raw < raw_min or raw > raw_max:
            label = "zero-bus" if max_vdc <= DEFAULT_LV_ARM_MAX_VDC else "low-voltage"
            return False, f"raw DC bus is outside the calibrated {label} window: raw={raw} expected={raw_min}..{raw_max}"
    if min_vdc >= DEFAULT_HV_ARM_MIN_VDC:
        raw_min = math.floor(_vbus_raw_for_voltage(min_vdc - VBUS_RAW_WINDOW_MARGIN_V))
        if raw < raw_min:
            return False, f"raw DC bus does not confirm an energized HV bus: raw={raw} expected>={raw_min}"
    return True, "ok"


def vbus_capture_precheck(data: Optional[dict]) -> tuple[bool, str]:
    if data is None:
        return False, "status unavailable"
    state = str(data.get("state", "")).upper()
    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
    if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
        return False, f"not SAFE: state={data.get('state')}"
    if _as_int(data, "pwm", 1) != 0:
        return False, "PWM is not off"
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"Blue Pill fault is active: bp_fault={_as_int(data, 'bp_fault', 255)}"
    if _status_bp_bad(data) != 0:
        return False, "Blue Pill bad counter is non-zero"
    if not _status_link_live(data):
        return False, "Blue Pill link is stale or down"
    if _as_float(data, "bp_vbus_age_ms", 999999.0) > CMD_GUARD_MAX_AGE_MS:
        return False, "DC bus telemetry is stale"
    if "bp_vbus_raw" not in data:
        return False, "raw DC bus telemetry is missing"
    raw = _as_int(data, "bp_vbus_raw", -1)
    if raw < 0 or raw > 4095:
        return False, f"raw DC bus telemetry is invalid: raw={raw}"
    if not math.isfinite(_status_vdc(data)):
        return False, "scaled DC bus telemetry is not readable"
    if _as_int(data, "bp_temp_valid", 0) != 1 or _as_int(data, "bp_temp_fault", 1) != 0:
        return False, "heatsink temperature protection is not healthy"
    if not math.isfinite(_as_float(data, "bp_temp_c", float("nan"))):
        return False, "heatsink temperature is not readable"
    for key in ("precharge", "pfc", "brake", "bp_ext"):
        if _as_int(data, key, 0) != 0:
            return False, f"output must be off during Vbus capture: {key}={_as_int(data, key, 0)}"
    return True, "ok"


def vbus_capture_summary(samples: list[dict], meter_vdc: Optional[float]) -> dict:
    def stats(values: list[float]) -> dict:
        count = len(values)
        mean = sum(values) / count
        variance = sum((value - mean) ** 2 for value in values) / count
        return {
            "samples": count,
            "mean": mean,
            "std": math.sqrt(variance),
            "min": min(values),
            "max": max(values),
        }

    raw_values = [float(_as_int(sample, "bp_vbus_raw", -1)) for sample in samples]
    vdc_values = [float(_status_vdc(sample)) for sample in samples]
    temp_values = [float(_as_float(sample, "bp_temp_c", float("nan"))) for sample in samples]
    return {
        "timestamp": _now_ts(),
        "meter_vdc": meter_vdc,
        "outputs_commanded": False,
        "state": "SAFE",
        "pwm": 0,
        "bp_vbus_raw": stats(raw_values),
        "bp_vdc": stats(vdc_values),
        "bp_temp_c": stats(temp_values),
    }


def _status_link_live(data: dict) -> bool:
    if data.get("link") is False:
        return False
    ages: list[float] = []
    for key in ("bp_rsp_age_ms", "bp_age_ms"):
        if key in data:
            ages.append(_as_float(data, key, 999999.0))
    if data.get("last_rx_age_s") is not None:
        ages.append(_as_float(data, "last_rx_age_s", 999999.0) * 1000.0)
    return bool(ages) and min(ages) <= CMD_GUARD_MAX_AGE_MS


def command_guard_check(cmd: str, data: Optional[dict], cfg: CommandGuardConfig) -> tuple[bool, str]:
    if not (command_requests_start(cmd) or command_requests_service_output(cmd)):
        return True, "not guarded"
    if data is None:
        return False, "status unavailable"
    state = str(data.get("state", "")).upper()
    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
    if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
        return False, f"not SAFE: state={data.get('state')}"
    if _as_int(data, "pwm", 1) != 0:
        return False, f"PWM is not off: pwm={_as_int(data, 'pwm', 1)}"
    if _as_int(data, "estop", 1) != 0:
        return False, f"ESTOP is active: estop={_as_int(data, 'estop', 1)}"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"Blue Pill fault is active: bp_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_bp_bad(data)
    if bad != 0:
        return False, f"Blue Pill bad counter is non-zero: bp_bad={bad}"
    if not _status_link_live(data):
        return False, "Blue Pill link is stale or down"
    vdc = _status_vdc(data)
    if not math.isfinite(vdc):
        return False, "DC bus telemetry is not readable"
    if not (cfg.allow_hv or cfg.disabled):
        if vdc > cfg.max_vdc:
            return False, f"DC bus too high for command: vdc={vdc:.1f} V"
        raw_ok, raw_reason = raw_vbus_window_check(data, 0.0, cfg.max_vdc)
        if not raw_ok:
            return False, raw_reason
    if command_requests_start(cmd):
        return start_bench_gate_check(cfg)
    return True, "ok"


class HvArmConfig:
    def __init__(
        self,
        enabled: bool = False,
        ttl_sec: float = DEFAULT_HV_ARM_TTL_SEC,
        min_vdc: float = DEFAULT_HV_ARM_MIN_VDC,
        max_vdc: float = DEFAULT_HV_ARM_MAX_VDC,
        confirm: str = DEFAULT_HV_ARM_CONFIRM,
        min_temp_c: float = DEFAULT_HV_ARM_MIN_TEMP_C,
        max_temp_c: float = DEFAULT_HV_ARM_MAX_TEMP_C,
        profile: str = "hv",
    ) -> None:
        self.enabled = bool(enabled)
        self.ttl_sec = max(1.0, float(ttl_sec))
        self.min_vdc = float(min_vdc)
        self.max_vdc = float(max_vdc)
        self.confirm = str(confirm)
        self.min_temp_c = float(min_temp_c)
        self.max_temp_c = float(max_temp_c)
        self.profile = str(profile).strip().lower() or "hv"

    @property
    def profile_label(self) -> str:
        return self.profile.upper()


def hv_arm_precheck(data: Optional[dict], cfg: HvArmConfig) -> tuple[bool, str]:
    if not cfg.enabled:
        return False, "standalone arm mode is disabled"
    if cfg.profile == ARM_PROFILE_HV and not VBUS_HV_CALIBRATION_VALID:
        return False, "HV Vbus calibration is incomplete; capture a known-voltage point before arming"
    if data is None:
        return False, "status unavailable"
    state = str(data.get("state", "")).upper()
    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
    if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
        return False, f"not SAFE: state={data.get('state')}"
    if _as_int(data, "pwm", 1) != 0:
        return False, "PWM is not off"
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"Blue Pill fault is active: bp_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_bp_bad(data)
    if bad != 0:
        return False, f"Blue Pill bad counter is non-zero: bp_bad={bad}"
    if not _status_link_live(data):
        return False, "Blue Pill link is stale or down"

    vdc = _status_vdc(data)
    if not math.isfinite(vdc):
        return False, "DC bus telemetry is not readable"
    if vdc < cfg.min_vdc or vdc > cfg.max_vdc:
        return False, f"DC bus is outside {cfg.profile_label} arm window: vdc={vdc:.1f} V"
    raw_ok, raw_reason = raw_vbus_window_check(data, cfg.min_vdc, cfg.max_vdc)
    if not raw_ok:
        return False, raw_reason

    if _as_int(data, "bp_temp_valid", 0) != 1:
        return False, "heatsink temperature is invalid"
    if _as_int(data, "bp_temp_fault", 1) != 0:
        return False, "heatsink temperature fault is active"
    if _as_float(data, "bp_temp_age_ms", 999999.0) > CMD_GUARD_MAX_AGE_MS:
        return False, "heatsink temperature is stale"
    temp_c = _as_float(data, "bp_temp_c", float("nan"))
    if not math.isfinite(temp_c) or temp_c < cfg.min_temp_c or temp_c > cfg.max_temp_c:
        return False, f"heatsink temperature is implausible: temp={temp_c:.1f} C"
    return True, "ok"


def arm_profile_switch_precheck(data: Optional[dict], cfg: HvArmConfig) -> tuple[bool, str]:
    """Allow profile changes only while every commanded power output is inactive."""
    if data is None:
        return False, "status unavailable"
    state = str(data.get("state", "")).upper()
    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
    if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
        return False, f"not SAFE: state={data.get('state')}"
    if _as_int(data, "pwm", 1) != 0:
        return False, "PWM is not off"
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if _as_int(data, "precharge", 1) != 0:
        return False, "precharge relay is active"
    if _as_int(data, "pfc", 1) != 0:
        return False, "PFC output is active"
    if _as_int(data, "brake", 1) != 0 or _as_float(data, "brake_duty", 1.0) > 0.0001:
        return False, "brake output is active"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"Blue Pill fault is active: bp_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_bp_bad(data)
    if bad != 0:
        return False, f"Blue Pill bad counter is non-zero: bp_bad={bad}"
    if not _status_link_live(data):
        return False, "Blue Pill link is stale or down"

    if cfg.profile == ARM_PROFILE_LV:
        # LV selection itself is fail-closed. Arming repeats the complete check.
        vdc = _status_vdc(data)
        if not math.isfinite(vdc) or vdc < cfg.min_vdc or vdc > cfg.max_vdc:
            return False, f"DC bus is outside {cfg.profile_label} profile window: vdc={vdc:.1f} V"
        raw_ok, raw_reason = raw_vbus_window_check(data, cfg.min_vdc, cfg.max_vdc)
        if not raw_ok:
            return False, raw_reason
    return True, "ok"


def hv_runtime_check(
    data: Optional[dict], cfg: HvArmConfig, allow_nonzero_bad: bool = False
) -> tuple[bool, str]:
    if cfg.profile == ARM_PROFILE_HV and not VBUS_HV_CALIBRATION_VALID:
        return False, "HV Vbus calibration is incomplete"
    if data is None:
        return False, "status unavailable"
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"Blue Pill fault is active: bp_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_bp_bad(data)
    if bad != 0 and not allow_nonzero_bad:
        return False, f"Blue Pill bad counter is non-zero: bp_bad={bad}"
    if not _status_link_live(data):
        return False, "Blue Pill link is stale or down"

    vdc = _status_vdc(data)
    if not math.isfinite(vdc) or vdc < cfg.min_vdc or vdc > cfg.max_vdc:
        return False, f"DC bus is outside {cfg.profile_label} runtime window: vdc={vdc:.1f} V"
    raw_ok, raw_reason = raw_vbus_window_check(data, cfg.min_vdc, cfg.max_vdc)
    if not raw_ok:
        return False, raw_reason

    if _as_int(data, "bp_temp_valid", 0) != 1:
        return False, "heatsink temperature is invalid"
    if _as_int(data, "bp_temp_fault", 1) != 0:
        return False, "heatsink temperature fault is active"
    if _as_float(data, "bp_temp_age_ms", 999999.0) > CMD_GUARD_MAX_AGE_MS:
        return False, "heatsink temperature is stale"
    temp_c = _as_float(data, "bp_temp_c", float("nan"))
    if not math.isfinite(temp_c) or temp_c < cfg.min_temp_c or temp_c > cfg.max_temp_c:
        return False, f"heatsink temperature is implausible: temp={temp_c:.1f} C"
    return True, "ok"


def output_sequence_health_check(
    data: Optional[dict], arm_cfg: HvArmConfig, guard_cfg: CommandGuardConfig
) -> tuple[bool, str]:
    if arm_cfg.enabled:
        return hv_runtime_check(data, arm_cfg)
    if data is None:
        return False, "status unavailable"
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"Blue Pill fault is active: bp_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_bp_bad(data)
    if bad != 0:
        return False, f"Blue Pill bad counter is non-zero: bp_bad={bad}"
    if not _status_link_live(data):
        return False, "Blue Pill link is stale or down"
    vdc = _status_vdc(data)
    if not math.isfinite(vdc):
        return False, "DC bus telemetry is not readable"
    if not (guard_cfg.allow_hv or guard_cfg.disabled):
        if vdc > guard_cfg.max_vdc:
            return False, f"DC bus too high for command: vdc={vdc:.1f} V"
        raw_ok, raw_reason = raw_vbus_window_check(data, 0.0, guard_cfg.max_vdc)
        if not raw_ok:
            return False, raw_reason
    return True, "ok"


class HvRuntimeBadFrameMonitor:
    """Trip on an error burst, not on one CRC-rejected frame under PWM EMI."""

    def __init__(
        self,
        burst_limit: int = HV_RUNTIME_BAD_BURST_LIMIT,
        window_sec: float = HV_RUNTIME_BAD_WINDOW_SEC,
    ) -> None:
        self.burst_limit = max(1, int(burst_limit))
        self.window_sec = max(0.1, float(window_sec))
        self._previous: dict[str, int] = {}
        self._events: Deque[tuple[float, int]] = deque()

    def reset(self) -> None:
        self._previous.clear()
        self._events.clear()

    def observe(self, data: dict, now: Optional[float] = None) -> tuple[bool, str]:
        timestamp = _now_ts() if now is None else float(now)
        delta = 0
        current: dict[str, int] = {}
        for key in ("bp_bad_cnt", "bp_bad"):
            if key not in data:
                continue
            value = max(0, _as_int(data, key, 999999))
            current[key] = value
            previous = self._previous.get(key, 0)
            if value >= previous:
                delta += value - previous
        self._previous = current

        if delta > 0:
            self._events.append((timestamp, delta))
        cutoff = timestamp - self.window_sec
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()
        burst = sum(count for _, count in self._events)
        if burst >= self.burst_limit:
            return False, f"Blue Pill UART error burst: {burst} errors/{self.window_sec:.1f}s"
        if delta > 0:
            return True, f"isolated Blue Pill UART errors: delta={delta}, window={burst}"
        return True, "ok"


class HvArmState:
    def __init__(self, cfg: HvArmConfig) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._expires_at = 0.0
        self._started = False

    def arm(self, confirm: str, data: Optional[dict]) -> tuple[bool, str]:
        if not secrets.compare_digest(str(confirm), self.cfg.confirm):
            return False, "confirmation phrase mismatch"
        ok, reason = hv_arm_precheck(data, self.cfg)
        if not ok:
            return False, reason
        with self._lock:
            self._expires_at = _now_ts() + self.cfg.ttl_sec
            self._started = False
        return True, "armed"

    def disarm(self) -> None:
        with self._lock:
            self._expires_at = 0.0
            self._started = False

    def set_config(self, cfg: HvArmConfig) -> None:
        with self._lock:
            self.cfg = cfg
            self._expires_at = 0.0
            self._started = False

    def command_allowed(self, data: Optional[dict]) -> tuple[bool, str]:
        with self._lock:
            remaining = self._expires_at - _now_ts()
            if remaining <= 0.0:
                if not self._started:
                    self._expires_at = 0.0
                return False, f"{self.cfg.profile_label} arm is not active"
        return hv_arm_precheck(data, self.cfg)

    def mark_started(self) -> None:
        with self._lock:
            if self._expires_at > _now_ts():
                self._started = True

    def mark_stopped(self) -> None:
        with self._lock:
            self._started = False

    def take_expired_session_action(self) -> bool:
        with self._lock:
            if self._expires_at <= 0.0:
                return False
            if self._expires_at > _now_ts():
                return False
            must_stop = self._started
            self._expires_at = 0.0
            self._started = False
            return must_stop

    def runtime_monitor_required(self) -> bool:
        with self._lock:
            return self._started and self._expires_at > _now_ts()

    def snapshot(self) -> dict:
        with self._lock:
            remaining = max(0.0, self._expires_at - _now_ts())
            if remaining <= 0.0 and not self._started:
                self._expires_at = 0.0
            return {
                "hmi_hv_enabled": int(self.cfg.enabled),
                "hmi_hv_armed": int(remaining > 0.0),
                "hmi_hv_started": int(self._started and remaining > 0.0),
                "hmi_hv_remaining_s": round(remaining, 1),
                "hmi_hv_min_vdc": self.cfg.min_vdc,
                "hmi_hv_max_vdc": self.cfg.max_vdc,
                "hmi_arm_profile": self.cfg.profile if self.cfg.enabled else "none",
                "hmi_arm_confirm": self.cfg.confirm if self.cfg.enabled else "",
            }


class FirmwareUpdateConfig:
    def __init__(
        self,
        token_file: Optional[str],
        upload_dir: str,
        remoteocd_bin: str,
        remoteocd_cfg: str,
        max_bytes: int,
        timeout_sec: float,
        max_vdc: float,
    ) -> None:
        self.token_file = token_file
        self.upload_dir = upload_dir
        self.remoteocd_bin = remoteocd_bin
        self.remoteocd_cfg = remoteocd_cfg
        self.max_bytes = max_bytes
        self.timeout_sec = timeout_sec
        self.max_vdc = max_vdc

    @property
    def enabled(self) -> bool:
        return bool(self.token_file)

    def read_token(self) -> Optional[str]:
        if not self.token_file:
            return None
        try:
            with open(os.path.expanduser(self.token_file), "r", encoding="utf-8") as f:
                token = f.read().strip()
        except OSError:
            return None
        if len(token) < 16:
            return None
        return token


class RouterClient:
    def __init__(self, endpoint: str) -> None:
        if msgpack is None:
            raise RuntimeError("msgpack not available")
        self._endpoint = endpoint
        self._sock: Optional[socket.socket] = None
        self._unpacker: Optional[msgpack.Unpacker] = None
        self._packer = msgpack.Packer(use_bin_type=False)
        self._msgid = 1
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._unpacker = None

    def _connect(self) -> None:
        if self._sock is not None:
            return
        endpoint = self._endpoint
        if endpoint.startswith("unix:"):
            path = endpoint[5:]
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(path)
        elif "/" in endpoint or endpoint.startswith("."):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(endpoint)
        else:
            host, port = self._parse_tcp(endpoint)
            sock = socket.create_connection((host, port), timeout=1.0)
        sock.settimeout(0.2)
        self._sock = sock
        self._unpacker = msgpack.Unpacker(raw=False)

    @staticmethod
    def _parse_tcp(endpoint: str) -> tuple[str, int]:
        if ":" in endpoint:
            host, port_str = endpoint.rsplit(":", 1)
        else:
            host, port_str = endpoint, "7501"
        host = host or "127.0.0.1"
        try:
            port = int(port_str)
        except ValueError:
            port = 7501
        return host, port

    def call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    if self._sock is None or self._unpacker is None:
                        raise RuntimeError("no socket")
                    msgid = self._msgid
                    self._msgid += 1
                    self._sock.sendall(self._packer.pack([0, msgid, method, params]))
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
                        try:
                            data = self._sock.recv(4096)
                        except socket.timeout:
                            continue
                        if not data:
                            raise RuntimeError("router closed")
                        self._unpacker.feed(data)
                        for obj in self._unpacker:
                            if isinstance(obj, list) and len(obj) >= 4 and obj[0] == 1 and obj[1] == msgid:
                                return obj
                    raise RuntimeError("router timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


class SerialClient:
    def __init__(self, device: str, baud: int = 115200) -> None:
        if msgpack is None:
            raise RuntimeError("msgpack not available")
        self._device = device
        self._baud = baud
        self._fd: Optional[int] = None
        self._unpacker: Optional[msgpack.Unpacker] = None
        self._packer = msgpack.Packer(use_bin_type=False)
        self._msgid = 1
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
        self._fd = None
        self._unpacker = None

    def _connect(self) -> None:
        if termios is None:
            raise RuntimeError("termios not available on this platform")
        if self._fd is not None:
            return
        fd = os.open(self._device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0  # iflag
        attrs[1] = 0  # oflag
        attrs[3] = 0  # lflag
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        baud_const = termios_baud_constant(self._baud)
        attrs[4] = baud_const
        attrs[5] = baud_const
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        self._fd = fd
        self._unpacker = msgpack.Unpacker(raw=False)

    def call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    if self._fd is None or self._unpacker is None:
                        raise RuntimeError("serial not open")
                    msgid = self._msgid
                    self._msgid += 1
                    os.write(self._fd, self._packer.pack([0, msgid, method, params]))
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
                        r, _, _ = select.select([self._fd], [], [], 0.05)
                        if not r:
                            continue
                        data = os.read(self._fd, 4096)
                        if not data:
                            raise RuntimeError("serial closed")
                        self._unpacker.feed(data)
                        for obj in self._unpacker:
                            if isinstance(obj, list) and len(obj) >= 4 and obj[0] == 1 and obj[1] == msgid:
                                return obj
                    raise RuntimeError("serial timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


class TextSerialClient:
    def __init__(self, device: str, baud: int = 115200) -> None:
        self._device = device
        self._baud = baud
        self._fd: Optional[int] = None
        self._lock = threading.Lock()
        self._rx_buf = bytearray()

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
        self._fd = None
        self._rx_buf.clear()

    def _connect(self) -> None:
        if termios is None:
            raise RuntimeError("termios not available on this platform")
        if self._fd is not None:
            return
        fd = os.open(self._device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        baud_const = termios_baud_constant(self._baud)
        attrs[4] = baud_const
        attrs[5] = baud_const
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        self._fd = fd

    def _read_lines(self, deadline: float) -> list[str]:
        lines: list[str] = []
        while _now_ts() < deadline:
            if self._fd is None:
                break
            r, _, _ = select.select([self._fd], [], [], 0.05)
            if not r:
                continue
            data = os.read(self._fd, 4096)
            if not data:
                raise RuntimeError("serial closed")
            self._rx_buf.extend(data)
            while True:
                nl = self._rx_buf.find(b"\n")
                if nl == -1:
                    break
                line = self._rx_buf[:nl].decode("utf-8", errors="ignore").strip()
                del self._rx_buf[: nl + 1]
                if line:
                    lines.append(line)
        return lines

    def _write_line(self, text: str) -> None:
        if self._fd is None:
            raise RuntimeError("serial not open")
        if not text.endswith("\n"):
            text += "\n"
        os.write(self._fd, text.encode("utf-8"))

    def cmd(self, cmd: str, timeout: float = 0.5, retries: int = 1) -> bool:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    self._write_line(cmd)
                    for line in self._read_lines(_now_ts() + timeout):
                        if line == "OK" or line.startswith("OK "):
                            return True
                        if line.startswith("ERR") or line.startswith("ERROR"):
                            return False
                    raise RuntimeError("serial command not acknowledged")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return False

    def get(self, timeout: float = 1.0, retries: int = 1) -> Optional[str]:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    self._write_line("GET")
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
                        lines = self._read_lines(deadline)
                        for line in lines:
                            if line.startswith("DATA"):
                                return line
                    raise RuntimeError("serial timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


class RpcBridge:
    def __init__(self, endpoint: str, serial_baud: int = 115200) -> None:
        self._router: Optional[RouterClient] = None
        self._serial: Optional[SerialClient] = None
        self._serial_text: Optional[TextSerialClient] = None
        if endpoint.startswith("serial:"):
            self._serial_text = TextSerialClient(endpoint.replace("serial:", "", 1), baud=serial_baud)
        elif endpoint.startswith("/dev/"):
            self._serial_text = TextSerialClient(endpoint, baud=serial_baud)
        else:
            try:
                self._router = RouterClient(endpoint)
            except RuntimeError:
                self._router = None
            self._serial_text = TextSerialClient("/dev/ttyHS1", baud=serial_baud)

    def _call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        if self._router is not None:
            resp = self._router.call(method, params, timeout=timeout, retries=retries)
            if resp is not None:
                return resp
        return None

    def cmd(self, cmd: str) -> Tuple[bool, Optional[str]]:
        resp = self._call("cmd", [cmd], timeout=0.8, retries=2)
        if resp and len(resp) >= 4:
            err = resp[2]
            if err is not None:
                return False, str(err)
            if resp[3] is False:
                return False, "rejected"
            return True, None
        if self._serial_text is not None:
            ok = self._serial_text.cmd(cmd, timeout=0.8, retries=2)
            return (ok, None if ok else "no response")
        return False, "no response"

    def get(self) -> Tuple[bool, Optional[dict], Optional[str]]:
        resp = self._call("get", [], timeout=2.0, retries=2)
        if resp and len(resp) >= 4:
            err = resp[2]
            if err is not None:
                return False, None, str(err)
            result = resp[3]
            if isinstance(result, str):
                parsed = self._parse_status_string(result)
                if parsed is None:
                    return False, None, "bad result"
                return True, parsed, None
            if not isinstance(result, list) or len(result) < 9:
                return False, None, "bad result"
            state_code = int(result[0])
            mode_code = int(result[1])
            bp_mode = int(result[29]) if len(result) >= 31 else 0
            diag_mode = int(result[45]) if len(result) >= 47 else None
            duty_mode = int(result[46]) if len(result) >= 47 else None
            mode_code_eff, mode_name_eff = effective_mode(mode_code, bp_mode, diag_mode, duty_mode)
            data = {
                "state_code": state_code,
                "state": STATE_NAMES.get(state_code, str(state_code)),
                "mode_code": mode_code_eff,
                "mode": mode_name_eff,
                "pwm": int(result[2]),
                "freq": float(result[3]),
                "speed": float(result[4]),
                "ia": float(result[5]),
                "ib": float(result[6]),
                "ic": float(result[7]),
                "vdc": float(result[8]),
                "ts": int(_now_ts() * 1000.0),
            }
            if len(result) >= 12:
                data["id"] = float(result[9])
                data["iq"] = float(result[10])
                data["i_rms"] = float(result[11])
            else:
                ia = data["ia"]
                ib = data["ib"]
                ic = data["ic"]
                data["i_rms"] = float(((ia * ia + ib * ib + ic * ic) / 3.0) ** 0.5)
            if len(result) >= 15:
                data["mic_active"] = int(result[12])
                data["id_ref"] = float(result[13])
                data["mic_saving_pct"] = float(result[14])
            else:
                data["mic_active"] = 0
                data["id_ref"] = 0.0
                data["mic_saving_pct"] = 0.0
            if len(result) >= 17:
                data["freq_cmd"] = float(result[15])
                data["estop"] = int(result[16])
            else:
                data["freq_cmd"] = data.get("freq", 0.0)
                data["estop"] = 0
            if len(result) >= 21:
                data["ntc"] = int(result[17])
                data["pfc"] = int(result[18])
                data["brake"] = int(result[19])
                data["brake_duty"] = float(result[20])
            else:
                data["ntc"] = 0
                data["pfc"] = 0
                data["brake"] = 0
                data["brake_duty"] = 0.0

            # Optional extended telemetry (keep in sync with UNOQ_MOTOR/UNOQ_MOTOR.ino rpc_send_response_get()).
            if len(result) >= 24:
                data["enc_raw"] = int(result[21])
                data["enc_ok"] = int(result[22])
                data["enc_deg"] = float(result[23])
            else:
                data["enc_raw"] = 0
                data["enc_ok"] = 0
                data["enc_deg"] = 0.0

            if len(result) >= 27:
                data["bp_good"] = int(result[24])
                data["bp_bad"] = int(result[25])
                data["bp_age_ms"] = int(result[26])
            else:
                data["bp_good"] = 0
                data["bp_bad"] = 999999
                data["bp_age_ms"] = 999999

            if len(result) >= 31:
                data["bp_status"] = int(result[27])
                data["bp_pwm_active"] = 1 if (data["bp_status"] & 0x20) else 0
                data["bp_fault"] = int(result[28])
                data["bp_mode"] = bp_mode
                data["bp_seq"] = int(result[30])
            else:
                data["bp_status"] = 0
                data["bp_pwm_active"] = 0
                data["bp_fault"] = 255
                data["bp_mode"] = 0
                data["bp_seq"] = 0

            if len(result) >= 33:
                data["bp_ping_pairs"] = int(result[31])
                data["bp_ping_age_ms"] = int(result[32])
            else:
                data["bp_ping_pairs"] = 0
                data["bp_ping_age_ms"] = 999999

            if len(result) >= 34:
                data["bp_rsp_age_ms"] = int(result[33])
            else:
                data["bp_rsp_age_ms"] = 999999

            # Optional extended encoder telemetry (append-only after bp_rsp_age_ms).
            if len(result) >= 37:
                data["enc_rpm"] = float(result[34])
                data["enc_mech_hz"] = float(result[35])
                data["enc_elec_hz"] = float(result[36])
            else:
                data["enc_rpm"] = 0.0
                data["enc_mech_hz"] = 0.0
                data["enc_elec_hz"] = 0.0
            if len(result) >= 45:
                data["mic_gated"] = int(result[37])
                data["mic_enable_ai"] = int(result[38])
                data["mic_enc_used"] = int(result[39])
                data["mic_freq_meas_hz"] = float(result[40])
                data["mic_speed_err_hz"] = float(result[41])
                data["mic_speed_tol_hz"] = float(result[42])
                data["mic_link_flags"] = int(result[43])
                data["mic_status_flags"] = int(result[44])
            else:
                data["mic_gated"] = 0
                data["mic_enable_ai"] = 0
                data["mic_enc_used"] = 0
                data["mic_freq_meas_hz"] = 0.0
                data["mic_speed_err_hz"] = 0.0
                data["mic_speed_tol_hz"] = 0.0
                data["mic_link_flags"] = 0
                data["mic_status_flags"] = 0
            if len(result) >= 47:
                data["diag_mode"] = int(result[45])
                data["duty_mode"] = int(result[46])
            else:
                data["diag_mode"] = 1 if mode_code_eff == 3 else 0
                data["duty_mode"] = 1 if mode_code_eff == 4 else 0
            if len(result) >= 50:
                data["bp_vbus_raw"] = int(result[47])
                data["bp_vdc"] = float(result[48])
                data["bp_vbus_age_ms"] = int(result[49])
                data["vdc"] = data["bp_vdc"]
            else:
                data["bp_vbus_raw"] = 0
                data["bp_vdc"] = 0.0
                data["bp_vbus_age_ms"] = 999999
            if len(result) >= 54:
                temp_flags = int(result[53])
                data["bp_temp_raw"] = int(result[50])
                data["bp_temp_v"] = float(result[51])
                data["bp_temp_c"] = float(result[52])
                data["bp_temp_flags"] = temp_flags
                data["bp_temp_valid"] = 1 if (temp_flags & 0x01) else 0
                data["bp_temp_fault"] = 1 if (temp_flags & 0x02) else 0
                data["bp_temp_age_ms"] = data.get("bp_rsp_age_ms", 999999)
            else:
                data["bp_temp_raw"] = 0
                data["bp_temp_v"] = 0.0
                data["bp_temp_c"] = 0.0
                data["bp_temp_flags"] = 0
                data["bp_temp_valid"] = 0
                data["bp_temp_fault"] = 0
                data["bp_temp_age_ms"] = 999999
            if len(result) >= 62:
                phase_flags = int(result[60])
                data["bp_phase_a_raw"] = int(result[54])
                data["bp_phase_b_raw"] = int(result[55])
                data["bp_phase_c_raw"] = int(result[56])
                data["bp_phase_a_v"] = float(result[57])
                data["bp_phase_b_v"] = float(result[58])
                data["bp_phase_c_v"] = float(result[59])
                data["bp_phase_flags"] = phase_flags
                data["bp_phase_valid"] = 1 if (phase_flags & 0x01) else 0
                data["bp_phase_c_virtual"] = 1 if (phase_flags & 0x02) else 0
                data["bp_phase_age_ms"] = int(result[61])
            else:
                data["bp_phase_a_raw"] = 0
                data["bp_phase_b_raw"] = 0
                data["bp_phase_c_raw"] = 0
                data["bp_phase_a_v"] = 0.0
                data["bp_phase_b_v"] = 0.0
                data["bp_phase_c_v"] = 0.0
                data["bp_phase_flags"] = 0
                data["bp_phase_valid"] = 0
                data["bp_phase_c_virtual"] = 0
                data["bp_phase_age_ms"] = 999999
            if len(result) >= 63:
                data["bp_ext"] = int(result[62])
            else:
                data["bp_ext"] = 0
            if len(result) >= 64:
                data["iotest"] = int(result[63])
            else:
                data["iotest"] = 0
            if len(result) >= 65:
                data["precharge"] = int(result[64])
            else:
                data["precharge"] = 0
            if len(result) >= 68:
                data["fan_duty"] = float(result[65])
                data["bp_fan_duty"] = float(result[66])
                data["bp_fan_rpm"] = float(result[67])
            else:
                data["fan_duty"] = 0.0
                data["bp_fan_duty"] = 0.0
                data["bp_fan_rpm"] = 0.0
            if len(result) >= 70:
                data["bp_foc_backend"] = int(result[68])
                data["bp_cmd_mode"] = int(result[69])
            else:
                data["bp_foc_backend"] = 0
                data["bp_cmd_mode"] = data.get("bp_mode", 0)
            data["fw_build"] = int(result[70]) if len(result) >= 71 else 0
            data["matrix_test"] = int(result[71]) if len(result) >= 72 else 0
            data["bp_mcsdk_telemetry"] = int(result[72]) if len(result) >= 73 else 0
            data["bp_vbus_valid"] = int(result[73]) if len(result) >= 74 else 0
            data["bp_precharge_managed"] = int(result[74]) if len(result) >= 75 else 0
            return True, data, None
        if self._serial_text is not None:
            line = self._serial_text.get(timeout=1.2, retries=2)
            if not line:
                return False, None, "no response"
            parsed = self._parse_status_string(line)
            if parsed is None:
                return False, None, "bad result"
            return True, parsed, None
        return False, None, "no response"

    @staticmethod
    def _parse_status_string(text: str) -> Optional[dict]:
        # Expected format: DATA freq=.. speed=.. ia=.. ib=.. ic=.. vdc=.. state=.. mode=.. pwm=..
        try:
            parts = text.replace("DATA", "").strip().split()
            kv = {}
            for part in parts:
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                kv[k.strip()] = v.strip()
            state_s = kv.get("state", "")
            mode_s = kv.get("mode", "")
            state_code = STATE_CODES.get(state_s, -1)
            mode_code = MODE_CODES.get(mode_s, -1)
            diag_mode = int(float(kv.get("diag", "0")))
            duty_mode = int(float(kv.get("duty", "0")))
            mode_code_eff, mode_name_eff = effective_mode(mode_code, int(float(kv.get("bp_mode", "0"))), diag_mode, duty_mode)
            return {
                "state_code": int(state_code),
                "state": state_s or str(state_code),
                "mode_code": int(mode_code_eff),
                "mode": mode_name_eff,
                "pwm": int(float(kv.get("pwm", "0"))),
                "freq": float(kv.get("freq", "0")),
                "speed": float(kv.get("speed", "0")),
                "ia": float(kv.get("ia", "0")),
                "ib": float(kv.get("ib", "0")),
                "ic": float(kv.get("ic", "0")),
                "vdc": float(kv.get("vdc", "0")),
                "id": float(kv.get("id", "0")),
                "iq": float(kv.get("iq", "0")),
                "i_rms": float(kv.get("irm", "0")),
                "mic_active": int(float(kv.get("mic", "0"))),
                "id_ref": float(kv.get("idref", "0")),
                "mic_saving_pct": float(kv.get("save", "0")),
                "freq_cmd": float(kv.get("freqcmd", kv.get("freq", "0"))),
                "estop": int(float(kv.get("estop", "0"))),
                "iotest": int(float(kv.get("iotest", "0"))),
                "ntc": int(float(kv.get("ntc", "0"))),
                "pfc": int(float(kv.get("pfc", "0"))),
                "precharge": int(float(kv.get("precharge", "0"))),
                "brake": int(float(kv.get("brake", "0"))),
                "brake_duty": float(kv.get("brake_duty", "0")),
                "fan_duty": float(kv.get("fan_duty", "0")),
                "bp_fan_duty": float(kv.get("bp_fan_duty", "0")),
                "bp_fan_rpm": float(kv.get("bp_fan_rpm", "0")),
                "enc_raw": int(float(kv.get("enc_raw", "0"))),
                "enc_ok": int(float(kv.get("enc_ok", "0"))),
                "enc_deg": float(kv.get("enc_deg", "0")),
                "enc_rpm": float(kv.get("enc_rpm", "0")),
                "enc_mech_hz": float(kv.get("enc_mech_hz", "0")),
                "enc_elec_hz": float(kv.get("enc_elec_hz", "0")),
                "mic_gated": int(float(kv.get("mic_gated", "0"))),
                "mic_enable_ai": int(float(kv.get("mic_enable_ai", "0"))),
                "mic_enc_used": int(float(kv.get("mic_enc_used", "0"))),
                "mic_freq_meas_hz": float(kv.get("mic_fmeas", "0")),
                "mic_speed_err_hz": float(kv.get("mic_ferr", "0")),
                "mic_speed_tol_hz": float(kv.get("mic_ftol", "0")),
                "mic_link_flags": int(float(kv.get("mic_lflags", "0"))),
                "mic_status_flags": int(float(kv.get("mic_sflags", "0"))),
                "diag_mode": diag_mode,
                "duty_mode": duty_mode,
                "bp_good": int(float(kv.get("bp_good", "0"))),
                "bp_bad": int(float(kv.get("bp_bad", "999999"))),
                "bp_age_ms": int(float(kv.get("bp_age_ms", "999999"))),
                "bp_status": int(float(kv.get("bp_status", "0"))),
                "bp_fault": int(float(kv.get("bp_fault", "255"))),
                "bp_mode": int(float(kv.get("bp_mode", "0"))),
                "bp_cmd_mode": int(float(kv.get("bp_cmd_mode", kv.get("bp_mode", "0")))),
                "bp_foc_backend": int(float(kv.get("bp_foc_backend", "0"))),
                "fw_build": int(float(kv.get("fw_build", "0"))),
                "matrix_test": int(float(kv.get("matrix_test", "0"))),
                "bp_seq": int(float(kv.get("bp_seq", "0"))),
                "bp_good_cnt": int(float(kv.get("bp_good_cnt", kv.get("bp_good", "0")))),
                "bp_bad_cnt": int(float(kv.get("bp_bad_cnt", kv.get("bp_bad", "999999")))),
                "bp_ext": int(float(kv.get("bp_ext", "0"))),
                "bp_brake_duty": float(kv.get("bp_brake_duty", "0")),
                "bp_vbus_raw": int(float(kv.get("bp_vbus_raw", "0"))),
                "bp_vdc": float(kv.get("bp_vdc", kv.get("vdc", "0"))),
                "bp_vbus_age_ms": int(float(kv.get("bp_vbus_age_ms", "999999"))),
                "bp_mcsdk_telemetry": int(float(kv.get("bp_mcsdk_telemetry", "0"))),
                "bp_vbus_valid": int(float(kv.get("bp_vbus_valid", "0"))),
                "bp_precharge_managed": int(float(kv.get("bp_precharge_managed", "0"))),
                "bp_temp_raw": int(float(kv.get("bp_temp_raw", "0"))),
                "bp_temp_v": float(kv.get("bp_temp_v", "0")),
                "bp_temp_c": float(kv.get("bp_temp_c", "0")),
                "bp_temp_flags": int(float(kv.get("bp_temp_flags", "0"))),
                "bp_temp_valid": int(float(kv.get("bp_temp_valid", "0"))),
                "bp_temp_fault": int(float(kv.get("bp_temp_fault", "0"))),
                "bp_temp_age_ms": int(float(kv.get("bp_temp_age_ms", "999999"))),
                "bp_phase_a_raw": int(float(kv.get("bp_phase_a_raw", "0"))),
                "bp_phase_b_raw": int(float(kv.get("bp_phase_b_raw", "0"))),
                "bp_phase_c_raw": int(float(kv.get("bp_phase_c_raw", "0"))),
                "bp_phase_a_v": float(kv.get("bp_phase_a_v", "0")),
                "bp_phase_b_v": float(kv.get("bp_phase_b_v", "0")),
                "bp_phase_c_v": float(kv.get("bp_phase_c_v", "0")),
                "bp_phase_flags": int(float(kv.get("bp_phase_flags", "0"))),
                "bp_phase_valid": int(float(kv.get("bp_phase_valid", "0"))),
                "bp_phase_c_virtual": int(float(kv.get("bp_phase_c_virtual", "0"))),
                "bp_phase_age_ms": int(float(kv.get("bp_phase_age_ms", "999999"))),
                "bp_rsp_age_ms": int(float(kv.get("bp_rsp_age_ms", "999999"))),
                "bp_ping_pairs": int(float(kv.get("bp_ping_pairs", "0"))),
                "bp_ping_age_ms": int(float(kv.get("bp_ping_age_ms", "999999"))),
                "ts": int(_now_ts() * 1000.0),
            }
        except Exception:
            return None


class AppState:
    def __init__(
        self,
        rpc: RpcBridge,
        logs: LogStore,
        status_log_interval: float,
        firmware_update: Optional[FirmwareUpdateConfig] = None,
        command_guard: Optional[CommandGuardConfig] = None,
        hv_arm: Optional[HvArmState] = None,
        start_runlimit_sec: float = DEFAULT_START_RUNLIMIT_SEC,
        arm_profiles: Optional[dict[str, HvArmConfig]] = None,
        profile_runlimits: Optional[dict[str, float]] = None,
        guard_max_vdc: float = DEFAULT_CMD_GUARD_MAX_VDC,
    ) -> None:
        self.rpc = rpc
        self.logs = logs
        self.firmware_update = firmware_update
        self.command_guard = command_guard or CommandGuardConfig(DEFAULT_CMD_GUARD_MAX_VDC)
        self.hv_arm = hv_arm or HvArmState(HvArmConfig())
        self.start_runlimit_sec = max(0.1, float(start_runlimit_sec))
        self.arm_profiles = dict(arm_profiles or {})
        self.profile_runlimits = {
            str(name).lower(): max(0.1, float(limit))
            for name, limit in (profile_runlimits or {}).items()
        }
        self.guard_max_vdc = float(guard_max_vdc)
        self.control_lock = threading.Lock()
        self._status_log_interval = status_log_interval
        self._last_status_log = 0.0
        self._lock = threading.Lock()
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._runtime_bad_monitor = HvRuntimeBadFrameMonitor()

    def _precharge_off(self) -> tuple[bool, str]:
        return True, "nucleo-managed-via-stop"

    def stop_sequence(
        self,
        emergency: bool = False,
        confirm_timeout_sec: float = 0.75,
        poll_sec: float = 0.05,
    ) -> tuple[bool, str, Optional[dict]]:
        """Stop PWM and confirm that every motor-control output is off."""
        primary_cmd = "ESTOP" if emergency else "STOP"
        primary_ok, primary_err = self.rpc.cmd(primary_cmd)
        relay_ok, relay_err = self._precharge_off()
        self.hv_arm.disarm()
        self._runtime_bad_monitor.reset()

        deadline = time.monotonic() + max(0.0, float(confirm_timeout_sec))
        status_ok = False
        status: Optional[dict] = None
        status_err = "status unavailable"
        off_confirmed = False
        while True:
            status_ok, candidate, status_err = self.rpc.get()
            if status_ok and candidate is not None:
                status = candidate
                off_confirmed = bool(
                    _as_int(candidate, "pwm", 1) == 0
                    and _as_int(candidate, "precharge", 1) == 0
                    and (_as_int(candidate, "bp_ext", 0x08) & 0x08) == 0
                )
                if off_confirmed:
                    break
            if time.monotonic() >= deadline:
                break
            time.sleep(max(0.0, float(poll_sec)))
        ok = bool(primary_ok and relay_ok and off_confirmed)
        detail = (
            f"{primary_cmd}={primary_err or primary_ok}; "
            f"PRECHARGE_OFF={relay_err or relay_ok}; "
            f"outputs_off={int(off_confirmed)}"
        )
        if not status_ok:
            detail += f"; status={status_err or 'unavailable'}"
        self.logs.add(f"WIFI_STOP_SEQUENCE emergency={int(emergency)} ok={int(ok)} {detail}")
        return ok, detail, status

    def start_sequence(
        self,
        relay_timeout_sec: float = DEFAULT_RELAY_CONFIRM_TIMEOUT_SEC,
        relay_settle_sec: float = DEFAULT_RELAY_SETTLE_SEC,
        run_timeout_sec: float = DEFAULT_RUN_CONFIRM_TIMEOUT_SEC,
        poll_sec: float = 0.05,
    ) -> tuple[bool, str, Optional[dict]]:
        """Confirm safety, then let Nucleo sequence its local precharge relay."""
        st_ok, status, st_err = self.rpc.get()
        allowed, guard_err = command_guard_check(
            "START", status if st_ok else None, self.command_guard
        )
        if not allowed:
            detail = guard_err if st_ok else f"{guard_err}: {st_err or 'no status'}"
            self.logs.add(f"WIFI_START_REJECT guard {detail}")
            return False, detail, status

        if self.hv_arm.cfg.enabled:
            arm_ok, arm_err = self.hv_arm.command_allowed(status)
            if not arm_ok:
                self.logs.add(f"WIFI_START_REJECT arm {arm_err}")
                return False, arm_err, status

        if status is None:
            return False, "status unavailable", None
        if _as_int(status, "precharge", 0) != 0 or (_as_int(status, "bp_ext", 0) & 0x08) != 0:
            self.stop_sequence(emergency=False)
            return False, "precharge relay was already active; outputs were forced off, retry START", status

        return self._start_without_precharge(status, run_timeout_sec, poll_sec)

    def _start_without_precharge(
        self,
        initial_status: dict,
        run_timeout_sec: float,
        poll_sec: float,
    ) -> tuple[bool, str, Optional[dict]]:
        precharge_managed = _as_int(initial_status, "bp_precharge_managed", 0) == 1
        self.logs.add(
            f"WIFI_START_STEP PRECHARGE_OWNER "
            f"owner={'nucleo' if precharge_managed else 'none'}"
        )
        arm_ok, arm_err = self.hv_arm.command_allowed(initial_status)
        if self.hv_arm.cfg.enabled and not arm_ok:
            self.stop_sequence(emergency=False)
            self.logs.add(f"WIFI_START_FAIL arm_recheck {arm_err}")
            return False, arm_err, initial_status

        runlimit_cmd = f"SET RUNLIMIT {self.start_runlimit_sec:.3f}"
        limit_ok, limit_err = self.rpc.cmd(runlimit_cmd)
        if not limit_ok:
            self.stop_sequence(emergency=False)
            detail = f"run limit rejected: {limit_err or 'no acknowledgement'}"
            self.logs.add(f"WIFI_START_FAIL runlimit {detail}")
            return False, detail, initial_status

        start_ok, start_err = self.rpc.cmd("START")
        if not start_ok:
            self.stop_sequence(emergency=True)
            detail = f"START rejected: {start_err or 'no acknowledgement'}"
            self.logs.add(f"WIFI_START_FAIL start_cmd {detail}")
            return False, detail, initial_status

        run_deadline = time.monotonic() + max(0.0, float(run_timeout_sec))
        run_status: Optional[dict] = None
        last_run_error = "PWM did not start"
        while True:
            read_ok, candidate, read_err = self.rpc.get()
            if read_ok and candidate is not None:
                run_status = candidate
                run_ok, run_err = output_sequence_health_check(
                    candidate, self.hv_arm.cfg, self.command_guard
                )
                relay_active = bool(
                    _as_int(candidate, "precharge", 0) != 0
                    or (_as_int(candidate, "bp_ext", 0) & 0x08) != 0
                )
                relay_state_ok = relay_active if precharge_managed else not relay_active
                nucleo_pwm_ok = (
                    (_as_int(candidate, "bp_status", 0) & 0x20) != 0
                    if precharge_managed
                    else True
                )
                running = (
                    _as_int(candidate, "pwm", 0) == 1
                    and str(candidate.get("state", "")).upper()
                    in ("VF_RUN", "FOC_ALIGN", "FOC_RUN")
                    and relay_state_ok
                    and nucleo_pwm_ok
                )
                if run_ok and running:
                    self.hv_arm.mark_started()
                    self.logs.add(
                        f"WIFI_START_OK state={candidate.get('state')} "
                        f"freq={_as_float(candidate, 'freq', 0.0):.2f} "
                        f"speed={_as_float(candidate, 'speed', 0.0):.1f} "
                        f"precharge_owner={'nucleo' if precharge_managed else 'none'}"
                    )
                    detail = "PWM started; precharge relay confirmed by Nucleo" if precharge_managed else "PWM started"
                    return True, detail, candidate
                last_run_error = run_err if not run_ok else "PWM did not enter a running state"
            else:
                last_run_error = read_err or "status unavailable"
            if time.monotonic() >= run_deadline:
                self.stop_sequence(emergency=True)
                detail = f"START confirmation failed: {last_run_error}"
                self.logs.add(f"WIFI_START_FAIL run_feedback {detail}")
                return False, detail, run_status
            time.sleep(max(0.0, float(poll_sec)))

    def arm_snapshot(self, status: Optional[dict] = None) -> dict:
        snapshot = self.hv_arm.snapshot()
        available = [name for name in (ARM_PROFILE_HV, ARM_PROFILE_LV) if name in self.arm_profiles]
        snapshot["hmi_arm_profiles"] = available
        snapshot["hmi_start_runlimit_s"] = round(self.start_runlimit_sec, 1)
        snapshot["hmi_precharge_relay_present"] = int(
            status is not None and _as_int(status, "bp_precharge_managed", 0) == 1
        )
        snapshot["hmi_vbus_hv_calibrated"] = int(VBUS_HV_CALIBRATION_VALID)
        current_cfg = self.hv_arm.cfg
        switch_ok, _ = arm_profile_switch_precheck(status, current_cfg) if status is not None else (False, "")
        snapshot["hmi_arm_profile_switch_ready"] = int(switch_ok and not snapshot["hmi_hv_armed"])
        return snapshot

    def switch_arm_profile(self, profile: str, status: Optional[dict]) -> tuple[bool, str]:
        target = str(profile).strip().lower()
        cfg = self.arm_profiles.get(target)
        if cfg is None:
            return False, f"unsupported arm profile: {profile}"
        ok, reason = arm_profile_switch_precheck(status, cfg)
        if not ok:
            return False, reason

        self.hv_arm.set_config(cfg)
        if target == ARM_PROFILE_LV:
            self.command_guard.max_vdc = min(self.guard_max_vdc, cfg.max_vdc)
            self.command_guard.allow_hv = False
        else:
            self.command_guard.max_vdc = self.guard_max_vdc
            self.command_guard.allow_hv = True
        self.start_runlimit_sec = self.profile_runlimits.get(target, DEFAULT_START_RUNLIMIT_SEC)
        self._runtime_bad_monitor.reset()
        return True, "profile selected"

    def start_safety_watchdog(self) -> None:
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(target=self._safety_watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def stop_safety_watchdog(self) -> None:
        self._watchdog_stop.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=1.0)

    def _safety_watchdog_loop(self) -> None:
        while not self._watchdog_stop.wait(0.2):
            reason = ""
            if self.hv_arm.take_expired_session_action():
                reason = "HV_ARM_EXPIRED"
            elif self.hv_arm.runtime_monitor_required():
                status_ok, status, status_err = self.rpc.get()
                live_ok, live_err = hv_runtime_check(
                    status if status_ok else None,
                    self.hv_arm.cfg,
                    allow_nonzero_bad=True,
                )
                if live_ok and status is not None:
                    live_ok, bad_err = self._runtime_bad_monitor.observe(status)
                    if live_ok and bad_err != "ok":
                        self.logs.add(f"HV_RUNTIME_UART_WARN {bad_err}")
                    elif not live_ok:
                        live_err = bad_err
                if not live_ok:
                    reason = f"HV_RUNTIME_REJECT {status_err or live_err}"
                    self.hv_arm.disarm()
            else:
                self._runtime_bad_monitor.reset()
            if not reason:
                continue
            stop_ok, stop_err = self.rpc.cmd("STOP")
            estop_ok, estop_err = self.rpc.cmd("ESTOP")
            relay_ok, relay_err = self._precharge_off()
            self.logs.add(
                f"{reason} "
                f"stop_ok={int(stop_ok)} stop_err={stop_err or '-'} "
                f"estop_ok={int(estop_ok)} estop_err={estop_err or '-'} "
                f"relay_ok={int(relay_ok)} relay_err={relay_err or '-'}"
            )

    def maybe_log_status(self, data: dict) -> None:
        now = _now_ts()
        with self._lock:
            if (now - self._last_status_log) < self._status_log_interval:
                return
            self._last_status_log = now
        line = (
            f"STAT state={data.get('state')} mode={data.get('mode')} pwm={data.get('pwm')} "
            f"freq={data.get('freq'):.2f} speed={data.get('speed'):.1f} vdc={data.get('vdc'):.2f} "
            f"bp_temp_c={data.get('bp_temp_c', 0.0):.1f} bp_temp_fault={data.get('bp_temp_fault', 0)} "
            f"bp_phase_c_v={data.get('bp_phase_c_v', 0.0):.3f} bp_phase_c_virtual={data.get('bp_phase_c_virtual', 0)} "
            f"fan_duty={data.get('fan_duty', 0.0):.2f} bp_fan_rpm={data.get('bp_fan_rpm', 0.0):.0f} "
            f"bp_cmd_mode={data.get('bp_cmd_mode', 0)} bp_foc_backend={data.get('bp_foc_backend', 0)}"
        )
        self.logs.add(line)


class Handler(BaseHTTPRequestHandler):
    server_version = "UNOQHMI/0.1"

    def _send_json(self, payload: dict, code: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _send_text(self, text: str, code: int = 200, filename: Optional[str] = None) -> None:
        data = text.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            if filename:
                self.send_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _send_static(self, name: str, content_type: str) -> None:
        base = os.path.dirname(__file__)
        path = os.path.join(base, "static", name)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self.send_error(404)
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/style.css":
            self._send_static("style.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/status":
            self._handle_status()
            return
        if parsed.path == "/api/logs":
            self._handle_logs(parsed)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/cmd":
            self._handle_cmd()
            return
        if parsed.path == "/api/start-sequence":
            self._handle_start_sequence()
            return
        if parsed.path == "/api/stop-sequence":
            self._handle_stop_sequence()
            return
        if parsed.path == "/api/hv-arm":
            self._handle_hv_arm()
            return
        if parsed.path == "/api/arm-profile":
            self._handle_arm_profile()
            return
        if parsed.path == "/api/calibration/vbus":
            self._handle_vbus_capture()
            return
        if parsed.path == "/api/firmware/update":
            self._handle_firmware_update(parsed)
            return
        self.send_error(404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _handle_cmd(self) -> None:
        data = self._read_json()
        cmd = str(data.get("cmd", "")).strip()
        if not cmd:
            self._send_json({"ok": False, "error": "missing cmd"}, 400)
            return
        if _cmd_head(cmd) == "NTC":
            self._send_json({"ok": False, "error": "unsupported: STEVAL J2-21 is not connected"}, 400)
            return
        if _cmd_head(cmd) in ("PRECHARGE", "RELAY"):
            self._send_json({"ok": False, "error": "unsupported: precharge relay is managed by Nucleo"}, 400)
            return
        with self.server.app.control_lock:  # type: ignore[attr-defined]
            self._handle_cmd_locked(cmd)

    def _handle_start_sequence(self) -> None:
        app = self.server.app  # type: ignore[attr-defined]
        with app.control_lock:
            ok, detail, status = app.start_sequence()
        self._send_json(
            {"ok": ok, "message": detail if ok else "", "error": "" if ok else detail, "status": status},
            200 if ok else 409,
        )

    def _handle_stop_sequence(self) -> None:
        request = self._read_json()
        emergency = bool(request.get("emergency", False))
        app = self.server.app  # type: ignore[attr-defined]
        with app.control_lock:
            ok, detail, status = app.stop_sequence(emergency=emergency)
        self._send_json(
            {"ok": ok, "message": detail if ok else "", "error": "" if ok else detail, "status": status},
            200 if ok else 500,
        )

    def _handle_cmd_locked(self, cmd: str) -> None:
        app = self.server.app  # type: ignore[attr-defined]
        if command_requests_start(cmd):
            ok, detail, status = app.start_sequence()
            self._send_json(
                {"ok": ok, "message": detail if ok else "", "error": "" if ok else detail, "status": status},
                200 if ok else 409,
            )
            return
        normalized = " ".join(_cmd_tokens(cmd)).upper()
        if normalized in ("STOP", "ESTOP"):
            ok, detail, status = app.stop_sequence(emergency=normalized == "ESTOP")
            self._send_json(
                {"ok": ok, "message": detail if ok else "", "error": "" if ok else detail, "status": status},
                200 if ok else 500,
            )
            return
        guard_cfg = self.server.app.command_guard  # type: ignore[attr-defined]
        armed_output_command = False
        if command_requests_start(cmd) or command_requests_service_output(cmd):
            st_ok, st_data, st_err = self.server.app.rpc.get()  # type: ignore[attr-defined]
            allowed, guard_err = command_guard_check(cmd, st_data if st_ok else None, guard_cfg)
            if not allowed:
                err = guard_err if st_ok else f"{guard_err}: {st_err or 'no status'}"
                self.server.app.logs.add(f"CMD_REJECT {cmd} {err}")  # type: ignore[attr-defined]
                self._send_json({"ok": False, "error": err, "status": st_data}, 409)
                return
            armed_output_command = bool(self.server.app.hv_arm.cfg.enabled)  # type: ignore[attr-defined]
            if armed_output_command:
                arm_ok, arm_err = self.server.app.hv_arm.command_allowed(st_data)  # type: ignore[attr-defined]
                if not arm_ok:
                    self.server.app.logs.add(f"CMD_REJECT {cmd} {arm_err}")  # type: ignore[attr-defined]
                    self._send_json({"ok": False, "error": arm_err, "status": st_data}, 409)
                    return
        if command_requests_start(cmd):
            runlimit_cmd = f"SET RUNLIMIT {self.server.app.start_runlimit_sec:.3f}"  # type: ignore[attr-defined]
            limit_ok, limit_err = self.server.app.rpc.cmd(runlimit_cmd)  # type: ignore[attr-defined]
            if not limit_ok:
                self.server.app.logs.add(f"CMD_FAIL {runlimit_cmd} {limit_err}")  # type: ignore[attr-defined]
                self._send_json({"ok": False, "error": f"run limit rejected: {limit_err}"}, 500)
                return
            self.server.app.logs.add(f"CMD {runlimit_cmd}")  # type: ignore[attr-defined]
        ok, err = self.server.app.rpc.cmd(cmd)  # type: ignore[attr-defined]
        if ok:
            if armed_output_command:
                self.server.app.hv_arm.mark_started()  # type: ignore[attr-defined]
            elif command_releases_service_output(cmd):
                status_ok, status, _ = self.server.app.rpc.get()  # type: ignore[attr-defined]
                if status_ok and not status_has_active_outputs(status):
                    self.server.app.hv_arm.mark_stopped()  # type: ignore[attr-defined]
            if _cmd_head(cmd) in ("STOP", "ESTOP"):
                self.server.app.hv_arm.disarm()  # type: ignore[attr-defined]
            self.server.app.logs.add(f"CMD {cmd}")  # type: ignore[attr-defined]
            self._send_json({"ok": True})
        else:
            self.server.app.logs.add(f"CMD_FAIL {cmd} {err}")  # type: ignore[attr-defined]
            self._send_json({"ok": False, "error": err}, 500)

    def _handle_status(self) -> None:
        ok, data, err = self.server.app.rpc.get()  # type: ignore[attr-defined]
        if not ok or data is None:
            self._send_json({"ok": False, "error": err or "no response"}, 503)
            return
        data.update(self.server.app.arm_snapshot(data))  # type: ignore[attr-defined]
        self.server.app.maybe_log_status(data)  # type: ignore[attr-defined]
        self._send_json({"ok": True, "data": data})

    def _handle_hv_arm(self) -> None:
        request = self._read_json()
        with self.server.app.control_lock:  # type: ignore[attr-defined]
            self._handle_hv_arm_locked(request)

    def _handle_hv_arm_locked(self, request: dict) -> None:
        action = str(request.get("action", "arm")).strip().lower()
        arm = self.server.app.hv_arm  # type: ignore[attr-defined]
        if action == "disarm":
            arm.disarm()
            stop_ok, stop_err = self.server.app.rpc.cmd("STOP")  # type: ignore[attr-defined]
            estop_ok, estop_err = self.server.app.rpc.cmd("ESTOP")  # type: ignore[attr-defined]
            relay_ok, relay_err = self.server.app._precharge_off()  # type: ignore[attr-defined]
            self.server.app.logs.add("HV_DISARM")  # type: ignore[attr-defined]
            ok = bool(stop_ok and estop_ok and relay_ok)
            self._send_json(
                {
                    "ok": ok,
                    "error": "" if ok else (
                        f"STOP={stop_err or stop_ok}; ESTOP={estop_err or estop_ok}; "
                        f"PRECHARGE={relay_err or relay_ok}"
                    ),
                    "arm": arm.snapshot(),
                },
                200 if ok else 500,
            )
            return
        if action != "arm":
            self._send_json({"ok": False, "error": "unsupported HV arm action"}, 400)
            return
        st_ok, st_data, st_err = self.server.app.rpc.get()  # type: ignore[attr-defined]
        if not st_ok or st_data is None:
            self._send_json({"ok": False, "error": st_err or "status unavailable"}, 503)
            return
        ok, reason = arm.arm(str(request.get("confirm", "")), st_data)
        if not ok:
            self.server.app.logs.add(f"HV_ARM_REJECT {reason}")  # type: ignore[attr-defined]
            self._send_json({"ok": False, "error": reason, "status": st_data, "arm": arm.snapshot()}, 409)
            return
        self.server.app.logs.add(  # type: ignore[attr-defined]
            f"ARM profile={arm.cfg.profile} ttl={arm.cfg.ttl_sec:.1f}s vdc={_status_vdc(st_data):.1f}"
        )
        self._send_json({"ok": True, "arm": self.server.app.arm_snapshot(st_data)})  # type: ignore[attr-defined]

    def _handle_arm_profile(self) -> None:
        request = self._read_json()
        profile = str(request.get("profile", "")).strip().lower()
        app = self.server.app  # type: ignore[attr-defined]
        with app.control_lock:
            stop_ok, stop_err = app.rpc.cmd("STOP")
            relay_ok, relay_err = app._precharge_off()
            app.hv_arm.disarm()
            if not stop_ok or not relay_ok:
                error = f"safe shutdown failed: STOP={stop_err or stop_ok}; PRECHARGE={relay_err or relay_ok}"
                app.logs.add(f"ARM_PROFILE_REJECT {profile or '-'} {error}")
                self._send_json({"ok": False, "error": error}, 500)
                return
            time.sleep(0.05)
            st_ok, st_data, st_err = app.rpc.get()
            if not st_ok or st_data is None:
                error = st_err or "status unavailable"
                app.logs.add(f"ARM_PROFILE_REJECT {profile or '-'} {error}")
                self._send_json({"ok": False, "error": error}, 503)
                return
            ok, reason = app.switch_arm_profile(profile, st_data)
            if not ok:
                app.logs.add(f"ARM_PROFILE_REJECT {profile or '-'} {reason}")
                self._send_json(
                    {"ok": False, "error": reason, "status": st_data, "arm": app.arm_snapshot(st_data)},
                    409,
                )
                return
            app.logs.add(f"ARM_PROFILE {profile} runlimit={app.start_runlimit_sec:.1f}s")
            self._send_json({"ok": True, "arm": app.arm_snapshot(st_data)})

    def _handle_vbus_capture(self) -> None:
        request = self._read_json()
        try:
            meter_vdc = float(request["meter_vdc"]) if request.get("meter_vdc") not in (None, "") else None
        except (TypeError, ValueError):
            self._send_json({"ok": False, "error": "meter_vdc must be a number"}, 400)
            return
        if meter_vdc is not None and (not math.isfinite(meter_vdc) or meter_vdc < 0.0 or meter_vdc > 450.0):
            self._send_json({"ok": False, "error": "meter_vdc must be within 0..450 V"}, 400)
            return

        samples: list[dict] = []
        for _ in range(20):
            ok, data, err = self.server.app.rpc.get()  # type: ignore[attr-defined]
            if not ok or data is None:
                self._send_json({"ok": False, "error": err or "status unavailable"}, 503)
                return
            safe, reason = vbus_capture_precheck(data)
            if not safe:
                self.server.app.logs.add(f"VBUS_CAPTURE_REJECT {reason}")  # type: ignore[attr-defined]
                self._send_json({"ok": False, "error": reason, "status": data}, 409)
                return
            samples.append(data)
            time.sleep(0.02)

        capture = vbus_capture_summary(samples, meter_vdc)
        raw = capture["bp_vbus_raw"]
        scaled = capture["bp_vdc"]
        meter_text = "none" if meter_vdc is None else f"{meter_vdc:.3f}"
        self.server.app.logs.add(  # type: ignore[attr-defined]
            "VBUS_CAPTURE "
            f"meter_vdc={meter_text} raw_mean={raw['mean']:.3f} raw_std={raw['std']:.3f} "
            f"raw_min={raw['min']:.0f} raw_max={raw['max']:.0f} vdc_mean={scaled['mean']:.3f}"
        )
        self._send_json({"ok": True, "capture": capture})

    def _handle_logs(self, parsed) -> None:
        query = parse_qs(parsed.query)
        try:
            hours = float(query.get("hours", ["24"])[0])
        except ValueError:
            hours = 24.0
        download = query.get("download", ["0"])[0] in ("1", "true", "yes")
        since = _now_ts() - (hours * 3600.0)
        lines = self.server.app.logs.dump_since(since)  # type: ignore[attr-defined]
        text = "\n".join(lines) + ("\n" if lines else "")
        if download:
            self._send_text(text, filename="unoq_logs.txt")
        else:
            self._send_text(text)

    def _firmware_update_authorized(self, cfg: FirmwareUpdateConfig) -> tuple[bool, str]:
        expected = cfg.read_token()
        if not expected:
            return False, "firmware update token file is missing or too short"
        provided = self.headers.get("X-UNOQ-Update-Token", "")
        if not provided or not secrets.compare_digest(provided, expected):
            return False, "bad firmware update token"
        return True, ""

    def _ensure_firmware_update_safe(self, cfg: FirmwareUpdateConfig) -> tuple[bool, Optional[dict], str]:
        ok, err = self.server.app.rpc.cmd("STOP")  # type: ignore[attr-defined]
        if not ok:
            return False, None, f"STOP failed: {err}"
        relay_ok, relay_err = self.server.app._precharge_off()  # type: ignore[attr-defined]
        if not relay_ok:
            return False, None, f"PRECHARGE OFF failed: {relay_err}"
        time.sleep(0.2)

        last_err = "no status"
        for _ in range(10):
            ok, data, err = self.server.app.rpc.get()  # type: ignore[attr-defined]
            if ok and data is not None:
                state = str(data.get("state", "")).upper()
                state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
                pwm = _as_int(data, "pwm", 1)
                estop = _as_int(data, "estop", 0)
                bp_fault = _as_int(data, "bp_fault", 0)
                vdc = _status_vdc(data)
                if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
                    return False, data, f"not SAFE: state={data.get('state')}"
                if pwm != 0:
                    return False, data, f"PWM is not off: pwm={pwm}"
                if estop != 0:
                    return False, data, f"ESTOP is active: estop={estop}"
                if bp_fault != 0:
                    return False, data, f"Blue Pill fault is active: bp_fault={bp_fault}"
                bad = _status_bp_bad(data)
                if bad != 0:
                    return False, data, f"Blue Pill bad counter is non-zero: bp_bad={bad}"
                if not _status_link_live(data):
                    return False, data, "Blue Pill link is stale or down"
                if not math.isfinite(vdc):
                    return False, data, "DC bus telemetry is not readable for firmware update"
                if vdc > cfg.max_vdc:
                    return False, data, f"DC bus too high for firmware update: vdc={vdc:.1f} V"
                raw_ok, raw_reason = raw_vbus_window_check(data, 0.0, cfg.max_vdc)
                if not raw_ok:
                    return False, data, f"firmware update blocked: {raw_reason}"
                return True, data, ""
            last_err = err or "no response"
            time.sleep(0.1)
        return False, None, f"status failed: {last_err}"

    def _handle_firmware_update(self, parsed) -> None:
        cfg = self.server.app.firmware_update  # type: ignore[attr-defined]
        if cfg is None or not cfg.enabled:
            self._send_json({"ok": False, "error": "firmware update disabled"}, 403)
            return

        ok, err = self._firmware_update_authorized(cfg)
        if not ok:
            self._send_json({"ok": False, "error": err}, 403)
            return

        query = parse_qs(parsed.query)
        dry_run = query.get("dry_run", ["0"])[0].lower() in ("1", "true", "yes")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self._send_json({"ok": False, "error": "empty firmware body"}, 400)
            return
        if length > cfg.max_bytes:
            self._send_json({"ok": False, "error": f"firmware too large: {length} > {cfg.max_bytes}"}, 413)
            return

        safe, status, safe_err = self._ensure_firmware_update_safe(cfg)
        if not safe:
            self.server.app.logs.add(f"FW_UPDATE_REJECT {safe_err}")  # type: ignore[attr-defined]
            self._send_json({"ok": False, "error": safe_err, "status": status}, 409)
            return

        os.makedirs(cfg.upload_dir, exist_ok=True)
        filename = f"unoq_firmware_{int(time.time())}_{threading.get_ident()}.bin"
        path = os.path.join(cfg.upload_dir, filename)
        sha256 = hashlib.sha256()
        remaining = length
        try:
            with open(path, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        raise RuntimeError("short firmware body")
                    f.write(chunk)
                    sha256.update(chunk)
                    remaining -= len(chunk)
        except Exception as exc:
            try:
                os.remove(path)
            except OSError:
                pass
            self._send_json({"ok": False, "error": f"failed to save firmware: {exc}"}, 400)
            return

        digest = sha256.hexdigest()
        self.server.app.logs.add(  # type: ignore[attr-defined]
            f"FW_UPDATE_UPLOAD bytes={length} sha256={digest} dry_run={int(dry_run)}"
        )
        if dry_run:
            self._send_json({"ok": True, "dry_run": True, "bytes": length, "sha256": digest, "path": path})
            return

        if not os.path.exists(cfg.remoteocd_bin):
            self._send_json({"ok": False, "error": f"remoteocd not found: {cfg.remoteocd_bin}"}, 500)
            return
        if not os.path.exists(cfg.remoteocd_cfg):
            self._send_json({"ok": False, "error": f"remoteocd cfg not found: {cfg.remoteocd_cfg}"}, 500)
            return

        cmd = [cfg.remoteocd_bin, "upload", "--verbose", "-f", cfg.remoteocd_cfg, path]
        try:
            result = subprocess.run(
                cmd,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=cfg.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            out = _tail_text(exc.stdout or "")
            self.server.app.logs.add(f"FW_UPDATE_TIMEOUT sha256={digest}")  # type: ignore[attr-defined]
            self._send_json({"ok": False, "error": "remoteocd timeout", "output": out}, 504)
            return
        output = _tail_text(result.stdout or "")
        if result.returncode != 0:
            self.server.app.logs.add(f"FW_UPDATE_FAIL rc={result.returncode} sha256={digest}")  # type: ignore[attr-defined]
            self._send_json(
                {"ok": False, "error": f"remoteocd failed: rc={result.returncode}", "output": output},
                500,
            )
            return
        self.server.app.logs.add(f"FW_UPDATE_WRITE_OK sha256={digest}")  # type: ignore[attr-defined]
        self._send_json(
            {
                "ok": True,
                "dry_run": False,
                "write_only": True,
                "bytes": length,
                "sha256": digest,
                "output": output,
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="UNOQ WiFi HMI server")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument(
        "--router",
        default="/run/arduino-router.sock",
        help="Router endpoint (unix:/path or host:port)",
    )
    parser.add_argument(
        "--serial-baud",
        type=int,
        default=115200,
        help="Baud rate for serial fallback endpoints such as serial:/dev/ttyX",
    )
    parser.add_argument("--log-bytes", type=int, default=2 * 1024 * 1024, help="Max in-memory log bytes")
    parser.add_argument(
        "--log-file",
        default=os.path.join(os.path.dirname(__file__), "logs", "unoq.log"),
        help="Log file path (empty to disable)",
    )
    parser.add_argument("--log-file-bytes", type=int, default=4 * 1024 * 1024, help="Max log file bytes")
    parser.add_argument("--status-log-sec", type=float, default=5.0, help="Status log interval")
    parser.add_argument(
        "--firmware-update-token-file",
        default=os.environ.get("UNOQ_FIRMWARE_UPDATE_TOKEN_FILE", ""),
        help="Enable firmware update API with a token stored in this file",
    )
    parser.add_argument(
        "--firmware-upload-dir",
        default="/tmp/unoq_firmware_updates",
        help="Directory for received firmware images",
    )
    parser.add_argument("--firmware-update-max-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--firmware-update-timeout-sec", type=float, default=90.0)
    parser.add_argument("--firmware-update-max-vdc", type=float, default=10.0)
    parser.add_argument("--cmd-guard-max-vdc", type=float, default=float(os.environ.get("UNOQ_CMD_GUARD_MAX_VDC", DEFAULT_CMD_GUARD_MAX_VDC)))
    parser.add_argument("--cmd-guard-allow-hv", action="store_true", default=_truthy_env("UNOQ_CMD_GUARD_ALLOW_HV"))
    standalone_group = parser.add_mutually_exclusive_group()
    standalone_group.add_argument(
        "--standalone-hv",
        action="store_true",
        default=_truthy_env("UNOQ_STANDALONE_HV"),
        help="Enable both Wi-Fi arm profiles and start fail-closed in HV mode.",
    )
    standalone_group.add_argument(
        "--standalone-lv",
        action="store_true",
        default=_truthy_env("UNOQ_STANDALONE_LV"),
        help="Enable both Wi-Fi arm profiles and start in HV-disconnected LV test mode.",
    )
    parser.add_argument(
        "--hv-arm-ttl-sec",
        type=float,
        default=float(os.environ.get("UNOQ_HV_ARM_TTL_SEC", DEFAULT_HV_ARM_TTL_SEC)),
    )
    parser.add_argument(
        "--hv-arm-min-vdc",
        type=float,
        default=float(os.environ.get("UNOQ_HV_ARM_MIN_VDC", DEFAULT_HV_ARM_MIN_VDC)),
    )
    parser.add_argument(
        "--hv-arm-max-vdc",
        type=float,
        default=float(os.environ.get("UNOQ_HV_ARM_MAX_VDC", DEFAULT_HV_ARM_MAX_VDC)),
    )
    parser.add_argument(
        "--hv-arm-confirm",
        default=os.environ.get("UNOQ_HV_ARM_CONFIRM", DEFAULT_HV_ARM_CONFIRM),
    )
    parser.add_argument(
        "--lv-arm-ttl-sec",
        type=float,
        default=float(os.environ.get("UNOQ_LV_ARM_TTL_SEC", DEFAULT_LV_ARM_TTL_SEC)),
    )
    parser.add_argument(
        "--lv-arm-max-vdc",
        type=float,
        default=float(os.environ.get("UNOQ_LV_ARM_MAX_VDC", DEFAULT_LV_ARM_MAX_VDC)),
    )
    parser.add_argument(
        "--lv-arm-confirm",
        default=os.environ.get("UNOQ_LV_ARM_CONFIRM", DEFAULT_LV_ARM_CONFIRM),
    )
    parser.add_argument(
        "--start-runlimit-sec",
        type=float,
        default=float(os.environ.get("UNOQ_START_RUNLIMIT_SEC", DEFAULT_START_RUNLIMIT_SEC)),
        help="Bound every accepted START command with this automatic run limit.",
    )
    parser.add_argument(
        "--cmd-guard-disable",
        action="store_true",
        default=_truthy_env("UNOQ_CMD_GUARD_DISABLE"),
        help="Bypass only the DC bus voltage command guard; status, link, ESTOP, fault, PWM-active and bad-counter checks stay enforced.",
    )
    parser.add_argument(
        "--bench-gate-url",
        default=os.environ.get("UNOQ_BENCH_GATE_URL", ""),
        help="Live HMI URL used by bench_gate_report.py before accepting START. Defaults to this server on 127.0.0.1.",
    )
    parser.add_argument(
        "--bench-gate-attestation-url",
        default=os.environ.get("UNOQ_BENCH_GATE_ATTESTATION_URL", ""),
        help="Short-lived PC bench-gate attestation URL. START fails closed if it is unavailable, red, stale or expired.",
    )
    parser.add_argument("--remoteocd-bin", default=DEFAULT_REMOTEOCD)
    parser.add_argument("--remoteocd-cfg", default=DEFAULT_REMOTEOCD_CFG)
    args = parser.parse_args()
    if args.router == "/run/arduino-router.sock" and not os.path.exists(args.router):
        if os.path.exists("/var/run/arduino-router.sock"):
            args.router = "/var/run/arduino-router.sock"

    rpc = RpcBridge(args.router, serial_baud=int(args.serial_baud))
    log_path = args.log_file.strip() if isinstance(args.log_file, str) else args.log_file
    if log_path == "":
        log_path = None
    logs = LogStore(max_bytes=args.log_bytes, log_path=log_path, file_max_bytes=args.log_file_bytes)
    firmware_update = None
    token_file = args.firmware_update_token_file.strip()
    if token_file:
        firmware_update = FirmwareUpdateConfig(
            token_file=token_file,
            upload_dir=args.firmware_upload_dir,
            remoteocd_bin=args.remoteocd_bin,
            remoteocd_cfg=args.remoteocd_cfg,
            max_bytes=args.firmware_update_max_bytes,
            timeout_sec=args.firmware_update_timeout_sec,
            max_vdc=args.firmware_update_max_vdc,
        )
    attestation_url = args.bench_gate_attestation_url.strip()
    standalone_enabled = bool(args.standalone_hv or args.standalone_lv)
    initial_profile = ARM_PROFILE_LV if args.standalone_lv else ARM_PROFILE_HV
    hv_cfg = HvArmConfig(
        enabled=standalone_enabled,
        ttl_sec=float(args.hv_arm_ttl_sec),
        min_vdc=float(args.hv_arm_min_vdc),
        max_vdc=float(args.hv_arm_max_vdc),
        confirm=str(args.hv_arm_confirm),
        profile=ARM_PROFILE_HV,
    )
    lv_cfg = HvArmConfig(
        enabled=standalone_enabled,
        ttl_sec=float(args.lv_arm_ttl_sec),
        min_vdc=DEFAULT_LV_ARM_MIN_VDC,
        max_vdc=float(args.lv_arm_max_vdc),
        confirm=str(args.lv_arm_confirm),
        profile=ARM_PROFILE_LV,
    )
    arm_profiles = (
        {ARM_PROFILE_HV: hv_cfg, ARM_PROFILE_LV: lv_cfg}
        if standalone_enabled
        else {}
    )
    hv_runlimit_sec = float(args.start_runlimit_sec)
    lv_runlimit_sec = min(hv_runlimit_sec, DEFAULT_LV_START_RUNLIMIT_SEC)
    profile_runlimits = {
        ARM_PROFILE_HV: hv_runlimit_sec,
        ARM_PROFILE_LV: lv_runlimit_sec,
    }
    selected_cfg = arm_profiles.get(initial_profile, hv_cfg)
    guard_max_vdc = (
        min(float(args.cmd_guard_max_vdc), selected_cfg.max_vdc)
        if initial_profile == ARM_PROFILE_LV
        else float(args.cmd_guard_max_vdc)
    )
    start_runlimit_sec = profile_runlimits[initial_profile]

    command_guard = CommandGuardConfig(
        max_vdc=guard_max_vdc,
        allow_hv=bool(args.cmd_guard_allow_hv or args.standalone_hv),
        disabled=bool(args.cmd_guard_disable),
        bench_gate_url=attestation_url or args.bench_gate_url.strip() or f"http://127.0.0.1:{int(args.port)}",
        bench_gate_runner=attested_bench_gate_runner if attestation_url else None,
        local_bench_gate=standalone_enabled,
    )
    hv_arm = HvArmState(selected_cfg)
    app = AppState(
        rpc,
        logs,
        args.status_log_sec,
        firmware_update=firmware_update,
        command_guard=command_guard,
        hv_arm=hv_arm,
        start_runlimit_sec=start_runlimit_sec,
        arm_profiles=arm_profiles,
        profile_runlimits=profile_runlimits,
        guard_max_vdc=float(args.cmd_guard_max_vdc),
    )

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.app = app  # type: ignore[attr-defined]
    server.daemon_threads = True

    print(
        f"UNOQ HMI on http://{args.bind}:{args.port} (router: {args.router}, "
        f"standalone_hv={int(args.standalone_hv)}, standalone_lv={int(args.standalone_lv)}, "
        f"precharge_relay=nucleo-managed, runlimit={start_runlimit_sec:.1f}s)"
    )
    app.start_safety_watchdog()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop_safety_watchdog()


if __name__ == "__main__":
    main()

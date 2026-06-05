#!/usr/bin/env python3
import argparse
import base64
import csv
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime
import urllib.error

import grpc
from saleae.automation import Manager
from saleae.automation.capture import Capture
from saleae.grpc import saleae_pb2
import urllib.request

BP_MAX_AGE_MS = 1000.0

ADB_ROUTER_CMD_SNIPPET = r"""
import base64, socket, sys, time
sys.path.insert(0, '/data/local/tmp')
from router_rpc import rpc_call

if len(sys.argv) >= 2 and sys.argv[1] == '--b64':
    cmds = [base64.b64decode(x.encode('ascii')).decode('utf-8') for x in sys.argv[2:]]
else:
    cmds = sys.argv[1:]
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(1.0)
sock.connect('/var/run/arduino-router.sock')
ok = True
for i, cmd in enumerate(cmds, 1):
    try:
        resp = rpc_call(sock, i, 'cmd', [cmd])
        if not (isinstance(resp, list) and len(resp) >= 4 and resp[2] is None and resp[3] is True):
            print(cmd, resp)
            ok = False
    except Exception as exc:
        print(cmd, 'ERR', repr(exc))
        ok = False
    time.sleep(0.05)
sock.close()
raise SystemExit(0 if ok else 2)
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def http_json(url: str, body: dict | None = None, timeout: float = 6.5) -> dict | None:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            last_exc = exc
            transient = exc.code in (500, 502, 503, 504)
        except Exception as exc:
            last_exc = exc
            transient = True
        if transient and attempt < 2:
            time.sleep(0.15 * (attempt + 1))
            continue
        break
    log(f"HTTP error: {last_exc}")
    return None


def adb_router_fallback_enabled() -> bool:
    val = os.environ.get("UNOQ_ADB_ROUTER_FALLBACK", "")
    return val.strip().lower() in ("1", "true", "yes", "on")


def post_cmd_adb_router(cmd: str) -> bool:
    if not adb_router_fallback_enabled():
        return False
    device = os.environ.get("UNOQ_ADB_DEVICE") or os.environ.get("ANDROID_SERIAL") or "79204341"
    encoded = base64.b64encode(cmd.encode("utf-8")).decode("ascii")
    try:
        proc = subprocess.run(
            ["adb", "-s", device, "shell", "python3", "-", "--b64", encoded],
            input=ADB_ROUTER_CMD_SNIPPET,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except Exception as exc:
        log(f"WARN: ADB router fallback failed for {cmd!r}: {exc}")
        return False
    if proc.returncode == 0:
        log(f"WARN: UI cmd fallback via ADB router OK: {cmd}")
        return True
    detail = (proc.stdout or proc.stderr or "").strip()
    if detail:
        log(f"WARN: ADB router fallback rejected {cmd!r}: {detail}")
    else:
        log(f"WARN: ADB router fallback rejected {cmd!r}: rc={proc.returncode}")
    return False


def truthy_env(name: str) -> bool:
    val = os.environ.get(name, "")
    return val.strip().lower() in ("1", "true", "yes", "on")


def command_requests_start(cmd: str) -> bool:
    return cmd.strip().upper() == "START"


def max_start_vdc() -> float:
    raw = os.environ.get("UNOQ_MAX_START_VDC", "60.0").strip()
    try:
        val = float(raw)
        if math.isfinite(val) and val >= 0.0:
            return val
    except Exception:
        pass
    return 60.0


def start_vdc_samples() -> int:
    raw = os.environ.get("UNOQ_START_VDC_SAMPLES", "5").strip()
    try:
        return max(1, min(20, int(float(raw))))
    except Exception:
        return 5


def status_vdc(st: dict | None) -> float:
    if st is None:
        return float("nan")
    return max(st_num(st, "bp_vdc", -1.0), st_num(st, "vdc", -1.0))


def start_allowed_by_vdc(base: str) -> bool:
    if truthy_env("UNOQ_ALLOW_HV"):
        return True
    limit = max_start_vdc()
    samples: list[float] = []
    for idx in range(start_vdc_samples()):
        st = get_status(base)
        vdc = status_vdc(st)
        if math.isfinite(vdc) and vdc >= 0.0:
            samples.append(vdc)
        if idx + 1 < start_vdc_samples():
            time.sleep(0.05)
    if not samples:
        log("ERROR: START blocked: status/vdc is not readable. Set UNOQ_ALLOW_HV=1 only for an intentional HV run.")
        return False
    vdc = max(samples)
    if vdc > limit:
        log(
            f"ERROR: START blocked: max sampled vdc={vdc:.2f} V exceeds UNOQ_MAX_START_VDC={limit:.2f} V. "
            "Remove/discharge HV or set UNOQ_ALLOW_HV=1 for an intentional HV run."
        )
        return False
    return True


def post_cmd(base: str, cmd: str) -> bool:
    if command_requests_start(cmd) and not start_allowed_by_vdc(base):
        return False
    resp = http_json(base + "/api/cmd", {"cmd": cmd})
    if resp and resp.get("ok"):
        return True
    return post_cmd_adb_router(cmd)


def configure_adb_router_fallback(enabled: bool, device: str | None = None) -> None:
    if enabled:
        os.environ["UNOQ_ADB_ROUTER_FALLBACK"] = "1"
    if device:
        os.environ["UNOQ_ADB_DEVICE"] = device


def get_status(base: str) -> dict | None:
    resp = http_json(base + "/api/status")
    if not resp or not resp.get("ok"):
        return None
    return resp.get("data")


def st_num(st: dict, key: str, default: float = 0.0) -> float:
    try:
        val = st.get(key, default)
        if isinstance(val, str):
            val = val.strip()
        num = float(val)
        if not math.isfinite(num):
            return float(default)
        return num
    except Exception:
        return float(default)


def bp_link_live(st: dict | None, max_age_ms: float = BP_MAX_AGE_MS) -> bool:
    if st is None:
        return False
    if st.get("link") is False:
        return False
    ages: list[float] = []
    for key in ("bp_rsp_age_ms", "bp_age_ms"):
        if key in st:
            ages.append(st_num(st, key, 999999.0))
    if st.get("last_rx_age_s") is not None:
        ages.append(st_num(st, "last_rx_age_s", 999999.0) * 1000.0)
    return bool(ages) and min(ages) <= max_age_ms


def bp_bad_value(st: dict | None) -> int:
    if st is None:
        return 999999
    return int(st_num(st, "bp_bad", 999999.0))


def bp_cmd_bad_value(st: dict | None) -> int:
    if st is None:
        return 999999
    return int(st_num(st, "bp_bad_cnt", 999999.0))


def bp_bad_limit() -> int:
    raw = os.environ.get("UNOQ_BP_BAD_BASELINE", "0").strip()
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 0


def bp_cmd_bad_limit() -> int:
    raw = os.environ.get("UNOQ_BP_CMD_BAD_BASELINE", "0").strip()
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 0


def bp_bad_ok(st: dict | None) -> bool:
    return bp_bad_value(st) <= bp_bad_limit()


def bp_cmd_bad_ok(st: dict | None) -> bool:
    return bp_cmd_bad_value(st) <= bp_cmd_bad_limit()


def configure_bp_bad_baseline(st: dict | None) -> int:
    baseline = bp_bad_value(st)
    if baseline < 999999:
        os.environ["UNOQ_BP_BAD_BASELINE"] = str(max(0, baseline))
    cmd_baseline = bp_cmd_bad_value(st)
    if cmd_baseline < 999999:
        os.environ["UNOQ_BP_CMD_BAD_BASELINE"] = str(max(0, cmd_baseline))
    return baseline


def status_is_safe(st: dict | None, allow_estop: bool = False) -> bool:
    if st is None:
        return False
    estop = int(st_num(st, "estop", 1.0))
    bp_fault_free = int(st_num(st, "bp_fault", 255.0)) == 0
    return (
        st.get("state") == "SAFE"
        and int(st_num(st, "pwm", 1.0)) == 0
        and bp_link_live(st)
        and bp_cmd_bad_ok(st)
        and (allow_estop or estop == 0)
        and (allow_estop or bp_fault_free)
    )


def status_fault_free(st: dict | None) -> bool:
    if st is None:
        return False
    return (
        bp_link_live(st)
        and int(st_num(st, "bp_fault", 255.0)) == 0
        and bp_cmd_bad_ok(st)
    )


def status_mode_matches(st: dict | None, expected_mode: str) -> bool:
    if st is None:
        return False
    mode_name = str(st.get("mode", ""))
    diag_mode = int(st_num(st, "diag_mode", -1.0))
    duty_mode = int(st_num(st, "duty_mode", -1.0))
    if expected_mode == "VF":
        if diag_mode >= 0 and duty_mode >= 0:
            return mode_name == "VF" and diag_mode == 0 and duty_mode == 0
        return mode_name == "VF"
    if expected_mode == "FOC":
        return mode_name == "FOC"
    if expected_mode == "DIAG":
        return mode_name == "DIAG"
    if expected_mode == "DUTY":
        return mode_name == "DUTY"
    return mode_name == expected_mode


def vf_steady_matches(
    st: dict | None,
    freq_cmd: float,
    freq_tol_abs: float = 0.25,
    freq_tol_rel: float = 0.03,
) -> bool:
    if st is None:
        return False
    tol = max(freq_tol_abs, abs(freq_cmd) * freq_tol_rel)
    return (
        st.get("state") == "VF_RUN"
        and status_mode_matches(st, "VF")
        and int(st_num(st, "pwm", -1.0)) == 1
        and int(st_num(st, "estop", 1.0)) == 0
        and status_fault_free(st)
        and abs(st_num(st, "freq_cmd", 0.0) - float(freq_cmd)) <= 0.06
        and abs(st_num(st, "freq", 0.0) - float(freq_cmd)) <= tol
    )


def wait_for(base: str, predicate, timeout_s: float, poll_s: float) -> tuple[bool, dict | None, float]:
    start = time.monotonic()
    last = None
    while (time.monotonic() - start) < timeout_s:
        st = get_status(base)
        if st is not None:
            last = st
            if predicate(st):
                return True, st, (time.monotonic() - start)
        time.sleep(poll_s)
    return False, last, (time.monotonic() - start)


def wait_http_ready(base: str, timeout_s: float, poll_s: float) -> tuple[bool, dict | None, float]:
    return wait_for(base, lambda _st: True, timeout_s=timeout_s, poll_s=poll_s)


def wait_status_retry(
    base: str,
    predicate,
    timeout_s: float,
    poll_s: float,
    retries: int = 0,
    retry_delay_s: float = 0.15,
    label: str = "status",
) -> tuple[bool, dict | None, float]:
    st = None
    dt = 0.0
    for attempt in range(retries + 1):
        ok, st, dt = wait_for(base, predicate, timeout_s=timeout_s, poll_s=poll_s)
        if ok:
            return True, st, dt
        if attempt < retries:
            log(f"WARN: {label} timeout or mismatch, retry {attempt + 1}/{retries}")
            time.sleep(retry_delay_s)
    return False, st, dt


# StartCapture can sporadically take a few seconds on Logic2 (USB reconnect, device reconfig, app hiccup).
# Keep it finite, but less brittle than 5s.
_START_CAPTURE_TIMEOUT_S = 15.0
_START_CAPTURE_RETRIES = 2
_DEVICE_REAPPEAR_TIMEOUT_S = 12.0
DEFAULT_MAX_OVERLAP_RATIO = 5e-4
DEFAULT_MIN_PULSE_WIDTH_NS = 100.0


def refresh_manager_connection(mgr: Manager, port: int) -> bool:
    try:
        try:
            mgr.channel.close()
        except Exception:
            pass
        new_mgr = Manager.connect(port=port, connect_timeout_seconds=5)
        mgr.channel = new_mgr.channel
        mgr._stub = new_mgr._stub
        mgr.logic2_process = None
        mgr._codex_port = port
        return True
    except Exception as exc:
        log(f"WARN: failed to refresh Saleae manager connection: {exc}")
        return False


def recover_logic2(mgr: Manager) -> bool:
    port = int(getattr(mgr, "_codex_port", 10430))
    script = os.path.join(os.path.dirname(__file__), "logic2_recover.py")
    cmd = [
        sys.executable,
        script,
        "--restart",
        "--port",
        str(port),
        "--wait-app",
        "30",
        "--wait-device",
        "30",
    ]
    log(f"WARN: attempting Logic2 recovery on port {port}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        log(f"WARN: Logic2 recovery launch failed: {exc}")
        return False
    if proc.stdout.strip():
        for line in proc.stdout.strip().splitlines():
            log(line)
    if proc.stderr.strip():
        for line in proc.stderr.strip().splitlines():
            log(line)
    if proc.returncode != 0:
        log(f"WARN: Logic2 recovery failed rc={proc.returncode}")
        return False
    return refresh_manager_connection(mgr, port)


def start_capture(mgr: Manager, channels: list[int], rate: int, duration: float) -> Capture:
    req = saleae_pb2.StartCaptureRequest()
    req.logic_device_configuration.logic_channels.CopyFrom(
        saleae_pb2.LogicChannels(digital_channels=channels, analog_channels=[])
    )
    req.logic_device_configuration.digital_sample_rate = rate
    req.capture_configuration.timed_capture_mode.CopyFrom(
        saleae_pb2.TimedCaptureMode(duration_seconds=duration, trim_data_seconds=0.0)
    )
    last_exc: grpc.RpcError | None = None
    for attempt in range(_START_CAPTURE_RETRIES + 1):
        try:
            if attempt:
                log(f"WARN: StartCapture retry {attempt}/{_START_CAPTURE_RETRIES}")
            reply = mgr.stub.StartCapture(req, timeout=_START_CAPTURE_TIMEOUT_S)
            return Capture(mgr, reply.capture_info.capture_id)
        except grpc.RpcError as exc:
            last_exc = exc
            code = exc.code() if hasattr(exc, "code") else None
            details = exc.details() if hasattr(exc, "details") else ""
            msg = details or str(exc)
            transient = code in (
                grpc.StatusCode.DEADLINE_EXCEEDED,
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.INTERNAL,
                grpc.StatusCode.UNKNOWN,
                grpc.StatusCode.ABORTED,
            )
            no_device = "No physical devices found" in msg
            if no_device:
                reappear_deadline = time.monotonic() + _DEVICE_REAPPEAR_TIMEOUT_S
                seen = False
                while time.monotonic() < reappear_deadline:
                    try:
                        if mgr.get_devices():
                            seen = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.25)
                if not seen:
                    log("WARN: Saleae device did not reappear before retry deadline")
                    if recover_logic2(mgr):
                        seen = False
                        recover_deadline = time.monotonic() + 5.0
                        while time.monotonic() < recover_deadline:
                            try:
                                if mgr.get_devices():
                                    seen = True
                                    break
                            except Exception:
                                pass
                            time.sleep(0.25)
                        if seen:
                            log("WARN: Saleae device restored after Logic2 recovery")
            if attempt < _START_CAPTURE_RETRIES and transient:
                log(
                    f"WARN: StartCapture failed attempt={attempt+1}/{_START_CAPTURE_RETRIES+1} code={code} details={msg}"
                )
                time.sleep(0.25 + 0.25 * attempt)
                continue
            log(
                f"ERROR: StartCapture failed attempt={attempt+1}/{_START_CAPTURE_RETRIES+1} code={code} details={msg}"
            )
            raise
    raise last_exc if last_exc is not None else RuntimeError("StartCapture failed")


def wait_capture_with_timeout(mgr: Manager, capture: Capture, timeout_s: float) -> None:
    req = saleae_pb2.WaitCaptureRequest(capture_id=capture.capture_id)
    try:
        mgr.stub.WaitCapture(req, timeout=timeout_s)
    except grpc.RpcError as exc:
        # Best-effort stop if wait timed out or failed
        try:
            capture.stop()
        except Exception:
            pass
        raise exc


def export_capture(capture: Capture, channels: list[int], outdir: str, tag: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.abspath(os.path.join(outdir, f"{tag}_{ts}"))
    os.makedirs(folder, exist_ok=True)
    capture.export_raw_data_csv(folder, digital_channels=channels)
    return os.path.join(folder, "digital.csv")


def load_transitions(
    csv_path: str, channels: list[int]
) -> tuple[dict[int, list[float]], dict[int, list[int]], float | None, float | None]:
    times = {ch: [] for ch in channels}
    levels = {ch: [] for ch in channels}
    prev = {ch: None for ch in channels}
    t0 = None
    t_last = None
    with open(csv_path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return times, levels, None, None
        chan_offset = 1
        for row in reader:
            if not row or len(row) <= chan_offset + max(channels):
                continue
            t = float(row[0])
            if t0 is None:
                t0 = t
            t_last = t
            for ch in channels:
                v = 1 if row[chan_offset + ch] == "1" else 0
                if prev[ch] is None or v != prev[ch]:
                    times[ch].append(t)
                    levels[ch].append(v)
                    prev[ch] = v
    return times, levels, t0, t_last


def filter_short_pulses(
    times: list[float], levels: list[int], min_width_s: float
) -> tuple[list[float], list[int], int]:
    if min_width_s <= 0.0 or len(times) < 3:
        return times, levels, 0

    out_times = list(times)
    out_levels = list(levels)
    removed = 0
    i = 1
    while i < len(out_times) - 1:
        is_pulse = out_levels[i] != out_levels[i - 1] and out_levels[i + 1] == out_levels[i - 1]
        width = out_times[i + 1] - out_times[i]
        if is_pulse and 0.0 <= width <= min_width_s:
            del out_times[i : i + 2]
            del out_levels[i : i + 2]
            removed += 1
            if i > 1:
                i -= 1
            continue
        i += 1
    return out_times, out_levels, removed


def pwm_metrics(times: list[float], levels: list[int]) -> tuple[int, float | None, float | None]:
    edges = max(0, len(times) - 1)
    if len(times) < 4:
        return edges, None, None
    rises = []
    falls = []
    for i in range(1, len(times)):
        if levels[i - 1] == 0 and levels[i] == 1:
            rises.append(times[i])
        elif levels[i - 1] == 1 and levels[i] == 0:
            falls.append(times[i])
    if len(rises) < 2:
        return edges, None, None

    fall_idx = 0
    periods = []
    duties = []
    for i in range(len(rises) - 1):
        t0 = rises[i]
        t1 = rises[i + 1]
        period = t1 - t0
        if period <= 0:
            continue
        if period < 1.0 / 20000.0 or period > 1.0 / 3000.0:
            continue
        while fall_idx < len(falls) and falls[fall_idx] <= t0:
            fall_idx += 1
        if fall_idx >= len(falls):
            break
        tf = falls[fall_idx]
        if tf >= t1:
            continue
        high = tf - t0
        duty = high / period if period > 0 else 0
        periods.append(period)
        duties.append(duty)
    if not periods:
        return edges, None, None
    periods.sort()
    duties.sort()
    period = periods[len(periods) // 2]
    duty = duties[len(duties) // 2]
    freq = 1.0 / period if period > 0 else None
    return edges, freq, duty


def high_ratio(times: list[float], levels: list[int], t_end: float | None) -> float | None:
    if t_end is None or not times or not levels:
        return None
    t_start = times[0]
    if t_end <= t_start:
        return None

    high = 0.0
    for i in range(1, len(times)):
        dt = times[i] - times[i - 1]
        if dt <= 0:
            continue
        if levels[i - 1] == 1:
            high += dt

    # Tail segment until capture end
    tail = t_end - times[-1]
    if tail > 0 and levels[-1] == 1:
        high += tail

    total = t_end - t_start
    if total <= 0:
        return None
    return high / total


def overlap_ratio(times_a: list[float], levels_a: list[int], times_b: list[float], levels_b: list[int]) -> float | None:
    if len(times_a) < 2 or len(times_b) < 2:
        return None
    t_start = max(times_a[0], times_b[0])
    t_end = min(times_a[-1], times_b[-1])
    if t_end <= t_start:
        return None
    ia = 0
    ib = 0
    while ia + 1 < len(times_a) and times_a[ia + 1] <= t_start:
        ia += 1
    while ib + 1 < len(times_b) and times_b[ib + 1] <= t_start:
        ib += 1
    la = levels_a[ia]
    lb = levels_b[ib]
    t = t_start
    overlap = 0.0
    total = 0.0
    while t < t_end:
        ta = times_a[ia + 1] if (ia + 1) < len(times_a) else t_end
        tb = times_b[ib + 1] if (ib + 1) < len(times_b) else t_end
        t_next = min(ta, tb, t_end)
        dt = t_next - t
        if dt > 0:
            total += dt
            if la == 1 and lb == 1:
                overlap += dt
        if t_next == ta and (ia + 1) < len(times_a):
            ia += 1
            la = levels_a[ia]
        if t_next == tb and (ib + 1) < len(times_b):
            ib += 1
            lb = levels_b[ib]
        t = t_next
    if total <= 0:
        return None
    return overlap / total


def edge_times(times: list[float], levels: list[int]) -> tuple[list[float], list[float]]:
    rises: list[float] = []
    falls: list[float] = []
    if len(times) < 2:
        return rises, falls
    for i in range(1, len(times)):
        if levels[i - 1] == 0 and levels[i] == 1:
            rises.append(times[i])
        elif levels[i - 1] == 1 and levels[i] == 0:
            falls.append(times[i])
    return rises, falls


def handoff_gap_stats(
    times_a: list[float],
    levels_a: list[int],
    times_b: list[float],
    levels_b: list[int],
    max_gap_s: float = 20e-6,
    trim_edge_s: float = 100e-6,
) -> dict[str, float] | None:
    rises_a, falls_a = edge_times(times_a, levels_a)
    rises_b, falls_b = edge_times(times_b, levels_b)
    if not rises_a or not rises_b or not falls_a or not falls_b:
        return None

    gaps_s: list[float] = []
    t_start = max(times_a[0], times_b[0])
    t_end = min(times_a[-1], times_b[-1])
    if t_end <= t_start:
        return None
    valid_from = t_start + max(0.0, trim_edge_s)
    valid_to = t_end - max(0.0, trim_edge_s)
    if valid_to <= valid_from:
        valid_from = t_start
        valid_to = t_end

    def collect(falls_from: list[float], rises_to: list[float], rises_from: list[float]) -> None:
        if not falls_from or not rises_to:
            return
        j = 0
        k = 0
        for tf in falls_from:
            if tf < valid_from or tf > valid_to:
                continue
            while j < len(rises_to) and rises_to[j] <= tf:
                j += 1
            if j >= len(rises_to):
                break
            while k < len(rises_from) and rises_from[k] <= tf:
                k += 1
            next_same_rise = rises_from[k] if k < len(rises_from) else None
            tr = rises_to[j]
            if tr < valid_from or tr > valid_to:
                continue
            gap = tr - tf
            if gap <= 0.0 or gap > max_gap_s:
                continue
            if next_same_rise is not None and tr >= next_same_rise:
                continue
            gaps_s.append(gap)

    collect(falls_a, rises_b, rises_a)
    collect(falls_b, rises_a, rises_b)

    if not gaps_s:
        return None
    gaps_ns = [gap * 1e9 for gap in gaps_s]
    return {
        "min": min(gaps_ns),
        "mean": sum(gaps_ns) / len(gaps_ns),
        "max": max(gaps_ns),
        "count": float(len(gaps_ns)),
    }


def analyze(
    csv_path: str,
    channels: list[int],
    brake_active_high: bool,
    expect_pwm: bool,
    expect_estop: bool,
    expect_brake_active: bool | None = None,
    max_overlap_ratio: float = DEFAULT_MAX_OVERLAP_RATIO,
    min_handoff_gap_ns: float = 0.0,
    min_pulse_width_ns: float = DEFAULT_MIN_PULSE_WIDTH_NS,
) -> dict:
    times, levels, t0, t_last = load_transitions(csv_path, channels)
    glitch_removed: dict[str, int] = {}
    min_pulse_width_s = max(0.0, float(min_pulse_width_ns)) * 1e-9
    if min_pulse_width_s > 0.0:
        for ch in channels:
            times[ch], levels[ch], removed = filter_short_pulses(times.get(ch, []), levels.get(ch, []), min_pulse_width_s)
            glitch_removed[str(ch)] = removed
    metrics = {
        "channels": {},
        "brake_high": None,
        "overlap": {},
        "handoff_gap_ns": {},
        "max_overlap_ratio": max_overlap_ratio,
        "min_handoff_gap_ns": float(min_handoff_gap_ns),
        "min_pulse_width_ns": float(min_pulse_width_ns),
        "glitch_removed": glitch_removed,
    }

    pwm_ok = True
    for ch in [0, 2, 4]:
        edges, freq, duty = pwm_metrics(times.get(ch, []), levels.get(ch, []))
        metrics["channels"][str(ch)] = {"edges": edges, "freq_hz": freq, "duty": duty}
        if expect_pwm:
            if edges < 1000:
                pwm_ok = False
            if freq is None or not (3000.0 <= freq <= 20000.0):
                pwm_ok = False
            if duty is None or not (0.01 <= duty <= 0.99):
                pwm_ok = False
        else:
            if edges >= 1000:
                pwm_ok = False

    for ch in [1, 3, 5]:
        edges, freq, duty = pwm_metrics(times.get(ch, []), levels.get(ch, []))
        metrics["channels"][str(ch)] = {"edges": edges, "freq_hz": freq, "duty": duty}
        if expect_pwm:
            if edges < 1000:
                pwm_ok = False
        else:
            if edges >= 1000:
                pwm_ok = False

    # By default:
    # - RUN (expect_pwm=True)     -> expect brake deasserted
    # - SAFE/STOP (expect_pwm=False) -> expect brake asserted (inverter shutdown)
    # - ESTOP (expect_estop=True) -> expect brake asserted
    if expect_brake_active is None:
        expect_brake_active = bool(expect_estop or (not expect_pwm))

    b_ratio = high_ratio(times.get(6, []), levels.get(6, []), t_last)
    metrics["brake_high"] = b_ratio
    brake_ok = True
    if b_ratio is None:
        brake_ok = False
    elif expect_brake_active:
        if brake_active_high and b_ratio < 0.95:
            brake_ok = False
        if (not brake_active_high) and b_ratio > 0.05:
            brake_ok = False
    else:
        if brake_active_high and b_ratio > 0.05:
            brake_ok = False
        if (not brake_active_high) and b_ratio < 0.95:
            brake_ok = False

    overlap_ok = True
    deadtime_ok = True
    if expect_pwm:
        for a, b in [(0, 1), (2, 3), (4, 5)]:
            r = overlap_ratio(times.get(a, []), levels.get(a, []), times.get(b, []), levels.get(b, []))
            metrics["overlap"][f"{a}-{b}"] = r
            if r is not None and r > max_overlap_ratio:
                overlap_ok = False
            gap_stats = handoff_gap_stats(times.get(a, []), levels.get(a, []), times.get(b, []), levels.get(b, []))
            metrics["handoff_gap_ns"][f"{a}-{b}"] = gap_stats
            if min_handoff_gap_ns > 0.0:
                if gap_stats is None or gap_stats["min"] < min_handoff_gap_ns:
                    deadtime_ok = False

    metrics["pass"] = bool(pwm_ok and brake_ok and overlap_ok and deadtime_ok)
    metrics["pwm_ok"] = pwm_ok
    metrics["brake_ok"] = brake_ok
    metrics["overlap_ok"] = overlap_ok
    metrics["deadtime_ok"] = deadtime_ok
    return metrics


def send_cmds(base: str, cmds: list[str]) -> bool:
    ok = True
    for cmd in cmds:
        if not post_cmd(base, cmd):
            log(f"ERROR: UI cmd failed: {cmd}")
            ok = False
    return ok


def send_cmds_retry(base: str, cmds: list[str], retries: int = 1, retry_delay_s: float = 0.15) -> bool:
    for attempt in range(retries + 1):
        ok = send_cmds(base, cmds)
        if ok:
            return True
        if attempt < retries:
            log(f"WARN: cmd send failed, retry {attempt + 1}/{retries}")
            time.sleep(retry_delay_s)
    return False


def control_retry_reason(cmd_ok: bool, status_ok: bool, metrics: dict | None) -> str:
    if metrics is None:
        return "capture"
    if not metrics.get("pass"):
        return ""
    reasons = []
    if not cmd_ok:
        reasons.append("cmd")
    if not status_ok:
        reasons.append("status")
    return "+".join(reasons)


def safe_stop(base: str) -> None:
    # Best-effort bounded cleanup:
    # 1. Normal STOP.
    # 2. If run did not stop, force ESTOP.
    # 3. CLEAR estop latch and confirm SAFE without PWM.
    # This must never block forever.
    try:
        wait_http_ready(base, timeout_s=2.0, poll_s=0.1)
        send_cmds_retry(base, ["STOP"], retries=2, retry_delay_s=0.2)
        ok, st, dt = wait_for(
            base,
            lambda s: status_is_safe(s, allow_estop=True),
            timeout_s=1.5,
            poll_s=0.05,
        )
        if not ok:
            log(f"WARN: STOP not confirmed after {dt*1000:.1f}ms st={st}")
            wait_http_ready(base, timeout_s=2.0, poll_s=0.1)
            send_cmds_retry(base, ["ESTOP"], retries=2, retry_delay_s=0.2)
            estop_ok, estop_st, estop_dt = wait_for(
                base,
                lambda s: status_is_safe(s, allow_estop=True),
                timeout_s=1.5,
                poll_s=0.05,
            )
            if not estop_ok:
                log(f"WARN: ESTOP cleanup not confirmed after {estop_dt*1000:.1f}ms st={estop_st}")
        wait_http_ready(base, timeout_s=2.0, poll_s=0.1)
        send_cmds_retry(base, ["CLEAR"], retries=2, retry_delay_s=0.2)
        clear_ok, clear_st, clear_dt = wait_for(
            base,
            lambda s: status_is_safe(s, allow_estop=False),
            timeout_s=2.0,
            poll_s=0.05,
        )
        if not clear_ok:
            log(f"WARN: CLEAR not confirmed after {clear_dt*1000:.1f}ms st={clear_st}")
    except Exception as exc:
        log(f"WARN: safe_stop failed: {exc}")


def run_case(args) -> int:
    base = args.url.rstrip("/")
    channels = [int(x) for x in args.la_channels.split(",") if x.strip() != ""]

    log(f"START case tag={args.tag} mode={args.mode} freq={args.freq} duty={args.duty}")
    mgr = None
    try:
        log("Connect Saleae")
        if args.saleae_host not in ("127.0.0.1", "localhost"):
            log(f"WARN: saleae-host '{args.saleae_host}' not supported by this Saleae SDK, using localhost")
        mgr = Manager.connect(port=args.saleae_port, connect_timeout_seconds=2)
        mgr._codex_port = args.saleae_port
        # Logic2 can be running without an attached device. Poll briefly to avoid flakiness on USB reconnect.
        devices = []
        for _ in range(30):
            devices = mgr.get_devices()
            if devices:
                break
            time.sleep(0.1)
        if not devices:
            try:
                info = mgr.get_app_info()
                log(f"Logic2 connected: {info}")
            except Exception:
                pass
            log("ERROR: No Saleae device found (Logic2 sees no connected analyzer)")
            log("FIX: Open Logic2 and confirm a device is shown (not Demo mode). Replug USB or restart Logic2.")
            return 2

        log("Check UI reachability")
        ui_ok, ui_st, ui_dt = wait_http_ready(base, timeout_s=args.ui_ready_timeout, poll_s=max(0.05, args.poll))
        if not ui_ok:
            log(f"ERROR: UI not reachable after {ui_dt*1000:.1f}ms last_status={ui_st}")
            return 5

        cmds = []
        if not args.skip_clear:
            cmds.append("CLEAR")
        if args.mode == "VF":
            cmds += ["MODE VF", f"SET FREQ {args.freq:.1f}"]
        elif args.mode == "FOC":
            cmds += ["MODE FOC", f"SET FREQ {args.freq:.1f}"]
        elif args.mode == "DIAG":
            cmds += ["DIAG ON"]
        elif args.mode == "DUTY":
            cmds += ["MODE DUTY"]
            if args.duty:
                duty_str = args.duty.replace(",", " ").strip()
                cmds += [f"DUTY {duty_str}"]
        cmds += ["START"]

        def status_predicate(st):
            pwm_ok = int(st_num(st, "pwm", -1.0)) == (1 if args.expect_pwm else 0)
            if args.expect_estop and (not bp_link_live(st) or not bp_cmd_bad_ok(st)):
                return False
            if not args.expect_estop and not status_fault_free(st):
                return False
            if args.mode in ("VF", "FOC"):
                if abs(st_num(st, "freq_cmd", 0.0) - float(args.freq)) > 0.06:
                    return False
            if not status_mode_matches(st, args.mode):
                return False
            if args.mode == "VF" and args.expect_pwm:
                if not vf_steady_matches(st, args.freq):
                    return False
            if args.expect_estop:
                return pwm_ok and int(st_num(st, "estop", -1.0)) == 1
            return pwm_ok

        passed = False
        cmd_ok = False
        ok = False
        dt = 0.0
        st = None
        metrics = None
        csv_path = ""
        retry_reason = ""
        attempts = 0
        for attempt in range(args.case_retries + 1):
            attempts = attempt + 1
            if attempt:
                log(f"WARN: retry case attempt {attempts}/{args.case_retries + 1} after {retry_reason}")
                safe_stop(base)
                time.sleep(args.retry_delay)

            log("Send UI commands")
            cmd_ok = send_cmds_retry(base, cmds, retries=args.cmd_retries, retry_delay_s=args.retry_delay)

            log("Wait status")
            ok, st, dt = wait_status_retry(
                base,
                status_predicate,
                timeout_s=args.status_timeout,
                poll_s=args.poll,
                retries=args.status_retries,
                retry_delay_s=args.retry_delay,
                label="status",
            )
            if not ok:
                log("WARN: status timeout or mismatch")
            log(f"Status ok={ok} dt={dt*1000:.1f}ms st={st}")

            log("Start capture")
            try:
                capture = start_capture(mgr, channels, args.la_rate, args.la_duration)
            except grpc.RpcError as exc:
                code = exc.code() if hasattr(exc, "code") else None
                details = exc.details() if hasattr(exc, "details") else ""
                msg = details or str(exc)
                log(f"ERROR: StartCapture failed code={code} details={msg}")
                return 3
            try:
                wait_capture_with_timeout(mgr, capture, timeout_s=args.la_duration + 2.0)
            except grpc.RpcError as exc:
                log(f"ERROR: capture wait failed: {exc.details()}")
                return 3

            outdir = args.outdir
            csv_path = export_capture(capture, channels, outdir, args.tag)
            log(f"Capture saved: {csv_path}")
            capture.close()

            log("Analyze capture")
            metrics = analyze(
                csv_path,
                channels,
                args.brake_active_high == 1,
                args.expect_pwm,
                args.expect_estop,
                max_overlap_ratio=args.max_overlap_ratio,
                min_handoff_gap_ns=args.min_handoff_gap_ns,
                min_pulse_width_ns=args.min_pulse_width_ns,
            )
            passed = bool(metrics["pass"] and ok and cmd_ok)
            retry_reason = control_retry_reason(cmd_ok, ok, metrics)
            if retry_reason and attempt < args.case_retries:
                log(f"WARN: clean capture with transient {retry_reason}; retrying case")
                continue
            break

        summary = {
            "tag": args.tag,
            "mode": args.mode,
            "freq": args.freq,
            "duty": args.duty,
            "attempts": attempts,
            "retry_reason": retry_reason,
            "cmd_ok": cmd_ok,
            "status_ok": ok,
            "status_dt_ms": dt * 1000.0,
            "status": st,
            "metrics": metrics,
            "csv": csv_path,
        }
        summary_path = os.path.join(os.path.dirname(csv_path), "summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        log(f"Summary: {summary_path}")
        log(f"PASS={passed}")
        return 0 if passed else 4
    finally:
        if mgr is not None:
            try:
                mgr.close()
            except Exception:
                pass
        safe_stop(base)


def main() -> int:
    parser = argparse.ArgumentParser(description="Single UI->PWM case with Saleae capture")
    parser.add_argument("--url", required=True)
    parser.add_argument("--mode", choices=["VF", "FOC", "DIAG", "DUTY"], required=True)
    parser.add_argument("--freq", type=float, default=0.0)
    parser.add_argument("--duty", default="")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--la-channels", default="0,1,2,3,4,5,6")
    parser.add_argument("--la-rate", type=int, default=2000000)
    parser.add_argument("--la-duration", type=float, default=0.7)
    parser.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "_la_exports"))
    parser.add_argument("--poll", type=float, default=0.03)
    parser.add_argument("--status-timeout", type=float, default=0.6)
    parser.add_argument("--saleae-host", default="127.0.0.1")
    parser.add_argument("--saleae-port", type=int, default=10430)
    # IPM15 EM_STOP shutdown input is typically active-low.
    parser.add_argument("--brake-active-high", type=int, default=0)
    parser.add_argument("--expect-pwm", type=int, default=1)
    parser.add_argument("--expect-estop", type=int, default=0)
    parser.add_argument("--max-overlap-ratio", type=float, default=DEFAULT_MAX_OVERLAP_RATIO)
    parser.add_argument("--min-handoff-gap-ns", type=float, default=0.0)
    parser.add_argument("--min-pulse-width-ns", type=float, default=DEFAULT_MIN_PULSE_WIDTH_NS)
    parser.add_argument("--ui-ready-timeout", type=float, default=3.0)
    parser.add_argument("--cmd-retries", type=int, default=1)
    parser.add_argument("--status-retries", type=int, default=1)
    parser.add_argument("--case-retries", type=int, default=1)
    parser.add_argument("--retry-delay", type=float, default=0.2)
    parser.add_argument("--skip-clear", action="store_true")
    args = parser.parse_args()

    return run_case(args)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())

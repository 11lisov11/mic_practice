#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

import grpc
from saleae.automation import Manager
from saleae.automation.capture import Capture
from saleae.grpc import saleae_pb2
import urllib.request


def log(msg: str) -> None:
    print(msg, flush=True)


def http_json(url: str, body: dict | None = None, timeout: float = 2.0) -> dict | None:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except Exception as exc:
        log(f"HTTP error: {exc}")
        return None


def post_cmd(base: str, cmd: str) -> bool:
    resp = http_json(base + "/api/cmd", {"cmd": cmd})
    return bool(resp and resp.get("ok"))


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
        return float(val)
    except Exception:
        return float(default)


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


# StartCapture can sporadically take a few seconds on Logic2 (USB reconnect, device reconfig, app hiccup).
# Keep it finite, but less brittle than 5s.
_START_CAPTURE_TIMEOUT_S = 15.0
_START_CAPTURE_RETRIES = 2
DEFAULT_MAX_OVERLAP_RATIO = 5e-4


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
            )
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


def analyze(
    csv_path: str,
    channels: list[int],
    brake_active_high: bool,
    expect_pwm: bool,
    expect_estop: bool,
    expect_brake_active: bool | None = None,
    max_overlap_ratio: float = DEFAULT_MAX_OVERLAP_RATIO,
) -> dict:
    times, levels, t0, t_last = load_transitions(csv_path, channels)
    metrics = {"channels": {}, "brake_high": None, "overlap": {}, "max_overlap_ratio": max_overlap_ratio}

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
    if expect_pwm:
        for a, b in [(0, 1), (2, 3), (4, 5)]:
            r = overlap_ratio(times.get(a, []), levels.get(a, []), times.get(b, []), levels.get(b, []))
            metrics["overlap"][f"{a}-{b}"] = r
            if r is not None and r > max_overlap_ratio:
                overlap_ok = False

    metrics["pass"] = bool(pwm_ok and brake_ok and overlap_ok)
    metrics["pwm_ok"] = pwm_ok
    metrics["brake_ok"] = brake_ok
    metrics["overlap_ok"] = overlap_ok
    return metrics


def send_cmds(base: str, cmds: list[str]) -> bool:
    ok = True
    for cmd in cmds:
        if not post_cmd(base, cmd):
            log(f"ERROR: UI cmd failed: {cmd}")
            ok = False
    return ok


def safe_stop(base: str) -> None:
    # Best-effort stop + clear to force PWM off and brake on.
    # This must never block forever (tooling requirement).
    try:
        send_cmds(base, ["STOP"])
        ok, st, dt = wait_for(
            base,
            lambda s: int(st_num(s, "pwm", 0.0)) == 0,
            timeout_s=0.9,
            poll_s=0.05,
        )
        if not ok:
            log(f"WARN: STOP not confirmed after {dt*1000:.1f}ms st={st}")
    except Exception as exc:
        log(f"WARN: safe_stop STOP failed: {exc}")
    try:
        send_cmds(base, ["CLEAR"])
    except Exception as exc:
        log(f"WARN: safe_stop CLEAR failed: {exc}")


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

        log("Send UI commands")
        cmd_ok = True
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
        cmd_ok = send_cmds(base, cmds)

        log("Wait status")
        def status_predicate(st):
            pwm_ok = int(st_num(st, "pwm", 0.0)) == (1 if args.expect_pwm else 0)
            if args.mode in ("VF", "FOC"):
                if abs(st_num(st, "freq_cmd", 0.0) - float(args.freq)) > 0.06:
                    return False
            if args.expect_estop:
                return pwm_ok and int(st_num(st, "estop", 0.0)) == 1
            return pwm_ok

        ok, st, dt = wait_for(
            base,
            status_predicate,
            timeout_s=args.status_timeout,
            poll_s=args.poll,
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
        )
        passed = bool(metrics["pass"] and ok and cmd_ok)
        summary = {
            "tag": args.tag,
            "mode": args.mode,
            "freq": args.freq,
            "duty": args.duty,
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
    parser.add_argument("--skip-clear", action="store_true")
    args = parser.parse_args()

    return run_case(args)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())

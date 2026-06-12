#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError

RELAY_CONFIGS = {
    "ntc": {
        "cmd": "NTC",
        "field": "ntc",
        "ext_bit": 0x01,
        "tool": "ntc_relay_preflight",
        "tag": "ntc_relay_preflight",
        "description": "STEVAL J2-21 NTC bypass relay on Blue Pill PB1",
    },
    "precharge": {
        "cmd": "PRECHARGE",
        "field": "precharge",
        "ext_bit": 0x08,
        "tool": "precharge_relay_preflight",
        "tag": "precharge_relay_preflight",
        "description": "MIC_AI RELAY1 precharge bypass relay driver on Blue Pill PB4",
    },
}


def log(msg: str) -> None:
    print(msg, flush=True)


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def http_json(url: str, timeout_s: float) -> dict | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log(f"HTTP GET failed: {exc}")
        return None


def http_post_json(url: str, payload: dict, timeout_s: float) -> dict | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        log(f"HTTP POST failed cmd={payload.get('cmd')!r}: {exc}")
        return None


def get_status(base: str, timeout_s: float = 2.0) -> dict | None:
    resp = http_json(base.rstrip("/") + "/api/status", timeout_s)
    if not resp or not resp.get("ok"):
        return None
    data = resp.get("data")
    return data if isinstance(data, dict) else None


def post_cmd(base: str, cmd: str, timeout_s: float = 2.0) -> bool:
    resp = http_post_json(base.rstrip("/") + "/api/cmd", {"cmd": cmd}, timeout_s)
    ok = bool(resp and resp.get("ok"))
    log(f"CMD {cmd}: {'OK' if ok else 'FAIL'}")
    return ok


def status_num(st: dict | None, key: str, default: float = 0.0) -> float:
    if st is None:
        return float(default)
    try:
        val = st.get(key, default)
        if isinstance(val, str):
            val = val.strip()
        num = float(val)
        return num if math.isfinite(num) else float(default)
    except Exception:
        return float(default)


def status_int(st: dict | None, key: str, default: int = 0) -> int:
    return int(status_num(st, key, float(default)))


def bp_link_live(st: dict | None, max_age_ms: float = 1000.0) -> bool:
    if st is None:
        return False
    if st.get("link") is False:
        return False
    ages: list[float] = []
    for key in ("bp_rsp_age_ms", "bp_age_ms"):
        if key in st:
            ages.append(status_num(st, key, 999999.0))
    if st.get("last_rx_age_s") is not None:
        ages.append(status_num(st, "last_rx_age_s", 999999.0) * 1000.0)
    return bool(ages) and min(ages) <= max_age_ms


def vdc_max_seen(st: dict | None) -> float:
    if st is None:
        return 999999.0
    return max(status_num(st, "vdc", 0.0), status_num(st, "bp_vdc", 0.0))


def bp_bad_count(st: dict | None) -> int:
    if st is None:
        return 999999
    if "bp_bad_cnt" in st:
        return status_int(st, "bp_bad_cnt", 999999)
    return status_int(st, "bp_bad", 999999)


def safe_low_voltage(st: dict | None, max_vdc: float, allow_hv: bool) -> bool:
    if st is None:
        return False
    vdc_ok = allow_hv or vdc_max_seen(st) <= max_vdc
    return (
        st.get("state") == "SAFE"
        and status_int(st, "pwm", 1) == 0
        and status_int(st, "estop", 1) == 0
        and status_int(st, "bp_fault", 255) == 0
        and bp_bad_count(st) == 0
        and bp_link_live(st)
        and vdc_ok
    )


def wait_for(base: str, predicate, timeout_s: float, poll_s: float) -> tuple[bool, dict | None, float]:
    start = time.monotonic()
    last = None
    while (time.monotonic() - start) < timeout_s:
        st = get_status(base)
        if st is not None:
            last = st
            if predicate(st):
                return True, st, time.monotonic() - start
        time.sleep(poll_s)
    return False, last, time.monotonic() - start


def cleanup(base: str) -> None:
    for cmd in ("STOP", "IOTEST OFF", "CLEAR", "NTC OFF", "PRECHARGE OFF", "PFC OFF", "BRAKE OFF"):
        post_cmd(base, cmd)
        time.sleep(0.05)


def relay_status_ok(st: dict | None, on: bool, field: str, ext_bit: int) -> bool:
    if st is None:
        return False
    expected = 1 if on else 0
    if status_int(st, "pwm", 1) != 0:
        return False
    if status_int(st, "estop", 1) != 0:
        return False
    if status_int(st, "bp_fault", 255) != 0:
        return False
    if status_int(st, field, 1 - expected) != expected:
        return False
    if "bp_ext" in st and (1 if (status_int(st, "bp_ext", 0) & ext_bit) else 0) != expected:
        return False
    return True


def start_saleae_capture(port: int, channel: int, rate: int, duration_s: float):
    import grpc  # type: ignore
    import saleae.automation as sa  # type: ignore
    from saleae.automation.capture import Capture  # type: ignore
    from saleae.grpc import saleae_pb2  # type: ignore

    mgr = sa.Manager.connect(port=port, connect_timeout_seconds=5)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if mgr.get_devices():
            break
        time.sleep(0.25)
    if not mgr.get_devices():
        mgr.close()
        raise RuntimeError("Logic2 is running, but no Saleae device is visible")

    req = saleae_pb2.StartCaptureRequest()
    req.logic_device_configuration.logic_channels.CopyFrom(
        saleae_pb2.LogicChannels(digital_channels=[channel], analog_channels=[])
    )
    req.logic_device_configuration.digital_sample_rate = rate
    req.capture_configuration.timed_capture_mode.CopyFrom(
        saleae_pb2.TimedCaptureMode(duration_seconds=duration_s, trim_data_seconds=0.0)
    )
    reply = mgr.stub.StartCapture(req, timeout=15.0)
    return mgr, Capture(mgr, reply.capture_info.capture_id), saleae_pb2, grpc


def wait_saleae_capture(mgr, capture, saleae_pb2, grpc_mod, timeout_s: float) -> None:
    req = saleae_pb2.WaitCaptureRequest(capture_id=capture.capture_id)
    try:
        mgr.stub.WaitCapture(req, timeout=timeout_s)
    except grpc_mod.RpcError:
        try:
            capture.stop()
        except Exception:
            pass
        raise


def export_saleae_csv(capture, channel: int, outdir: Path) -> Path:
    folder = outdir / "saleae"
    folder.mkdir(parents=True, exist_ok=True)
    capture.export_raw_data_csv(str(folder), digital_channels=[channel])
    return folder / "digital.csv"


def find_channel_column(header: list[str], channel: int) -> int | None:
    target = f"channel{channel}"
    for idx, name in enumerate(header[1:], start=1):
        norm = "".join(ch.lower() for ch in name if ch.isalnum())
        if target in norm:
            return idx
    if len(header) == 2:
        return 1
    return None


def load_transitions(csv_path: Path, channel: int) -> tuple[list[float], list[int], float | None, float | None]:
    times: list[float] = []
    levels: list[int] = []
    prev: int | None = None
    t0 = None
    t_last = None
    with csv_path.open("r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return times, levels, None, None
        col = find_channel_column(header, channel)
        if col is None:
            raise RuntimeError(f"channel {channel} column not found in {csv_path}")
        for row in reader:
            if len(row) <= col:
                continue
            try:
                t = float(row[0])
            except ValueError:
                continue
            if t0 is None:
                t0 = t
            t_last = t
            v = 1 if row[col].strip() == "1" else 0
            if prev is None or v != prev:
                times.append(t)
                levels.append(v)
                prev = v
    return times, levels, t0, t_last


def high_ratio(times: list[float], levels: list[int], t_end: float | None) -> float | None:
    if t_end is None or not times or not levels:
        return None
    t_start = times[0]
    if t_end <= t_start:
        return None
    high = 0.0
    for i in range(1, len(times)):
        dt = times[i] - times[i - 1]
        if dt > 0.0 and levels[i - 1] == 1:
            high += dt
    tail = t_end - times[-1]
    if tail > 0.0 and levels[-1] == 1:
        high += tail
    return high / (t_end - t_start)


def parse_args(default_relay: str = "ntc") -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Low-voltage relay preflight.")
    p.add_argument("--relay", choices=sorted(RELAY_CONFIGS), default=default_relay)
    p.add_argument("--url", default="http://127.0.0.1:18080")
    p.add_argument("--cycles", type=int, default=5)
    p.add_argument("--dwell", type=float, default=0.40)
    p.add_argument("--poll", type=float, default=0.05)
    p.add_argument("--status-timeout", type=float, default=1.5)
    p.add_argument("--max-vdc", type=float, default=60.0)
    p.add_argument("--allow-hv", action="store_true")
    p.add_argument("--la-channel", type=int, default=-1, help="Optional Saleae channel connected to relay control pin.")
    p.add_argument("--la-port", type=int, default=10430)
    p.add_argument("--la-rate", type=int, default=100000)
    p.add_argument("--la-duration", type=float, default=0.0)
    p.add_argument("--outdir", default=str(Path(__file__).resolve().parent / "_preflight_exports"))
    return p.parse_args()


def main(default_relay: str = "ntc") -> int:
    args = parse_args(default_relay)
    cfg = RELAY_CONFIGS[args.relay]
    if args.cycles < 1:
        raise SystemExit("--cycles must be >= 1")
    root = Path(args.outdir) / f"{cfg['tag']}_{ts_tag()}"
    root.mkdir(parents=True, exist_ok=True)

    summary: dict = {
        "tool": cfg["tool"],
        "relay": args.relay,
        "description": cfg["description"],
        "url": args.url,
        "cycles": args.cycles,
        "dwell_s": args.dwell,
        "max_vdc": args.max_vdc,
        "allow_hv": bool(args.allow_hv),
        "saleae_channel": args.la_channel,
        "steps": [],
    }

    mgr = None
    capture = None
    saleae_pb2 = None
    grpc_mod = None
    la_csv: Path | None = None
    try:
        cleanup(args.url)
        st0 = get_status(args.url)
        summary["initial_status"] = st0
        pre_ok = safe_low_voltage(st0, args.max_vdc, args.allow_hv)
        summary["pre_safe_low_voltage"] = pre_ok
        if not pre_ok:
            log("FAIL: precheck is not safe low-voltage state")
            return_code = 2
            summary["pass"] = False
            return return_code

        la_enabled = args.la_channel >= 0
        if la_enabled:
            duration = args.la_duration if args.la_duration > 0.0 else max(2.0, 0.7 + args.cycles * args.dwell * 2.0)
            log(f"Saleae capture CH{args.la_channel} duration={duration:.2f}s rate={args.la_rate}")
            mgr, capture, saleae_pb2, grpc_mod = start_saleae_capture(
                args.la_port, args.la_channel, args.la_rate, duration
            )
            time.sleep(0.20)

        if not post_cmd(args.url, "IOTEST ON"):
            summary["pass"] = False
            return 3
        ok, st, dt = wait_for(
            args.url,
            lambda s: status_int(s, "pwm", 1) == 0
            and status_int(s, "estop", 1) == 0
            and status_int(s, "bp_fault", 255) == 0,
            args.status_timeout,
            args.poll,
        )
        summary["iotest_on"] = {"ok": ok, "dt_s": dt, "status": st}
        if not ok:
            summary["pass"] = False
            return 4

        status_steps_ok = True
        for idx in range(args.cycles):
            if not post_cmd(args.url, f"{cfg['cmd']} ON"):
                status_steps_ok = False
                break
            ok_on, st_on, dt_on = wait_for(
                args.url,
                lambda s: relay_status_ok(s, True, str(cfg["field"]), int(cfg["ext_bit"])),
                args.status_timeout,
                args.poll,
            )
            summary["steps"].append({"cycle": idx + 1, "target": "on", "ok": ok_on, "dt_s": dt_on, "status": st_on})
            status_steps_ok = status_steps_ok and ok_on
            time.sleep(args.dwell)

            if not post_cmd(args.url, f"{cfg['cmd']} OFF"):
                status_steps_ok = False
                break
            ok_off, st_off, dt_off = wait_for(
                args.url,
                lambda s: relay_status_ok(s, False, str(cfg["field"]), int(cfg["ext_bit"])),
                args.status_timeout,
                args.poll,
            )
            summary["steps"].append(
                {"cycle": idx + 1, "target": "off", "ok": ok_off, "dt_s": dt_off, "status": st_off}
            )
            status_steps_ok = status_steps_ok and ok_off
            time.sleep(args.dwell)

        summary["status_steps_pass"] = bool(status_steps_ok)

        la_pass = True
        if la_enabled and mgr is not None and capture is not None and saleae_pb2 is not None and grpc_mod is not None:
            wait_saleae_capture(mgr, capture, saleae_pb2, grpc_mod, timeout_s=max(5.0, args.cycles * args.dwell * 3.0))
            la_csv = export_saleae_csv(capture, args.la_channel, root)
            times, levels, _t0, t_last = load_transitions(la_csv, args.la_channel)
            edges = max(0, len(times) - 1)
            ratio = high_ratio(times, levels, t_last)
            expected_min_edges = max(2, args.cycles * 2 - 1)
            la_pass = edges >= expected_min_edges and ratio is not None and 0.10 <= ratio <= 0.90
            summary["saleae"] = {
                "enabled": True,
                "csv": str(la_csv),
                "edges": edges,
                "expected_min_edges": expected_min_edges,
                "high_ratio": ratio,
                "pass": la_pass,
            }
        else:
            summary["saleae"] = {"enabled": False, "pass": True}

        cleanup(args.url)
        ok_final, st_final, dt_final = wait_for(
            args.url,
            lambda s: safe_low_voltage(s, args.max_vdc, args.allow_hv)
            and status_int(s, "ntc", 1) == 0
            and status_int(s, "precharge", 1) == 0
            and status_int(s, "pfc", 1) == 0
            and status_int(s, "brake", 1) == 0,
            timeout_s=2.0,
            poll_s=args.poll,
        )
        summary["final_safe"] = {"ok": ok_final, "dt_s": dt_final, "status": st_final}
        summary["pass"] = bool(pre_ok and status_steps_ok and la_pass and ok_final)
        return 0 if summary["pass"] else 5
    except Exception as exc:
        summary["exception"] = repr(exc)
        summary["pass"] = False
        log(f"FAIL: {exc}")
        return 10
    finally:
        try:
            cleanup(args.url)
        except Exception:
            pass
        if mgr is not None:
            try:
                mgr.close()
            except Exception:
                pass
        (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"summary={root / 'summary.json'}")
        log(f"overall_pass={str(bool(summary.get('pass'))).lower()}")


if __name__ == "__main__":
    raise SystemExit(main())

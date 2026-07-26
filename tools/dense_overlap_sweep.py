#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import math
from datetime import datetime
from pathlib import Path

from active_pwm_guard import start_allowed_by_bench_gate

BP_MAX_AGE_MS = 1000.0


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
    values = [int(st_num(st, key, 999999.0)) for key in ("bp_bad_cnt", "bp_bad") if key in st]
    if not values:
        return 999999
    return max(values)


def bp_bad_limit() -> int:
    raw = os.environ.get("UNOQ_BP_BAD_BASELINE", "0").strip()
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 0


def bp_bad_ok(st: dict | None) -> bool:
    return bp_bad_value(st) <= bp_bad_limit()


def configure_bp_bad_baseline(st: dict | None) -> int:
    baseline = bp_bad_value(st)
    if baseline < 999999:
        os.environ["UNOQ_BP_BAD_BASELINE"] = str(max(0, baseline))
    return baseline


def log(msg: str) -> None:
    print(msg, flush=True)


def freq_grid(start: float, stop: float, step: float) -> list[float]:
    scale = 10
    a = int(round(start * scale))
    b = int(round(stop * scale))
    s = max(1, int(round(step * scale)))
    return [i / scale for i in range(a, b + 1, s)]


def wait_freq_state(
    base: str,
    freq: float,
    expect_pwm: bool,
    timeout_s: float,
    poll_s: float,
) -> tuple[bool, dict | None, float]:
    start = time.monotonic()
    last: dict | None = None
    tol = max(0.25, abs(freq) * 0.03)
    while time.monotonic() - start < timeout_s:
        st = get_status(base)
        if st is not None:
            last = st
            mode_ok = (
                str(st.get("mode", "")) == "VF"
                and int(st_num(st, "diag_mode", 0.0)) == 0
                and int(st_num(st, "duty_mode", 0.0)) == 0
            )
            common_ok = (
                mode_ok
                and int(st_num(st, "estop", 1.0)) == 0
                and bp_link_live(st)
                and int(st_num(st, "bp_fault", 255.0)) == 0
            )
            if expect_pwm:
                ok = (
                    common_ok
                    and st.get("state") == "VF_RUN"
                    and int(st_num(st, "pwm", 0.0)) == 1
                    and abs(st_num(st, "freq_cmd", -999.0) - freq) <= 0.06
                    and abs(st_num(st, "freq", -999.0) - freq) <= tol
                )
            else:
                ok = (
                    common_ok
                    and st.get("state") == "SAFE"
                    and int(st_num(st, "pwm", 1.0)) == 0
                    and abs(st_num(st, "freq_cmd", 999.0) - freq) <= 0.06
                )
            if ok:
                return True, st, time.monotonic() - start
        time.sleep(poll_s)
    return False, last, time.monotonic() - start


def status_vdc(st: dict | None) -> float:
    if st is None:
        return float("nan")
    return max(st_num(st, "bp_vdc", -1.0), st_num(st, "vdc", -1.0))


def low_voltage_start_precheck(st: dict | None, max_vdc: float, allow_hv: bool) -> tuple[bool, str]:
    if st is None:
        return False, "status unavailable"
    if not bp_link_live(st):
        return False, "Blue Pill link is not live"
    if int(st_num(st, "pwm", 1.0)) != 0:
        return False, "PWM is already active"
    if int(st_num(st, "estop", 1.0)) != 0:
        return False, "ESTOP is active"
    if int(st_num(st, "bp_fault", 255.0)) != 0:
        return False, f"bp_fault={int(st_num(st, 'bp_fault', 255.0))}"
    if not bp_bad_ok(st):
        return False, f"bp_bad={bp_bad_value(st)} exceeds baseline"
    vdc = status_vdc(st)
    if not (vdc == vdc) or vdc < 0.0:
        return False, "Vbus telemetry is not readable"
    if not allow_hv:
        if vdc > max_vdc:
            return False, f"Vbus {vdc:.2f} V exceeds low-voltage limit {max_vdc:.2f} V"
    return True, "ok"


def bench_gate_start_precheck(base_url: str, guard_fn=start_allowed_by_bench_gate) -> tuple[bool, str]:
    messages: list[str] = []
    ok = bool(guard_fn(messages.append, url=base_url))
    if ok:
        return True, "ok"
    detail = "; ".join(messages) if messages else "bench gate refused START"
    return False, detail


def get_pair_metric(metrics: dict, section: str, pair: str, key: str | None = None):
    val = (metrics.get(section) or {}).get(pair)
    if key is None:
        return val
    if isinstance(val, dict):
        return val.get(key)
    return None


def parse_pairs(spec: str) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if "-" not in raw:
            raise ValueError(f"bad pair {raw!r}, expected A-B")
        a, b = raw.split("-", 1)
        pairs.append((int(a), int(b)))
    if not pairs:
        raise ValueError("at least one PWM pair is required")
    return pairs


def analyze_mapped(
    csv_path: str,
    channels: list[int],
    pwm_pairs: list[tuple[int, int]],
    brake_channel: int,
    brake_active_high: bool,
    expect_pwm: bool,
    max_overlap_ratio: float,
    min_handoff_gap_ns: float,
) -> dict:
    times, levels, _t0, t_last = load_transitions(csv_path, channels)
    glitch_removed: dict[str, int] = {}
    for ch in channels:
        times[ch], levels[ch], removed = filter_short_pulses(
            times.get(ch, []),
            levels.get(ch, []),
            100e-9,
        )
        glitch_removed[str(ch)] = removed

    pair_channels = sorted({ch for pair in pwm_pairs for ch in pair})
    metrics = {
        "channels": {},
        "brake_channel": brake_channel,
        "pwm_pairs": [f"{a}-{b}" for a, b in pwm_pairs],
        "brake_high": None,
        "overlap": {},
        "handoff_gap_ns": {},
        "max_overlap_ratio": max_overlap_ratio,
        "min_handoff_gap_ns": float(min_handoff_gap_ns),
        "glitch_removed": glitch_removed,
    }

    pwm_ok = True
    for ch in channels:
        edges, freq, duty = pwm_metrics(times.get(ch, []), levels.get(ch, []))
        metrics["channels"][str(ch)] = {"edges": edges, "freq_hz": freq, "duty": duty}

    if expect_pwm:
        for idx, ch in enumerate(pair_channels):
            chm = metrics["channels"].get(str(ch), {})
            edges = chm.get("edges", 0) or 0
            freq = chm.get("freq_hz")
            duty = chm.get("duty")
            if edges < 1000:
                pwm_ok = False
            # Check full frequency/duty on at least the first side of each pair.
            if ch in [a for a, _b in pwm_pairs]:
                if freq is None or not (3000.0 <= freq <= 20000.0):
                    pwm_ok = False
                if duty is None or not (0.01 <= duty <= 0.99):
                    pwm_ok = False
    else:
        for ch in pair_channels:
            edges = metrics["channels"].get(str(ch), {}).get("edges", 0) or 0
            if edges >= 1000:
                pwm_ok = False

    b_ratio = high_ratio(times.get(brake_channel, []), levels.get(brake_channel, []), t_last)
    metrics["brake_high"] = b_ratio
    expect_brake_active = not expect_pwm
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
        for a, b in pwm_pairs:
            key = f"{a}-{b}"
            r = overlap_ratio(times.get(a, []), levels.get(a, []), times.get(b, []), levels.get(b, []))
            metrics["overlap"][key] = r
            if r is not None and r > max_overlap_ratio:
                overlap_ok = False
            gap_stats = handoff_gap_stats(times.get(a, []), levels.get(a, []), times.get(b, []), levels.get(b, []))
            metrics["handoff_gap_ns"][key] = gap_stats
            if min_handoff_gap_ns > 0.0:
                if gap_stats is None or gap_stats["min"] < min_handoff_gap_ns:
                    deadtime_ok = False

    metrics["pass"] = bool(pwm_ok and brake_ok and overlap_ok and deadtime_ok)
    metrics["pwm_ok"] = pwm_ok
    metrics["brake_ok"] = brake_ok
    metrics["overlap_ok"] = overlap_ok
    metrics["deadtime_ok"] = deadtime_ok
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Dense scalar/VF overlap sweep.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--min", type=float, default=0.0)
    parser.add_argument("--max", type=float, default=50.0)
    parser.add_argument("--step", type=float, default=0.1)
    parser.add_argument("--la-channels", default="0,1,2,3,4,5,6")
    parser.add_argument("--la-rate", type=int, default=24000000)
    parser.add_argument("--la-duration", type=float, default=0.003)
    parser.add_argument("--brake-active-high", type=int, default=0)
    parser.add_argument("--brake-channel", type=int, default=6)
    parser.add_argument("--pwm-pairs", default="0-1,2-3,4-5")
    parser.add_argument("--min-handoff-gap-ns", type=float, default=600.0)
    parser.add_argument("--max-overlap-ratio", type=float, default=5e-4)
    parser.add_argument("--status-timeout", type=float, default=1.5)
    parser.add_argument("--poll", type=float, default=0.03)
    parser.add_argument("--max-start-vdc", type=float, default=60.0)
    parser.add_argument("--allow-hv", action="store_true", help="Allow START when Vbus exceeds --max-start-vdc.")
    parser.add_argument("--capture-retries", type=int, default=2)
    parser.add_argument("--capture-retry-delay", type=float, default=0.5)
    parser.add_argument("--saleae-port", type=int, default=10430)
    parser.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "_preflight_exports"))
    args = parser.parse_args()

    # Keep module import light for build-only selftests; real capture dependencies
    # are loaded only for an actual dense sweep.
    global export_capture, filter_short_pulses, get_status, handoff_gap_stats, high_ratio
    global load_transitions, overlap_ratio, pwm_metrics, recover_logic2
    global send_cmds_retry, start_capture, wait_capture_with_timeout, wait_http_ready
    sys.path.insert(0, os.path.dirname(__file__))
    from ui_pwm_case import (  # noqa: E402
        export_capture,
        filter_short_pulses,
        get_status,
        handoff_gap_stats,
        high_ratio,
        load_transitions,
        overlap_ratio,
        pwm_metrics,
        recover_logic2,
        send_cmds_retry,
        start_capture,
        wait_capture_with_timeout,
        wait_http_ready,
    )

    base = args.url.rstrip("/")
    channels = [int(x) for x in args.la_channels.split(",") if x.strip()]
    pwm_pairs = parse_pairs(args.pwm_pairs)
    freqs = freq_grid(args.min, args.max, args.step)
    brake_active_high = args.brake_active_high == 1

    run_dir = Path(args.outdir) / ("dense_overlap_sweep_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    captures_dir = run_dir / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = run_dir / "summary.csv"
    summary_json = run_dir / "summary.json"

    initial_status = get_status(base)
    configure_bp_bad_baseline(initial_status)
    log(f"RUN_DIR={run_dir}")
    log(f"POINTS={len(freqs)} RANGE={args.min:.1f}..{args.max:.1f} STEP={args.step:.1f}")

    rows: list[dict] = []
    mgr = None
    csv_file = None
    try:
        ui_ok, ui_st, ui_dt = wait_http_ready(base, timeout_s=3.0, poll_s=max(0.05, args.poll))
        if not ui_ok:
            raise RuntimeError(f"UI not reachable after {ui_dt*1000:.1f}ms last_status={ui_st}")

        from saleae.automation import Manager

        mgr = Manager.connect(port=args.saleae_port, connect_timeout_seconds=2)
        mgr._codex_port = args.saleae_port
        devices = []
        for _ in range(30):
            devices = mgr.get_devices()
            if devices:
                break
            time.sleep(0.1)
        if not devices:
            raise RuntimeError("No Saleae device found")
        log(f"SALEAE_DEVICES={devices}")

        fieldnames = [
            "idx",
            "total",
            "freq_cmd",
            "cmd_ok",
            "status_ok",
            "status_dt_ms",
            "state",
            "freq_status",
            "pwm",
            "estop",
            "bp_bad",
            "bp_fault",
            "metrics_pass",
            "pwm_ok",
            "brake_ok",
            "overlap_ok",
            "deadtime_ok",
            "brake_high",
            "brake_channel",
            "pwm_pairs",
            "edges_ch0",
            "edges_ch1",
            "edges_ch2",
            "edges_ch3",
            "edges_ch4",
            "edges_ch5",
            "edges_ch6",
            "freq_ch1_hz",
            "freq_ch2_hz",
            "freq_ch3_hz",
            "freq_ch4_hz",
            "freq_ch5_hz",
            "freq_ch6_hz",
            "ov_0_1",
            "ov_2_3",
            "ov_4_5",
            "ov_pair1",
            "ov_pair2",
            "ov_pair3",
            "gap_0_1_min_ns",
            "gap_2_3_min_ns",
            "gap_4_5_min_ns",
            "gap_pair1_min_ns",
            "gap_pair2_min_ns",
            "gap_pair3_min_ns",
            "capture_error",
            "csv",
        ]
        csv_file = summary_csv.open("w", newline="", encoding="utf-8")
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        csv_file.flush()

        send_cmds_retry(base, ["STOP", "ESTOP CLEAR", "CLEAR", "MODE VF"], retries=2, retry_delay_s=0.2)
        time.sleep(0.2)
        pre_start_status = get_status(base)
        pre_start_ok, pre_start_reason = low_voltage_start_precheck(
            pre_start_status,
            max_vdc=float(args.max_start_vdc),
            allow_hv=bool(args.allow_hv),
        )
        needs_start = any(abs(freq) > 1e-9 for freq in freqs)
        if needs_start and not pre_start_ok:
            raise RuntimeError(f"Refusing dense sweep START: {pre_start_reason}; status={pre_start_status}")
        if needs_start:
            bench_gate_ok, bench_gate_reason = bench_gate_start_precheck(base)
            if not bench_gate_ok:
                raise RuntimeError(f"Refusing dense sweep START: bench gate blocked START: {bench_gate_reason}")

        for idx, freq in enumerate(freqs, 1):
            expect_pwm = abs(freq) > 1e-9
            if expect_pwm:
                cmds = [f"SET FREQ {freq:.1f}", "START"]
            else:
                cmds = [f"SET FREQ {freq:.1f}", "STOP"]
            cmd_ok = send_cmds_retry(base, cmds, retries=1, retry_delay_s=0.12)
            status_ok, st, dt = wait_freq_state(base, freq, expect_pwm, args.status_timeout, args.poll)

            capture_error = ""
            csv_path = ""
            metrics = None
            for capture_attempt in range(max(0, args.capture_retries) + 1):
                capture = None
                try:
                    if capture_attempt:
                        log(
                            "WARN: retrying capture for freq={:.1f} attempt {}/{}".format(
                                freq,
                                capture_attempt + 1,
                                max(0, args.capture_retries) + 1,
                            )
                        )
                    capture = start_capture(mgr, channels, args.la_rate, args.la_duration)
                    wait_capture_with_timeout(mgr, capture, timeout_s=args.la_duration + 2.0)
                    tag = f"vf_{freq:.1f}Hz".replace(".", "p")
                    csv_path = export_capture(capture, channels, str(captures_dir), tag)
                    metrics = analyze_mapped(
                        csv_path,
                        channels,
                        pwm_pairs,
                        args.brake_channel,
                        brake_active_high,
                        expect_pwm,
                        args.max_overlap_ratio,
                        args.min_handoff_gap_ns,
                    )
                    capture_error = ""
                    break
                except Exception as exc:
                    capture_error = repr(exc)
                    csv_path = ""
                    log(
                        "WARN: capture failed for freq={:.1f} attempt {}/{}: {}".format(
                            freq,
                            capture_attempt + 1,
                            max(0, args.capture_retries) + 1,
                            capture_error,
                        )
                    )
                    if capture_attempt < max(0, args.capture_retries):
                        recover_logic2(mgr)
                        time.sleep(max(0.0, args.capture_retry_delay))
                finally:
                    if capture is not None:
                        try:
                            capture.close()
                        except Exception:
                            pass

            if metrics is None:
                metrics = {
                    "pass": False,
                    "pwm_ok": False,
                    "brake_ok": False,
                    "overlap_ok": False,
                    "deadtime_ok": False,
                    "channels": {},
                    "overlap": {},
                    "handoff_gap_ns": {},
                }

            ch = metrics.get("channels") or {}
            row = {
                "idx": idx,
                "total": len(freqs),
                "freq_cmd": f"{freq:.1f}",
                "cmd_ok": int(bool(cmd_ok)),
                "status_ok": int(bool(status_ok)),
                "status_dt_ms": f"{dt*1000.0:.1f}",
                "state": "" if st is None else st.get("state", ""),
                "freq_status": "" if st is None else st_num(st, "freq", 0.0),
                "pwm": "" if st is None else int(st_num(st, "pwm", -1.0)),
                "estop": "" if st is None else int(st_num(st, "estop", -1.0)),
                "bp_bad": "" if st is None else int(st_num(st, "bp_bad", -1.0)),
                "bp_fault": "" if st is None else int(st_num(st, "bp_fault", -1.0)),
                "metrics_pass": int(bool(metrics.get("pass"))),
                "pwm_ok": metrics.get("pwm_ok"),
                "brake_ok": metrics.get("brake_ok"),
                "overlap_ok": metrics.get("overlap_ok"),
                "deadtime_ok": metrics.get("deadtime_ok"),
                "brake_high": metrics.get("brake_high"),
                "brake_channel": args.brake_channel,
                "pwm_pairs": ",".join(metrics.get("pwm_pairs", [])),
                "edges_ch0": (ch.get("0") or {}).get("edges"),
                "edges_ch1": (ch.get("1") or {}).get("edges"),
                "edges_ch2": (ch.get("2") or {}).get("edges"),
                "edges_ch3": (ch.get("3") or {}).get("edges"),
                "edges_ch4": (ch.get("4") or {}).get("edges"),
                "edges_ch5": (ch.get("5") or {}).get("edges"),
                "edges_ch6": (ch.get("6") or {}).get("edges"),
                "freq_ch1_hz": (ch.get("1") or {}).get("freq_hz"),
                "freq_ch2_hz": (ch.get("2") or {}).get("freq_hz"),
                "freq_ch3_hz": (ch.get("3") or {}).get("freq_hz"),
                "freq_ch4_hz": (ch.get("4") or {}).get("freq_hz"),
                "freq_ch5_hz": (ch.get("5") or {}).get("freq_hz"),
                "freq_ch6_hz": (ch.get("6") or {}).get("freq_hz"),
                "ov_0_1": get_pair_metric(metrics, "overlap", "0-1"),
                "ov_2_3": get_pair_metric(metrics, "overlap", "2-3"),
                "ov_4_5": get_pair_metric(metrics, "overlap", "4-5"),
                "ov_pair1": get_pair_metric(metrics, "overlap", metrics["pwm_pairs"][0]) if len(metrics.get("pwm_pairs", [])) > 0 else None,
                "ov_pair2": get_pair_metric(metrics, "overlap", metrics["pwm_pairs"][1]) if len(metrics.get("pwm_pairs", [])) > 1 else None,
                "ov_pair3": get_pair_metric(metrics, "overlap", metrics["pwm_pairs"][2]) if len(metrics.get("pwm_pairs", [])) > 2 else None,
                "gap_0_1_min_ns": get_pair_metric(metrics, "handoff_gap_ns", "0-1", "min"),
                "gap_2_3_min_ns": get_pair_metric(metrics, "handoff_gap_ns", "2-3", "min"),
                "gap_4_5_min_ns": get_pair_metric(metrics, "handoff_gap_ns", "4-5", "min"),
                "gap_pair1_min_ns": get_pair_metric(metrics, "handoff_gap_ns", metrics["pwm_pairs"][0], "min") if len(metrics.get("pwm_pairs", [])) > 0 else None,
                "gap_pair2_min_ns": get_pair_metric(metrics, "handoff_gap_ns", metrics["pwm_pairs"][1], "min") if len(metrics.get("pwm_pairs", [])) > 1 else None,
                "gap_pair3_min_ns": get_pair_metric(metrics, "handoff_gap_ns", metrics["pwm_pairs"][2], "min") if len(metrics.get("pwm_pairs", [])) > 2 else None,
                "capture_error": capture_error,
                "csv": csv_path,
            }
            writer.writerow(row)
            csv_file.flush()
            rows.append(row)
            log(
                "POINT {}/{} freq={:.1f} cmd={} status={} overlap_ok={} deadtime_ok={} "
                "ov01={} ov23={} ov45={} csv={}".format(
                    idx,
                    len(freqs),
                    freq,
                    row["cmd_ok"],
                    row["status_ok"],
                    row["overlap_ok"],
                    row["deadtime_ok"],
                    row["ov_0_1"],
                    row["ov_2_3"],
                    row["ov_4_5"],
                    csv_path,
                )
            )

        summary = {
            "run_dir": str(run_dir),
            "summary_csv": str(summary_csv),
            "points": len(rows),
            "all_cmd_ok": all(int(r["cmd_ok"]) for r in rows),
            "all_status_ok": all(int(r["status_ok"]) for r in rows),
            "all_metrics_pass": all(int(r["metrics_pass"]) for r in rows),
            "overlap_fail_count": sum(str(r["overlap_ok"]) != "True" for r in rows),
            "deadtime_fail_count": sum(str(r["deadtime_ok"]) != "True" for r in rows),
            "pwm_fail_count": sum(str(r["pwm_ok"]) != "True" for r in rows),
            "capture_error_count": sum(1 for r in rows if r["capture_error"]),
        }
        summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"SUMMARY_JSON={summary_json}")
        log(json.dumps(summary, ensure_ascii=False))
        return 0 if summary["all_cmd_ok"] and summary["all_status_ok"] and summary["all_metrics_pass"] else 4
    finally:
        if csv_file is not None:
            csv_file.close()
        try:
            send_cmds_retry(base, ["STOP"], retries=2, retry_delay_s=0.2)
            time.sleep(0.2)
            send_cmds_retry(base, ["ESTOP"], retries=2, retry_delay_s=0.2)
        except Exception as exc:
            log(f"WARN: final STOP/ESTOP failed: {exc}")
        if mgr is not None:
            try:
                mgr.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

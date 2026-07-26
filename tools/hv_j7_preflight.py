#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from datetime import datetime

from runtime_python import ensure_modules_or_reexec

ensure_modules_or_reexec(["grpc", "saleae"], "MIC_PRACTICE_HV_J7_PREFLIGHT_REEXEC")
import grpc
from saleae.automation import Manager

sys.path.insert(0, os.path.dirname(__file__))
from run_metadata import collect_run_metadata  # noqa: E402
from ui_pwm_case import (  # noqa: E402
    analyze,
    bp_cmd_bad_ok,
    bp_link_live,
    configure_adb_router_fallback,
    configure_bp_bad_baseline,
    control_retry_reason,
    DEFAULT_MIN_PULSE_WIDTH_NS,
    export_capture,
    get_status,
    log,
    safe_stop,
    send_cmds_retry,
    start_capture,
    status_is_safe,
    status_vdc,
    st_num,
    vf_steady_matches,
    wait_capture_with_timeout,
    wait_for,
    wait_http_ready,
)


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_freqs(spec: str) -> list[float]:
    out: list[float] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    return out


def vdc_in_range(st: dict | None, vdc_min: float | None, vdc_max: float | None) -> bool:
    if st is None:
        return False
    vdc = status_vdc(st)
    if not math.isfinite(vdc) or vdc < 0.0:
        return False
    if vdc_min is not None and vdc < vdc_min:
        return False
    if vdc_max is not None and vdc > vdc_max:
        return False
    return True


def format_status_vdc(st: dict | None) -> str:
    if st is None:
        return ""
    vdc = status_vdc(st)
    if not math.isfinite(vdc) or vdc < 0.0:
        return ""
    return f"{vdc:.6f}"


def require_run_status(st: dict | None, freq: float, vdc_min: float | None, vdc_max: float | None) -> bool:
    if st is None:
        return False
    return (
        vf_steady_matches(st, freq)
        and bp_link_live(st)
        and int(st_num(st, "bp_fault", 255.0)) == 0
        and bp_cmd_bad_ok(st)
        and vdc_in_range(st, vdc_min, vdc_max)
    )


def require_estop_status(st: dict | None, vdc_min: float | None, vdc_max: float | None) -> bool:
    if st is None:
        return False
    return (
        st.get("state") == "SAFE"
        and int(st_num(st, "pwm", 1.0)) == 0
        and int(st_num(st, "estop", -1.0)) == 1
        and bp_link_live(st)
        and bp_cmd_bad_ok(st)
        and vdc_in_range(st, vdc_min, vdc_max)
    )


def capture_metrics(
    mgr: Manager,
    channels: list[int],
    rate: int,
    duration: float,
    outdir: str,
    tag: str,
    brake_active_high: bool,
    expect_pwm: bool,
    expect_estop: bool,
    min_handoff_gap_ns: float,
    min_pulse_width_ns: float,
) -> tuple[str, dict | None]:
    capture = None
    try:
        capture = start_capture(mgr, channels, rate, duration)
        wait_capture_with_timeout(mgr, capture, timeout_s=duration + 2.0)
        csv_path = export_capture(capture, channels, outdir, tag)
        metrics = analyze(
            csv_path,
            channels,
            brake_active_high,
            expect_pwm,
            expect_estop,
            min_handoff_gap_ns=min_handoff_gap_ns,
            min_pulse_width_ns=min_pulse_width_ns,
        )
        return csv_path, metrics
    except grpc.RpcError as exc:
        code = exc.code() if hasattr(exc, "code") else None
        details = exc.details() if hasattr(exc, "details") else ""
        log(f"ERROR: capture failed tag={tag} code={code} details={details or exc}")
        return "", None
    finally:
        if capture is not None:
            try:
                capture.close()
            except Exception:
                pass


def latest_status(base: str) -> dict | None:
    return get_status(base)


def main() -> int:
    ap = argparse.ArgumentParser(description="HV/J7 preflight after low-voltage HIL has already passed.")
    ap.add_argument("--url", required=True)
    ap.add_argument("--vf-freqs", default="0.5,1,2,5")
    ap.add_argument("--estop-freqs", default="1,5")
    ap.add_argument("--la-channels", default="0,1,2,3,4,5,6")
    ap.add_argument("--la-rate", type=int, default=24000000)
    ap.add_argument("--la-duration", type=float, default=0.02)
    ap.add_argument("--saleae-port", type=int, default=10430)
    ap.add_argument("--poll", type=float, default=0.05)
    ap.add_argument("--status-timeout", type=float, default=1.5)
    ap.add_argument("--ui-ready-timeout", type=float, default=3.0)
    ap.add_argument("--cmd-retries", type=int, default=2)
    ap.add_argument("--case-retries", type=int, default=1)
    ap.add_argument("--retry-delay", type=float, default=0.2)
    ap.add_argument("--settle", type=float, default=0.5)
    ap.add_argument("--min-handoff-gap-ns", type=float, default=600.0)
    ap.add_argument("--min-pulse-width-ns", type=float, default=DEFAULT_MIN_PULSE_WIDTH_NS)
    ap.add_argument("--brake-active-high", type=int, default=0)
    ap.add_argument("--vdc-min", type=float, default=None)
    ap.add_argument("--vdc-max", type=float, default=None)
    ap.add_argument("--adb-router-fallback", action="store_true", help="Fallback failed HTTP commands to direct ADB router RPC.")
    ap.add_argument("--adb-device", default=os.environ.get("UNOQ_ADB_DEVICE", ""), help="ADB serial for --adb-router-fallback.")
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "_preflight_exports"))
    args = ap.parse_args()

    os.environ["UNOQ_ALLOW_HV"] = "1"
    configure_adb_router_fallback(args.adb_router_fallback or bool(args.adb_device), args.adb_device or None)

    base = args.url.rstrip("/")
    configure_bp_bad_baseline(get_status(base))
    vf_freqs = parse_freqs(args.vf_freqs)
    estop_freqs = parse_freqs(args.estop_freqs)
    channels = [int(x) for x in args.la_channels.split(",") if x.strip()]
    run_dir = os.path.join(os.path.abspath(args.outdir), f"hv_j7_preflight_{ts_tag()}")
    os.makedirs(run_dir, exist_ok=True)
    summary_csv = os.path.join(run_dir, "summary.csv")

    mgr = None
    pass_count = 0
    fail_count = 0
    rows: list[dict] = []

    def record(
        tag: str,
        phase: str,
        freq: float,
        cmd_ok: bool,
        status_ok: bool,
        status_dt_ms: float,
        status: dict | None,
        metrics: dict | None,
        csv_path: str,
        attempts: int,
        retry_reason: str,
    ) -> None:
        nonlocal pass_count, fail_count
        passed = bool(metrics and metrics.get("pass") and cmd_ok and status_ok)
        row = {
            "tag": tag,
            "phase": phase,
            "freq": freq,
            "cmd_ok": int(bool(cmd_ok)),
            "status_ok": int(bool(status_ok)),
            "status_dt_ms": f"{status_dt_ms:.1f}",
            "pass": "PASS" if passed else "FAIL",
            "pwm_ok": "" if metrics is None else metrics.get("pwm_ok"),
            "brake_ok": "" if metrics is None else metrics.get("brake_ok"),
            "overlap_ok": "" if metrics is None else metrics.get("overlap_ok"),
            "deadtime_ok": "" if metrics is None else metrics.get("deadtime_ok"),
            "brake_high": "" if metrics is None else metrics.get("brake_high"),
            "state": "" if status is None else status.get("state", ""),
            "mode": "" if status is None else status.get("mode", ""),
            "pwm": "" if status is None else int(st_num(status, "pwm", 0.0)),
            "estop": "" if status is None else int(st_num(status, "estop", 0.0)),
            "bp_fault": "" if status is None else int(st_num(status, "bp_fault", 255.0)),
            "bp_bad": "" if status is None else int(st_num(status, "bp_bad", 999999.0)),
            "vdc": format_status_vdc(status),
            "attempts": attempts,
            "retry_reason": retry_reason,
            "csv": csv_path,
        }
        rows.append(row)
        if passed:
            pass_count += 1
        else:
            fail_count += 1

    def run_vf_case(freq: float) -> dict:
        tag = f"hv_vf_{freq:.1f}Hz".replace(".", "p")
        last = None
        retry_reason = ""
        for attempt in range(args.case_retries + 1):
            if attempt:
                log(f"WARN: retry {tag} attempt {attempt + 1}/{args.case_retries + 1} after {retry_reason}")
                safe_stop(base)
                time.sleep(args.settle)
            cmd_ok = send_cmds_retry(
                base,
                ["CLEAR", "MODE VF", f"SET FREQ {freq:.1f}", "START"],
                retries=args.cmd_retries,
                retry_delay_s=args.retry_delay,
            )
            status_ok, st, dt = wait_for(
                base,
                lambda s: require_run_status(s, freq, args.vdc_min, args.vdc_max),
                timeout_s=args.status_timeout,
                poll_s=max(0.02, args.poll),
            )
            csv_path, metrics = capture_metrics(
                mgr,
                channels,
                args.la_rate,
                args.la_duration,
                run_dir,
                tag,
                bool(args.brake_active_high),
                True,
                False,
                args.min_handoff_gap_ns,
                args.min_pulse_width_ns,
            )
            retry_reason = control_retry_reason(cmd_ok, status_ok, metrics)
            last = {
                "tag": tag,
                "phase": "vf_run",
                "freq": freq,
                "cmd_ok": cmd_ok,
                "status_ok": status_ok,
                "status_dt_ms": dt * 1000.0,
                "status": st,
                "metrics": metrics,
                "csv_path": csv_path,
                "attempts": attempt + 1,
                "retry_reason": retry_reason,
            }
            if not retry_reason:
                break
        return last

    def run_estop_trip(freq: float) -> list[dict]:
        trip_rows: list[dict] = []
        retry_reason = ""
        for attempt in range(args.case_retries + 1):
            if attempt:
                log(f"WARN: retry hv estop {freq:.1f}Hz attempt {attempt + 1}/{args.case_retries + 1} after {retry_reason}")
                safe_stop(base)
                time.sleep(args.settle)

            run_case = run_vf_case(freq)

            estop_cmd_ok = send_cmds_retry(
                base,
                ["ESTOP"],
                retries=args.cmd_retries,
                retry_delay_s=args.retry_delay,
            )
            estop_ok, estop_st, estop_dt = wait_for(
                base,
                lambda s: require_estop_status(s, args.vdc_min, args.vdc_max),
                timeout_s=args.status_timeout,
                poll_s=max(0.02, args.poll),
            )
            estop_tag = f"hv_estop_{freq:.1f}Hz".replace(".", "p")
            estop_csv, estop_metrics = capture_metrics(
                mgr,
                channels,
                args.la_rate,
                args.la_duration,
                run_dir,
                estop_tag,
                bool(args.brake_active_high),
                False,
                True,
                args.min_handoff_gap_ns,
                args.min_pulse_width_ns,
            )
            recover_cmd_ok = send_cmds_retry(
                base,
                ["ESTOP CLEAR", "START"],
                retries=args.cmd_retries,
                retry_delay_s=args.retry_delay,
            )
            recover_ok, recover_st, recover_dt = wait_for(
                base,
                lambda s: require_run_status(s, freq, args.vdc_min, args.vdc_max),
                timeout_s=args.status_timeout,
                poll_s=max(0.02, args.poll),
            )
            recover_tag = f"hv_recover_{freq:.1f}Hz".replace(".", "p")
            recover_csv, recover_metrics = capture_metrics(
                mgr,
                channels,
                args.la_rate,
                args.la_duration,
                run_dir,
                recover_tag,
                bool(args.brake_active_high),
                True,
                False,
                args.min_handoff_gap_ns,
                args.min_pulse_width_ns,
            )
            reasons = [
                control_retry_reason(run_case["cmd_ok"], run_case["status_ok"], run_case["metrics"]),
                control_retry_reason(estop_cmd_ok, estop_ok, estop_metrics),
                control_retry_reason(recover_cmd_ok, recover_ok, recover_metrics),
            ]
            retry_reason = ",".join(r for r in reasons if r)
            trip_rows = [
                run_case,
                {
                    "tag": estop_tag,
                    "phase": "estop",
                    "freq": freq,
                    "cmd_ok": estop_cmd_ok,
                    "status_ok": estop_ok,
                    "status_dt_ms": estop_dt * 1000.0,
                    "status": estop_st,
                    "metrics": estop_metrics,
                    "csv_path": estop_csv,
                    "attempts": attempt + 1,
                    "retry_reason": retry_reason,
                },
                {
                    "tag": recover_tag,
                    "phase": "recover",
                    "freq": freq,
                    "cmd_ok": recover_cmd_ok,
                    "status_ok": recover_ok,
                    "status_dt_ms": recover_dt * 1000.0,
                    "status": recover_st,
                    "metrics": recover_metrics,
                    "csv_path": recover_csv,
                    "attempts": attempt + 1,
                    "retry_reason": retry_reason,
                },
            ]
            if not retry_reason:
                break
        return trip_rows

    try:
        ui_ok, ui_st, ui_dt = wait_http_ready(base, timeout_s=args.ui_ready_timeout, poll_s=max(0.05, args.poll))
        log(f"UI ready ok={ui_ok} dt={ui_dt*1000:.1f}ms st={ui_st}")
        if not ui_ok:
            return 2
        st0 = latest_status(base)
        if not status_is_safe(st0):
            log(f"ERROR: bench not SAFE before HV/J7 preflight st={st0}")
            return 3
        if not vdc_in_range(st0, args.vdc_min, args.vdc_max):
            log(f"ERROR: initial Vbus telemetry unreadable or out of requested window st={st0}")
            return 3

        mgr = Manager.connect(port=args.saleae_port, connect_timeout_seconds=2)
        mgr._codex_port = args.saleae_port
        devices = []
        for _ in range(30):
            devices = mgr.get_devices()
            if devices:
                break
            time.sleep(0.1)
        if not devices:
            log("ERROR: no Saleae device visible for HV/J7 preflight")
            return 2

        idle_csv, idle_metrics = capture_metrics(
            mgr,
            channels,
            args.la_rate,
            args.la_duration,
            run_dir,
            "hv_idle_safe",
            bool(args.brake_active_high),
            False,
            False,
            args.min_handoff_gap_ns,
            args.min_pulse_width_ns,
        )
        record("hv_idle_safe", "idle_safe", 0.0, True, True, 0.0, st0, idle_metrics, idle_csv, 1, "")

        for freq in vf_freqs:
            res = run_vf_case(freq)
            record(
                res["tag"],
                res["phase"],
                res["freq"],
                res["cmd_ok"],
                res["status_ok"],
                res["status_dt_ms"],
                res["status"],
                res["metrics"],
                res["csv_path"],
                res["attempts"],
                res["retry_reason"],
            )
            safe_stop(base)
            time.sleep(args.settle)

        for freq in estop_freqs:
            for res in run_estop_trip(freq):
                record(
                    res["tag"],
                    res["phase"],
                    res["freq"],
                    res["cmd_ok"],
                    res["status_ok"],
                    res["status_dt_ms"],
                    res["status"],
                    res["metrics"],
                    res["csv_path"],
                    res["attempts"],
                    res["retry_reason"],
                )
            safe_stop(base)
            time.sleep(args.settle)

        final_st = latest_status(base)
        final_safe = status_is_safe(final_st) and vdc_in_range(final_st, args.vdc_min, args.vdc_max)

        with open(summary_csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "tag",
                    "phase",
                    "freq",
                    "cmd_ok",
                    "status_ok",
                    "status_dt_ms",
                    "pass",
                    "pwm_ok",
                    "brake_ok",
                    "overlap_ok",
                    "deadtime_ok",
                    "brake_high",
                    "state",
                    "mode",
                    "pwm",
                    "estop",
                    "bp_fault",
                    "bp_bad",
                    "vdc",
                    "attempts",
                    "retry_reason",
                    "csv",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        summary = {
            "run_dir": run_dir,
            "run_metadata": collect_run_metadata(os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))),
            "vf_freqs": vf_freqs,
            "estop_freqs": estop_freqs,
            "vdc_window": {"min": args.vdc_min, "max": args.vdc_max},
            "pass_count": pass_count,
            "fail_count": fail_count,
            "final_safe": final_safe,
            "status_before": st0,
            "status_after": final_st,
            "pass": (fail_count == 0) and final_safe,
            "summary_csv": summary_csv,
        }
        summary_path = os.path.join(run_dir, "summary.json")
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        log(f"SUMMARY: {summary_path}")
        log(f"PASS={summary['pass']}")
        return 0 if summary["pass"] else 4
    finally:
        if mgr is not None:
            try:
                mgr.close()
            except Exception:
                pass
        safe_stop(base)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())

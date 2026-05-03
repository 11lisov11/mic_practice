#!/usr/bin/env python3
from __future__ import annotations

import argparse
import grpc
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from ui_pwm_case import (  # noqa: E402
    analyze,
    export_capture,
    get_status,
    log,
    safe_stop,
    send_cmds_retry,
    start_capture,
    status_mode_matches,
    st_num,
    wait_capture_with_timeout,
    wait_for,
    wait_http_ready,
)
from saleae.automation import Manager  # noqa: E402


def status_is_safe(st: dict | None) -> bool:
    if st is None:
        return False
    return (
        int(st_num(st, "pwm", 0.0)) == 0
        and int(st_num(st, "estop", 0.0)) == 0
        and st.get("state") == "SAFE"
        and int(st_num(st, "bp_fault", 0.0)) == 0
    )


def wait_safe(base: str, timeout_s: float, poll_s: float) -> tuple[bool, dict | None, float]:
    start = time.monotonic()
    last = None
    while (time.monotonic() - start) < timeout_s:
        st = get_status(base)
        if st is not None:
            last = st
            if status_is_safe(st):
                return True, st, (time.monotonic() - start)
        time.sleep(poll_s)
    return False, last, (time.monotonic() - start)


def wait_foc_run(
    base: str,
    mode: str,
    freq_cmd: float,
    timeout_s: float,
    poll_s: float,
    freq_tol_abs: float,
    freq_tol_rel: float,
    consecutive: int,
) -> tuple[bool, dict | None, float]:
    start = time.monotonic()
    last = None
    stable = 0
    tol = max(freq_tol_abs, abs(freq_cmd) * freq_tol_rel)
    while (time.monotonic() - start) < timeout_s:
        st = get_status(base)
        if st is not None:
            last = st
            ok = (
                st.get("state") == "FOC_RUN"
                and status_mode_matches(st, mode)
                and int(st_num(st, "pwm", 0.0)) == 1
                and int(st_num(st, "estop", 0.0)) == 0
                and int(st_num(st, "bp_fault", 0.0)) == 0
                and abs(st_num(st, "freq_cmd", 0.0) - freq_cmd) <= 0.06
                and abs(st_num(st, "freq", 0.0) - freq_cmd) <= tol
            )
            if ok:
                stable += 1
                if stable >= consecutive:
                    return True, st, (time.monotonic() - start)
            else:
                stable = 0
        time.sleep(poll_s)
    return False, last, (time.monotonic() - start)


def soak_status(base: str, duration_s: float, poll_s: float) -> dict:
    samples: list[dict] = []
    start = time.monotonic()
    while (time.monotonic() - start) < duration_s:
        st = get_status(base)
        if st is not None:
            samples.append(st)
        time.sleep(poll_s)
    if not samples:
        return {
            "count": 0,
            "freq_min": None,
            "freq_max": None,
            "freq_mean": None,
            "bp_bad_delta": None,
            "bp_good_delta": None,
            "bp_fault_values": [],
            "states": [],
            "modes": [],
            "mic_active_ratio": None,
            "mic_enable_ai_ratio": None,
            "mic_gated_ratio": None,
        }
    freq_vals = [st_num(st, "freq", 0.0) for st in samples]
    bp_bad_vals = [st_num(st, "bp_bad", 0.0) for st in samples]
    bp_good_vals = [st_num(st, "bp_good", 0.0) for st in samples]
    mic_active = [int(st_num(st, "mic_active", 0.0)) for st in samples]
    mic_enable_ai = [int(st_num(st, "mic_enable_ai", 0.0)) for st in samples]
    mic_gated = [int(st_num(st, "mic_gated", 0.0)) for st in samples]
    n = float(len(samples))
    return {
        "count": len(samples),
        "freq_min": min(freq_vals),
        "freq_max": max(freq_vals),
        "freq_mean": sum(freq_vals) / len(freq_vals),
        "bp_bad_delta": max(bp_bad_vals) - min(bp_bad_vals),
        "bp_good_delta": max(bp_good_vals) - min(bp_good_vals),
        "bp_fault_values": sorted({int(st_num(st, "bp_fault", 0.0)) for st in samples}),
        "states": sorted({str(st.get("state", "")) for st in samples}),
        "modes": sorted({str(st.get("mode", "")) for st in samples}),
        "mic_active_ratio": sum(mic_active) / n,
        "mic_enable_ai_ratio": sum(mic_enable_ai) / n,
        "mic_gated_ratio": sum(mic_gated) / n,
    }


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
    retries: int = 1,
    retry_delay_s: float = 0.2,
):
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
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
                max_overlap_ratio=5e-4,
                min_handoff_gap_ns=min_handoff_gap_ns,
            )
            return csv_path, metrics
        except grpc.RpcError as exc:
            last_exc = exc
            code = exc.code() if hasattr(exc, "code") else None
            details = exc.details() if hasattr(exc, "details") else str(exc)
            if attempt < retries:
                log(f"WARN: capture retry {attempt + 1}/{retries} code={code} details={details}")
                time.sleep(retry_delay_s)
                continue
            raise
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                log(f"WARN: capture retry {attempt + 1}/{retries} error={exc}")
                time.sleep(retry_delay_s)
                continue
            raise
        finally:
            if capture is not None:
                try:
                    capture.close()
                except Exception:
                    pass
    raise last_exc if last_exc is not None else RuntimeError("capture failed")


def main() -> int:
    ap = argparse.ArgumentParser(description="FOC/MIC safety preflight with Saleae deadtime + overlap checks.")
    ap.add_argument("--url", required=True)
    ap.add_argument("--foc-freqs", default="0.5,5,10,20,50")
    ap.add_argument("--foc-estop-freqs", default="10,50")
    ap.add_argument("--mic-freqs", default="5,10,20")
    ap.add_argument("--saleae-port", type=int, default=10430)
    ap.add_argument("--la-channels", default="0,1,2,3,4,5,6")
    ap.add_argument("--la-rate", type=int, default=24000000)
    ap.add_argument("--la-duration", type=float, default=0.003)
    ap.add_argument("--brake-active-high", type=int, default=0)
    ap.add_argument("--ui-ready-timeout", type=float, default=3.0)
    ap.add_argument("--settle-timeout", type=float, default=2.0)
    ap.add_argument("--poll", type=float, default=0.05)
    ap.add_argument("--steady-consecutive", type=int, default=3)
    ap.add_argument("--freq-tol-abs", type=float, default=0.25)
    ap.add_argument("--freq-tol-rel", type=float, default=0.03)
    ap.add_argument("--min-handoff-gap-ns", type=float, default=600.0)
    ap.add_argument("--soak-duration", type=float, default=0.3)
    ap.add_argument("--case-retries", type=int, default=2)
    ap.add_argument("--capture-retries", type=int, default=2)
    ap.add_argument("--retry-delay", type=float, default=0.2)
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "_preflight_exports"))
    args = ap.parse_args()

    base = args.url.rstrip("/")
    channels = [int(x) for x in args.la_channels.split(",") if x.strip()]
    foc_freqs = [float(x) for x in args.foc_freqs.split(",") if x.strip()]
    foc_estop_freqs = [float(x) for x in args.foc_estop_freqs.split(",") if x.strip()]
    mic_freqs = [float(x) for x in args.mic_freqs.split(",") if x.strip()]
    brake_active_high = args.brake_active_high == 1

    ui_ok, ui_st, ui_dt = wait_http_ready(base, timeout_s=args.ui_ready_timeout, poll_s=max(0.05, args.poll))
    if not ui_ok:
        log(f"ERROR: UI not reachable after {ui_dt*1000:.1f}ms last_status={ui_st}")
        return 2

    mgr = Manager.connect(port=args.saleae_port, connect_timeout_seconds=2)
    mgr._codex_port = args.saleae_port
    devices = []
    for _ in range(30):
        devices = mgr.get_devices()
        if devices:
            break
        time.sleep(0.1)
    if not devices:
        log("ERROR: No Saleae device found")
        return 3

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(args.outdir, f"foc_mic_preflight_{ts}")
    os.makedirs(outdir, exist_ok=True)

    result: dict = {
        "ts": ts,
        "base": base,
        "la_rate": args.la_rate,
        "la_duration": args.la_duration,
        "min_handoff_gap_ns": args.min_handoff_gap_ns,
        "foc": [],
        "foc_estop": [],
        "mic": [],
    }

    try:
        safe_stop(base)
        ok, st, dt = wait_safe(base, timeout_s=1.5, poll_s=args.poll)
        result["safe_before"] = {"ok": ok, "status_dt_ms": dt * 1000.0, "status": st}

        for freq in foc_freqs:
            tag = f"foc_{freq:.1f}".replace(".", "p")
            item = None
            for attempt in range(args.case_retries + 1):
                if attempt:
                    log(f"WARN: foc freq retry {attempt}/{args.case_retries} freq={freq:.1f}")
                    safe_stop(base)
                    time.sleep(args.retry_delay)
                cmds = ["CLEAR", "MODE FOC", f"SET FREQ {freq:.1f}", "START"]
                cmds_ok = send_cmds_retry(base, cmds, retries=1, retry_delay_s=0.2)
                run_ok, st, dt = wait_foc_run(
                    base,
                    mode="FOC",
                    freq_cmd=freq,
                    timeout_s=args.settle_timeout,
                    poll_s=args.poll,
                    freq_tol_abs=args.freq_tol_abs,
                    freq_tol_rel=args.freq_tol_rel,
                    consecutive=max(1, args.steady_consecutive),
                )
                soak = soak_status(base, duration_s=args.soak_duration, poll_s=args.poll)
                capture_error = None
                csv_path = ""
                try:
                    csv_path, metrics = capture_metrics(
                        mgr,
                        channels,
                        args.la_rate,
                        args.la_duration,
                        outdir,
                        tag,
                        brake_active_high,
                        True,
                        False,
                        args.min_handoff_gap_ns,
                        retries=args.capture_retries,
                        retry_delay_s=args.retry_delay,
                    )
                except Exception as exc:
                    capture_error = str(exc)
                    metrics = {"pass": False, "error": capture_error}
                item = {
                    "freq_cmd": freq,
                    "attempts": attempt + 1,
                    "cmds_ok": cmds_ok,
                    "run_ok": run_ok,
                    "status_dt_ms": dt * 1000.0,
                    "status": st,
                    "soak": soak,
                    "csv": csv_path,
                    "metrics": metrics,
                    "capture_error": capture_error,
                }
                item["pass"] = bool(
                    cmds_ok
                    and run_ok
                    and metrics.get("pass")
                    and soak.get("bp_bad_delta") == 0
                    and soak.get("bp_fault_values") == [0]
                    and soak.get("states") == ["FOC_RUN"]
                    and soak.get("modes") == ["FOC"]
                )
                retryable = bool(
                    (capture_error is not None)
                    or (
                        metrics.get("pass")
                        and (not cmds_ok or not run_ok or soak.get("bp_bad_delta") != 0 or soak.get("bp_fault_values") != [0] or soak.get("states") != ["FOC_RUN"] or soak.get("modes") != ["FOC"])
                    )
                )
                if item["pass"] or attempt >= args.case_retries or not retryable:
                    break
            result["foc"].append(item)

        for freq in foc_estop_freqs:
            run_tag = f"foc_estop_run_{freq:.1f}".replace(".", "p")
            estop_tag = f"foc_estop_{freq:.1f}".replace(".", "p")
            rec_tag = f"foc_recover_{freq:.1f}".replace(".", "p")

            run_cmds_ok = send_cmds_retry(base, ["CLEAR", "MODE FOC", f"SET FREQ {freq:.1f}", "START"], retries=1, retry_delay_s=0.2)
            run_ok, run_st, run_dt = wait_foc_run(
                base,
                mode="FOC",
                freq_cmd=freq,
                timeout_s=args.settle_timeout,
                poll_s=args.poll,
                freq_tol_abs=args.freq_tol_abs,
                freq_tol_rel=args.freq_tol_rel,
                consecutive=max(1, args.steady_consecutive),
            )
            run_csv, run_metrics = capture_metrics(
                mgr,
                channels,
                args.la_rate,
                args.la_duration,
                outdir,
                run_tag,
                brake_active_high,
                True,
                False,
                args.min_handoff_gap_ns,
            )

            estop_cmd_ok = send_cmds_retry(base, ["ESTOP"], retries=1, retry_delay_s=0.2)
            estop_ok, estop_st, estop_dt = wait_for(
                base,
                lambda s: int(st_num(s, "pwm", 0.0)) == 0 and int(st_num(s, "estop", 0.0)) == 1 and s.get("state") == "SAFE",
                timeout_s=1.5,
                poll_s=args.poll,
            )
            estop_csv, estop_metrics = capture_metrics(
                mgr,
                channels,
                args.la_rate,
                args.la_duration,
                outdir,
                estop_tag,
                brake_active_high,
                False,
                True,
                0.0,
            )

            rec_cmd_ok = send_cmds_retry(base, ["ESTOP CLEAR", "START"], retries=1, retry_delay_s=0.2)
            rec_ok, rec_st, rec_dt = wait_foc_run(
                base,
                mode="FOC",
                freq_cmd=freq,
                timeout_s=args.settle_timeout,
                poll_s=args.poll,
                freq_tol_abs=args.freq_tol_abs,
                freq_tol_rel=args.freq_tol_rel,
                consecutive=max(1, args.steady_consecutive),
            )
            rec_csv, rec_metrics = capture_metrics(
                mgr,
                channels,
                args.la_rate,
                args.la_duration,
                outdir,
                rec_tag,
                brake_active_high,
                True,
                False,
                args.min_handoff_gap_ns,
            )
            result["foc_estop"].append(
                {
                    "freq_cmd": freq,
                    "run": {
                        "cmds_ok": run_cmds_ok,
                        "run_ok": run_ok,
                        "status_dt_ms": run_dt * 1000.0,
                        "status": run_st,
                        "csv": run_csv,
                        "metrics": run_metrics,
                    },
                    "estop": {
                        "cmds_ok": estop_cmd_ok,
                        "ok": estop_ok,
                        "status_dt_ms": estop_dt * 1000.0,
                        "status": estop_st,
                        "csv": estop_csv,
                        "metrics": estop_metrics,
                    },
                    "recover": {
                        "cmds_ok": rec_cmd_ok,
                        "run_ok": rec_ok,
                        "status_dt_ms": rec_dt * 1000.0,
                        "status": rec_st,
                        "csv": rec_csv,
                        "metrics": rec_metrics,
                    },
                    "pass": bool(
                        run_cmds_ok
                        and run_ok
                        and run_metrics.get("pass")
                        and estop_cmd_ok
                        and estop_ok
                        and estop_metrics.get("pass")
                        and rec_cmd_ok
                        and rec_ok
                        and rec_metrics.get("pass")
                    ),
                }
            )

        for freq in mic_freqs:
            tag = f"mic_{freq:.1f}".replace(".", "p")
            item = None
            for attempt in range(args.case_retries + 1):
                if attempt:
                    log(f"WARN: mic freq retry {attempt}/{args.case_retries} freq={freq:.1f}")
                    safe_stop(base)
                    time.sleep(args.retry_delay)
                cmds = ["CLEAR", "MODE MIC", f"SET FREQ {freq:.1f}", "START"]
                cmds_ok = send_cmds_retry(base, cmds, retries=1, retry_delay_s=0.2)
                run_ok, st, dt = wait_foc_run(
                    base,
                    mode="MIC",
                    freq_cmd=freq,
                    timeout_s=args.settle_timeout,
                    poll_s=args.poll,
                    freq_tol_abs=args.freq_tol_abs,
                    freq_tol_rel=args.freq_tol_rel,
                    consecutive=max(1, args.steady_consecutive),
                )
                soak = soak_status(base, duration_s=args.soak_duration, poll_s=args.poll)
                capture_error = None
                csv_path = ""
                try:
                    csv_path, metrics = capture_metrics(
                        mgr,
                        channels,
                        args.la_rate,
                        args.la_duration,
                        outdir,
                        tag,
                        brake_active_high,
                        True,
                        False,
                        args.min_handoff_gap_ns,
                        retries=args.capture_retries,
                        retry_delay_s=args.retry_delay,
                    )
                except Exception as exc:
                    capture_error = str(exc)
                    metrics = {"pass": False, "error": capture_error}
                item = {
                    "freq_cmd": freq,
                    "attempts": attempt + 1,
                    "cmds_ok": cmds_ok,
                    "run_ok": run_ok,
                    "status_dt_ms": dt * 1000.0,
                    "status": st,
                    "soak": soak,
                    "csv": csv_path,
                    "metrics": metrics,
                    "capture_error": capture_error,
                    "ai_active": bool((soak.get("mic_active_ratio") or 0.0) > 0.0),
                    "ai_enabled": bool((soak.get("mic_enable_ai_ratio") or 0.0) > 0.0),
                    "ai_gated": bool((soak.get("mic_gated_ratio") or 0.0) > 0.0),
                }
                item["pass"] = bool(
                    cmds_ok
                    and run_ok
                    and metrics.get("pass")
                    and soak.get("bp_bad_delta") == 0
                    and soak.get("bp_fault_values") == [0]
                    and soak.get("states") == ["FOC_RUN"]
                    and soak.get("modes") == ["MIC"]
                )
                retryable = bool(
                    (capture_error is not None)
                    or (
                        metrics.get("pass")
                        and (not cmds_ok or not run_ok or soak.get("bp_bad_delta") != 0 or soak.get("bp_fault_values") != [0] or soak.get("states") != ["FOC_RUN"] or soak.get("modes") != ["MIC"])
                    )
                )
                if item["pass"] or attempt >= args.case_retries or not retryable:
                    break
            result["mic"].append(item)

        safe_stop(base)
        ok, st, dt = wait_safe(base, timeout_s=1.5, poll_s=args.poll)
        result["safe_after"] = {"ok": ok, "status_dt_ms": dt * 1000.0, "status": st}
        result["summary"] = {
            "foc_pass": all(item["pass"] for item in result["foc"]),
            "foc_estop_pass": all(item["pass"] for item in result["foc_estop"]),
            "mic_pass": all(item["pass"] for item in result["mic"]),
            "final_safe": bool(result["safe_after"]["ok"]),
        }

        out_path = os.path.join(outdir, "summary.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        log(f"SUMMARY: {out_path}")
        overall = bool(
            result["summary"]["foc_pass"]
            and result["summary"]["foc_estop_pass"]
            and result["summary"]["mic_pass"]
            and result["summary"]["final_safe"]
        )
        log(f"PASS={overall}")
        return 0 if overall else 4
    finally:
        try:
            mgr.close()
        except Exception:
            pass
        safe_stop(base)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())

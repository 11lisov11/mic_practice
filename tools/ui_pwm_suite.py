#!/usr/bin/env python3
import argparse
import csv
import os
import sys
import time

# Reuse helpers from ui_pwm_case
sys.path.insert(0, os.path.dirname(__file__))
from ui_pwm_case import (  # noqa: E402
    log,
    post_cmd,
    get_status,
    wait_for,
    wait_http_ready,
    st_num,
    send_cmds,
    safe_stop,
    start_capture,
    wait_capture_with_timeout,
    export_capture,
    analyze,
    DEFAULT_MAX_OVERLAP_RATIO,
    status_fault_free,
    status_mode_matches,
    vf_steady_matches,
)
from saleae.automation import Manager
from saleae.automation.capture import Capture
from saleae.grpc import saleae_pb2
import grpc

MAX_OVERLAP_RATIO = DEFAULT_MAX_OVERLAP_RATIO


def summary_writer(path: str):
    f = open(path, "w", newline="", encoding="utf-8")
    writer = csv.writer(f)
    writer.writerow(
        [
            "tag",
            "mode",
            "freq",
            "cmd_ok",
            "status_ok",
            "status_dt_ms",
            "expect_pwm",
            "expect_estop",
            "pass",
            "pwm_ok",
            "brake_ok",
            "overlap_ok",
            "deadtime_ok",
            "brake_high",
            "io_ok",
            "io_detail",
            "attempts",
            "retry_reason",
            "csv",
        ]
    )
    return f, writer


def capture_and_analyze(
    mgr: Manager,
    channels,
    la_rate,
    la_duration,
    outdir,
    tag,
    brake_active_high,
    expect_pwm,
    expect_estop,
    min_handoff_gap_ns: float = 0.0,
):
    try:
        capture = start_capture(mgr, channels, la_rate, la_duration)
    except grpc.RpcError as exc:
        code = exc.code() if hasattr(exc, "code") else None
        details = exc.details() if hasattr(exc, "details") else ""
        msg = details or str(exc)
        log(f"ERROR: StartCapture failed code={code} details={msg}")
        return None, None
    except Exception as exc:
        log(f"ERROR: StartCapture failed: {exc}")
        return None, None
    try:
        wait_capture_with_timeout(mgr, capture, timeout_s=la_duration + 2.0)
    except grpc.RpcError as exc:
        log(f"ERROR: capture wait failed: {exc.details()}")
        try:
            capture.stop()
        except Exception:
            pass
        return None, None
    try:
        csv_path = export_capture(capture, channels, outdir, tag)
    except Exception as exc:
        log(f"ERROR: capture export failed: {exc}")
        try:
            capture.close()
        except Exception:
            pass
        return None, None
    capture.close()
    metrics = analyze(
        csv_path,
        channels,
        brake_active_high,
        expect_pwm,
        expect_estop,
        max_overlap_ratio=MAX_OVERLAP_RATIO,
        min_handoff_gap_ns=min_handoff_gap_ns,
    )
    return csv_path, metrics


def wait_status(
    base: str,
    expect_pwm: bool,
    expect_estop: bool,
    timeout_s: float,
    poll_s: float,
    retries: int = 0,
    expect_freq_cmd: float | None = None,
    freq_tol: float = 0.06,
    expect_mode: str | None = None,
    require_vf_steady: bool = False,
):
    def predicate(st):
        pwm_ok = int(st_num(st, "pwm", 0.0)) == (1 if expect_pwm else 0)
        if expect_estop and int(st_num(st, "bp_bad", 999999.0)) != 0:
            return False
        if not expect_estop and not status_fault_free(st):
            return False
        if expect_freq_cmd is not None:
            if abs(st_num(st, "freq_cmd", 0.0) - float(expect_freq_cmd)) > freq_tol:
                return False
        if expect_mode is not None and not status_mode_matches(st, expect_mode):
            return False
        if require_vf_steady:
            if expect_freq_cmd is None:
                return False
            if not vf_steady_matches(st, expect_freq_cmd):
                return False
        if expect_estop:
            return pwm_ok and int(st_num(st, "estop", 0.0)) == 1
        return pwm_ok

    for attempt in range(retries + 1):
        ok, st, dt = wait_for(base, predicate, timeout_s=timeout_s, poll_s=poll_s)
        if ok:
            log(f"Status ok=True dt={dt*1000:.1f}ms st={st}")
            return True, st, dt
        log("WARN: status timeout or mismatch")
        log(f"Status ok=False dt={dt*1000:.1f}ms st={st}")
        if attempt < retries:
            time.sleep(0.15)
    return False, st, dt


def send_cmds_retry(base: str, cmds, retries: int = 1):
    for attempt in range(retries + 1):
        ok = send_cmds(base, cmds)
        if ok:
            return True
        if attempt < retries:
            log("WARN: cmd send failed, retrying")
            time.sleep(0.15)
    return False


def control_retry_reason(cmd_ok: bool, status_ok: bool, metrics: dict | None, io_ok=None) -> str:
    if metrics is None:
        return "capture"
    if not metrics.get("pass"):
        return ""
    reasons = []
    if not cmd_ok:
        reasons.append("cmd")
    if not status_ok:
        reasons.append("status")
    if io_ok is False:
        reasons.append("io")
    return "+".join(reasons)


def main() -> int:
    global MAX_OVERLAP_RATIO
    parser = argparse.ArgumentParser(description="Full UI->PWM test suite with Saleae captures")
    parser.add_argument("--url", required=True)
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
    # 0 = only capture at key points (0, 0.1, 0.5, 1, 2, 5, 10, 20, 30, 40, 50).
    # Set to e.g. 1.0 to capture every 1 Hz in addition to the key points.
    parser.add_argument("--capture-every-hz", type=float, default=0.0)
    parser.add_argument("--skip-diag", action="store_true")
    parser.add_argument("--skip-duty", action="store_true")
    parser.add_argument("--skip-sweep", action="store_true")
    parser.add_argument("--skip-hot", action="store_true")
    parser.add_argument("--skip-estop", action="store_true")
    parser.add_argument("--sweep-min", type=float, default=0.0)
    parser.add_argument("--sweep-max", type=float, default=50.0)
    parser.add_argument("--sweep-step", type=float, default=0.1)
    parser.add_argument("--max-overlap-ratio", type=float, default=DEFAULT_MAX_OVERLAP_RATIO)
    parser.add_argument("--min-handoff-gap-ns", type=float, default=0.0)
    parser.add_argument("--ui-ready-timeout", type=float, default=3.0)
    parser.add_argument("--case-retries", type=int, default=1)
    parser.add_argument("--retry-delay", type=float, default=0.2)
    args = parser.parse_args()
    MAX_OVERLAP_RATIO = max(0.0, float(args.max_overlap_ratio))

    base = args.url.rstrip("/")
    channels = [int(x) for x in args.la_channels.split(",") if x.strip() != ""]
    brake_active_high = args.brake_active_high == 1

    log("Connect Saleae")
    if args.saleae_host not in ("127.0.0.1", "localhost"):
        log(f"WARN: saleae-host '{args.saleae_host}' not supported by this Saleae SDK, using localhost")
    mgr = Manager.connect(port=args.saleae_port, connect_timeout_seconds=2)
    mgr._codex_port = args.saleae_port
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

    os.makedirs(args.outdir, exist_ok=True)
    summary_path = os.path.join(args.outdir, "summary.csv")
    summary_file, writer = summary_writer(summary_path)
    pass_count = 0
    fail_count = 0

    def record(
        tag,
        mode,
        freq,
        expect_pwm,
        expect_estop,
        metrics,
        csv_path,
        cmd_ok,
        status_ok,
        status_dt_ms,
        io_ok=None,
        io_detail="",
        attempts: int = 1,
        retry_reason: str = "",
    ):
        nonlocal pass_count, fail_count
        if metrics is None:
            writer.writerow(
                [
                    tag,
                    mode,
                    freq,
                    cmd_ok,
                    status_ok,
                    status_dt_ms,
                    expect_pwm,
                    expect_estop,
                    "FAIL",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "" if io_ok is None else int(bool(io_ok)),
                    io_detail,
                    attempts,
                    retry_reason,
                    csv_path or "",
                ]
            )
            summary_file.flush()
            fail_count += 1
            return
        passed = bool(metrics["pass"] and cmd_ok and status_ok and (True if io_ok is None else io_ok))
        writer.writerow(
            [
                tag,
                mode,
                freq,
                int(cmd_ok),
                int(status_ok),
                f"{status_dt_ms:.1f}",
                int(expect_pwm),
                int(expect_estop),
                "PASS" if passed else "FAIL",
                metrics.get("pwm_ok"),
                metrics.get("brake_ok"),
                metrics.get("overlap_ok"),
                metrics.get("deadtime_ok"),
                metrics.get("brake_high"),
                "" if io_ok is None else int(bool(io_ok)),
                io_detail,
                attempts,
                retry_reason,
                csv_path,
            ]
        )
        summary_file.flush()
        if passed:
            pass_count += 1
        else:
            fail_count += 1

    def check_io(st, expect_ntc=None, expect_pfc=None, expect_brake=None, expect_brake_duty=None, tol=0.05):
        if st is None:
            return False, "no status"
        ok = True
        details = []
        if expect_ntc is not None:
            got = int(st_num(st, "ntc", 0.0))
            if got != expect_ntc:
                ok = False
            details.append(f"ntc={got}")
        if expect_pfc is not None:
            got = int(st_num(st, "pfc", 0.0))
            if got != expect_pfc:
                ok = False
            details.append(f"pfc={got}")
        if expect_brake is not None:
            got = int(st_num(st, "brake", 0.0))
            if got != expect_brake:
                ok = False
            details.append(f"brake={got}")
        if expect_brake_duty is not None:
            got = st_num(st, "brake_duty", 0.0)
            if abs(got - expect_brake_duty) > tol:
                ok = False
            details.append(f"brake_duty={got:.2f}")
        return ok, " ".join(details)

    def run_with_control_retry(tag: str, runner):
        last = None
        retry_reason = ""
        for attempt in range(args.case_retries + 1):
            if attempt:
                log(f"WARN: retry {tag} attempt {attempt + 1}/{args.case_retries + 1} after {retry_reason}")
                safe_stop(base)
                time.sleep(args.retry_delay)
            last = runner()
            retry_reason = control_retry_reason(
                last["cmd_ok"],
                last["status_ok"],
                last["metrics"],
                last.get("io_ok"),
            )
            if not retry_reason:
                break
            log(f"WARN: {tag} capture clean but control-plane mismatch ({retry_reason})")
        if last is None:
            raise RuntimeError(f"runner returned no data for {tag}")
        last["attempts"] = attempt + 1
        last["retry_reason"] = retry_reason
        return last
    try:
        ui_ok, ui_st, ui_dt = wait_http_ready(base, timeout_s=args.ui_ready_timeout, poll_s=max(0.05, args.poll))
        if not ui_ok:
            log(f"ERROR: UI not reachable after {ui_dt*1000:.1f}ms last_status={ui_st}")
            return 3

        # DIAG
        if not args.skip_diag:
            log("TEST: DIAG")
            def diag_runner():
                cmd_ok = send_cmds_retry(base, ["CLEAR", "DIAG ON", "START"], retries=1)
                time.sleep(0.2)
                status_ok, st, dt = wait_status(
                    base,
                    True,
                    False,
                    args.status_timeout,
                    args.poll,
                    retries=1,
                    expect_mode="DIAG",
                )
                csv_path, metrics = capture_and_analyze(
                    mgr, channels, args.la_rate, args.la_duration, args.outdir, "diag", brake_active_high, True, False, args.min_handoff_gap_ns
                )
                return {
                    "cmd_ok": cmd_ok,
                    "status_ok": status_ok,
                    "status": st,
                    "status_dt_ms": dt * 1000.0,
                    "csv_path": csv_path,
                    "metrics": metrics,
                    "io_ok": None,
                    "io_detail": "",
                }

            res = run_with_control_retry("diag", diag_runner)
            record(
                "diag",
                "DIAG",
                0.0,
                True,
                False,
                res["metrics"],
                res["csv_path"],
                res["cmd_ok"],
                res["status_ok"],
                res["status_dt_ms"],
                attempts=res["attempts"],
                retry_reason=res["retry_reason"],
            )

        # DUTY
        if not args.skip_duty:
            log("TEST: DUTY")
            def duty_runner():
                cmd_ok = send_cmds_retry(base, ["CLEAR", "MODE DUTY", "DUTY 0.2 0.4 0.6", "START"], retries=1)
                time.sleep(0.2)
                status_ok, st, dt = wait_status(
                    base,
                    True,
                    False,
                    args.status_timeout,
                    args.poll,
                    retries=1,
                    expect_mode="DUTY",
                )
                csv_path, metrics = capture_and_analyze(
                    mgr, channels, args.la_rate, args.la_duration, args.outdir, "duty", brake_active_high, True, False, args.min_handoff_gap_ns
                )
                return {
                    "cmd_ok": cmd_ok,
                    "status_ok": status_ok,
                    "status": st,
                    "status_dt_ms": dt * 1000.0,
                    "csv_path": csv_path,
                    "metrics": metrics,
                    "io_ok": None,
                    "io_detail": "",
                }

            res = run_with_control_retry("duty", duty_runner)
            record(
                "duty",
                "DUTY",
                0.0,
                True,
                False,
                res["metrics"],
                res["csv_path"],
                res["cmd_ok"],
                res["status_ok"],
                res["status_dt_ms"],
                attempts=res["attempts"],
                retry_reason=res["retry_reason"],
            )

        # IO (NTC/PFC/BRAKE PWM)
        log("TEST: IO NTC/PFC/BRAKE")
        def io_runner():
            cmd_ok = send_cmds_retry(
                base,
                ["CLEAR", "MODE VF", "SET FREQ 5.0", "START", "NTC ON", "PFC ON", "BRAKE PWM 0.25"],
                retries=1,
            )
            time.sleep(0.2)
            ok, st, dt = wait_for(
                base,
                lambda s: int(st_num(s, "pwm", 0.0)) == 1
                and int(st_num(s, "ntc", 0.0)) == 1
                and int(st_num(s, "pfc", 0.0)) == 1
                and int(st_num(s, "brake", 0.0)) == 1
                and abs(st_num(s, "brake_duty", 0.0) - 0.25) <= 0.05,
                timeout_s=args.status_timeout,
                poll_s=args.poll,
            )
            log(f"IO status ok={ok} dt={dt*1000:.1f}ms st={st}")
            csv_path, metrics = capture_and_analyze(
                mgr, channels, args.la_rate, args.la_duration, args.outdir, "io_ntc_pfc_brake", brake_active_high, True, False, args.min_handoff_gap_ns
            )
            io_ok, io_detail = check_io(st, expect_ntc=1, expect_pfc=1, expect_brake=1, expect_brake_duty=0.25)
            return {
                "cmd_ok": cmd_ok,
                "status_ok": ok,
                "status": st,
                "status_dt_ms": dt * 1000.0,
                "csv_path": csv_path,
                "metrics": metrics,
                "io_ok": io_ok,
                "io_detail": io_detail,
            }

        res = run_with_control_retry("io_ntc_pfc_brake", io_runner)
        record(
            "io_ntc_pfc_brake",
            "VF",
            5.0,
            True,
            False,
            res["metrics"],
            res["csv_path"],
            res["cmd_ok"],
            res["status_ok"],
            res["status_dt_ms"],
            res["io_ok"],
            res["io_detail"],
            res["attempts"],
            res["retry_reason"],
        )
        send_cmds(base, ["BRAKE OFF", "NTC OFF", "PFC OFF"])

        # Sweep
        if not args.skip_sweep:
            log("TEST: sweep 0..50 step 0.1")
            # Sweep uses a special case for 0.0 Hz: firmware auto-stops (PWM off + brake asserted).
            # So we don't force START here; each step will decide START/STOP.
            cmd_ok = send_cmds_retry(base, ["CLEAR", "MODE VF"], retries=1)
            time.sleep(0.2)
            key_freqs = {0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 40.0, 50.0}
            def is_key_freq(fv: float) -> bool:
                for k in key_freqs:
                    if abs(fv - k) <= 1e-6:
                        return True
                return False
            f = float(args.sweep_min)
            f_max = float(args.sweep_max)
            step = max(0.05, float(args.sweep_step))
            capture_every = float(args.capture_every_hz)
            next_cap = f if capture_every > 0 else None
            while f <= f_max + 1e-6:
                # 0.0 Hz is treated as STOP (PWM off) for safety.
                if abs(f) <= 1e-9:
                    step_cmds = [f"SET FREQ {f:.1f}", "STOP"]
                    expect_pwm = False
                else:
                    step_cmds = [f"SET FREQ {f:.1f}", "START"]
                    expect_pwm = True
                do_cap = False
                if is_key_freq(f):
                    do_cap = True
                if next_cap is not None and f + 1e-6 >= next_cap:
                    do_cap = True
                if do_cap:
                    tag = f"vf_{f:.1f}Hz".replace(".", "p")
                    def sweep_runner():
                        local_step_ok = send_cmds_retry(base, step_cmds, retries=1)
                        local_ok, local_st, local_dt = wait_status(
                            base,
                            expect_pwm,
                            False,
                            args.status_timeout,
                            args.poll,
                            retries=1,
                            expect_freq_cmd=f,
                            expect_mode="VF",
                            require_vf_steady=expect_pwm,
                        )
                        csv_path, metrics = capture_and_analyze(
                            mgr,
                            channels,
                            args.la_rate,
                            args.la_duration,
                            args.outdir,
                            tag,
                            brake_active_high,
                            expect_pwm,
                            False,
                            args.min_handoff_gap_ns,
                        )
                        return {
                            "cmd_ok": bool(cmd_ok and local_step_ok),
                            "status_ok": local_ok,
                            "status": local_st,
                            "status_dt_ms": local_dt * 1000.0,
                            "csv_path": csv_path,
                            "metrics": metrics,
                            "io_ok": None,
                            "io_detail": "",
                        }

                    res = run_with_control_retry(tag, sweep_runner)
                    record(
                        tag,
                        "VF",
                        f,
                        expect_pwm,
                        False,
                        res["metrics"],
                        res["csv_path"],
                        res["cmd_ok"],
                        res["status_ok"],
                        res["status_dt_ms"],
                        attempts=res["attempts"],
                        retry_reason=res["retry_reason"],
                    )
                    if next_cap is not None:
                        next_cap = f + capture_every
                else:
                    step_ok = send_cmds_retry(base, step_cmds, retries=1)
                    ok, st, dt = wait_status(
                        base,
                        expect_pwm,
                        False,
                        args.status_timeout,
                        args.poll,
                        retries=1,
                        expect_freq_cmd=f,
                        expect_mode="VF",
                        require_vf_steady=expect_pwm,
                    )
                    if ok:
                        log(f"FREQ {f:.1f} status ok=True dt={dt*1000:.1f}ms st={st}")
                    else:
                        log(f"FREQ {f:.1f} status ok=False dt={dt*1000:.1f}ms st={st}")
                    if not (cmd_ok and step_ok):
                        log(f"WARN: sweep step {f:.1f}Hz command not fully acknowledged")

                f = round(f + step, 3)

        # Hot switching
        if not args.skip_hot:
            log("TEST: hot switch VF<->FOC")
            for freq in [0.5, 2.0, 5.0, 10.0, 20.0, 50.0]:
                tag = f"hot_vf_{freq:.1f}".replace(".", "p")
                def hot_vf_runner():
                    cmd_ok = send_cmds_retry(base, [f"SET FREQ {freq:.1f}", "MODE VF", "START"], retries=1)
                    time.sleep(0.2)
                    status_ok, st, dt = wait_status(
                        base,
                        True,
                        False,
                        args.status_timeout,
                        args.poll,
                        retries=1,
                        expect_freq_cmd=freq,
                        expect_mode="VF",
                        require_vf_steady=True,
                    )
                    csv_path, metrics = capture_and_analyze(
                        mgr, channels, args.la_rate, args.la_duration, args.outdir, tag, brake_active_high, True, False, args.min_handoff_gap_ns
                    )
                    return {
                        "cmd_ok": cmd_ok,
                        "status_ok": status_ok,
                        "status": st,
                        "status_dt_ms": dt * 1000.0,
                        "csv_path": csv_path,
                        "metrics": metrics,
                        "io_ok": None,
                        "io_detail": "",
                    }

                res = run_with_control_retry(tag, hot_vf_runner)
                record(
                    tag,
                    "VF",
                    freq,
                    True,
                    False,
                    res["metrics"],
                    res["csv_path"],
                    res["cmd_ok"],
                    res["status_ok"],
                    res["status_dt_ms"],
                    attempts=res["attempts"],
                    retry_reason=res["retry_reason"],
                )

                tag = f"hot_foc_{freq:.1f}".replace(".", "p")
                def hot_foc_runner():
                    cmd_ok = send_cmds_retry(base, [f"SET FREQ {freq:.1f}", "MODE FOC", "START"], retries=2)
                    time.sleep(0.2)
                    status_ok, st, dt = wait_status(
                        base,
                        True,
                        False,
                        args.status_timeout,
                        args.poll,
                        retries=1,
                        expect_freq_cmd=freq,
                        expect_mode="FOC",
                    )
                    csv_path, metrics = capture_and_analyze(
                        mgr, channels, args.la_rate, args.la_duration, args.outdir, tag, brake_active_high, True, False, args.min_handoff_gap_ns
                    )
                    return {
                        "cmd_ok": cmd_ok,
                        "status_ok": status_ok,
                        "status": st,
                        "status_dt_ms": dt * 1000.0,
                        "csv_path": csv_path,
                        "metrics": metrics,
                        "io_ok": None,
                        "io_detail": "",
                    }

                res = run_with_control_retry(tag, hot_foc_runner)
                record(
                    tag,
                    "FOC",
                    freq,
                    True,
                    False,
                    res["metrics"],
                    res["csv_path"],
                    res["cmd_ok"],
                    res["status_ok"],
                    res["status_dt_ms"],
                    attempts=res["attempts"],
                    retry_reason=res["retry_reason"],
                )

                tag = f"hot_vf2_{freq:.1f}".replace(".", "p")
                def hot_vf2_runner():
                    cmd_ok = send_cmds_retry(base, [f"SET FREQ {freq:.1f}", "MODE VF", "START"], retries=2)
                    time.sleep(0.2)
                    status_ok, st, dt = wait_status(
                        base,
                        True,
                        False,
                        args.status_timeout,
                        args.poll,
                        retries=1,
                        expect_freq_cmd=freq,
                        expect_mode="VF",
                        require_vf_steady=True,
                    )
                    csv_path, metrics = capture_and_analyze(
                        mgr, channels, args.la_rate, args.la_duration, args.outdir, tag, brake_active_high, True, False, args.min_handoff_gap_ns
                    )
                    return {
                        "cmd_ok": cmd_ok,
                        "status_ok": status_ok,
                        "status": st,
                        "status_dt_ms": dt * 1000.0,
                        "csv_path": csv_path,
                        "metrics": metrics,
                        "io_ok": None,
                        "io_detail": "",
                    }

                res = run_with_control_retry(tag, hot_vf2_runner)
                record(
                    tag,
                    "VF",
                    freq,
                    True,
                    False,
                    res["metrics"],
                    res["csv_path"],
                    res["cmd_ok"],
                    res["status_ok"],
                    res["status_dt_ms"],
                    attempts=res["attempts"],
                    retry_reason=res["retry_reason"],
                )

        # ESTOP
        if not args.skip_estop:
            log("TEST: ESTOP @10Hz and 50Hz")
            for freq in [10.0, 50.0]:
                run_tag = f"estop_run_{freq:.1f}".replace(".", "p")
                estop_tag = f"estop_{freq:.1f}".replace(".", "p")
                recover_tag = f"recover_{freq:.1f}".replace(".", "p")
                def estop_sequence_runner():
                    nonlocal brake_active_high
                    run_cmd_ok = send_cmds_retry(base, ["MODE VF", f"SET FREQ {freq:.1f}", "START"], retries=1)
                    time.sleep(0.2)
                    run_status_ok, st_run, run_dt = wait_status(
                        base,
                        True,
                        False,
                        args.status_timeout,
                        args.poll,
                        retries=1,
                        expect_freq_cmd=freq,
                        expect_mode="VF",
                        require_vf_steady=True,
                    )
                    run_csv_path, run_metrics = capture_and_analyze(
                        mgr, channels, args.la_rate, args.la_duration, args.outdir, run_tag, brake_active_high, True, False, args.min_handoff_gap_ns
                    )

                    estop_cmd_ok = send_cmds_retry(base, ["ESTOP"], retries=1)
                    time.sleep(0.1)
                    estop_status_ok, st_estop, estop_dt = wait_status(
                        base,
                        False,
                        True,
                        args.status_timeout,
                        args.poll,
                        retries=1,
                        expect_mode="VF",
                    )
                    csv_path_estop, metrics_estop = capture_and_analyze(
                        mgr, channels, args.la_rate, args.la_duration, args.outdir, estop_tag, brake_active_high, False, True
                    )
                    if run_metrics and metrics_estop:
                        run_b = run_metrics.get("brake_high")
                        estop_b = metrics_estop.get("brake_high")
                        if run_b is not None and estop_b is not None:
                            if run_b > 0.95 and estop_b < 0.05 and brake_active_high:
                                log("Auto-detect: BRAKE polarity inverted (active-low). Re-evaluating.")
                                brake_active_high = False
                                run_metrics = analyze(
                                    run_csv_path,
                                    channels,
                                    brake_active_high,
                                    True,
                                    False,
                                    max_overlap_ratio=MAX_OVERLAP_RATIO,
                                )
                                metrics_estop = analyze(
                                    csv_path_estop,
                                    channels,
                                    brake_active_high,
                                    False,
                                    True,
                                    max_overlap_ratio=MAX_OVERLAP_RATIO,
                                )
                            elif run_b < 0.05 and estop_b > 0.95 and (not brake_active_high):
                                log("Auto-detect: BRAKE polarity inverted (active-high). Re-evaluating.")
                                brake_active_high = True
                                run_metrics = analyze(
                                    run_csv_path,
                                    channels,
                                    brake_active_high,
                                    True,
                                    False,
                                    max_overlap_ratio=MAX_OVERLAP_RATIO,
                                )
                                metrics_estop = analyze(
                                    csv_path_estop,
                                    channels,
                                    brake_active_high,
                                    False,
                                    True,
                                    max_overlap_ratio=MAX_OVERLAP_RATIO,
                                )

                    recover_cmd_ok = send_cmds_retry(base, ["ESTOP CLEAR", "START"], retries=1)
                    time.sleep(0.2)
                    recover_status_ok, st_rec, rec_dt = wait_status(
                        base,
                        True,
                        False,
                        args.status_timeout,
                        args.poll,
                        retries=1,
                        expect_freq_cmd=freq,
                        expect_mode="VF",
                        require_vf_steady=True,
                    )
                    rec_csv_path, rec_metrics = capture_and_analyze(
                        mgr, channels, args.la_rate, args.la_duration, args.outdir, recover_tag, brake_active_high, True, False, args.min_handoff_gap_ns
                    )
                    return {
                        "run": {
                            "cmd_ok": run_cmd_ok,
                            "status_ok": run_status_ok,
                            "status_dt_ms": run_dt * 1000.0,
                            "csv_path": run_csv_path,
                            "metrics": run_metrics,
                        },
                        "estop": {
                            "cmd_ok": estop_cmd_ok,
                            "status_ok": estop_status_ok,
                            "status_dt_ms": estop_dt * 1000.0,
                            "csv_path": csv_path_estop,
                            "metrics": metrics_estop,
                        },
                        "recover": {
                            "cmd_ok": recover_cmd_ok,
                            "status_ok": recover_status_ok,
                            "status_dt_ms": rec_dt * 1000.0,
                            "csv_path": rec_csv_path,
                            "metrics": rec_metrics,
                        },
                    }

                attempts = 0
                retry_reason = ""
                res = None
                for attempt in range(args.case_retries + 1):
                    attempts = attempt + 1
                    if attempt:
                        log(f"WARN: retry estop {freq:.1f}Hz attempt {attempts}/{args.case_retries + 1} after {retry_reason}")
                        safe_stop(base)
                        time.sleep(args.retry_delay)
                    res = estop_sequence_runner()
                    reasons = [
                        control_retry_reason(res["run"]["cmd_ok"], res["run"]["status_ok"], res["run"]["metrics"]),
                        control_retry_reason(res["estop"]["cmd_ok"], res["estop"]["status_ok"], res["estop"]["metrics"]),
                        control_retry_reason(res["recover"]["cmd_ok"], res["recover"]["status_ok"], res["recover"]["metrics"]),
                    ]
                    retry_reason = ",".join(r for r in reasons if r)
                    if not retry_reason:
                        break
                    log(f"WARN: estop {freq:.1f}Hz capture clean but control-plane mismatch ({retry_reason})")
                if res is None:
                    raise RuntimeError(f"estop sequence returned no data for {freq}")

                record(
                    run_tag,
                    "VF",
                    freq,
                    True,
                    False,
                    res["run"]["metrics"],
                    res["run"]["csv_path"],
                    res["run"]["cmd_ok"],
                    res["run"]["status_ok"],
                    res["run"]["status_dt_ms"],
                    attempts=attempts,
                    retry_reason=retry_reason,
                )
                record(
                    estop_tag,
                    "ESTOP",
                    freq,
                    False,
                    True,
                    res["estop"]["metrics"],
                    res["estop"]["csv_path"],
                    res["estop"]["cmd_ok"],
                    res["estop"]["status_ok"],
                    res["estop"]["status_dt_ms"],
                    attempts=attempts,
                    retry_reason=retry_reason,
                )
                record(
                    recover_tag,
                    "VF",
                    freq,
                    True,
                    False,
                    res["recover"]["metrics"],
                    res["recover"]["csv_path"],
                    res["recover"]["cmd_ok"],
                    res["recover"]["status_ok"],
                    res["recover"]["status_dt_ms"],
                    attempts=attempts,
                    retry_reason=retry_reason,
                )

        log(f"DONE. Summary: {summary_path}")
        log(f"PASS={pass_count} FAIL={fail_count}")
        return 0 if fail_count == 0 else 1
    finally:
        try:
            summary_file.close()
        except Exception:
            pass
        try:
            mgr.close()
        except Exception:
            pass
        safe_stop(base)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())

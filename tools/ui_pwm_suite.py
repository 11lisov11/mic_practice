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
    st_num,
    send_cmds,
    safe_stop,
    start_capture,
    wait_capture_with_timeout,
    export_capture,
    analyze,
    DEFAULT_MAX_OVERLAP_RATIO,
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
            "brake_high",
            "io_ok",
            "io_detail",
            "csv",
        ]
    )
    return f, writer


def capture_and_analyze(mgr: Manager, channels, la_rate, la_duration, outdir, tag, brake_active_high, expect_pwm, expect_estop):
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
):
    def predicate(st):
        pwm_ok = int(st_num(st, "pwm", 0.0)) == (1 if expect_pwm else 0)
        if expect_freq_cmd is not None:
            if abs(st_num(st, "freq_cmd", 0.0) - float(expect_freq_cmd)) > freq_tol:
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
    args = parser.parse_args()
    MAX_OVERLAP_RATIO = max(0.0, float(args.max_overlap_ratio))

    base = args.url.rstrip("/")
    channels = [int(x) for x in args.la_channels.split(",") if x.strip() != ""]
    brake_active_high = args.brake_active_high == 1

    log("Connect Saleae")
    if args.saleae_host not in ("127.0.0.1", "localhost"):
        log(f"WARN: saleae-host '{args.saleae_host}' not supported by this Saleae SDK, using localhost")
    mgr = Manager.connect(port=args.saleae_port, connect_timeout_seconds=2)
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

    def record(tag, mode, freq, expect_pwm, expect_estop, metrics, csv_path, cmd_ok, status_ok, status_dt_ms, io_ok=None, io_detail=""):
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
                    "" if io_ok is None else int(bool(io_ok)),
                    io_detail,
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
                metrics.get("brake_high"),
                "" if io_ok is None else int(bool(io_ok)),
                io_detail,
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
    try:
        # DIAG
        if not args.skip_diag:
            log("TEST: DIAG")
            cmd_ok = send_cmds_retry(base, ["CLEAR", "DIAG ON", "START"], retries=1)
            time.sleep(0.2)
            status_ok, st, dt = wait_status(base, True, False, args.status_timeout, args.poll, retries=1)
            csv_path, metrics = capture_and_analyze(
                mgr, channels, args.la_rate, args.la_duration, args.outdir, "diag", brake_active_high, True, False
            )
            record("diag", "DIAG", 0.0, True, False, metrics, csv_path, cmd_ok, status_ok, dt * 1000.0)

        # DUTY
        if not args.skip_duty:
            log("TEST: DUTY")
            cmd_ok = send_cmds_retry(base, ["CLEAR", "MODE DUTY", "DUTY 0.2 0.4 0.6", "START"], retries=1)
            time.sleep(0.2)
            status_ok, st, dt = wait_status(base, True, False, args.status_timeout, args.poll, retries=1)
            csv_path, metrics = capture_and_analyze(
                mgr, channels, args.la_rate, args.la_duration, args.outdir, "duty", brake_active_high, True, False
            )
            record("duty", "DUTY", 0.0, True, False, metrics, csv_path, cmd_ok, status_ok, dt * 1000.0)

        # IO (NTC/PFC/BRAKE PWM)
        log("TEST: IO NTC/PFC/BRAKE")
        cmd_ok = send_cmds(base, ["CLEAR", "MODE VF", "SET FREQ 5.0", "START", "NTC ON", "PFC ON", "BRAKE PWM 0.25"])
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
            mgr, channels, args.la_rate, args.la_duration, args.outdir, "io_ntc_pfc_brake", brake_active_high, True, False
        )
        io_ok, io_detail = check_io(st, expect_ntc=1, expect_pfc=1, expect_brake=1, expect_brake_duty=0.25)
        record("io_ntc_pfc_brake", "VF", 5.0, True, False, metrics, csv_path, cmd_ok, ok, dt * 1000.0, io_ok, io_detail)
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
                step_ok = send_cmds_retry(base, step_cmds, retries=1)
                ok, st, dt = wait_status(
                    base,
                    expect_pwm,
                    False,
                    args.status_timeout,
                    args.poll,
                    retries=1,
                    expect_freq_cmd=f,
                )
                if ok:
                    log(f"FREQ {f:.1f} status ok=True dt={dt*1000:.1f}ms st={st}")
                else:
                    log(f"FREQ {f:.1f} status ok=False dt={dt*1000:.1f}ms st={st}")

                do_cap = False
                if is_key_freq(f):
                    do_cap = True
                if next_cap is not None and f + 1e-6 >= next_cap:
                    do_cap = True
                if do_cap:
                    tag = f"vf_{f:.1f}Hz".replace(".", "p")
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
                    )
                    record(tag, "VF", f, expect_pwm, False, metrics, csv_path, (cmd_ok and step_ok), ok, dt * 1000.0)
                    if next_cap is not None:
                        next_cap = f + capture_every

                f = round(f + step, 3)

        # Hot switching
        if not args.skip_hot:
            log("TEST: hot switch VF<->FOC")
            for freq in [0.5, 2.0, 5.0, 10.0, 20.0, 50.0]:
                cmd_ok = send_cmds_retry(base, [f"SET FREQ {freq:.1f}", "MODE VF", "START"], retries=1)
                time.sleep(0.2)
                status_ok, st, dt = wait_status(base, True, False, args.status_timeout, args.poll, retries=1)
                tag = f"hot_vf_{freq:.1f}".replace(".", "p")
                csv_path, metrics = capture_and_analyze(
                    mgr, channels, args.la_rate, args.la_duration, args.outdir, tag, brake_active_high, True, False
                )
                record(tag, "VF", freq, True, False, metrics, csv_path, cmd_ok, status_ok, dt * 1000.0)

                cmd_ok = send_cmds_retry(base, ["MODE FOC", "START"], retries=1)
                time.sleep(0.2)
                status_ok, st, dt = wait_status(base, True, False, args.status_timeout, args.poll, retries=1)
                tag = f"hot_foc_{freq:.1f}".replace(".", "p")
                csv_path, metrics = capture_and_analyze(
                    mgr, channels, args.la_rate, args.la_duration, args.outdir, tag, brake_active_high, True, False
                )
                record(tag, "FOC", freq, True, False, metrics, csv_path, cmd_ok, status_ok, dt * 1000.0)

                cmd_ok = send_cmds_retry(base, ["MODE VF", "START"], retries=1)
                time.sleep(0.2)
                status_ok, st, dt = wait_status(base, True, False, args.status_timeout, args.poll, retries=1)
                tag = f"hot_vf2_{freq:.1f}".replace(".", "p")
                csv_path, metrics = capture_and_analyze(
                    mgr, channels, args.la_rate, args.la_duration, args.outdir, tag, brake_active_high, True, False
                )
                record(tag, "VF", freq, True, False, metrics, csv_path, cmd_ok, status_ok, dt * 1000.0)

        # ESTOP
        if not args.skip_estop:
            log("TEST: ESTOP @10Hz and 50Hz")
            for freq in [10.0, 50.0]:
                run_cmd_ok = send_cmds_retry(base, ["MODE VF", f"SET FREQ {freq:.1f}", "START"], retries=1)
                time.sleep(0.2)
                run_status_ok, st_run, run_dt = wait_status(base, True, False, args.status_timeout, args.poll, retries=1)
                run_tag = f"estop_run_{freq:.1f}".replace(".", "p")
                run_csv_path, run_metrics = capture_and_analyze(
                    mgr, channels, args.la_rate, args.la_duration, args.outdir, run_tag, brake_active_high, True, False
                )

                estop_cmd_ok = send_cmds_retry(base, ["ESTOP"], retries=1)
                time.sleep(0.1)
                estop_status_ok, st_estop, estop_dt = wait_status(base, False, True, args.status_timeout, args.poll, retries=1)
                estop_tag = f"estop_{freq:.1f}".replace(".", "p")
                csv_path_estop, metrics_estop = capture_and_analyze(
                    mgr, channels, args.la_rate, args.la_duration, args.outdir, estop_tag, brake_active_high, False, True
                )
                # Auto-detect brake polarity if it looks inverted
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

                # Record both captures after final brake polarity is known
                record(run_tag, "VF", freq, True, False, run_metrics, run_csv_path, run_cmd_ok, run_status_ok, run_dt * 1000.0)
                record(estop_tag, "ESTOP", freq, False, True, metrics_estop, csv_path_estop, estop_cmd_ok, estop_status_ok, estop_dt * 1000.0)

                recover_cmd_ok = send_cmds_retry(base, ["ESTOP CLEAR", "START"], retries=1)
                time.sleep(0.2)
                recover_status_ok, st_rec, rec_dt = wait_status(base, True, False, args.status_timeout, args.poll, retries=1)
                recover_tag = f"recover_{freq:.1f}".replace(".", "p")
                rec_csv_path, rec_metrics = capture_and_analyze(
                    mgr, channels, args.la_rate, args.la_duration, args.outdir, recover_tag, brake_active_high, True, False
                )
                record(recover_tag, "VF", freq, True, False, rec_metrics, rec_csv_path, recover_cmd_ok, recover_status_ok, rec_dt * 1000.0)

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

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from active_pwm_guard import start_allowed_by_bench_gate
from runtime_python import ensure_modules_or_reexec
from saleae_pwm_analyze import analyze_csv, parse_pairs

ensure_modules_or_reexec(["saleae"], "MIC_PRACTICE_SALEAE_PROBE_REEXEC")
from saleae import automation

PWM_STATIC_MAP = {
    0: {"stm32": "PA8", "signal": "PWM-1H"},
    1: {"stm32": "PB13", "signal": "PWM-1L"},
    2: {"stm32": "PA9", "signal": "PWM-2H"},
    3: {"stm32": "PB14", "signal": "PWM-2L"},
    4: {"stm32": "PA10", "signal": "PWM-3H"},
    5: {"stm32": "PB15", "signal": "PWM-3L"},
    6: {"stm32": "PB12", "signal": "EM_STOP/shutdown"},
}


def append_log(path: Path, msg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='milliseconds')} {msg}\n")


def command_requests_start(cmd: str) -> bool:
    return cmd.strip().upper() == "START"


def post_cmd(base: str, cmd: str, timeout_s: float = 2.0, log_fn=print) -> str:
    if command_requests_start(cmd) and not start_allowed_by_bench_gate(log_fn, url=base):
        raise RuntimeError("START blocked by bench gate")
    data = json.dumps({"cmd": cmd}).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/api/cmd",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return resp.read().decode("utf-8", "replace")


def required_pair_channels(pairs_raw: str) -> set[int]:
    return {ch for _, hi, lo in parse_pairs(pairs_raw) for ch in (hi, lo)}


def _level_pair(levels: dict[str, dict[str, int]], channel: int) -> tuple[int | None, int | None]:
    rec = levels.get(str(channel), {})
    if not isinstance(rec, dict):
        return None, None
    return rec.get("initial"), rec.get("final")


def classify_pwm_static_levels(levels: dict[str, dict[str, int]]) -> str:
    vals = {ch: _level_pair(levels, ch) for ch in range(6)}
    if all(v == (0, 0) for v in vals.values()):
        return "all_pwm_low_safe"
    if all(v == (1, 1) for v in vals.values()):
        return "all_pwm_high"
    if all(vals[ch] == (0, 0) for ch in (0, 2, 4)) and all(vals[ch] == (1, 1) for ch in (1, 3, 5)):
        return "low_side_static_high"
    if all(vals[ch] == (1, 1) for ch in (0, 2, 4)) and all(vals[ch] == (0, 0) for ch in (1, 3, 5)):
        return "high_side_static_high"
    if any(initial != final for initial, final in vals.values()):
        return "static_capture_has_level_change"
    return "mixed_static_levels"


def summarize_pwm_static_checks(channels: list[int], edges: dict[str, int], levels: dict[str, dict[str, int]]) -> dict:
    captured = set(channels)
    required = set(range(7))
    pwm_required = set(range(6))
    pwm_channels_present = pwm_required.issubset(captured)
    channels_0_6_present = required.issubset(captured)
    no_edges = channels_0_6_present and all(int(edges.get(str(ch), -1)) == 0 for ch in required)
    pwm_lines_low = pwm_channels_present and all(_level_pair(levels, ch) == (0, 0) for ch in range(6))
    em_stop_shutdown_asserted = channels_0_6_present and _level_pair(levels, 6) == (0, 0)
    high_pwm_channels = []
    changed_channels = []
    for ch in range(6):
        initial, final = _level_pair(levels, ch)
        info = PWM_STATIC_MAP[ch]
        label = f"CH{ch}/{info['stm32']}/{info['signal']}"
        if initial == 1 or final == 1:
            high_pwm_channels.append(label)
        if initial != final:
            changed_channels.append(label)
    return {
        "channels_0_6_present": channels_0_6_present,
        "pwm_channels_present": pwm_channels_present,
        "no_edges": no_edges,
        "pwm_lines_low": pwm_lines_low,
        "em_stop_shutdown_asserted": em_stop_shutdown_asserted,
        "pwm_static_safe_pass": bool(channels_0_6_present and no_edges and pwm_lines_low and em_stop_shutdown_asserted),
        "pattern": classify_pwm_static_levels(levels),
        "high_pwm_channels": high_pwm_channels,
        "changed_channels": changed_channels,
        "channel_map": PWM_STATIC_MAP,
    }


def sample_period_ns(rate: int | None) -> float | None:
    if rate is None or int(rate) <= 0:
        return None
    return 1_000_000_000.0 / float(rate)


def exit_code_for_summary(summary: dict, command_failures: int, require_static_safe: bool) -> int:
    if command_failures:
        return 4
    if require_static_safe and summary.get("pwm_static_safe_pass") is not True:
        return 5
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Minimal Saleae high-level Automation API probe.")
    ap.add_argument("--port", type=int, default=10430)
    ap.add_argument("--channels", default="0,1")
    ap.add_argument("--rate", type=int, default=6_000_000)
    ap.add_argument(
        "--auto-rate",
        dest="auto_rate",
        action="store_true",
        default=True,
        help="Retry lower common sample rates if requested rate is rejected; enabled by default.",
    )
    ap.add_argument(
        "--no-auto-rate",
        dest="auto_rate",
        action="store_false",
        help="Fail immediately if the requested Saleae sample rate is not supported.",
    )
    ap.add_argument("--duration", type=float, default=0.12)
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--url", default="http://127.0.0.1:18080")
    ap.add_argument(
        "--pre-cmd",
        action="append",
        default=[],
        help="Command executed before Saleae capture starts; repeat for a sequence.",
    )
    ap.add_argument("--cmd", action="append", default=[])
    ap.add_argument(
        "--post-cmd",
        action="append",
        default=[],
        help="Best-effort command executed after capture, including error paths.",
    )
    ap.add_argument("--pairs", default="0:1,2:3,4:5")
    ap.add_argument(
        "--analyze-pwm",
        dest="analyze_pwm",
        action="store_true",
        default=True,
        help="Write pwm_analysis.json when the captured channels cover all requested PWM pairs.",
    )
    ap.add_argument(
        "--no-analyze-pwm",
        dest="analyze_pwm",
        action="store_false",
        help="Skip pwm_analysis.json generation.",
    )
    ap.add_argument(
        "--require-static-safe",
        action="store_true",
        help=(
            "Fail with rc=5 unless CH0..CH6 are captured, all six PWM inputs stay LOW, "
            "and EM_STOP/shutdown CH6 stays LOW. START commands are still guarded separately."
        ),
    )
    ap.add_argument(
        "--outdir",
        default=str(Path(__file__).resolve().parent / "_preflight_exports"),
    )
    args = ap.parse_args()

    channels = [int(x) for x in args.channels.split(",") if x.strip()]
    run_dir = Path(args.outdir).resolve() / (
        "saleae_highlevel_probe_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"
    )
    log_path = run_dir / "probe.log"
    append_log(log_path, f"START channels={channels} rate={args.rate} duration={args.duration}")
    command_results: list[dict] = []
    command_failures = 0

    def run_command_phase(commands: list[str], phase: str) -> None:
        nonlocal command_failures
        for command in commands:
            append_log(log_path, f"{phase}_cmd_begin {command}")
            try:
                response = post_cmd(args.url, command, log_fn=lambda msg: append_log(log_path, msg))
                append_log(log_path, f"{phase}_cmd_ok {command} {response}")
                command_results.append(
                    {"phase": phase, "cmd": command, "ok": True, "response": response}
                )
            except Exception as exc:
                command_failures += 1
                append_log(log_path, f"{phase}_cmd_err {command} {exc!r}")
                command_results.append(
                    {
                        "phase": phase,
                        "cmd": command,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    run_command_phase(args.pre_cmd, "pre")
    try:
        append_log(log_path, "connect_begin")
        with automation.Manager.connect(port=args.port) as manager:
            append_log(log_path, f"connect_ok app={manager.get_app_info()}")
            devices = manager.get_devices()
            append_log(log_path, f"devices={devices}")

            capture_configuration = automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=args.duration)
            )

            common_rates = [24_000_000, 12_000_000, 6_000_000, 3_000_000, 2_000_000, 1_000_000,
                            500_000, 250_000, 200_000, 100_000, 50_000, 25_000]
            rates = [args.rate]
            if args.auto_rate:
                rates = []
                for rate in [args.rate, *common_rates]:
                    if rate <= args.rate and rate not in rates:
                        rates.append(rate)

            capture = None
            selected_rate = None
            selected_threshold = None
            start_errors: list[str] = []
            for rate in rates:
                threshold_candidates = [args.threshold] if args.threshold is not None else [None]
                if args.threshold is not None:
                    # Some Saleae devices expose no configurable digital threshold.
                    # Treat the requested threshold as best-effort and retry defaults.
                    threshold_candidates.append(None)
                for threshold in threshold_candidates:
                    device_kwargs = {
                        "enabled_digital_channels": channels,
                        "digital_sample_rate": rate,
                    }
                    threshold_label = "default"
                    if threshold is not None:
                        device_kwargs["digital_threshold_volts"] = threshold
                        threshold_label = str(threshold)
                    device_configuration = automation.LogicDeviceConfiguration(**device_kwargs)
                    append_log(log_path, f"start_capture_begin rate={rate} threshold={threshold_label}")
                    try:
                        capture = manager.start_capture(
                            device_configuration=device_configuration,
                            capture_configuration=capture_configuration,
                        )
                        selected_rate = rate
                        selected_threshold = threshold
                        append_log(log_path, f"start_capture_ok rate={rate} threshold={threshold_label}")
                        break
                    except Exception as exc:
                        msg = f"{rate} threshold={threshold_label}: {type(exc).__name__}: {exc}"
                        start_errors.append(msg)
                        append_log(log_path, f"start_capture_err {msg}")
                        if not args.auto_rate and threshold is None:
                            raise
                if capture is not None:
                    break
            if capture is None:
                raise RuntimeError("no Saleae sample rate accepted; " + " | ".join(start_errors))

            with capture:
                time.sleep(min(0.03, max(0.0, args.duration / 4.0)))
                run_command_phase(args.cmd, "capture")
                append_log(log_path, "wait_begin")
                capture.wait()
                append_log(log_path, "wait_ok")
                append_log(log_path, "export_begin")
                capture.export_raw_data_csv(directory=str(run_dir), digital_channels=channels)
                append_log(log_path, "export_ok")
    except Exception as exc:
        append_log(log_path, f"ERROR {type(exc).__name__}: {exc}")
        print(f"PROBE_LOG={log_path}")
        raise
    finally:
        run_command_phase(args.post_cmd, "post")

    csv_path = run_dir / "digital.csv"
    summary = {
        "run_dir": str(run_dir),
        "csv": str(csv_path),
        "channels": channels,
        "requested_rate": args.rate,
        "selected_rate": selected_rate,
        "requested_sample_period_ns": sample_period_ns(args.rate),
        "selected_sample_period_ns": sample_period_ns(selected_rate),
        "selected_rate_meets_requested": bool(selected_rate is not None and selected_rate >= args.rate),
        "requested_threshold": args.threshold,
        "selected_threshold": selected_threshold,
        "auto_rate": bool(args.auto_rate),
        "require_static_safe": bool(args.require_static_safe),
        "commands": command_results,
        "command_pass": command_failures == 0,
        "edges": {},
        "levels": {},
    }
    if csv_path.exists():
        prev = {ch: None for ch in channels}
        rows = 0
        with csv_path.open(newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                rows += 1
                for idx, ch in enumerate(channels, start=1):
                    if idx >= len(row):
                        continue
                    val = 1 if row[idx] == "1" else 0
                    if prev[ch] is None:
                        summary["edges"][str(ch)] = 0
                        summary["levels"][str(ch)] = {"initial": val, "final": val}
                    elif val != prev[ch]:
                        summary["edges"][str(ch)] = summary["edges"].get(str(ch), 0) + 1
                    if str(ch) in summary["levels"]:
                        summary["levels"][str(ch)]["final"] = val
                    prev[ch] = val
        summary["rows"] = rows
        summary["pwm_static_checks"] = summarize_pwm_static_checks(channels, summary["edges"], summary["levels"])
        summary["pwm_static_safe_pass"] = bool(summary["pwm_static_checks"]["pwm_static_safe_pass"])
        summary["require_static_safe_pass"] = (
            bool(summary["pwm_static_safe_pass"]) if args.require_static_safe else None
        )
        if args.analyze_pwm:
            analysis_path = run_dir / "pwm_analysis.json"
            try:
                required_channels = required_pair_channels(args.pairs)
                captured_channels = set(channels)
                if required_channels.issubset(captured_channels):
                    analysis = analyze_csv(csv_path, args.pairs, expect_pwm=False)
                    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    summary["pwm_analysis"] = str(analysis_path)
                    summary["pwm_analysis_pass"] = bool(analysis.get("pass"))
                    summary["pwm_analysis_pass_meaning"] = analysis.get("pass_meaning")
                    summary["pwm_analysis_expect_pwm"] = bool(analysis.get("expect_pwm"))
                    summary["pwm_analysis_csv_row_timing"] = analysis.get("csv_row_timing")
                    summary["pwm_analysis_timing_resolution_pass"] = analysis.get("timing_resolution_pass")
                    summary["pwm_overlap_analysis_pass"] = bool(analysis.get("overlap_analysis_pass"))
                    summary["pwm_no_overlap_pass"] = bool(analysis.get("no_overlap_pass"))
                    summary["pwm_activity_pass"] = bool(analysis.get("pwm_activity_pass"))
                    append_log(log_path, f"pwm_analysis_ok path={analysis_path}")
                else:
                    missing = sorted(required_channels - captured_channels)
                    summary["pwm_analysis_skipped"] = f"missing captured channels {missing} for pairs {args.pairs}"
                    append_log(log_path, f"pwm_analysis_skipped {summary['pwm_analysis_skipped']}")
            except Exception as exc:
                summary["pwm_analysis_error"] = f"{type(exc).__name__}: {exc}"
                append_log(log_path, f"pwm_analysis_error {summary['pwm_analysis_error']}")
    elif args.require_static_safe:
        summary["require_static_safe_pass"] = False
        summary["pwm_static_safe_pass"] = False
        summary["pwm_static_checks"] = {"pwm_static_safe_pass": False, "error": "digital.csv not found"}
    exit_code = exit_code_for_summary(summary, command_failures, bool(args.require_static_safe))
    summary["exit_code"] = exit_code
    if exit_code == 5:
        checks = summary.get("pwm_static_checks", {})
        summary["exit_reason"] = f"static-safe requirement failed: pattern={checks.get('pattern')}"
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    append_log(log_path, f"DONE summary={summary_path}")
    print(f"PROBE_LOG={log_path}")
    print(f"SUMMARY={summary_path}")
    print(json.dumps(summary, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from run_metadata import collect_run_metadata


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"


def run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return {
            "step": step,
            "cmd": cmd,
            "returncode": proc.returncode,
            "duration_s": time.monotonic() - started,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "ok": proc.returncode == 0,
        }
    except Exception as exc:
        return {
            "step": step,
            "cmd": cmd,
            "returncode": None,
            "duration_s": time.monotonic() - started,
            "stdout": "",
            "stderr": repr(exc),
            "ok": False,
            "exception": type(exc).__name__,
        }


def latest_probe_summary(run_dir: Path) -> Path | None:
    candidates = sorted(run_dir.glob("saleae_highlevel_probe_*/summary.json"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def platformio_run_cmd(pio_dir: Path, env: str, *extra: str) -> list[str]:
    return [sys.executable, "-m", "platformio", "run", "-d", str(pio_dir), "-e", env, *extra]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Flash Blue Pill PWM self-test, capture all PWM lines with Saleae, analyze overlap, and restore firmware."
    )
    ap.add_argument("--confirm-hv-off", action="store_true", help="Required: 310 V bus is disconnected and discharged.")
    ap.add_argument("--dry-run", action="store_true", help="Build and plan only; do not upload or capture.")
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--pio-dir", type=Path, default=Path("bluepill_uart_pwm_pio"))
    ap.add_argument("--selftest-env", default="bluepill_pwm_selftest")
    ap.add_argument("--restore-env", default="bluepill_uart_pwm")
    ap.add_argument("--channels", default="0,1,2,3,4,5,6")
    ap.add_argument("--pairs", default="0:1,2:3,4:5")
    ap.add_argument("--rate", type=int, default=24_000_000)
    ap.add_argument("--no-auto-rate", action="store_true", help="Do not let Saleae probe fall back to lower supported rates.")
    ap.add_argument(
        "--max-sample-period-ns",
        type=float,
        default=250.0,
        help="Fail the self-test if Saleae effective sample period is coarser than this. Use 0 to disable.",
    )
    ap.add_argument("--duration", type=float, default=4.0)
    ap.add_argument("--saleae-port", type=int, default=10430)
    ap.add_argument("--settle-s", type=float, default=1.0)
    ap.add_argument("--upload-timeout-s", type=float, default=90.0)
    ap.add_argument("--capture-timeout-s", type=float, default=60.0)
    ap.add_argument("--out-root", type=Path, default=Path("tools/_preflight_exports"))
    args = ap.parse_args()

    repo = args.repo.resolve()
    pio_dir = (repo / args.pio_dir).resolve() if not args.pio_dir.is_absolute() else args.pio_dir.resolve()
    run_dir = (repo / args.out_root).resolve() / f"bluepill_pwm_selftest_preflight_{ts_tag()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"

    result: dict[str, Any] = {
        "tool": "bluepill_pwm_selftest_preflight",
        "run_dir": str(run_dir),
        "run_metadata": collect_run_metadata(repo),
        "confirm_hv_off": bool(args.confirm_hv_off),
        "dry_run": bool(args.dry_run),
        "pio_dir": str(pio_dir),
        "selftest_env": args.selftest_env,
        "restore_env": args.restore_env,
        "channels": [int(x) for x in args.channels.split(",") if x.strip()],
        "pairs": args.pairs,
        "rate": int(args.rate),
        "auto_rate": not bool(args.no_auto_rate),
        "duration_s": float(args.duration),
        "steps": [],
        "diagnostic_upload_attempted": False,
        "restored": False,
        "restore_attempted": False,
    }

    if not args.confirm_hv_off and not args.dry_run:
        result["pass"] = False
        result["error"] = "--confirm-hv-off is required before uploading self-test firmware"
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pass": False, "summary": str(summary_path), "error": result["error"]}, ensure_ascii=False))
        return 2

    py = sys.executable
    build_selftest = platformio_run_cmd(pio_dir, args.selftest_env)
    build_restore = platformio_run_cmd(pio_dir, args.restore_env)
    upload_selftest = platformio_run_cmd(pio_dir, args.selftest_env, "-t", "upload")
    upload_restore = platformio_run_cmd(pio_dir, args.restore_env, "-t", "upload")
    capture_cmd = [
        py,
        "-u",
        str(repo / "tools" / "saleae_highlevel_probe.py"),
        "--channels",
        args.channels,
        "--rate",
        str(args.rate),
        "--duration",
        f"{args.duration:.3f}",
        "--port",
        str(args.saleae_port),
        "--outdir",
        str(run_dir),
        "--no-analyze-pwm",
    ]
    if not args.no_auto_rate:
        capture_cmd.append("--auto-rate")

    try:
        for step, cmd in (("build_selftest", build_selftest), ("build_restore", build_restore)):
            rec = run_cmd(cmd, repo, args.upload_timeout_s, step)
            result["steps"].append(rec)
            if not rec["ok"]:
                result["pass"] = False
                result["error"] = f"{step} failed"
                return 3

        if args.dry_run:
            result["pass"] = True
            result["planned_commands"] = {
                "upload_selftest": upload_selftest,
                "capture": capture_cmd,
                "upload_restore": upload_restore,
            }
            return 0

        result["diagnostic_upload_attempted"] = True
        rec = run_cmd(upload_selftest, repo, args.upload_timeout_s, "upload_selftest")
        result["steps"].append(rec)
        if not rec["ok"]:
            result["pass"] = False
            result["error"] = "upload_selftest failed"
            return 4

        time.sleep(max(0.0, args.settle_s))

        rec = run_cmd(capture_cmd, repo, args.capture_timeout_s, "saleae_capture")
        result["steps"].append(rec)
        capture_ok = bool(rec["ok"])
        result["saleae_capture_ok"] = capture_ok
        probe_summary_path = latest_probe_summary(run_dir)
        result["probe_summary_path"] = str(probe_summary_path) if probe_summary_path else None
        probe_summary = read_json(probe_summary_path)
        result["probe_summary"] = probe_summary
        if not capture_ok or not probe_summary:
            result["pass"] = False
            result["error"] = "saleae_capture failed"
            return 5

        selected_rate = int(probe_summary.get("selected_rate") or args.rate)
        result["selected_rate"] = selected_rate
        csv_path = Path(str(probe_summary["csv"]))
        analysis_path = run_dir / "pwm_analysis.json"
        analyze_cmd = [
            py,
            "-u",
            str(repo / "tools" / "saleae_pwm_analyze.py"),
            str(csv_path),
            "--pairs",
            args.pairs,
            "--expect-pwm",
            "--max-sample-period-ns",
            f"{float(args.max_sample_period_ns):.3f}",
            "--selected-sample-rate-hz",
            str(selected_rate),
            "--out",
            str(analysis_path),
        ]
        rec = run_cmd(analyze_cmd, repo, 30.0, "analyze_pwm")
        result["steps"].append(rec)
        analysis = read_json(analysis_path)
        result["analysis_path"] = str(analysis_path)
        result["analysis"] = analysis

        timing_resolution_s = 1.0 / float(selected_rate) if selected_rate > 0 else None
        result["timing_resolution_s"] = timing_resolution_s
        max_sample_period_s = max(0.0, float(args.max_sample_period_ns)) * 1e-9
        timing_resolution_pass = True
        if max_sample_period_s > 0.0:
            timing_resolution_pass = bool(timing_resolution_s is not None and timing_resolution_s <= max_sample_period_s)
        result["max_sample_period_ns"] = float(args.max_sample_period_ns)
        result["timing_resolution_pass"] = timing_resolution_pass
        result["deadtime_resolution_warning"] = not timing_resolution_pass
        result["pass"] = bool(rec["ok"] and analysis and analysis.get("pass") is True and timing_resolution_pass)
        if not result["pass"]:
            if not timing_resolution_pass:
                result["error"] = (
                    f"Saleae timing resolution too coarse for deadtime proof: "
                    f"sample_period_s={timing_resolution_s}, max_sample_period_ns={args.max_sample_period_ns}"
                )
            else:
                result["error"] = "PWM analysis failed"
        return 0 if result["pass"] else 6
    finally:
        if not args.dry_run and args.confirm_hv_off and result["diagnostic_upload_attempted"]:
            result["restore_attempted"] = True
            rec = run_cmd(upload_restore, repo, args.upload_timeout_s, "restore_uart_firmware")
            result["steps"].append(rec)
            result["restored"] = bool(rec["ok"])
            if not rec["ok"]:
                result["pass"] = False
                result["error"] = "restore_uart_firmware failed"
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pass": bool(result.get("pass")), "summary": str(summary_path), "restored": result["restored"]}, ensure_ascii=False))
        if result["restore_attempted"] and not result["restored"]:
            raise SystemExit(7)


if __name__ == "__main__":
    raise SystemExit(main())

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

import bluepill_runtime_static_preflight as rt
from run_metadata import collect_run_metadata, collect_source_fingerprint


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"


def run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s)
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


def platformio_run_cmd(pio_dir: Path, env: str, *extra: str) -> list[str]:
    return [sys.executable, "-m", "platformio", "run", "-d", str(pio_dir), "-e", env, *extra]


def static_low_conclusion(checks: dict[str, Any] | None, restored: bool | None = None) -> dict[str, Any]:
    checks = checks or {}
    pattern = str(checks.get("pattern") or "unknown")
    passed = checks.get("pass") is True
    base = {
        "pattern": pattern,
        "static_low_pass": passed,
        "restored_runtime": restored,
        "active_pwm_allowed": False,
    }
    if passed:
        return {
            **base,
            "result": "static_low_pin_drive_path_ok",
            "meaning": (
                "The diagnostic firmware proved STM32/Saleae/IPM logic inputs can be held LOW. "
                "If runtime static preflight still fails, focus on TIM1/runtime initialization, not basic wiring."
            ),
            "next_actions": ["run_runtime_static_preflight"],
        }
    return {
        **base,
        "result": "static_low_pin_drive_path_failed",
        "meaning": (
            "The diagnostic firmware could not prove all PWM logic inputs LOW. "
            "Do not run active PWM; inspect physical wiring, Saleae ground/channel mapping, STM32 PB13/PB14/PB15 pins, "
            "and IPM input pull-ups/reference before debugging TIM1 modulation."
        ),
        "next_actions": ["inspect_pwm_static_wiring", "repeat_static_low_preflight_after_fix"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Flash a diagnostic Blue Pill firmware that only drives PA8/PA9/PA10/PB13/PB14/PB15/PB12 LOW, "
            "capture those lines with Saleae, then restore the normal runtime firmware."
        )
    )
    ap.add_argument("--confirm-hv-off", action="store_true", help="Required before upload: HV/J7 is disconnected and DC bus is discharged.")
    ap.add_argument("--dry-run", action="store_true", help="Build and print planned commands, but do not upload or capture.")
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--pio-dir", type=Path, default=Path("bluepill_uart_pwm_pio"))
    ap.add_argument("--test-env", default="bluepill_static_low_test")
    ap.add_argument("--restore-env", default="bluepill_uart_pwm")
    ap.add_argument("--channels", default="0,1,2,3,4,5,6")
    ap.add_argument("--pairs", default="0:1,2:3,4:5")
    ap.add_argument("--rate", type=int, default=24_000_000)
    ap.add_argument("--no-auto-rate", action="store_true")
    ap.add_argument("--duration", type=float, default=0.25)
    ap.add_argument("--saleae-port", type=int, default=10430)
    ap.add_argument("--settle-s", type=float, default=0.7)
    ap.add_argument("--upload-timeout-s", type=float, default=90.0)
    ap.add_argument("--capture-timeout-s", type=float, default=60.0)
    ap.add_argument("--out-root", type=Path, default=Path("tools/_preflight_exports"))
    args = ap.parse_args()

    repo = args.repo.resolve()
    pio_dir = (repo / args.pio_dir).resolve() if not args.pio_dir.is_absolute() else args.pio_dir.resolve()
    run_dir = (repo / args.out_root).resolve() / f"bluepill_static_low_preflight_{ts_tag()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"

    result: dict[str, Any] = {
        "tool": "bluepill_static_low_preflight",
        "run_dir": str(run_dir),
        "run_metadata": collect_run_metadata(repo),
        "source_fingerprint": collect_source_fingerprint(repo),
        "confirm_hv_off": bool(args.confirm_hv_off),
        "dry_run": bool(args.dry_run),
        "safe_only": True,
        "diagnostic_meaning": "all_pwm_inputs_low_proves_stm32_pin_drive_path",
        "test_env": args.test_env,
        "restore_env": args.restore_env,
        "pio_dir": str(pio_dir),
        "channels": [int(x) for x in args.channels.split(",") if x.strip()],
        "pairs": args.pairs,
        "rate": int(args.rate),
        "auto_rate": not bool(args.no_auto_rate),
        "duration_s": float(args.duration),
        "steps": [],
        "diagnostic_upload_attempted": False,
        "restore_attempted": False,
        "restored": False,
    }

    if not args.confirm_hv_off and not args.dry_run:
        result["pass"] = False
        result["error"] = "--confirm-hv-off is required before uploading static-low diagnostic firmware"
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pass": False, "summary": str(summary_path), "error": result["error"]}, ensure_ascii=False))
        return 2

    py = sys.executable
    build_test_cmd = platformio_run_cmd(pio_dir, args.test_env)
    build_restore_cmd = platformio_run_cmd(pio_dir, args.restore_env)
    upload_test_cmd = platformio_run_cmd(pio_dir, args.test_env, "-t", "upload")
    upload_restore_cmd = platformio_run_cmd(pio_dir, args.restore_env, "-t", "upload")
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
        "--require-static-safe",
    ]
    if not args.no_auto_rate:
        capture_cmd.append("--auto-rate")

    try:
        for step_name, cmd in (("build_static_low", build_test_cmd), ("build_restore_runtime", build_restore_cmd)):
            rec = run_cmd(cmd, repo, args.upload_timeout_s, step_name)
            result["steps"].append(rec)
            if not rec["ok"]:
                result["pass"] = False
                result["error"] = f"{step_name} failed"
                return 3

        if args.dry_run:
            result["pass"] = True
            result["planned_commands"] = {
                "upload_static_low": upload_test_cmd,
                "capture_static_low": capture_cmd,
                "restore_runtime": upload_restore_cmd,
            }
            return 0

        result["diagnostic_upload_attempted"] = True
        rec = run_cmd(upload_test_cmd, repo, args.upload_timeout_s, "upload_static_low")
        result["steps"].append(rec)
        if not rec["ok"]:
            result["pass"] = False
            result["error"] = "upload_static_low failed"
            return 4

        time.sleep(max(0.0, args.settle_s))

        rec = run_cmd(capture_cmd, repo, args.capture_timeout_s, "saleae_static_low_capture")
        result["steps"].append(rec)
        capture_ok = bool(rec["ok"])
        result["saleae_static_low_capture_ok"] = capture_ok
        probe_summary_path = rt.latest_probe_summary(run_dir)
        probe_summary = rt.read_json(probe_summary_path)
        result["probe_summary_path"] = str(probe_summary_path) if probe_summary_path else None
        result["probe_summary"] = probe_summary
        if not probe_summary:
            result["pass"] = False
            result["error"] = "saleae_static_low_capture failed"
            return 5

        csv_path = Path(str(probe_summary["csv"]))
        analysis_path = run_dir / "pwm_analysis.json"
        analyze_cmd = rt.build_analyze_cmd(py, repo, csv_path, args.pairs, analysis_path, probe_summary, 0.0)
        rec = run_cmd(analyze_cmd, repo, 30.0, "analyze_static_low")
        result["steps"].append(rec)
        analysis = rt.read_json(analysis_path)
        checks = rt.static_checks(probe_summary, analysis)
        result["analysis_path"] = str(analysis_path)
        result["analysis"] = analysis
        result["static_checks"] = checks
        result["pass"] = bool(capture_ok and rec["ok"] and checks.get("pass") is True)
        result["diagnostic_conclusion"] = static_low_conclusion(checks, None)
        if not result["pass"]:
            if not capture_ok:
                result["error"] = "saleae_static_low_capture command failed"
            else:
                result["error"] = f"static-low diagnostic failed: pattern={checks.get('pattern')}"
        return 0 if result["pass"] else 6
    finally:
        if not args.dry_run and args.confirm_hv_off and result["diagnostic_upload_attempted"]:
            result["restore_attempted"] = True
            rec = run_cmd(upload_restore_cmd, repo, args.upload_timeout_s, "restore_runtime")
            result["steps"].append(rec)
            result["restored"] = bool(rec["ok"])
            if not rec["ok"]:
                result["pass"] = False
                result["error"] = "restore_runtime failed"
            if isinstance(result.get("diagnostic_conclusion"), dict):
                result["diagnostic_conclusion"]["restored_runtime"] = bool(result["restored"])
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "pass": bool(result.get("pass")),
                    "summary": str(summary_path),
                    "restored": result["restored"],
                    "pattern": (result.get("static_checks") or {}).get("pattern"),
                },
                ensure_ascii=False,
            )
        )
        if result["restore_attempted"] and not result["restored"]:
            raise SystemExit(7)


if __name__ == "__main__":
    raise SystemExit(main())

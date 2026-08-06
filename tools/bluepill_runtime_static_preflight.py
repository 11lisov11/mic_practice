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


def latest_probe_summary(run_dir: Path) -> Path | None:
    candidates = sorted(run_dir.glob("saleae_highlevel_probe_*/summary.json"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def channel_levels(probe_summary: dict[str, Any], analysis: dict[str, Any] | None, channels: list[int]) -> dict[str, Any]:
    levels = probe_summary.get("levels")
    out: dict[str, Any] = {}
    if isinstance(levels, dict) and levels:
        for ch in channels:
            rec = levels.get(str(ch), {})
            if isinstance(rec, dict):
                out[str(ch)] = {"initial": rec.get("initial"), "final": rec.get("final")}
        return out
    if isinstance(analysis, dict):
        analysis_channels = analysis.get("channels", {})
        if isinstance(analysis_channels, dict):
            for ch in channels:
                rec = analysis_channels.get(str(ch), {})
                if isinstance(rec, dict):
                    out[str(ch)] = {"initial": rec.get("initial"), "final": rec.get("final")}
    return out


def classify_static_levels(levels: dict[str, Any]) -> str:
    vals = {ch: (levels.get(str(ch), {}).get("initial"), levels.get(str(ch), {}).get("final")) for ch in range(6)}
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


def static_checks(probe_summary: dict[str, Any] | None, analysis: dict[str, Any] | None) -> dict[str, Any]:
    if not probe_summary:
        return {"pass": False, "error": "missing Saleae probe summary"}
    channels = [int(ch) for ch in probe_summary.get("channels", []) if isinstance(ch, int) or str(ch).isdigit()]
    required = set(range(7))
    edges = probe_summary.get("edges", {}) if isinstance(probe_summary.get("edges"), dict) else {}
    levels = channel_levels(probe_summary, analysis, list(range(7)))
    pattern = classify_static_levels(levels)
    channels_ok = required.issubset(set(channels))
    no_edges = channels_ok and all(int(edges.get(str(ch), -1)) == 0 for ch in required)
    pwm_low = all(levels.get(str(ch), {}).get("initial") == 0 and levels.get(str(ch), {}).get("final") == 0 for ch in range(6))
    em_stop_low = levels.get("6", {}).get("initial") == 0 and levels.get("6", {}).get("final") == 0
    no_overlap = bool(analysis and analysis.get("no_overlap_pass") is True)
    probe_static_checks = probe_summary.get("pwm_static_checks")
    probe_static_flag_ok = True
    if isinstance(probe_static_checks, dict):
        probe_static_flag_ok = bool(probe_static_checks.get("pwm_static_safe_pass"))
    selected_rate = probe_summary.get("selected_rate")
    requested_rate = probe_summary.get("requested_rate")
    return {
        "pass": bool(channels_ok and no_edges and pwm_low and em_stop_low and no_overlap and probe_static_flag_ok),
        "channels_ok": channels_ok,
        "no_edges": no_edges,
        "pwm_lines_low": pwm_low,
        "em_stop_shutdown_asserted": em_stop_low,
        "no_overlap_pass": no_overlap,
        "probe_pwm_static_safe_pass": probe_static_flag_ok,
        "probe_pwm_static_checks": probe_static_checks if isinstance(probe_static_checks, dict) else None,
        "requested_sample_rate_hz": requested_rate,
        "selected_sample_rate_hz": selected_rate,
        "selected_rate_meets_requested": probe_summary.get("selected_rate_meets_requested"),
        "timing_resolution_pass": analysis.get("timing_resolution_pass") if isinstance(analysis, dict) else None,
        "pattern": pattern,
        "levels": {str(ch): levels.get(str(ch), {}) for ch in range(7)},
        "edges": {str(ch): edges.get(str(ch)) for ch in range(7)},
    }


def build_analyze_cmd(
    py: str,
    repo: Path,
    csv_path: Path,
    pairs: str,
    analysis_path: Path,
    probe_summary: dict[str, Any] | None,
    max_sample_period_ns: float = 0.0,
) -> list[str]:
    cmd = [
        py,
        "-u",
        str(repo / "tools" / "saleae_pwm_analyze.py"),
        str(csv_path),
        "--pairs",
        pairs,
        "--out",
        str(analysis_path),
    ]
    if isinstance(probe_summary, dict) and probe_summary.get("selected_rate"):
        cmd.extend(["--selected-sample-rate-hz", str(probe_summary["selected_rate"])])
    if max_sample_period_ns > 0.0:
        cmd.extend(["--max-sample-period-ns", str(max_sample_period_ns)])
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Flash the normal Blue Pill runtime firmware, capture static PWM pins with Saleae, and verify SAFE levels."
    )
    ap.add_argument("--confirm-hv-off", action="store_true", help="Required before upload: HV/J7 is disconnected and DC bus is discharged.")
    ap.add_argument("--dry-run", action="store_true", help="Build and print planned commands, but do not upload or capture.")
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--pio-dir", type=Path, default=Path("bluepill_uart_pwm_pio"))
    ap.add_argument("--env", default="bluepill_uart_pwm")
    ap.add_argument("--upload-port", default="", help="Optional PlatformIO upload port, for example COM6 for the serial bootloader.")
    ap.add_argument("--channels", default="0,1,2,3,4,5,6")
    ap.add_argument("--pairs", default="0:1,2:3,4:5")
    ap.add_argument("--rate", type=int, default=24_000_000)
    ap.add_argument("--no-auto-rate", action="store_true")
    ap.add_argument("--duration", type=float, default=0.12)
    ap.add_argument(
        "--max-static-sample-period-ns",
        type=float,
        default=0.0,
        help="Optional timing-resolution gate for static capture analysis. 0 keeps static-level proof independent of sample rate.",
    )
    ap.add_argument("--saleae-port", type=int, default=10430)
    ap.add_argument("--settle-s", type=float, default=1.0)
    ap.add_argument("--upload-timeout-s", type=float, default=90.0)
    ap.add_argument("--capture-timeout-s", type=float, default=60.0)
    ap.add_argument("--out-root", type=Path, default=Path("tools/_preflight_exports"))
    args = ap.parse_args()

    repo = args.repo.resolve()
    pio_dir = (repo / args.pio_dir).resolve() if not args.pio_dir.is_absolute() else args.pio_dir.resolve()
    run_dir = (repo / args.out_root).resolve() / f"bluepill_runtime_static_preflight_{ts_tag()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"

    result: dict[str, Any] = {
        "tool": "bluepill_runtime_static_preflight",
        "run_dir": str(run_dir),
        "run_metadata": collect_run_metadata(repo),
        "source_fingerprint": collect_source_fingerprint(repo),
        "confirm_hv_off": bool(args.confirm_hv_off),
        "dry_run": bool(args.dry_run),
        "safe_only": True,
        "runtime_env": args.env,
        "upload_port": args.upload_port,
        "pio_dir": str(pio_dir),
        "channels": [int(x) for x in args.channels.split(",") if x.strip()],
        "pairs": args.pairs,
        "rate": int(args.rate),
        "auto_rate": not bool(args.no_auto_rate),
        "duration_s": float(args.duration),
        "steps": [],
    }

    if not args.confirm_hv_off and not args.dry_run:
        result["pass"] = False
        result["error"] = "--confirm-hv-off is required before uploading runtime firmware"
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pass": False, "summary": str(summary_path), "error": result["error"]}, ensure_ascii=False))
        return 2

    py = sys.executable
    build_cmd = platformio_run_cmd(pio_dir, args.env)
    upload_args = ["-t", "upload"]
    if args.upload_port:
        upload_args.extend(["--upload-port", args.upload_port])
    upload_cmd = platformio_run_cmd(pio_dir, args.env, *upload_args)
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

    rec = run_cmd(build_cmd, repo, args.upload_timeout_s, "build_runtime")
    result["steps"].append(rec)
    if not rec["ok"]:
        result["pass"] = False
        result["error"] = "build_runtime failed"
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pass": False, "summary": str(summary_path), "error": result["error"]}, ensure_ascii=False))
        return 3

    if args.dry_run:
        result["pass"] = True
        result["planned_commands"] = {
            "upload_runtime": upload_cmd,
            "capture_static": capture_cmd,
        }
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pass": True, "summary": str(summary_path), "dry_run": True}, ensure_ascii=False))
        return 0

    rec = run_cmd(upload_cmd, repo, args.upload_timeout_s, "upload_runtime")
    result["steps"].append(rec)
    if not rec["ok"]:
        result["pass"] = False
        result["error"] = "upload_runtime failed"
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pass": False, "summary": str(summary_path), "error": result["error"]}, ensure_ascii=False))
        return 4

    time.sleep(max(0.0, args.settle_s))

    rec = run_cmd(capture_cmd, repo, args.capture_timeout_s, "saleae_static_capture")
    result["steps"].append(rec)
    capture_ok = bool(rec["ok"])
    result["saleae_static_capture_ok"] = capture_ok
    probe_summary_path = latest_probe_summary(run_dir)
    probe_summary = read_json(probe_summary_path)
    result["probe_summary_path"] = str(probe_summary_path) if probe_summary_path else None
    result["probe_summary"] = probe_summary
    if not probe_summary:
        result["pass"] = False
        result["error"] = "saleae_static_capture failed"
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pass": False, "summary": str(summary_path), "error": result["error"]}, ensure_ascii=False))
        return 5

    csv_path = Path(str(probe_summary["csv"]))
    analysis_path = run_dir / "pwm_analysis.json"
    analyze_cmd = build_analyze_cmd(
        py,
        repo,
        csv_path,
        args.pairs,
        analysis_path,
        probe_summary,
        args.max_static_sample_period_ns,
    )
    rec = run_cmd(analyze_cmd, repo, 30.0, "analyze_static_pwm")
    result["steps"].append(rec)
    analysis = read_json(analysis_path)
    result["analysis_path"] = str(analysis_path)
    result["analysis"] = analysis
    checks = static_checks(probe_summary, analysis)
    result["static_checks"] = checks
    result["pass"] = bool(capture_ok and rec["ok"] and checks.get("pass") is True)
    if not result["pass"]:
        if not capture_ok:
            result["error"] = "saleae_static_capture command failed"
        else:
            result["error"] = f"static PWM safe-level check failed: pattern={checks.get('pattern')}"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "pass": result["pass"],
                "summary": str(summary_path),
                "pattern": checks.get("pattern"),
                "static_checks_pass": checks.get("pass"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["pass"] else 6


if __name__ == "__main__":
    raise SystemExit(main())

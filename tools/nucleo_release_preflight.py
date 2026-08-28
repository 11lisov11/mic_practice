#!/usr/bin/env python3
"""Nucleo-only software release gate; intentionally excludes Blue Pill legacy."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("configure_unoq_autonomous_wifi_selftest.py", ()),
    ("web_hmi_control_access_selftest.py", ()),
    ("web_hmi_command_guard_selftest.py", ()),
    ("adb_deploy_web_hmi_selftest.py", ()),
    ("uno_nucleo_mcsdk_contract_check.py", ()),
    ("air56b2_firmware_profile_check.py", ()),
    ("nucleo_firmware_safety_check.py", ()),
    ("start_guard_static_check.py", ()),
    ("verify_board_flash_package_selftest.py", ()),
)


def output_tail(text: str, lines: int = 20) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the active UNO Q + Nucleo release checks without Blue Pill dependencies."
    )
    parser.add_argument("--list", action="store_true", help="List checks without running them")
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    if args.list:
        for script, script_args in CHECKS:
            print(" ".join((script, *script_args)))
        return 0

    started = time.time()
    results: list[dict] = []
    for script, script_args in CHECKS:
        path = ROOT / "tools" / script
        command = [sys.executable, str(path), *script_args]
        run_started = time.time()
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        result = {
            "check": script,
            "pass": completed.returncode == 0,
            "returncode": completed.returncode,
            "duration_s": round(time.time() - run_started, 3),
            "stdout_tail": output_tail(completed.stdout),
            "stderr_tail": output_tail(completed.stderr),
        }
        results.append(result)
        print(f"{'PASS' if result['pass'] else 'FAIL'} {script} ({result['duration_s']:.3f}s)")
        if not result["pass"] and args.stop_on_failure:
            break

    report = {
        "tool": "nucleo_release_preflight",
        "profile": "active-nucleo-only",
        "pass": len(results) == len(CHECKS) and all(item["pass"] for item in results),
        "duration_s": round(time.time() - started, 3),
        "checks": results,
        "legacy_bluepill_executed": False,
        "legacy_bluepill_sources_read": False,
    }
    if args.json_output:
        target = args.json_output if args.json_output.is_absolute() else ROOT / args.json_output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uart_loopback_preflight as pre


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


def add_case(cases: list[CaseResult], name: str, ok: bool, detail: str = "", evidence: Any = None) -> None:
    cases.append(CaseResult(name=name, ok=bool(ok), detail=detail, evidence=evidence))


def args_for(tmp: Path, **overrides: Any) -> Any:
    args = pre.build_parser().parse_args(["--repo", str(tmp), "--out-root", "exports", *overrides.pop("extra", [])])
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def run_cases() -> list[CaseResult]:
    cases: list[CaseResult] = []
    parsed = pre.parse_json_stdout("noise\n{\"pass\": true, \"summary\": \"x\"}\n")
    add_case(cases, "parse_json_stdout_reads_last_json_line", parsed == {"pass": True, "summary": "x"}, evidence=parsed)

    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        dry = pre.run_preflight(args_for(tmp, dry_run=True, port="COM9", bauds="115200"))
        add_case(
            cases,
            "dry_run_does_not_execute_and_writes_plan",
            dry.get("pass") is True
            and dry.get("reason") == "dry_run_only_no_commands_executed"
            and "bluepill_uart_diagnose.py" in " ".join(dry["command_plan"]["loopback"]),
            evidence=dry,
        )

        missing = pre.run_preflight(args_for(tmp, port="COM3"))
        add_case(
            cases,
            "confirm_loopback_wired_is_required",
            missing.get("blocked") is True and missing.get("pass") is False and "confirm-loopback-wired" in str(missing.get("reason")),
            evidence=missing,
        )

        calls: list[list[str]] = []

        def ok_runner(cmd: list[str], cwd: Path, timeout_s: float) -> dict[str, Any]:
            calls.append(cmd)
            joined = " ".join(cmd)
            if "bluepill_uart_diagnose.py" in joined:
                payload = {"pass": True, "loopback_pass": True, "summary": "loopback/summary.json"}
            else:
                payload = {"pass": True}
            return {"cmd": cmd, "cwd": str(cwd), "returncode": 0, "ok": True, "json": payload}

        ok = pre.run_preflight(args_for(tmp, confirm_loopback_wired=True), runner=ok_runner)
        joined_calls = [" ".join(cmd) for cmd in calls]
        add_case(
            cases,
            "confirmed_preflight_runs_stop_loopback_start_in_order",
            ok.get("pass") is True
            and ok.get("loopback_pass") is True
            and ok.get("hmi_restored") is True
            and ["pc_direct_hmi_service.py stop" in joined_calls[0], "bluepill_uart_diagnose.py" in joined_calls[1], "--confirm-loopback-wired" in joined_calls[1], "pc_direct_hmi_service.py start" in joined_calls[2]] == [True, True, True, True],
            evidence={"summary": ok, "calls": joined_calls},
        )

        fail_calls: list[list[str]] = []

        def fail_runner(cmd: list[str], cwd: Path, timeout_s: float) -> dict[str, Any]:
            fail_calls.append(cmd)
            joined = " ".join(cmd)
            if "bluepill_uart_diagnose.py" in joined:
                payload = {"pass": False, "loopback_pass": False, "summary": "loopback/fail.json"}
                return {"cmd": cmd, "cwd": str(cwd), "returncode": 1, "ok": False, "json": payload}
            return {"cmd": cmd, "cwd": str(cwd), "returncode": 0, "ok": True, "json": {"pass": True}}

        failed = pre.run_preflight(args_for(tmp, confirm_loopback_wired=True), runner=fail_runner)
        fail_joined = [" ".join(cmd) for cmd in fail_calls]
        add_case(
            cases,
            "loopback_failure_still_restarts_hmi",
            failed.get("pass") is False
            and failed.get("next_action") == "fix_usb_uart_loopback_or_isolator_before_reconnecting_stm32"
            and len(fail_calls) == 3
            and "pc_direct_hmi_service.py start" in fail_joined[-1],
            evidence={"summary": failed, "calls": fail_joined},
        )

        stop_fail_calls: list[list[str]] = []

        def stop_fail_runner(cmd: list[str], cwd: Path, timeout_s: float) -> dict[str, Any]:
            stop_fail_calls.append(cmd)
            joined = " ".join(cmd)
            if "pc_direct_hmi_service.py" in joined and " stop " in f" {joined} ":
                return {"cmd": cmd, "cwd": str(cwd), "returncode": 1, "ok": False, "json": {"pass": False, "action": "stop"}}
            return {"cmd": cmd, "cwd": str(cwd), "returncode": 0, "ok": True, "json": {"pass": True}}

        stop_failed = pre.run_preflight(args_for(tmp, confirm_loopback_wired=True), runner=stop_fail_runner)
        stop_fail_joined = [" ".join(cmd) for cmd in stop_fail_calls]
        add_case(
            cases,
            "hmi_stop_failure_blocks_loopback",
            stop_failed.get("blocked") is True
            and stop_failed.get("pass") is False
            and stop_failed.get("next_action") == "stop_or_close_pc_direct_hmi_before_uart_loopback"
            and len(stop_fail_calls) == 1
            and "bluepill_uart_diagnose.py" not in " ".join(stop_fail_joined),
            evidence={"summary": stop_failed, "calls": stop_fail_joined},
        )

        no_restart_calls: list[list[str]] = []

        def no_restart_runner(cmd: list[str], cwd: Path, timeout_s: float) -> dict[str, Any]:
            no_restart_calls.append(cmd)
            joined = " ".join(cmd)
            payload = {"pass": True, "loopback_pass": True, "summary": "loopback/summary.json"} if "bluepill_uart_diagnose.py" in joined else {"pass": True}
            return {"cmd": cmd, "cwd": str(cwd), "returncode": 0, "ok": True, "json": payload}

        no_restart = pre.run_preflight(args_for(tmp, confirm_loopback_wired=True, no_restart_hmi=True), runner=no_restart_runner)
        add_case(
            cases,
            "no_restart_hmi_skips_start_step",
            no_restart.get("pass") is True and len(no_restart_calls) == 2 and all("start" not in " ".join(cmd) for cmd in no_restart_calls),
            evidence={"summary": no_restart, "calls": [" ".join(cmd) for cmd in no_restart_calls]},
        )

    return cases


def main() -> int:
    cases = run_cases()
    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "uart_loopback_preflight_selftest",
        "pass": len(failed) == 0,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    raise SystemExit(main())

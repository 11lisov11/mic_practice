#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    expected: Any = None
    actual: Any = None


def add_case(results: list[CaseResult], name: str, ok: bool, detail: str = "", expected: Any = None, actual: Any = None) -> None:
    results.append(CaseResult(name=name, ok=bool(ok), detail=detail, expected=expected, actual=actual))


def write_script(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def fake_repo(
    root: Path,
    *,
    check_fails: bool = False,
    malformed_bench_payload: bool = False,
    mismatched_bench_failed_checks: bool = False,
    stale_bench_first: bool = False,
) -> None:
    tools = root / "tools"
    if malformed_bench_payload:
        bench_script = """
import json
print(json.dumps({"unexpected": True}))
raise SystemExit(1)
""".lstrip()
    else:
        stale_literal = "True" if stale_bench_first else "False"
        failed_checks = ["a", "b", "c", "d"] if mismatched_bench_failed_checks else ["a", "b", "c", "d", "e"]
        bench_script = f"""
import json
from pathlib import Path
state = Path(".bench_gate_count")
count = int(state.read_text(encoding="utf-8")) if state.exists() else 0
state.write_text(str(count + 1), encoding="utf-8")
actions = ["run_runtime_static_preflight", "run_uart_loopback"]
if {stale_literal} and count == 0:
    actions = ["run_full_build_only_preflight", *actions]
print(json.dumps({{"ready_for_active_pwm": False, "failed": 5, "warnings": 2, "failed_checks": {failed_checks!r}, "warning_checks": ["w1", "w2"], "summary": "bench/summary.json", "next_actions": actions}}))
raise SystemExit(1)
""".lstrip()
    write_script(tools / "bench_gate_report.py", bench_script)
    write_script(
        tools / "full_system_preflight.py",
        """
print("SUMMARY: build/summary.json")
print("BUILD_ONLY_PASS=True")
raise SystemExit(0)
""".lstrip(),
    )
    write_script(
        tools / "research_readiness_check.py",
        """
import json
print(json.dumps({"ready": False, "profile": "bringup", "failed": 5, "warnings": 4, "summary": "readiness/summary.json"}))
raise SystemExit(4)
""".lstrip(),
    )
    check_rc = 1 if check_fails else 0
    check_pass = "False" if check_fails else "True"
    write_script(
        tools / "current_bench_status.py",
        f"""
import json
import sys
from pathlib import Path
out = "CURRENT_BENCH_STATUS_RU.md"
for idx, item in enumerate(sys.argv[:-1]):
    if item == "--out":
        out = sys.argv[idx + 1]
payload = {{"ready_for_active_pwm": False, "bench_summary": "bench/summary.json", "readiness_summary": "readiness/summary.json", "build_only_summary": "build/summary.json", "next_actions": ["run_runtime_static_preflight", "run_uart_loopback"], "out": str(Path(out).resolve())}}
if "--check" in sys.argv:
    payload["check_pass"] = {check_pass}
    payload["error"] = "" if payload["check_pass"] else "stale"
    print(json.dumps(payload))
    raise SystemExit({check_rc})
Path(out).write_text("status", encoding="utf-8")
print(json.dumps(payload))
raise SystemExit(0)
""".lstrip(),
    )


def run_refresh(repo: Path, *extra: str) -> tuple[int, dict[str, Any], str]:
    script = Path(__file__).resolve().parent / "refresh_bench_status.py"
    proc = subprocess.run(
        [sys.executable, "-u", str(script), "--repo", str(repo), "--timeout-step", "20", *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60.0,
    )
    try:
        payload = json.loads((proc.stdout or "").splitlines()[-1])
    except Exception:
        payload = {}
    return proc.returncode, payload, (proc.stdout or "") + (proc.stderr or "")


def run_red_gate_refresh_succeeds_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="refresh_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        fake_repo(repo)
        rc, payload, text = run_refresh(repo)
        ok = (
            rc == 0
            and payload.get("pass") is True
            and payload.get("ready_for_active_pwm") is False
            and payload.get("current_status_check_pass") is True
            and payload.get("next_actions") == ["run_runtime_static_preflight", "run_uart_loopback"]
            and (repo / "CURRENT_BENCH_STATUS_RU.md").exists()
        )
        add_case(
            results,
            "red_gate_refresh_succeeds_without_active_pwm",
            ok,
            detail="" if ok else text,
            expected={"rc": 0, "pass": True, "ready": False},
            actual={"rc": rc, "pass": payload.get("pass"), "ready": payload.get("ready_for_active_pwm")},
        )


def run_fail_if_not_ready_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="refresh_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        fake_repo(repo)
        rc, payload, text = run_refresh(repo, "--fail-if-not-ready")
        ok = rc == 1 and payload.get("pass") is True and payload.get("ready_for_active_pwm") is False
        add_case(
            results,
            "fail_if_not_ready_returns_one",
            ok,
            detail="" if ok else text,
            expected={"rc": 1, "pass": True, "ready": False},
            actual={"rc": rc, "pass": payload.get("pass"), "ready": payload.get("ready_for_active_pwm")},
        )


def run_check_failure_blocks_refresh_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="refresh_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        fake_repo(repo, check_fails=True)
        rc, payload, text = run_refresh(repo)
        steps = payload.get("steps", []) if isinstance(payload.get("steps"), list) else []
        check_step = next((step for step in steps if isinstance(step, dict) and step.get("name") == "current_bench_status_check"), {})
        ok = rc == 2 and payload.get("pass") is False and check_step.get("ok") is False
        add_case(
            results,
            "check_failure_blocks_refresh",
            ok,
            detail="" if ok else text,
            expected={"rc": 2, "pass": False, "check_ok": False},
            actual={"rc": rc, "pass": payload.get("pass"), "check_ok": check_step.get("ok")},
        )


def run_malformed_payload_blocks_refresh_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="refresh_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        fake_repo(repo, malformed_bench_payload=True)
        rc, payload, text = run_refresh(repo)
        steps = payload.get("steps", []) if isinstance(payload.get("steps"), list) else []
        bench_step = next((step for step in steps if isinstance(step, dict) and step.get("name") == "bench_gate_report"), {})
        ok = rc == 2 and payload.get("pass") is False and bench_step.get("schema_ok") is False
        add_case(
            results,
            "malformed_payload_blocks_refresh",
            ok,
            detail="" if ok else text,
            expected={"rc": 2, "pass": False, "schema_ok": False},
            actual={"rc": rc, "pass": payload.get("pass"), "schema_ok": bench_step.get("schema_ok")},
        )


def run_mismatched_bench_failed_checks_blocks_refresh_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="refresh_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        fake_repo(repo, mismatched_bench_failed_checks=True)
        rc, payload, text = run_refresh(repo)
        steps = payload.get("steps", []) if isinstance(payload.get("steps"), list) else []
        bench_step = next((step for step in steps if isinstance(step, dict) and step.get("name") == "bench_gate_report"), {})
        ok = (
            rc == 2
            and payload.get("pass") is False
            and bench_step.get("schema_ok") is False
            and "failed count does not match failed_checks" in str(bench_step.get("schema_detail", ""))
        )
        add_case(
            results,
            "mismatched_bench_failed_checks_blocks_refresh",
            ok,
            detail="" if ok else text,
            expected={"rc": 2, "pass": False, "schema_ok": False, "schema_detail": "failed count does not match failed_checks"},
            actual={
                "rc": rc,
                "pass": payload.get("pass"),
                "schema_ok": bench_step.get("schema_ok"),
                "schema_detail": bench_step.get("schema_detail"),
            },
        )


def run_build_if_stale_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="refresh_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        fake_repo(repo, stale_bench_first=True)
        rc, payload, text = run_refresh(repo, "--build-if-stale", "--build-timeout", "20")
        steps = payload.get("steps", []) if isinstance(payload.get("steps"), list) else []
        names = [step.get("name") for step in steps if isinstance(step, dict)]
        ok = (
            rc == 0
            and payload.get("pass") is True
            and payload.get("build_ran") is True
            and "full_system_preflight_build_only" in names
            and "bench_gate_report_after_build" in names
            and payload.get("next_actions") == ["run_runtime_static_preflight", "run_uart_loopback"]
        )
        add_case(
            results,
            "build_if_stale_runs_build_only_and_refreshes_gate",
            ok,
            detail="" if ok else text,
            expected={"rc": 0, "pass": True, "build_ran": True, "after_build_gate": True},
            actual={
                "rc": rc,
                "pass": payload.get("pass"),
                "build_ran": payload.get("build_ran"),
                "steps": names,
                "next_actions": payload.get("next_actions"),
            },
        )


def main() -> int:
    results: list[CaseResult] = []
    run_red_gate_refresh_succeeds_case(results)
    run_fail_if_not_ready_case(results)
    run_check_failure_blocks_refresh_case(results)
    run_malformed_payload_blocks_refresh_case(results)
    run_mismatched_bench_failed_checks_blocks_refresh_case(results)
    run_build_if_stale_case(results)
    failed = [r for r in results if not r.ok]
    summary = {
        "tool": "refresh_bench_status_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [r.__dict__ for r in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import active_pwm_guard as guard


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: Any
    actual: Any
    detail: str = ""


def run_parse_case(name: str, stdout: str, returncode: int, expected: dict[str, Any]) -> CaseResult:
    try:
        result = guard.parse_bench_gate_stdout(stdout, returncode)
        actual = {
            "ok": result.ok,
            "ready": result.ready,
            "summary": result.summary,
            "next_actions": result.next_actions,
        }
        ok = all(actual.get(k) == v for k, v in expected.items())
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "parse mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual={}, detail=f"{type(exc).__name__}: {exc}")


def run_legacy_bypass_disabled_case() -> CaseResult:
    expected = False
    old = os.environ.get("UNOQ_ALLOW_UNGATED_START")
    old_ack = os.environ.get("UNOQ_ALLOW_UNGATED_START_ACK")
    try:
        os.environ["UNOQ_ALLOW_UNGATED_START"] = "1"
        os.environ["UNOQ_ALLOW_UNGATED_START_ACK"] = guard.UNGATED_START_ACK
        called = {"value": False}

        def runner() -> guard.BenchGateResult:
            called["value"] = True
            return guard.BenchGateResult(ok=True, ready=True)

        guard.reset_cache()
        logs: list[str] = []
        actual = guard.start_allowed_by_bench_gate(logs.append, runner=runner)
        ok = actual is False and called["value"] is False and any("bypass is disabled" in msg for msg in logs)
        return CaseResult(
            name="legacy_two_step_bypass_is_disabled",
            ok=ok,
            expected=expected,
            actual={"allowed": actual, "called": called["value"], "logs": logs},
        )
    finally:
        if old is None:
            os.environ.pop("UNOQ_ALLOW_UNGATED_START", None)
        else:
            os.environ["UNOQ_ALLOW_UNGATED_START"] = old
        if old_ack is None:
            os.environ.pop("UNOQ_ALLOW_UNGATED_START_ACK", None)
        else:
            os.environ["UNOQ_ALLOW_UNGATED_START_ACK"] = old_ack
        guard.reset_cache()


def run_unarmed_bypass_case() -> CaseResult:
    expected = False
    old = os.environ.get("UNOQ_ALLOW_UNGATED_START")
    old_ack = os.environ.get("UNOQ_ALLOW_UNGATED_START_ACK")
    try:
        os.environ["UNOQ_ALLOW_UNGATED_START"] = "1"
        os.environ.pop("UNOQ_ALLOW_UNGATED_START_ACK", None)
        called = {"value": False}

        def runner() -> guard.BenchGateResult:
            called["value"] = True
            return guard.BenchGateResult(ok=True, ready=True)

        guard.reset_cache()
        logs: list[str] = []
        actual = guard.start_allowed_by_bench_gate(logs.append, runner=runner)
        ok = actual is False and called["value"] is False and any("legacy override is disabled" in msg for msg in logs)
        return CaseResult(name="single_env_bypass_is_disabled", ok=ok, expected=expected, actual={"allowed": actual, "called": called["value"], "logs": logs})
    finally:
        if old is None:
            os.environ.pop("UNOQ_ALLOW_UNGATED_START", None)
        else:
            os.environ["UNOQ_ALLOW_UNGATED_START"] = old
        if old_ack is None:
            os.environ.pop("UNOQ_ALLOW_UNGATED_START_ACK", None)
        else:
            os.environ["UNOQ_ALLOW_UNGATED_START_ACK"] = old_ack
        guard.reset_cache()


def run_block_case() -> CaseResult:
    expected = False
    old = os.environ.get("UNOQ_ALLOW_UNGATED_START")
    old_ack = os.environ.get("UNOQ_ALLOW_UNGATED_START_ACK")
    try:
        os.environ.pop("UNOQ_ALLOW_UNGATED_START", None)
        os.environ.pop("UNOQ_ALLOW_UNGATED_START_ACK", None)
        guard.reset_cache()
        logs: list[str] = []

        def runner() -> guard.BenchGateResult:
            return guard.BenchGateResult(
                ok=False,
                ready=False,
                summary="summary.json",
                next_actions=["run_runtime_static_preflight", "run_uart_loopback"],
                detail="not ready",
            )

        actual = guard.start_allowed_by_bench_gate(logs.append, runner=runner)
        ok = actual is False and any("run_runtime_static_preflight" in msg and "run_uart_loopback" in msg for msg in logs)
        return CaseResult(name="not_ready_gate_blocks_start", ok=ok, expected=expected, actual={"allowed": actual, "logs": logs})
    finally:
        if old is not None:
            os.environ["UNOQ_ALLOW_UNGATED_START"] = old
        if old_ack is not None:
            os.environ["UNOQ_ALLOW_UNGATED_START_ACK"] = old_ack
        guard.reset_cache()


def run_bench_gate_url_case() -> CaseResult:
    expected = {
        "calls": [["--url", "http://127.0.0.1:18080"]],
        "missing_url_ok": False,
        "missing_url_detail": "live bench-gate URL is required",
    }
    original_run = guard.subprocess.run
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *args, **kwargs):
        calls.append(list(cmd))
        stdout = json.dumps({"ready_for_active_pwm": False, "summary": "fake.json", "next_actions": []})
        return SimpleNamespace(stdout=stdout, stderr="", returncode=1)

    try:
        guard.subprocess.run = fake_run
        guard.run_bench_gate(url="http://127.0.0.1:18080")
        missing = guard.run_bench_gate()
        actual = {
            "calls": [call[-2:] for call in calls],
            "missing_url_ok": missing.ok,
            "missing_url_detail": missing.detail,
        }
        ok = (
            actual["calls"] == expected["calls"]
            and missing.ok is False
            and expected["missing_url_detail"] in missing.detail
            and all("--offline" not in call for call in calls)
        )
        return CaseResult(name="run_bench_gate_requires_live_url", ok=ok, expected=expected, actual=actual, detail="" if ok else str(calls))
    except Exception as exc:
        return CaseResult(name="run_bench_gate_requires_live_url", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")
    finally:
        guard.subprocess.run = original_run


def run_start_without_url_blocks_case() -> CaseResult:
    expected = {"allowed": False, "subprocess_calls": 0, "has_live_url_error": True}
    original_run = guard.subprocess.run
    calls: list[list[str]] = []
    old_url = os.environ.get("UNOQ_BENCH_GATE_URL")
    try:
        os.environ.pop("UNOQ_BENCH_GATE_URL", None)
        guard.reset_cache()

        def fake_run(cmd: list[str], *args, **kwargs):
            calls.append(list(cmd))
            stdout = json.dumps({"ready_for_active_pwm": True, "summary": "unexpected.json", "next_actions": []})
            return SimpleNamespace(stdout=stdout, stderr="", returncode=0)

        guard.subprocess.run = fake_run
        logs: list[str] = []
        allowed = guard.start_allowed_by_bench_gate(logs.append)
        actual = {
            "allowed": allowed,
            "subprocess_calls": len(calls),
            "logs": logs,
            "has_live_url_error": any("live bench-gate URL is required" in msg for msg in logs),
        }
        ok = (
            allowed is False
            and not calls
            and actual["has_live_url_error"] is True
        )
        return CaseResult(name="start_without_live_url_blocks_before_subprocess", ok=ok, expected=expected, actual=actual)
    except Exception as exc:
        return CaseResult(name="start_without_live_url_blocks_before_subprocess", ok=False, expected=expected, actual={}, detail=f"{type(exc).__name__}: {exc}")
    finally:
        guard.subprocess.run = original_run
        if old_url is None:
            os.environ.pop("UNOQ_BENCH_GATE_URL", None)
        else:
            os.environ["UNOQ_BENCH_GATE_URL"] = old_url
        guard.reset_cache()


def run_ready_gate_not_cached_case() -> CaseResult:
    expected = {"first": True, "second": False, "calls": 2}
    old = os.environ.get("UNOQ_BENCH_GATE_CACHE_S")
    try:
        os.environ["UNOQ_BENCH_GATE_CACHE_S"] = "60.0"
        guard.reset_cache()
        calls = {"count": 0}
        logs: list[str] = []

        def runner() -> guard.BenchGateResult:
            calls["count"] += 1
            if calls["count"] == 1:
                return guard.BenchGateResult(ok=True, ready=True, summary="green.json", next_actions=[])
            return guard.BenchGateResult(
                ok=False,
                ready=False,
                summary="red.json",
                next_actions=["restore_hmi_safe_status"],
                detail="became unsafe",
            )

        first = guard.start_allowed_by_bench_gate(logs.append, runner=runner)
        second = guard.start_allowed_by_bench_gate(logs.append, runner=runner)
        actual = {"first": first, "second": second, "calls": calls["count"], "logs": logs}
        ok = (
            first is True
            and second is False
            and calls["count"] == 2
            and any("restore_hmi_safe_status" in msg for msg in logs)
        )
        return CaseResult(name="ready_gate_result_is_not_cached", ok=ok, expected=expected, actual=actual)
    except Exception as exc:
        return CaseResult(name="ready_gate_result_is_not_cached", ok=False, expected=expected, actual={}, detail=f"{type(exc).__name__}: {exc}")
    finally:
        if old is None:
            os.environ.pop("UNOQ_BENCH_GATE_CACHE_S", None)
        else:
            os.environ["UNOQ_BENCH_GATE_CACHE_S"] = old
        guard.reset_cache()


def cases() -> list[CaseResult]:
    return [
        run_parse_case(
            "parse_ready_pass",
            json.dumps({"ready_for_active_pwm": True, "summary": "ok.json", "next_actions": []}),
            0,
            {"ok": True, "ready": True, "summary": "ok.json", "next_actions": []},
        ),
        run_parse_case(
            "parse_not_ready_actions",
            json.dumps({"ready_for_active_pwm": False, "summary": "fail.json", "next_actions": ["run_uart_loopback"]}),
            1,
            {"ok": False, "ready": False, "summary": "fail.json", "next_actions": ["run_uart_loopback"]},
        ),
        run_parse_case(
            "parse_missing_json_fails_closed",
            "not json",
            1,
            {"ok": False, "ready": False},
        ),
        run_legacy_bypass_disabled_case(),
        run_unarmed_bypass_case(),
        run_block_case(),
        run_bench_gate_url_case(),
        run_start_without_url_blocks_case(),
        run_ready_gate_not_cached_case(),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "active_pwm_guard_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass
from typing import Any


def install_import_stubs() -> None:
    if "saleae" in sys.modules:
        return
    saleae = types.ModuleType("saleae")
    automation = types.ModuleType("saleae.automation")

    class _DummyManager:
        pass

    automation.Manager = _DummyManager
    saleae.automation = automation
    sys.modules["saleae"] = saleae
    sys.modules["saleae.automation"] = automation


install_import_stubs()

import saleae_highlevel_probe as probe


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def read(self) -> bytes:
        return self.payload


def add_case(results: list[CaseResult], name: str, ok: bool, detail: str = "", evidence: Any = None) -> None:
    results.append(CaseResult(name=name, ok=bool(ok), detail=detail, evidence=evidence))


def case_command_detection(results: list[CaseResult]) -> None:
    checks = {
        "START": True,
        " start ": True,
        "Start": True,
        "RESTART": False,
        "START_PWM": False,
        "START NOW": False,
        "": False,
    }
    actual = {cmd: probe.command_requests_start(cmd) for cmd in checks}
    add_case(results, "command_requests_start_exact_only", actual == checks, evidence=actual)


def case_required_pair_channels(results: list[CaseResult]) -> None:
    try:
        actual = sorted(probe.required_pair_channels("0:1,2:3,4:5"))
        expected = [0, 1, 2, 3, 4, 5]
        add_case(results, "required_pair_channels_for_default_pwm_pairs", actual == expected, evidence=actual)
    except Exception as exc:
        add_case(results, "required_pair_channels_for_default_pwm_pairs", False, f"{type(exc).__name__}: {exc}")


def case_capture_rate_candidates(results: list[CaseResult]) -> None:
    actual = {
        "auto_24m": probe.capture_rate_candidates(24_000_000, True),
        "auto_5m": probe.capture_rate_candidates(5_000_000, True),
        "fixed": probe.capture_rate_candidates(7_000_000, False),
    }
    ok = (
        actual["auto_24m"][:3] == [24_000_000, 12_000_000, 6_000_000]
        and actual["auto_5m"][:3] == [5_000_000, 3_000_000, 2_000_000]
        and actual["fixed"] == [7_000_000]
        and len(actual["auto_24m"]) == len(set(actual["auto_24m"]))
    )
    add_case(results, "capture_rate_candidates_descend_without_duplicates", ok, evidence=actual)


def case_pwm_static_checks_all_low_safe(results: list[CaseResult]) -> None:
    levels = {str(ch): {"initial": 0, "final": 0} for ch in range(7)}
    edges = {str(ch): 0 for ch in range(7)}
    actual = probe.summarize_pwm_static_checks(list(range(7)), edges, levels)
    ok = (
        actual.get("pwm_static_safe_pass") is True
        and actual.get("pattern") == "all_pwm_low_safe"
        and actual.get("pwm_lines_low") is True
        and actual.get("em_stop_shutdown_asserted") is True
        and actual.get("high_pwm_channels") == []
    )
    add_case(results, "pwm_static_checks_all_low_safe", ok, evidence=actual)


def case_pwm_static_checks_low_side_high_fails(results: list[CaseResult]) -> None:
    levels = {
        str(ch): {"initial": level, "final": level}
        for ch, level in enumerate([0, 1, 0, 1, 0, 1, 0])
    }
    edges = {str(ch): 0 for ch in range(7)}
    actual = probe.summarize_pwm_static_checks(list(range(7)), edges, levels)
    expected_high = ["CH1/PB13/PWM-1L", "CH3/PB14/PWM-2L", "CH5/PB15/PWM-3L"]
    ok = (
        actual.get("pwm_static_safe_pass") is False
        and actual.get("pattern") == "low_side_static_high"
        and actual.get("pwm_lines_low") is False
        and actual.get("em_stop_shutdown_asserted") is True
        and actual.get("high_pwm_channels") == expected_high
    )
    add_case(results, "pwm_static_checks_low_side_high_fails", ok, evidence=actual)


def case_start_blocked_before_http(results: list[CaseResult]) -> None:
    old_guard = probe.start_allowed_by_bench_gate
    old_urlopen = probe.urllib.request.urlopen
    guard_calls: list[dict[str, Any]] = []
    http_calls: list[Any] = []
    logs: list[str] = []

    def fake_guard(log_fn, url: str | None = None) -> bool:
        guard_calls.append({"url": url})
        log_fn("guard called")
        return False

    def fake_urlopen(req, timeout: float = 0.0):
        http_calls.append({"req": req, "timeout": timeout})
        raise AssertionError("HTTP must not be called when START is blocked")

    probe.start_allowed_by_bench_gate = fake_guard
    probe.urllib.request.urlopen = fake_urlopen
    try:
        try:
            probe.post_cmd("http://bench.local:18080", " START ", timeout_s=0.25, log_fn=logs.append)
            add_case(results, "start_blocked_before_http", False, "post_cmd returned instead of raising")
        except RuntimeError as exc:
            ok = (
                "START blocked by bench gate" in str(exc)
                and guard_calls == [{"url": "http://bench.local:18080"}]
                and http_calls == []
                and logs == ["guard called"]
            )
            add_case(
                results,
                "start_blocked_before_http",
                ok,
                evidence={"guard_calls": guard_calls, "http_calls": len(http_calls), "logs": logs, "error": str(exc)},
            )
    finally:
        probe.start_allowed_by_bench_gate = old_guard
        probe.urllib.request.urlopen = old_urlopen


def case_non_start_uses_http_without_guard(results: list[CaseResult]) -> None:
    old_guard = probe.start_allowed_by_bench_gate
    old_urlopen = probe.urllib.request.urlopen
    guard_calls: list[Any] = []
    http_calls: list[dict[str, Any]] = []

    def fake_guard(log_fn, url: str | None = None) -> bool:
        guard_calls.append({"url": url})
        raise AssertionError("guard must not run for non-START commands")

    def fake_urlopen(req, timeout: float = 0.0):
        http_calls.append(
            {
                "url": req.full_url,
                "data": req.data.decode("utf-8"),
                "timeout": timeout,
                "content_type": req.headers.get("Content-type") or req.headers.get("Content-Type"),
            }
        )
        return FakeResponse(b'{"ok":true,"cmd":"SAFE"}')

    probe.start_allowed_by_bench_gate = fake_guard
    probe.urllib.request.urlopen = fake_urlopen
    try:
        response = probe.post_cmd("http://bench.local:18080/", "SAFE", timeout_s=1.25, log_fn=lambda _msg: None)
        ok = (
            response == '{"ok":true,"cmd":"SAFE"}'
            and guard_calls == []
            and len(http_calls) == 1
            and http_calls[0]["url"] == "http://bench.local:18080/api/cmd"
            and json.loads(http_calls[0]["data"]) == {"cmd": "SAFE"}
            and abs(http_calls[0]["timeout"] - 1.25) < 0.001
        )
        add_case(results, "non_start_uses_http_without_guard", ok, evidence={"http_calls": http_calls})
    except Exception as exc:
        add_case(results, "non_start_uses_http_without_guard", False, f"{type(exc).__name__}: {exc}")
    finally:
        probe.start_allowed_by_bench_gate = old_guard
        probe.urllib.request.urlopen = old_urlopen


def case_start_allowed_then_http(results: list[CaseResult]) -> None:
    old_guard = probe.start_allowed_by_bench_gate
    old_urlopen = probe.urllib.request.urlopen
    guard_calls: list[dict[str, Any]] = []
    http_calls: list[str] = []

    def fake_guard(log_fn, url: str | None = None) -> bool:
        guard_calls.append({"url": url})
        return True

    def fake_urlopen(req, timeout: float = 0.0):
        http_calls.append(req.full_url)
        return FakeResponse(b'{"ok":true,"cmd":"START"}')

    probe.start_allowed_by_bench_gate = fake_guard
    probe.urllib.request.urlopen = fake_urlopen
    try:
        response = probe.post_cmd("http://bench.local:18080", "START", timeout_s=0.5, log_fn=lambda _msg: None)
        ok = (
            response == '{"ok":true,"cmd":"START"}'
            and guard_calls == [{"url": "http://bench.local:18080"}]
            and http_calls == ["http://bench.local:18080/api/cmd"]
        )
        add_case(results, "start_allowed_then_http", ok, evidence={"guard_calls": guard_calls, "http_calls": http_calls})
    except Exception as exc:
        add_case(results, "start_allowed_then_http", False, f"{type(exc).__name__}: {exc}")
    finally:
        probe.start_allowed_by_bench_gate = old_guard
        probe.urllib.request.urlopen = old_urlopen


def case_require_static_safe_exit_codes(results: list[CaseResult]) -> None:
    unsafe = {
        "pwm_static_safe_pass": False,
        "pwm_static_checks": {"pattern": "low_side_static_high"},
    }
    safe = {
        "pwm_static_safe_pass": True,
        "pwm_static_checks": {"pattern": "all_pwm_low_safe"},
    }
    actual = {
        "unsafe_diagnostic": probe.exit_code_for_summary(unsafe, 0, require_static_safe=False),
        "unsafe_required": probe.exit_code_for_summary(unsafe, 0, require_static_safe=True),
        "safe_required": probe.exit_code_for_summary(safe, 0, require_static_safe=True),
        "command_failure_precedence": probe.exit_code_for_summary(safe, 2, require_static_safe=True),
    }
    expected = {
        "unsafe_diagnostic": 0,
        "unsafe_required": 5,
        "safe_required": 0,
        "command_failure_precedence": 4,
    }
    add_case(results, "require_static_safe_exit_codes", actual == expected, evidence=actual)


def main() -> int:
    results: list[CaseResult] = []
    case_command_detection(results)
    case_required_pair_channels(results)
    case_capture_rate_candidates(results)
    case_pwm_static_checks_all_low_safe(results)
    case_pwm_static_checks_low_side_high_fails(results)
    case_start_blocked_before_http(results)
    case_non_start_uses_http_without_guard(results)
    case_start_allowed_then_http(results)
    case_require_static_safe_exit_codes(results)

    failed = [r for r in results if not r.ok]
    summary = {
        "tool": "saleae_highlevel_probe_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [r.__dict__ for r in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

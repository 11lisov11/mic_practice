#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import fan_preflight as fan


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: Any
    actual: Any
    detail: str = ""


def base_status(**overrides: Any) -> dict[str, Any]:
    st: dict[str, Any] = {
        "state": "SAFE",
        "pwm": 0,
        "estop": 0,
        "bp_fault": 0,
        "bp_bad_cnt": 0,
        "link": True,
        "bp_rsp_age_ms": 10,
        "bp_age_ms": 10,
        "vdc": 12.0,
        "bp_vdc": 12.0,
    }
    st.update(overrides)
    return st


def without_vbus(**overrides: Any) -> dict[str, Any]:
    st = base_status(**overrides)
    st.pop("vdc", None)
    st.pop("bp_vdc", None)
    return st


def run_safe_case(name: str, st: dict[str, Any] | None, expected_ok: bool, expected_reason_contains: str = "", *, allow_hv: bool = False) -> CaseResult:
    try:
        actual_ok, reason = fan.safe_low_voltage(st, max_vdc=60.0, allow_hv=allow_hv)
        ok = actual_ok == expected_ok and (not expected_reason_contains or expected_reason_contains in reason)
        return CaseResult(
            name=name,
            ok=ok,
            expected={"ok": expected_ok, "reason_contains": expected_reason_contains},
            actual={"ok": actual_ok, "reason": reason},
            detail="" if ok else "safe_low_voltage mismatch",
        )
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected_ok, actual={}, detail=f"{type(exc).__name__}: {exc}")


def run_cmd_case(duty: float, expected: str) -> CaseResult:
    try:
        actual = fan.fan_cmd_for_duty(duty)
        ok = actual == expected
        return CaseResult(name=f"fan_cmd_{duty}", ok=ok, expected=expected, actual=actual, detail="" if ok else "command mismatch")
    except Exception as exc:
        return CaseResult(name=f"fan_cmd_{duty}", ok=False, expected=expected, actual="", detail=f"{type(exc).__name__}: {exc}")


def cases() -> list[CaseResult]:
    return [
        run_cmd_case(0.0, "FAN OFF"),
        run_cmd_case(1.0, "FAN ON"),
        run_cmd_case(0.3, "FAN PWM 0.30"),
        run_safe_case("safe_low_voltage_ok", base_status(), True, "ok"),
        run_safe_case("missing_status_blocks", None, False, "status unavailable"),
        run_safe_case("active_pwm_blocks", base_status(pwm=1), False, "pwm=1"),
        run_safe_case("estop_blocks", base_status(estop=1), False, "estop=1"),
        run_safe_case("fault_blocks", base_status(bp_fault=6), False, "bp_fault=6"),
        run_safe_case("bad_counter_blocks", base_status(bp_bad_cnt=1), False, "bp_bad=1"),
        run_safe_case("legacy_bad_counter_blocks", base_status(bp_bad_cnt=0, bp_bad=1), False, "bp_bad=1"),
        run_safe_case("stale_link_blocks", base_status(bp_rsp_age_ms=999999, bp_age_ms=999999), False, "link"),
        run_safe_case("missing_vbus_blocks", without_vbus(), False, "Vbus telemetry"),
        run_safe_case("allow_hv_still_requires_vbus", without_vbus(), False, "Vbus telemetry", allow_hv=True),
        run_safe_case("high_vbus_blocks_without_hv", base_status(vdc=315.0, bp_vdc=315.0), False, "exceeds"),
        run_safe_case("high_vbus_allows_with_hv", base_status(vdc=315.0, bp_vdc=315.0), True, "ok", allow_hv=True),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "fan_preflight_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

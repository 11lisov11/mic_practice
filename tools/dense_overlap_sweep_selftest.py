#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import dense_overlap_sweep as sweep


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected_ok: bool
    actual_ok: bool
    reason: str
    expected_reason_contains: str = ""


def base_status(**overrides: Any) -> dict[str, Any]:
    st: dict[str, Any] = {
        "link": True,
        "bp_rsp_age_ms": 10,
        "bp_age_ms": 10,
        "pwm": 0,
        "estop": 0,
        "bp_fault": 0,
        "bp_bad": 0,
        "bp_vdc": 12.0,
        "vdc": 12.0,
    }
    st.update(overrides)
    return st


def run_case(
    name: str,
    st: dict[str, Any] | None,
    expected_ok: bool,
    expected_reason_contains: str = "",
    *,
    max_vdc: float = 60.0,
    allow_hv: bool = False,
) -> CaseResult:
    actual_ok, reason = sweep.low_voltage_start_precheck(st, max_vdc=max_vdc, allow_hv=allow_hv)
    ok = actual_ok == expected_ok and (not expected_reason_contains or expected_reason_contains in reason)
    return CaseResult(
        name=name,
        ok=ok,
        expected_ok=expected_ok,
        actual_ok=actual_ok,
        reason=reason,
        expected_reason_contains=expected_reason_contains,
    )


def run_bench_gate_case(
    name: str,
    guard_ok: bool,
    expected_ok: bool,
    expected_reason_contains: str,
) -> CaseResult:
    def fake_guard(log_fn, url: str | None = None) -> bool:
        if not guard_ok:
            log_fn(f"blocked by fake bench gate url={url}")
        return guard_ok

    actual_ok, reason = sweep.bench_gate_start_precheck("http://127.0.0.1:18080", guard_fn=fake_guard)
    ok = actual_ok == expected_ok and expected_reason_contains in reason
    return CaseResult(
        name=name,
        ok=ok,
        expected_ok=expected_ok,
        actual_ok=actual_ok,
        reason=reason,
        expected_reason_contains=expected_reason_contains,
    )


def cases() -> list[CaseResult]:
    os.environ["UNOQ_BP_BAD_BASELINE"] = "0"
    return [
        run_case("safe_low_voltage_allows_start", base_status(), True, "ok"),
        run_case("missing_status_blocks_start", None, False, "status unavailable"),
        run_case("stale_link_blocks_start", base_status(bp_rsp_age_ms=999999, bp_age_ms=999999), False, "link"),
        run_case("active_pwm_blocks_start", base_status(pwm=1), False, "PWM"),
        run_case("estop_blocks_start", base_status(estop=1), False, "ESTOP"),
        run_case("fault_blocks_start", base_status(bp_fault=3), False, "bp_fault=3"),
        run_case("bad_counter_blocks_start", base_status(bp_bad=1), False, "bp_bad=1"),
        run_case("legacy_bad_counter_blocks_start", base_status(bp_bad_cnt=0, bp_bad=1), False, "bp_bad=1"),
        run_case("unreadable_vbus_blocks_start", base_status(bp_vdc=-1.0, vdc=-1.0), False, "Vbus telemetry"),
        run_case("high_vbus_blocks_without_hv", base_status(bp_vdc=315.0, vdc=315.0), False, "exceeds low-voltage"),
        run_case("high_vbus_allows_with_hv", base_status(bp_vdc=315.0, vdc=315.0), True, "ok", allow_hv=True),
        run_case("allow_hv_still_requires_vbus", base_status(bp_vdc=-1.0, vdc=-1.0), False, "Vbus telemetry", allow_hv=True),
        run_bench_gate_case("bench_gate_allows_dense_start", True, True, "ok"),
        run_bench_gate_case("bench_gate_blocks_dense_start", False, False, "blocked by fake bench gate"),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "dense_overlap_sweep_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bpfoc_backend_preflight as bpfoc


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
        "bp_status": bpfoc.STATUS_LINK_OK,
        "bp_rsp_age_ms": 10,
        "bp_age_ms": 10,
        "vdc": 12.0,
        "bp_vdc": 12.0,
        "enc_ok": 1,
    }
    st.update(overrides)
    return st


def without_vbus(**overrides: Any) -> dict[str, Any]:
    st = base_status(**overrides)
    st.pop("vdc", None)
    st.pop("bp_vdc", None)
    return st


def run_safe_case(
    name: str,
    st: dict[str, Any],
    expected_ok: bool,
    expected_reason_contains: str = "",
    *,
    allow_hv: bool = False,
    require_encoder: bool = True,
) -> CaseResult:
    try:
        actual_ok, reason = bpfoc.status_safe_for_backend_test(
            st,
            max_vdc=60.0,
            allow_hv=allow_hv,
            require_encoder=require_encoder,
            max_bp_age_ms=1000.0,
        )
        ok = actual_ok == expected_ok and (not expected_reason_contains or expected_reason_contains in reason)
        return CaseResult(
            name=name,
            ok=ok,
            expected={"ok": expected_ok, "reason_contains": expected_reason_contains},
            actual={"ok": actual_ok, "reason": reason},
            detail="" if ok else "status_safe_for_backend_test mismatch",
        )
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected_ok, actual=None, detail=f"{type(exc).__name__}: {exc}")


def run_observed_case(name: str, st: dict[str, Any], expected: float | str) -> CaseResult:
    try:
        actual = bpfoc.observed_vdc(st)
        if expected == "nan":
            ok = math.isnan(actual)
        else:
            ok = abs(actual - float(expected)) < 1e-9
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "observed_vdc mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=None, detail=f"{type(exc).__name__}: {exc}")


def run_no_undefined_base_url_case() -> CaseResult:
    try:
        source = Path(bpfoc.__file__).read_text(encoding="utf-8")
        main_source = source.split("def main() -> int:", 1)[1]
        bad = "bench_gate_guard(result, base_url,"
        good = "bench_gate_guard(result, args.url,"
        ok = bad not in main_source and good in main_source
        return CaseResult(
            name="main_live_switch_guard_uses_args_url",
            ok=ok,
            expected={"absent": bad, "present": good},
            actual={"bad_present_in_main": bad in main_source, "good_present_in_main": good in main_source},
            detail="" if ok else "live switch bench gate would raise NameError",
        )
    except Exception as exc:
        return CaseResult(
            name="main_live_switch_guard_uses_args_url",
            ok=False,
            expected={"source": "readable"},
            actual=None,
            detail=f"{type(exc).__name__}: {exc}",
        )


def cases() -> list[CaseResult]:
    return [
        run_observed_case("observed_vdc_prefers_max_readable", base_status(vdc=12.0, bp_vdc=14.0), 14.0),
        run_observed_case("observed_vdc_missing_is_nan", without_vbus(), "nan"),
        run_safe_case("safe_backend_status_ok", base_status(), True, "ok"),
        run_safe_case("missing_vbus_blocks", without_vbus(), False, "Vbus telemetry"),
        run_safe_case("allow_hv_still_requires_vbus", without_vbus(), False, "Vbus telemetry", allow_hv=True),
        run_safe_case("high_vbus_blocks_without_hv", base_status(vdc=315.0, bp_vdc=315.0), False, "exceeds"),
        run_safe_case("high_vbus_allows_with_hv", base_status(vdc=315.0, bp_vdc=315.0), True, "ok", allow_hv=True),
        run_safe_case("legacy_bad_counter_blocks", base_status(bp_bad_cnt=0, bp_bad=1), False, "bp_bad=1"),
        run_safe_case("missing_encoder_blocks_by_default", base_status(enc_ok=0), False, "enc_ok"),
        run_safe_case("missing_encoder_can_be_allowed", base_status(enc_ok=0), True, "ok", require_encoder=False),
        run_safe_case("stale_bp_link_blocks", base_status(bp_rsp_age_ms=999999, bp_age_ms=999999), False, "reply age"),
        run_safe_case("bp_status_link_bit_blocks", base_status(bp_status=0), False, "link flag"),
        run_no_undefined_base_url_case(),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "bpfoc_backend_preflight_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

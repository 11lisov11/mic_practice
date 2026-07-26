#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import mic_ai_compare as mic


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: Any
    actual: Any
    detail: str = ""


def base_status(**overrides: Any) -> dict[str, Any]:
    st: dict[str, Any] = {
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


def run_vdc_case(name: str, st: dict[str, Any] | None, expected: float | str) -> CaseResult:
    try:
        actual = mic.status_vdc(st)
        if expected == "nan":
            ok = math.isnan(actual)
        else:
            ok = abs(actual - float(expected)) < 1e-9
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "status_vdc mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=None, detail=f"{type(exc).__name__}: {exc}")


def run_start_case(
    name: str,
    st: dict[str, Any] | None,
    expected_ok: bool,
    *,
    allow_hv: bool = False,
) -> CaseResult:
    old_get_status = mic.get_status
    old_allow_hv = mic.START_ALLOW_HV
    old_max_vdc = mic.START_MAX_VDC
    old_samples = mic.START_VDC_SAMPLES
    try:
        mic.get_status = lambda _base: st  # type: ignore[assignment]
        mic.START_ALLOW_HV = bool(allow_hv)
        mic.START_MAX_VDC = 60.0
        mic.START_VDC_SAMPLES = 1
        actual = mic.start_allowed_by_vdc("http://bench.local")
        ok = actual == expected_ok
        return CaseResult(
            name=name,
            ok=ok,
            expected=expected_ok,
            actual=actual,
            detail="" if ok else "start_allowed_by_vdc mismatch",
        )
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected_ok, actual=None, detail=f"{type(exc).__name__}: {exc}")
    finally:
        mic.get_status = old_get_status  # type: ignore[assignment]
        mic.START_ALLOW_HV = old_allow_hv
        mic.START_MAX_VDC = old_max_vdc
        mic.START_VDC_SAMPLES = old_samples


def run_bp_bad_case(name: str, st: dict[str, Any] | None, expected_ok: bool) -> CaseResult:
    try:
        actual = mic.bp_cmd_bad_ok(st)
        ok = actual == expected_ok
        return CaseResult(
            name=name,
            ok=ok,
            expected=expected_ok,
            actual=actual,
            detail="" if ok else "bp_cmd_bad_ok mismatch",
        )
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected_ok, actual=None, detail=f"{type(exc).__name__}: {exc}")


def cases() -> list[CaseResult]:
    return [
        run_vdc_case("status_vdc_prefers_max_readable", base_status(vdc=11.0, bp_vdc=14.0), 14.0),
        run_vdc_case("status_vdc_missing_is_nan", without_vbus(), "nan"),
        run_vdc_case("status_vdc_negative_is_nan", base_status(vdc=-1.0, bp_vdc=-1.0), "nan"),
        run_start_case("low_vbus_allows_start_vdc_guard", base_status(), True),
        run_start_case("missing_status_blocks_start_vdc_guard", None, False),
        run_start_case("missing_vbus_blocks_start_vdc_guard", without_vbus(), False),
        run_start_case("allow_hv_still_requires_vbus", without_vbus(), False, allow_hv=True),
        run_start_case("high_vbus_blocks_without_hv", base_status(vdc=315.0, bp_vdc=315.0), False),
        run_start_case("high_vbus_allows_with_hv", base_status(vdc=315.0, bp_vdc=315.0), True, allow_hv=True),
        run_bp_bad_case("bp_bad_counter_ok", base_status(bp_bad_cnt=0, bp_bad=0), True),
        run_bp_bad_case("legacy_bad_counter_blocks", base_status(bp_bad_cnt=0, bp_bad=1), False),
        run_bp_bad_case("missing_bad_counter_blocks", base_status(), False),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "mic_ai_compare_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

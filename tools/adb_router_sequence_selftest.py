#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import adb_router_sequence as seq


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: Any
    actual: Any
    detail: str = ""


def base_status(**overrides: Any) -> dict[str, Any]:
    st: dict[str, Any] = {
        "link": True,
        "state": "SAFE",
        "pwm": 0,
        "estop": 0,
        "bp_fault": 0,
        "bp_bad": 0,
        "bp_bad_cnt": 0,
        "bp_age_ms": 10,
        "bp_rsp_age_ms": 10,
        "bp_vbus_age_ms": 10,
        "bp_vbus_raw": 250,
        "bp_vdc": 12.0,
        "vdc": 12.0,
    }
    st.update(overrides)
    return st


def without_vbus(**overrides: Any) -> dict[str, Any]:
    st = base_status(**overrides)
    st.pop("bp_vdc", None)
    st.pop("vdc", None)
    return st


def run_precheck_case(
    name: str,
    st: dict[str, Any] | None,
    expected_ok: bool,
    expected_reason_contains: str = "",
    *,
    allow_hv: bool = False,
    skip_hv_min: bool = False,
) -> CaseResult:
    try:
        ok, reason = seq.enabling_status_precheck(
            st,
            max_vdc=60.0,
            allow_hv=allow_hv,
            hv_vdc_min=100.0,
            skip_hv_vdc_min_check=skip_hv_min,
        )
        passed = ok == expected_ok and (not expected_reason_contains or expected_reason_contains in reason)
        return CaseResult(
            name=name,
            ok=passed,
            expected={"ok": expected_ok, "reason_contains": expected_reason_contains},
            actual={"ok": ok, "reason": reason},
            detail="" if passed else "enabling_status_precheck mismatch",
        )
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected_ok, actual=None, detail=f"{type(exc).__name__}: {exc}")


def run_vdc_case(name: str, st: dict[str, Any] | None, expected: float | str) -> CaseResult:
    try:
        actual = seq.status_vdc(st)
        if expected == "nan":
            ok = math.isnan(actual)
        else:
            ok = abs(actual - float(expected)) < 1e-9
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "status_vdc mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=None, detail=f"{type(exc).__name__}: {exc}")


def run_bad_case(name: str, st: dict[str, Any] | None, expected: int) -> CaseResult:
    try:
        actual = seq.status_bad_count(st)
        ok = actual == expected
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "status_bad_count mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=None, detail=f"{type(exc).__name__}: {exc}")


def run_runlimit_case() -> CaseResult:
    steps = [seq.Step(cmd="CLEAR"), seq.Step(cmd="START")]
    actual = [step.to_json() for step in seq.insert_run_limit_before_start(steps, 1.25)]
    expected = [{"cmd": "CLEAR"}, {"cmd": "SET RUNLIMIT 1.250"}, {"cmd": "START"}]
    return CaseResult(
        name="insert_run_limit_before_start",
        ok=actual == expected,
        expected=expected,
        actual=actual,
        detail="" if actual == expected else "run limit insertion mismatch",
    )


def run_remote_helper_case() -> CaseResult:
    actual = {
        "embedded_msgpack": "import base64, json, msgpack" in seq.ANDROID_SNIPPET,
        "no_external_router_rpc": "from router_rpc" not in seq.ANDROID_SNIPPET,
        "venv_python": seq.DEFAULT_REMOTE_PYTHON.endswith("/.venv/bin/python"),
        "snippet_compiles": True,
    }
    try:
        compile(seq.ANDROID_SNIPPET, "<adb-router-sequence>", "exec")
    except SyntaxError:
        actual["snippet_compiles"] = False
    expected = {key: True for key in actual}
    return CaseResult(
        name="standalone_remote_rpc_helper",
        ok=actual == expected,
        expected=expected,
        actual=actual,
        detail="" if actual == expected else "remote helper still depends on undeployed modules",
    )


def run_adb_device_parse_case() -> CaseResult:
    sample = "List of devices attached\nabc123 device product:uno_q\noffline offline\n"
    actual = seq.parse_adb_devices(sample)
    expected = ["abc123"]
    return CaseResult(
        name="adb_device_autodetect_parser",
        ok=actual == expected,
        expected=expected,
        actual=actual,
        detail="" if actual == expected else "ADB device parser mismatch",
    )


def cases() -> list[CaseResult]:
    return [
        run_runlimit_case(),
        run_remote_helper_case(),
        run_adb_device_parse_case(),
        run_vdc_case("status_vdc_prefers_max_readable", base_status(vdc=11.0, bp_vdc=14.0), 14.0),
        run_vdc_case("status_vdc_missing_is_nan", without_vbus(), "nan"),
        run_bad_case("bad_count_ok", base_status(), 0),
        run_bad_case("bad_count_legacy_blocks", base_status(bp_bad_cnt=0, bp_bad=1), 1),
        run_bad_case("bad_count_missing_blocks", {"state": "SAFE"}, 999999),
        run_precheck_case("safe_low_voltage_allows_enabling_sequence", base_status(), True, "ok"),
        run_precheck_case("missing_status_blocks", None, False, "unavailable"),
        run_precheck_case("link_down_blocks", base_status(link=False), False, "link"),
        run_precheck_case("stale_link_blocks", base_status(bp_age_ms=999999, bp_rsp_age_ms=999999), False, "stale"),
        run_precheck_case("not_safe_blocks", base_status(state="FAULT"), False, "SAFE"),
        run_precheck_case("pwm_active_blocks", base_status(pwm=1), False, "PWM"),
        run_precheck_case("estop_blocks", base_status(estop=1), False, "estop=1"),
        run_precheck_case("fault_blocks", base_status(bp_fault=6), False, "bp_fault=6"),
        run_precheck_case("legacy_bad_counter_blocks", base_status(bp_bad_cnt=0, bp_bad=1), False, "bp_bad=1"),
        run_precheck_case("missing_vbus_blocks", without_vbus(), False, "Vbus telemetry"),
        run_precheck_case("high_raw_vbus_blocks_with_zero_scaled", base_status(vdc=0.0, bp_vdc=0.0, bp_vbus_raw=3256), False, "raw Vbus"),
        run_precheck_case("missing_raw_vbus_blocks", {k: v for k, v in base_status().items() if k != "bp_vbus_raw"}, False, "missing"),
        run_precheck_case("stale_raw_vbus_blocks", base_status(bp_vbus_age_ms=5000), False, "stale"),
        run_precheck_case("invalid_raw_vbus_blocks", base_status(bp_vbus_raw=0), False, "invalid"),
        run_precheck_case("high_vbus_blocks_without_hv", base_status(vdc=315.0, bp_vdc=315.0, bp_vbus_raw=3256), False, "without --allow-hv"),
        run_precheck_case("high_vbus_allows_with_hv", base_status(vdc=315.0, bp_vdc=315.0, bp_vbus_raw=3256), True, "ok", allow_hv=True),
        run_precheck_case("allow_hv_still_requires_vbus", without_vbus(), False, "Vbus telemetry", allow_hv=True),
        run_precheck_case("allow_hv_requires_min_vbus", base_status(vdc=12.0, bp_vdc=12.0), False, "below --hv-vdc-min", allow_hv=True),
        run_precheck_case(
            "allow_hv_min_check_can_be_skipped",
            base_status(vdc=12.0, bp_vdc=12.0),
            True,
            "ok",
            allow_hv=True,
            skip_hv_min=True,
        ),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "adb_router_sequence_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

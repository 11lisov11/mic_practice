#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

import ntc_relay_preflight as relay


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
        "hmi_hv_enabled": 0,
        "hmi_hv_armed": 0,
        "vdc": 12.0,
        "bp_vdc": 12.0,
        "ntc": 0,
        "precharge": 0,
        "pfc": 0,
        "brake": 0,
        "bp_ext": 0,
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
    st: dict[str, Any] | None,
    expected_ok: bool,
    *,
    allow_hv: bool = False,
    confirmed_hv_off_bench: bool = False,
) -> CaseResult:
    try:
        actual = relay.safe_low_voltage(
            st,
            max_vdc=60.0,
            allow_hv=allow_hv,
            confirmed_hv_off_bench=confirmed_hv_off_bench,
        )
        ok = actual == expected_ok
        return CaseResult(
            name=name,
            ok=ok,
            expected=expected_ok,
            actual=actual,
            detail="" if ok else "safe_low_voltage mismatch",
        )
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected_ok, actual=None, detail=f"{type(exc).__name__}: {exc}")


def run_relay_status_case(name: str, st: dict[str, Any] | None, on: bool, field: str, ext_bit: int, expected_ok: bool) -> CaseResult:
    try:
        actual = relay.relay_status_ok(st, on=on, field=field, ext_bit=ext_bit)
        ok = actual == expected_ok
        return CaseResult(
            name=name,
            ok=ok,
            expected=expected_ok,
            actual=actual,
            detail="" if ok else "relay_status_ok mismatch",
        )
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected_ok, actual=None, detail=f"{type(exc).__name__}: {exc}")


def run_relay_config_case(name: str, relay_name: str, expected: dict[str, Any]) -> CaseResult:
    try:
        actual = relay.RELAY_CONFIGS.get(relay_name)
        ok = actual == expected
        return CaseResult(
            name=name,
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "relay config mismatch",
        )
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=None, detail=f"{type(exc).__name__}: {exc}")


def run_default_relay_parse_case(name: str, default_relay: str, expected_relay: str) -> CaseResult:
    old_argv = sys.argv[:]
    try:
        sys.argv = [f"{default_relay}_relay_preflight.py"]
        args = relay.parse_args(default_relay=default_relay)
        actual = args.relay
        ok = actual == expected_relay
        return CaseResult(
            name=name,
            ok=ok,
            expected=expected_relay,
            actual=actual,
            detail="" if ok else "default relay parse mismatch",
        )
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected_relay, actual=None, detail=f"{type(exc).__name__}: {exc}")
    finally:
        sys.argv = old_argv


def run_arm_case() -> CaseResult:
    old_post = relay.http_post_json
    seen: dict[str, Any] = {}
    try:
        def fake_post(url: str, payload: dict, timeout_s: float) -> dict:
            seen.update({"url": url, "payload": payload, "timeout_s": timeout_s})
            return {"ok": True, "arm": {"hmi_hv_armed": 1}}

        relay.http_post_json = fake_post
        actual = relay.arm_hmi("http://bench:18080/", "ARM LOWV", 1.25)
        expected = {
            "ok": True,
            "url": "http://bench:18080/api/hv-arm",
            "payload": {"action": "arm", "confirm": "ARM LOWV"},
            "timeout_s": 1.25,
        }
        observed = {"ok": actual, **seen}
        return CaseResult("hmi_arm_posts_confirmation", observed == expected, expected, observed)
    except Exception as exc:
        return CaseResult("hmi_arm_posts_confirmation", False, True, None, f"{type(exc).__name__}: {exc}")
    finally:
        relay.http_post_json = old_post


def cases() -> list[CaseResult]:
    return [
        run_relay_config_case(
            "ntc_config_removed",
            "ntc",
            None,
        ),
        run_relay_config_case(
            "precharge_config_matches_pb4_ext_bit",
            "precharge",
            {
                "cmd": "PRECHARGE",
                "field": "precharge",
                "ext_bit": 0x08,
                "tool": "precharge_relay_preflight",
                "tag": "precharge_relay_preflight",
                "description": "MIC_AI RELAY1 precharge bypass relay driver on Blue Pill PB4",
            },
        ),
        run_default_relay_parse_case("precharge_wrapper_default_selects_precharge", "precharge", "precharge"),
        run_arm_case(),
        run_safe_case("safe_low_voltage_ok", base_status(), True),
        run_safe_case("missing_status_blocks", None, False),
        run_safe_case("active_pwm_blocks", base_status(pwm=1), False),
        run_safe_case("estop_blocks", base_status(estop=1), False),
        run_safe_case("fault_blocks", base_status(bp_fault=3), False),
        run_safe_case("bad_counter_blocks", base_status(bp_bad_cnt=1), False),
        run_safe_case("legacy_bad_counter_blocks", base_status(bp_bad_cnt=0, bp_bad=1), False),
        run_safe_case("stale_link_blocks", base_status(bp_rsp_age_ms=999999, bp_age_ms=999999), False),
        run_safe_case("missing_vbus_blocks", without_vbus(), False),
        run_safe_case("allow_hv_still_requires_vbus", without_vbus(), False, allow_hv=True),
        run_safe_case("negative_vbus_blocks", base_status(vdc=-1.0, bp_vdc=-1.0), False),
        run_safe_case("high_vbus_blocks_without_hv", base_status(vdc=315.0, bp_vdc=315.0), False),
        run_safe_case("high_vbus_allows_with_hv", base_status(vdc=315.0, bp_vdc=315.0), True, allow_hv=True),
        run_safe_case(
            "confirmed_hv_off_bench_ignores_disconnected_vbus",
            without_vbus(),
            True,
            confirmed_hv_off_bench=True,
        ),
        run_safe_case(
            "confirmed_hv_off_bench_rejects_hv_mode",
            without_vbus(hmi_hv_enabled=1),
            False,
            confirmed_hv_off_bench=True,
        ),
        run_safe_case(
            "confirmed_hv_off_bench_rejects_hv_arm",
            without_vbus(hmi_hv_armed=1),
            False,
            confirmed_hv_off_bench=True,
        ),
        run_relay_status_case("precharge_off_status_ok", base_status(precharge=0, bp_ext=0x00), False, "precharge", 0x08, True),
        run_relay_status_case("precharge_on_status_ok", base_status(precharge=1, bp_ext=0x08), True, "precharge", 0x08, True),
        run_relay_status_case("precharge_on_ext_mismatch_blocks", base_status(precharge=1, bp_ext=0x00), True, "precharge", 0x08, False),
        run_relay_status_case("precharge_on_pwm_active_blocks", base_status(precharge=1, bp_ext=0x08, pwm=1), True, "precharge", 0x08, False),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "ntc_relay_preflight_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

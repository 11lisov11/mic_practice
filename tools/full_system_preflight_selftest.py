#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import full_system_preflight as preflight


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: Any
    actual: Any
    detail: str = ""


def case_all_required_steps_pass() -> CaseResult:
    steps = [{"name": name, "ok": True} for name in preflight.BUILD_ONLY_STEP_NAMES]
    audit = preflight.audit_required_steps(steps)
    expected = {"pass": True, "missing": [], "failed": [], "duplicates": []}
    actual = {key: audit[key] for key in expected}
    return CaseResult("all_required_steps_pass", actual == expected, expected, actual)


def case_missing_required_step_fails() -> CaseResult:
    omitted = "start_guard_static_check_selftest"
    steps = [{"name": name, "ok": True} for name in preflight.BUILD_ONLY_STEP_NAMES if name != omitted]
    audit = preflight.audit_required_steps(steps)
    actual = {"pass": audit["pass"], "missing": audit["missing"]}
    expected = {"pass": False, "missing": [omitted]}
    return CaseResult("missing_required_step_fails", actual == expected, expected, actual)


def case_failed_required_step_fails() -> CaseResult:
    failed = "run_metadata_selftest"
    steps = [{"name": name, "ok": name != failed} for name in preflight.BUILD_ONLY_STEP_NAMES]
    audit = preflight.audit_required_steps(steps)
    actual = {"pass": audit["pass"], "failed": audit["failed"]}
    expected = {"pass": False, "failed": [failed]}
    return CaseResult("failed_required_step_fails", actual == expected, expected, actual)


def case_duplicate_required_step_fails() -> CaseResult:
    duplicate = "protocol_contract_check"
    steps = [{"name": name, "ok": True} for name in preflight.BUILD_ONLY_STEP_NAMES]
    steps.append({"name": duplicate, "ok": True})
    audit = preflight.audit_required_steps(steps)
    actual = {"pass": audit["pass"], "duplicates": audit["duplicates"]}
    expected = {"pass": False, "duplicates": [duplicate]}
    return CaseResult("duplicate_required_step_fails", actual == expected, expected, actual)


def case_full_system_selftest_is_required() -> CaseResult:
    required = "full_system_preflight_selftest" in preflight.BUILD_ONLY_STEP_NAMES
    return CaseResult(
        "full_system_selftest_is_required",
        required,
        True,
        required,
        "" if required else "full_system_preflight_selftest is not part of BUILD_ONLY_STEP_NAMES",
    )


def case_all_discovered_selftests_are_required() -> CaseResult:
    expected = tuple(sorted(path.stem for path in Path(preflight.__file__).resolve().parent.glob("*_selftest.py")))
    actual = preflight.SELFTEST_STEP_NAMES
    return CaseResult(
        "all_discovered_selftests_are_required",
        actual == expected and all(name in preflight.BUILD_ONLY_STEP_NAMES for name in expected),
        expected,
        actual,
        "" if actual == expected else "SELFTEST_STEP_NAMES does not match tools/*_selftest.py",
    )


def case_all_firmware_targets_are_required() -> CaseResult:
    expected = {"unoq_build", "bluepill_build", "nucleo_build"}
    actual = set(preflight.BUILD_ONLY_STEP_NAMES) & expected
    return CaseResult(
        "all_firmware_targets_are_required",
        actual == expected,
        sorted(expected),
        sorted(actual),
        "" if actual == expected else "at least one target firmware build is missing from the release gate",
    )


def case_all_nucleo_profiles_are_built() -> CaseResult:
    source = Path(preflight.__file__).read_text(encoding="utf-8")
    expected = {
        "nucleo_g431_uart_bridge",
        "nucleo_g431_uart_bridge_vcp",
        "nucleo_g431_pwm_bench",
        "nucleo_g431_pwm_bench_vcp",
    }
    missing = sorted(profile for profile in expected if f'"{profile}"' not in source)
    return CaseResult(
        "all_nucleo_profiles_are_built",
        not missing,
        [],
        missing,
        "" if not missing else "at least one Nucleo UART/PWM transport profile is absent from the release build",
    )


def case_precharge_relay_stage_is_removed() -> CaseResult:
    source = Path(preflight.__file__).read_text(encoding="utf-8")
    forbidden_tokens = {
        "--with-precharge-relay",
        "precharge_relay_preflight.py",
    }
    present = sorted(token for token in forbidden_tokens if token in source)
    return CaseResult(
        "precharge_relay_stage_is_removed",
        not present,
        [],
        present,
        "" if not present else "removed K1/PB4 stage is still executable from the full preflight",
    )


def main() -> int:
    cases = [
        case_all_required_steps_pass(),
        case_missing_required_step_fails(),
        case_failed_required_step_fails(),
        case_duplicate_required_step_fails(),
        case_full_system_selftest_is_required(),
        case_all_discovered_selftests_are_required(),
        case_all_firmware_targets_are_required(),
        case_all_nucleo_profiles_are_built(),
        case_precharge_relay_stage_is_removed(),
    ]
    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "full_system_preflight_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

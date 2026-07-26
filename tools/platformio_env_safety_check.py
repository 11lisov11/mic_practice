#!/usr/bin/env python3
from __future__ import annotations

import configparser
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_ENVS = {
    "env:bluepill_uart_pwm",
    "env:bluepill_relay_test",
    "env:bluepill_pwm_selftest",
    "env:bluepill_static_low_test",
}

COMMON_EXPECTED = {
    "platform": "ststm32",
    "board": "bluepill_f103c8",
    "framework": "stm32cube",
    "upload_protocol": "stlink",
    "debug_tool": "stlink",
}


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "fail"
    evidence: Any = None


def ok_case(name: str, evidence: Any = None, detail: str = "") -> CaseResult:
    return CaseResult(name=name, ok=True, detail=detail, evidence=evidence)


def fail_case(name: str, detail: str, evidence: Any = None) -> CaseResult:
    return CaseResult(name=name, ok=False, detail=detail, evidence=evidence)


def warn_case(name: str, detail: str, evidence: Any = None) -> CaseResult:
    return CaseResult(name=name, ok=True, detail=detail, severity="warn", evidence=evidence)


def filter_tokens(raw: str) -> list[str]:
    return [tok.strip() for tok in re.split(r"\s+", raw.strip()) if tok.strip()]


def active_uart_baud(repo: Path) -> int | None:
    # Simple active-file check is enough here; firmware_config_safety_check owns
    # the full preprocessor-aware validation of config.h.
    path = repo / "bluepill_uart_pwm_pio" / "include" / "config.h"
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"^\s*#define\s+UART_BAUD\s+([0-9]+)", text, flags=re.MULTILINE)
    if not matches:
        return None
    return int(matches[-1])


def section_values(cfg: configparser.ConfigParser, section: str) -> dict[str, str]:
    return {key: cfg.get(section, key).strip() for key in cfg.options(section)}


def check_common_env(cfg: configparser.ConfigParser, section: str) -> list[CaseResult]:
    cases: list[CaseResult] = []
    values = section_values(cfg, section)
    for key, expected in COMMON_EXPECTED.items():
        actual = values.get(key)
        if actual == expected:
            cases.append(ok_case(f"{section}_{key}", actual))
        else:
            cases.append(
                fail_case(
                    f"{section}_{key}",
                    f"{key} must be {expected!r}",
                    {"actual": actual, "expected": expected},
                )
            )
    return cases


def run_checks(repo: Path) -> list[CaseResult]:
    ini_path = repo / "bluepill_uart_pwm_pio" / "platformio.ini"
    cfg = configparser.ConfigParser(interpolation=None)
    read_files = cfg.read(ini_path, encoding="utf-8")
    cases: list[CaseResult] = []

    if not read_files:
        return [fail_case("platformio_ini_readable", "platformio.ini was not read", str(ini_path))]
    cases.append(ok_case("platformio_ini_readable", str(ini_path)))

    sections = set(cfg.sections())
    missing = sorted(REQUIRED_ENVS - sections)
    extra_envs = sorted(sec for sec in sections if sec.startswith("env:") and sec not in REQUIRED_ENVS)
    cases.append(
        ok_case("required_envs_present", sorted(REQUIRED_ENVS))
        if not missing
        else fail_case("required_envs_present", "required PlatformIO env is missing", {"missing": missing})
    )
    if extra_envs:
        cases.append(warn_case("extra_envs_present", "unexpected extra PlatformIO envs exist", extra_envs))
    else:
        cases.append(ok_case("extra_envs_present", []))

    for section in sorted(REQUIRED_ENVS & sections):
        cases.extend(check_common_env(cfg, section))

    main_filter = filter_tokens(cfg.get("env:bluepill_uart_pwm", "build_src_filter", fallback=""))
    main_required = {"+<*>", "-<relay_test.cpp>", "-<pwm_selftest.cpp>", "-<pwm_static_low_test.cpp>"}
    missing_main = sorted(main_required - set(main_filter))
    cases.append(
        ok_case("main_build_src_filter", main_filter)
        if not missing_main
        else fail_case(
            "main_build_src_filter",
            "main runtime env must include normal sources and exclude test-only mains",
            {"tokens": main_filter, "missing": missing_main},
        )
    )

    relay_filter = filter_tokens(cfg.get("env:bluepill_relay_test", "build_src_filter", fallback=""))
    if "+<relay_test.cpp>" in relay_filter and "+<*>" not in relay_filter:
        cases.append(ok_case("relay_build_src_filter", relay_filter))
    else:
        cases.append(
            fail_case(
                "relay_build_src_filter",
                "relay env must build only relay_test.cpp, not the runtime main",
                relay_filter,
            )
        )

    selftest_filter = filter_tokens(cfg.get("env:bluepill_pwm_selftest", "build_src_filter", fallback=""))
    selftest_required = {"+<pwm_selftest.cpp>", "+<pwm_tim1.cpp>"}
    missing_selftest = sorted(selftest_required - set(selftest_filter))
    if not missing_selftest and "+<*>" not in selftest_filter:
        cases.append(ok_case("selftest_build_src_filter", selftest_filter))
    else:
        cases.append(
            fail_case(
                "selftest_build_src_filter",
                "PWM selftest env must build the selftest main plus TIM1 driver only",
                {"tokens": selftest_filter, "missing": missing_selftest},
            )
        )

    static_low_filter = filter_tokens(cfg.get("env:bluepill_static_low_test", "build_src_filter", fallback=""))
    if "+<pwm_static_low_test.cpp>" in static_low_filter and "+<*>" not in static_low_filter:
        cases.append(ok_case("static_low_build_src_filter", static_low_filter))
    else:
        cases.append(
            fail_case(
                "static_low_build_src_filter",
                "static-low env must build only pwm_static_low_test.cpp, not the runtime main",
                static_low_filter,
            )
        )

    monitor_speed = cfg.get("env:bluepill_uart_pwm", "monitor_speed", fallback="").strip()
    baud = active_uart_baud(repo)
    if baud is not None and monitor_speed and monitor_speed != str(baud):
        cases.append(
            warn_case(
                "main_monitor_speed_matches_uart_baud",
                "monitor_speed differs from UART_BAUD; this is OK if PlatformIO monitor is not used for runtime control",
                {"monitor_speed": monitor_speed, "UART_BAUD": baud},
            )
        )
    else:
        cases.append(ok_case("main_monitor_speed_matches_uart_baud", {"monitor_speed": monitor_speed, "UART_BAUD": baud}))

    return cases


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    cases = run_checks(repo)
    failed = [c for c in cases if not c.ok and c.severity == "fail"]
    warnings = [c for c in cases if c.severity == "warn"]
    summary = {
        "tool": "platformio_env_safety_check",
        "pass": len(failed) == 0,
        "failed": len(failed),
        "warnings": len(warnings),
        "cases": [c.__dict__ for c in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if len(failed) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

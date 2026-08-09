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
    "env:bluepill_pwm_selftest",
    "env:bluepill_static_low_test",
}

ALLOWED_ENVS = REQUIRED_ENVS | {
    "env:bluepill_uart_pwm_serial",
    "env:bluepill_uart_pwm_bench_no_temp",
    "env:bluepill_thermal_diag",
    "env:bluepill_thermal_diag_uart",
}

COMMON_EXPECTED = {
    "platform": "ststm32",
    "board": "bluepill_f103c8",
    "framework": "stm32cube",
    "upload_protocol": "stlink",
    "debug_tool": "stlink",
}

NUCLEO_REQUIRED_ENVS = {
    "env:nucleo_g431_uart_bridge",
    "env:nucleo_g431_pwm_bench",
}

NUCLEO_COMMON_EXPECTED = {
    "platform": "ststm32",
    "board": "nucleo_g431rb",
    "framework": "stm32cube",
    "upload_protocol": "stlink",
    "debug_tool": "stlink",
}

NUCLEO_STUB_FLAGS = {
    "-DMIC_MOTOR_BACKEND_STUB=1",
    "-DMIC_MOTOR_BACKEND_PWM_BENCH=0",
    "-DNUCLEO_MOTOR_CLOCK_170MHZ=0",
    "-DNUCLEO_BRIDGE_STATUS_LED=1",
}

NUCLEO_BENCH_FLAGS = {
    "-DMIC_MOTOR_BACKEND_STUB=0",
    "-DMIC_MOTOR_BACKEND_PWM_BENCH=1",
    "-DNUCLEO_MOTOR_CLOCK_170MHZ=1",
    "-DNUCLEO_BRIDGE_STATUS_LED=1",
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


def config_value(cfg: configparser.ConfigParser, section: str, option: str) -> str:
    if not cfg.has_section(section):
        return ""
    return cfg.get(section, option, fallback="").strip()


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


def macro_value(path: Path, name: str) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(rf"^\s*#define\s+{re.escape(name)}\s+([^\s/]+)", text, flags=re.MULTILINE)
    return matches[-1] if matches else None


def run_nucleo_checks(repo: Path) -> list[CaseResult]:
    ini_path = repo / "nucleo_g431_uart_bridge_pio" / "platformio.ini"
    cfg = configparser.ConfigParser(interpolation=None)
    read_files = cfg.read(ini_path, encoding="utf-8")
    cases: list[CaseResult] = []
    if not read_files:
        return [fail_case("nucleo_platformio_ini_readable", "Nucleo platformio.ini was not read", str(ini_path))]
    cases.append(ok_case("nucleo_platformio_ini_readable", str(ini_path)))

    sections = set(cfg.sections())
    missing = sorted(NUCLEO_REQUIRED_ENVS - sections)
    extra = sorted(sec for sec in sections if sec.startswith("env:") and sec not in NUCLEO_REQUIRED_ENVS)
    cases.append(
        ok_case("nucleo_required_envs_present", sorted(NUCLEO_REQUIRED_ENVS))
        if not missing
        else fail_case("nucleo_required_envs_present", "required Nucleo PlatformIO env is missing", {"missing": missing})
    )
    cases.append(
        ok_case("nucleo_extra_envs_present", [])
        if not extra
        else warn_case("nucleo_extra_envs_present", "unexpected Nucleo PlatformIO envs exist", extra)
    )

    default_envs = filter_tokens(config_value(cfg, "platformio", "default_envs"))
    expected_default = ["nucleo_g431_uart_bridge"]
    cases.append(
        ok_case("nucleo_default_env_is_safe_stub", default_envs)
        if default_envs == expected_default
        else fail_case(
            "nucleo_default_env_is_safe_stub",
            "default Nucleo build must remain the non-driving UART bridge stub",
            {"actual": default_envs, "expected": expected_default},
        )
    )

    base = "env:nucleo_g431_uart_bridge"
    if base in sections:
        values = section_values(cfg, base)
        for key, expected in NUCLEO_COMMON_EXPECTED.items():
            actual = values.get(key)
            cases.append(
                ok_case(f"nucleo_stub_{key}", actual)
                if actual == expected
                else fail_case(
                    f"nucleo_stub_{key}",
                    f"{key} must be {expected!r}",
                    {"actual": actual, "expected": expected},
                )
            )
        stub_flags = set(filter_tokens(values.get("build_flags", "")))
        cases.append(
            ok_case("nucleo_stub_build_flags", sorted(stub_flags))
            if stub_flags == NUCLEO_STUB_FLAGS
            else fail_case(
                "nucleo_stub_build_flags",
                "safe bridge profile must select only the stub backend and 8 MHz clock path",
                {"actual": sorted(stub_flags), "expected": sorted(NUCLEO_STUB_FLAGS)},
            )
        )

    bench = "env:nucleo_g431_pwm_bench"
    if bench in sections:
        values = section_values(cfg, bench)
        extends = values.get("extends")
        cases.append(
            ok_case("nucleo_bench_extends_stub", extends)
            if extends == base
            else fail_case(
                "nucleo_bench_extends_stub",
                "PWM bench profile must inherit the reviewed Nucleo base profile",
                {"actual": extends, "expected": base},
            )
        )
        bench_flags = set(filter_tokens(values.get("build_flags", "")))
        cases.append(
            ok_case("nucleo_bench_build_flags", sorted(bench_flags))
            if bench_flags == NUCLEO_BENCH_FLAGS
            else fail_case(
                "nucleo_bench_build_flags",
                "PWM bench profile must select only the diagnostic backend and 170 MHz clock path",
                {"actual": sorted(bench_flags), "expected": sorted(NUCLEO_BENCH_FLAGS)},
            )
        )

    config_path = repo / "nucleo_g431_uart_bridge_pio" / "include" / "config.h"
    expected_macros = {
        "LINK_TIMEOUT_MS": "300U",
        "MOTOR_BENCH_PWM_FREQ_HZ": "10000U",
        "MOTOR_BENCH_DEADTIME_NS": "2000U",
        "MOTOR_EM_STOP_SAFE_STATE": "GPIO_PIN_RESET",
    }
    actual_macros = (
        {name: macro_value(config_path, name) for name in expected_macros}
        if config_path.is_file()
        else {name: None for name in expected_macros}
    )
    cases.append(
        ok_case("nucleo_bench_config_safety", actual_macros)
        if actual_macros == expected_macros
        else fail_case(
            "nucleo_bench_config_safety",
            "Nucleo diagnostic timing or active-low EM_STOP safe state changed",
            {"actual": actual_macros, "expected": expected_macros},
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
    extra_envs = sorted(sec for sec in sections if sec.startswith("env:") and sec not in ALLOWED_ENVS)
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

    main_filter = filter_tokens(config_value(cfg, "env:bluepill_uart_pwm", "build_src_filter"))
    main_required = {
        "+<*>",
        "-<pwm_selftest.cpp>",
        "-<pwm_static_low_test.cpp>",
        "-<thermal_diag.cpp>",
    }
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

    relay_source = repo / "bluepill_uart_pwm_pio" / "src" / "relay_test.cpp"
    if "env:bluepill_relay_test" not in sections and not relay_source.exists():
        cases.append(ok_case("relay_test_firmware_removed"))
    else:
        cases.append(
            fail_case(
                "relay_test_firmware_removed",
                "the obsolete PB4 toggling firmware must not exist when K1 is absent",
                {"env_present": "env:bluepill_relay_test" in sections, "source_present": relay_source.exists()},
            )
        )

    selftest_filter = filter_tokens(config_value(cfg, "env:bluepill_pwm_selftest", "build_src_filter"))
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

    static_low_filter = filter_tokens(config_value(cfg, "env:bluepill_static_low_test", "build_src_filter"))
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

    monitor_speed = config_value(cfg, "env:bluepill_uart_pwm", "monitor_speed")
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

    cases.extend(run_nucleo_checks(repo))
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

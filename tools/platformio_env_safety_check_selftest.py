#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import platformio_env_safety_check as check


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


def find_case(cases: list[check.CaseResult], name: str) -> check.CaseResult:
    matches = [case for case in cases if case.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {name!r} result, got {len(matches)}")
    return matches[0]


def make_fixture(root: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    shutil.copytree(repo / "bluepill_uart_pwm_pio", root / "bluepill_uart_pwm_pio")
    shutil.copytree(repo / "nucleo_g431_uart_bridge_pio", root / "nucleo_g431_uart_bridge_pio")


def run_case(name: str, fn: Callable[[], Any]) -> CaseResult:
    try:
        return CaseResult(name=name, ok=True, evidence=fn())
    except Exception as exc:
        return CaseResult(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}")


def current_project_passes() -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[1]
    cases = check.run_checks(repo)
    failed = [case.name for case in cases if not case.ok and case.severity == "fail"]
    if failed:
        raise RuntimeError(f"current project failed: {failed}")
    return {"cases": len(cases), "warnings": [case.name for case in cases if case.severity == "warn"]}


def missing_nucleo_bench_is_rejected() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(root)
        ini = root / "nucleo_g431_uart_bridge_pio" / "platformio.ini"
        text = ini.read_text(encoding="utf-8")
        ini.write_text(text.split("[env:nucleo_g431_pwm_bench]", 1)[0], encoding="utf-8")
        result = find_case(check.run_checks(root), "nucleo_required_envs_present")
        if result.ok:
            raise RuntimeError("missing Nucleo PWM bench profile was accepted")
        return {"detail": result.detail, "evidence": result.evidence}


def missing_bluepill_runtime_is_rejected_without_exception() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(root)
        ini = root / "bluepill_uart_pwm_pio" / "platformio.ini"
        text = ini.read_text(encoding="utf-8")
        start = text.index("[env:bluepill_uart_pwm]")
        end = text.index("[env:bluepill_uart_pwm_serial]")
        ini.write_text(text[:start] + text[end:], encoding="utf-8")
        result = find_case(check.run_checks(root), "required_envs_present")
        if result.ok:
            raise RuntimeError("missing Blue Pill runtime profile was accepted")
        return {"detail": result.detail, "evidence": result.evidence}


def conflicting_nucleo_backend_is_rejected() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(root)
        ini = root / "nucleo_g431_uart_bridge_pio" / "platformio.ini"
        text = ini.read_text(encoding="utf-8")
        old = "-DMIC_MOTOR_BACKEND_PWM_BENCH=1"
        if old not in text:
            raise RuntimeError("bench backend flag fixture not found")
        ini.write_text(text.replace(old, "-DMIC_MOTOR_BACKEND_PWM_BENCH=0", 1), encoding="utf-8")
        result = find_case(check.run_checks(root), "nucleo_bench_build_flags")
        if result.ok:
            raise RuntimeError("conflicting Nucleo backend flags were accepted")
        return {"detail": result.detail, "evidence": result.evidence}


def released_em_stop_is_rejected() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(root)
        config = root / "nucleo_g431_uart_bridge_pio" / "include" / "config.h"
        text = config.read_text(encoding="utf-8")
        old = "#define MOTOR_EM_STOP_SAFE_STATE GPIO_PIN_RESET"
        if old not in text:
            raise RuntimeError("EM_STOP safe-state fixture not found")
        config.write_text(text.replace(old, "#define MOTOR_EM_STOP_SAFE_STATE GPIO_PIN_SET", 1), encoding="utf-8")
        result = find_case(check.run_checks(root), "nucleo_bench_config_safety")
        if result.ok:
            raise RuntimeError("released active-low EM_STOP was accepted")
        return {"detail": result.detail, "evidence": result.evidence}


def main() -> int:
    cases = [
        run_case("current_project_passes", current_project_passes),
        run_case("missing_nucleo_bench_is_rejected", missing_nucleo_bench_is_rejected),
        run_case(
            "missing_bluepill_runtime_is_rejected_without_exception",
            missing_bluepill_runtime_is_rejected_without_exception,
        ),
        run_case("conflicting_nucleo_backend_is_rejected", conflicting_nucleo_backend_is_rejected),
        run_case("released_em_stop_is_rejected", released_em_stop_is_rejected),
    ]
    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "platformio_env_safety_check_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

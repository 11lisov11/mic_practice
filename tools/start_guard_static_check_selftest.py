#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import start_guard_static_check as check


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: Any
    actual: Any
    detail: str = ""


def case_forbidden_patterns_catch_variants() -> CaseResult:
    text = """
    py -3 -m platformio run -d bluepill_uart_pwm_pio -e bluepill_uart_pwm --target upload
    arduino-cli upload -p COM5 --fqbn arduino:zephyr:unoq .\\UNOQ_MOTOR
    """
    hits = check.forbidden_operator_doc_hits(text)
    actual = [hit.split(":", 1)[0] for hit in hits]
    expected = ["direct_platformio_upload", "direct_arduino_upload"]
    return CaseResult(
        "forbidden_patterns_catch_variants",
        actual == expected,
        expected,
        actual,
        "" if actual == expected else str(hits),
    )


def case_safe_wrapper_text_is_allowed() -> CaseResult:
    text = """
    py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off
    py -3 -u .\\tools\\unoq_wifi_firmware_update.py --flash --confirm-hv-off
    """
    hits = check.forbidden_operator_doc_hits(text)
    return CaseResult(
        "safe_wrapper_text_is_allowed",
        hits == [],
        [],
        hits,
        "" if hits == [] else "safe wrapper text was rejected",
    )


def case_run_checks_reports_operator_doc_violation() -> CaseResult:
    with tempfile.TemporaryDirectory(prefix="start_guard_doc_selftest_") as tmp:
        repo = Path(tmp)
        for rel in check.REQUIRED_TOKENS:
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(check.REQUIRED_TOKENS[rel]), encoding="utf-8")
        for rel in check.OPERATOR_DOCS:
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("safe text", encoding="utf-8")
        (repo / "README.md").write_text(
            "py -3 -m platformio run -d bluepill_uart_pwm_pio -e bluepill_uart_pwm -t upload",
            encoding="utf-8",
        )
        cases = check.run_checks(repo)
        failed = [case.name for case in cases if not case.ok]
        expected = ["operator_doc_safe_upload:README.md"]
        return CaseResult(
            "run_checks_reports_operator_doc_violation",
            failed == expected,
            expected,
            failed,
            "" if failed == expected else str([case.__dict__ for case in cases if not case.ok]),
        )


def main() -> int:
    cases = [
        case_forbidden_patterns_catch_variants(),
        case_safe_wrapper_text_is_allowed(),
        case_run_checks_reports_operator_doc_violation(),
    ]
    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "start_guard_static_check_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

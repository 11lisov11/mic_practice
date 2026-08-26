#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CaseResult:
    name: str
    ok: bool
    file: str
    missing: list[str]


REQUIRED_TOKENS: dict[str, list[str]] = {
    "tools/active_pwm_guard.py": [
        "bench_gate_report.py",
        "ready_for_active_pwm",
        "UNOQ_ALLOW_UNGATED_START",
        "UNOQ_ALLOW_UNGATED_START_ACK",
        "bypass is disabled",
        "live bench-gate URL is required",
        "START blocked by bench gate",
    ],
    "web_hmi/server.py": [
        "CommandGuardConfig",
        "command_requests_service_output",
        "command_guard_check",
        "_status_vdc",
        "DC bus telemetry is not readable",
        "start_bench_gate_check",
        "start_allowed_by_bench_gate",
        "--bench-gate-url",
        "--cmd-guard-max-vdc",
        "CMD_REJECT",
    ],
    "tools/unoq_web_server.py": [
        "start_allowed_by_bench_gate",
        "start_bench_gate_permitted",
        "output_permitted_locked",
        "cmd_guard_max_vdc",
        "--bench-gate-url",
        "--cmd-guard-max-vdc",
        "DC bus too high",
        "bluepill bad counter non-zero",
    ],
    "tools/ui_pwm_case.py": [
        "command_requests_start",
        "commands_with_runlimit",
        "SET RUNLIMIT",
        "start_allowed_by_vdc",
        "start_status_precheck",
        "bp_bad_value",
        "Fix Vbus telemetry before any START",
        "start_allowed_by_bench_gate",
        "url=base",
        "UNOQ_ALLOW_HV",
        "START blocked",
    ],
    "tools/mic_ai_compare.py": [
        "command_requests_start",
        "commands_with_runlimit",
        "SET RUNLIMIT",
        "start_allowed_by_vdc",
        "Fix Vbus telemetry before any START",
        "start_allowed_by_bench_gate",
        "url=base",
        "--allow-hv",
        "--max-start-vdc",
    ],
    "tools/adb_router_sequence.py": [
        "sequence_can_enable_pwm",
        "insert_run_limit_before_start",
        "enabling_status_precheck",
        "status_bad_count",
        "Vbus telemetry is not readable",
        "start_allowed_by_bench_gate",
        "url=args.status_url",
        "--allow-hv",
        "refusing enabling sequence",
    ],
    "tools/dense_overlap_sweep.py": [
        "low_voltage_start_precheck",
        "bench_gate_start_precheck",
        "start_allowed_by_bench_gate",
        "--max-start-vdc",
        "--allow-hv",
        "Refusing dense sweep START",
        "bench gate blocked START",
    ],
    "tools/bpfoc_backend_preflight.py": [
        "vdc_guard",
        "Vbus telemetry is not readable",
        "bench_gate_guard",
        "url=base_url",
        "--allow-hv",
        "--vdc-samples",
        "pre-start guard failed",
    ],
    "tools/saleae_highlevel_probe.py": [
        "command_requests_start",
        "start_allowed_by_bench_gate",
        "url=base",
        "START blocked by bench gate",
        "command_pass",
    ],
    "tools/fan_preflight.py": [
        "safe_low_voltage",
        "Vbus telemetry is not readable",
        "bp_link_live",
        "bp_bad_count",
        "--max-vdc",
        "--allow-hv",
    ],
    "tools/ntc_relay_preflight.py": [
        "safe_low_voltage",
        "vdc_max_seen",
        "math.isfinite",
        "bp_link_live",
        "bp_bad_count",
        "--max-vdc",
        "--allow-hv",
        "IOTEST ON",
    ],
    "tools/scalar_vf_preflight.py": [
        "status_is_safe",
        "bp_link_live",
        "from ui_pwm_case import",
        "send_cmds_retry",
        "START",
    ],
    "tools/foc_mic_preflight.py": [
        "status_is_safe",
        "bp_link_live",
        "from ui_pwm_case import",
        "send_cmds_retry",
        "START",
    ],
    "tools/hv_j7_preflight.py": [
        "status_is_safe",
        "vdc_in_range",
        "status_vdc",
        "math.isfinite",
        "initial Vbus telemetry unreadable",
        "UNOQ_ALLOW_HV",
        "from ui_pwm_case import",
        "send_cmds_retry",
        "--vdc-min",
        "--vdc-max",
    ],
    "tools/ui_pwm_suite.py": [
        "from ui_pwm_case import",
        "send_cmds",
        "post_cmd",
        "send_cmds_retry",
        "commands_with_runlimit",
        "SET RUNLIMIT",
        "START",
    ],
    "UNOQ_MOTOR/UNOQ_MOTOR.ino": [
        "START_REQUIRE_RUN_LIMIT",
        "start_precheck",
        "runlimit required",
        "bluepill link stale",
        "bluepill bad counter",
        "BP_STATUS_PWM_ACTIVE",
    ],
    "tools/mic_research_matrix.py": [
        "status_safe_for_start",
        "mic_ai_compare.py",
        "--max-start-vdc",
        "--start-vdc-samples",
    ],
}


START_GUARDED_FILES = set(REQUIRED_TOKENS)
START_TEXT_ONLY_FILES = {
    "tools/active_pwm_guard.py",
    "tools/bench_gate_report.py",
    "tools/bluepill_uart_diagnose.py",
    "tools/current_bench_status.py",
    "tools/encoder_test.py",
    "tools/patch_mcsdk_uno_start_interlock.py",
    "tools/start_guard_static_check.py",
    "tools/uart_loopback_preflight.py",
    "tools/uno_nucleo_mcsdk_contract_check.py",
    "tools/ui_http_bridge.py",
}


OPERATOR_DOCS = [
    "README.md",
    "PC_DIRECT_STM32_RU.md",
    "BRINGUP_STEPS_RU.md",
    "CONNECTION_MATRIX_RU.md",
    "PWM_STATIC_BLOCKER_RU.md",
    "UART_LOOPBACK_STEPS_RU.md",
    "RESEARCH_READINESS_RU.md",
]


FORBIDDEN_OPERATOR_DOC_PATTERNS: dict[str, re.Pattern[str]] = {
    "direct_platformio_upload": re.compile(
        r"\bplatformio\s+run\b[^\r\n`]*?(?:-t|--target)\s+upload\b",
        re.IGNORECASE,
    ),
    "direct_arduino_upload": re.compile(
        r"\barduino-cli\s+upload\b",
        re.IGNORECASE,
    ),
}


def forbidden_operator_doc_hits(text: str) -> list[str]:
    hits: list[str] = []
    for name, pattern in FORBIDDEN_OPERATOR_DOC_PATTERNS.items():
        for match in pattern.finditer(text):
            snippet = " ".join(match.group(0).split())
            hits.append(f"{name}: {snippet}")
    return hits


def run_checks(repo: Path) -> list[CaseResult]:
    cases: list[CaseResult] = []
    for rel, tokens in REQUIRED_TOKENS.items():
        path = repo / rel
        if not path.exists():
            cases.append(CaseResult(name=rel, ok=False, file=str(path), missing=["file missing"]))
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        missing = [token for token in tokens if token not in text]
        cases.append(CaseResult(name=rel, ok=not missing, file=str(path), missing=missing))

    discovered: list[str] = []
    unclassified: list[str] = []
    for path in sorted((repo / "tools").glob("*.py")):
        rel = path.relative_to(repo).as_posix()
        if rel.endswith("_selftest.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "START" not in text:
            continue
        discovered.append(rel)
        if rel in START_GUARDED_FILES or rel in START_TEXT_ONLY_FILES:
            continue
        unclassified.append(rel)
    cases.append(
        CaseResult(
            name="start_guard_discovery_classifies_all_start_files",
            ok=not unclassified,
            file=str(repo / "tools"),
            missing=unclassified,
        )
    )
    for rel in OPERATOR_DOCS:
        path = repo / rel
        if not path.exists():
            cases.append(CaseResult(name=f"operator_doc_safe_upload:{rel}", ok=False, file=str(path), missing=["file missing"]))
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        present = forbidden_operator_doc_hits(text)
        cases.append(
            CaseResult(
                name=f"operator_doc_safe_upload:{rel}",
                ok=not present,
                file=str(path),
                missing=[f"forbidden direct upload command: {hit}" for hit in present],
            )
        )
    return cases


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    cases = run_checks(repo)
    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "start_guard_static_check",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

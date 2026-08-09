#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import research_readiness_check as readiness


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: list[str]
    actual: list[str]
    detail: str = ""


class Args:
    url = "http://127.0.0.1:18080"
    min_repeats = 3


def action_ids(actions: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("id", "")) for item in actions]


def failed_check(name: str, evidence: dict[str, Any] | None = None, detail: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "ok": False,
        "severity": "fail",
        "detail": detail,
        "evidence": evidence,
    }


def run_bench_action_propagation_case() -> CaseResult:
    expected = [
        "run_runtime_static_preflight",
        "run_static_low_isolation_preflight",
        "run_uart_loopback",
        "fix_pwm_safe_static_levels",
        "restore_hmi_safe_status",
    ]
    try:
        bench_actions = [
            {
                "id": "run_runtime_static_preflight",
                "command": "runtime-static-cmd",
                "detail": "runtime-static-detail",
            },
            {
                "id": "run_static_low_isolation_preflight",
                "command": "static-low-cmd",
                "detail": "static-low-detail",
            },
            {
                "id": "run_uart_loopback",
                "command": "loopback-cmd",
                "detail": "loopback-detail",
            },
            {
                "id": "fix_pwm_safe_static_levels",
                "command": "fix-static-cmd",
                "detail": "fix-static-detail",
            },
            {
                "id": "restore_hmi_safe_status",
                "command": "hmi-safe-cmd",
                "detail": "hmi-safe-detail",
            },
        ]
        failed = [
            failed_check(
                "bench_gate_ready_for_active_pwm",
                evidence={
                    "next_actions": [item["id"] for item in bench_actions],
                    "bench_next_actions": bench_actions,
                },
            )
        ]
        actual = action_ids(readiness.build_next_actions(failed, [], Args()))
        ok = actual == expected
        return CaseResult(
            name="bench_gate_next_actions_propagate_runtime_static_uart_static_levels_and_hmi",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "action propagation mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="bench_gate_next_actions_propagate_runtime_static_uart_static_levels_and_hmi",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_static_low_action_command_case() -> CaseResult:
    expected = ["run_static_low_isolation_preflight", "static-low-cmd"]
    try:
        failed = [
            failed_check(
                "bench_gate_ready_for_active_pwm",
                evidence={
                    "next_actions": ["run_static_low_isolation_preflight"],
                    "bench_next_actions": [
                        {
                            "id": "run_static_low_isolation_preflight",
                            "command": "static-low-cmd",
                            "detail": "static-low-detail",
                        }
                    ],
                },
            )
        ]
        actions = readiness.build_next_actions(failed, [], Args())
        actual = [str(actions[0].get("id", "")), str(actions[0].get("command", ""))] if actions else []
        ok = actual == expected
        return CaseResult(
            name="static_low_action_preserves_bench_command",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "static-low action command mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="static_low_action_preserves_bench_command",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_runtime_static_action_command_case() -> CaseResult:
    expected = ["run_runtime_static_preflight", "runtime-static-cmd"]
    try:
        failed = [
            failed_check(
                "bench_gate_ready_for_active_pwm",
                evidence={
                    "next_actions": ["run_runtime_static_preflight"],
                    "bench_next_actions": [
                        {
                            "id": "run_runtime_static_preflight",
                            "command": "runtime-static-cmd",
                            "detail": "runtime-static-detail",
                        }
                    ],
                },
            )
        ]
        actions = readiness.build_next_actions(failed, [], Args())
        actual = [str(actions[0].get("id", "")), str(actions[0].get("command", ""))] if actions else []
        ok = actual == expected
        return CaseResult(
            name="runtime_static_action_preserves_bench_command",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "runtime static command mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="runtime_static_action_preserves_bench_command",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_uart_loopback_action_detail_case() -> CaseResult:
    expected = ["run_uart_loopback", "loopback-cmd", "Do not run unoq_web_server"]
    try:
        failed = [
            failed_check(
                "bench_gate_ready_for_active_pwm",
                evidence={
                    "next_actions": ["run_uart_loopback"],
                    "bench_next_actions": [
                        {
                            "id": "run_uart_loopback",
                            "command": "loopback-cmd",
                            "detail": "Disconnect TX/RX, short TX-RX, close HMI/serial monitors. Do not run unoq_web_server on this COM port until loopback is complete.",
                        }
                    ],
                },
            )
        ]
        actions = readiness.build_next_actions(failed, [], Args())
        if actions:
            actual = [
                str(actions[0].get("id", "")),
                str(actions[0].get("command", "")),
                "Do not run unoq_web_server" if "Do not run unoq_web_server" in str(actions[0].get("detail", "")) else "",
            ]
        else:
            actual = []
        ok = actual == expected
        return CaseResult(
            name="uart_loopback_action_preserves_bench_detail_and_command",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "UART loopback detail/command mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="uart_loopback_action_preserves_bench_detail_and_command",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_hmi_safe_action_command_case() -> CaseResult:
    expected = ["restore_hmi_safe_status", "hmi-safe-cmd"]
    try:
        failed = [
            failed_check(
                "bench_gate_ready_for_active_pwm",
                evidence={
                    "next_actions": ["restore_hmi_safe_status"],
                    "bench_next_actions": [
                        {
                            "id": "restore_hmi_safe_status",
                            "command": "hmi-safe-cmd",
                            "detail": "hmi-safe-detail",
                        }
                    ],
                },
            )
        ]
        actions = readiness.build_next_actions(failed, [], Args())
        actual = [str(actions[0].get("id", "")), str(actions[0].get("command", ""))] if actions else []
        ok = actual == expected
        return CaseResult(
            name="hmi_safe_action_preserves_bench_command",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "HMI safe command mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="hmi_safe_action_preserves_bench_command",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_runtime_static_named_checks_case() -> CaseResult:
    expected = [
        "bench_gate_runtime_static_preflight_pass",
        "bench_gate_runtime_static_preflight_fresh",
        "bench_gate_runtime_static_pwm_lines_low",
    ]
    try:
        result = {"checks": []}
        data = {
            "ready_for_active_pwm": False,
            "failed": 3,
            "warnings": 0,
            "next_actions": [],
            "checks": [
                {
                    "name": "latest_runtime_static_preflight_pass",
                    "ok": False,
                    "detail": "runtime static preflight did not pass",
                },
                {
                    "name": "runtime_static_preflight_fresh_for_build",
                    "ok": False,
                    "detail": "runtime static preflight is older than build",
                },
                {
                    "name": "runtime_static_pwm_lines_low",
                    "ok": False,
                    "detail": "pattern=low_side_static_high",
                },
            ],
        }
        with _TempBenchGate(data) as bench_summary:
            original_latest = readiness.latest_bench_gate
            readiness.latest_bench_gate = lambda repo: (bench_summary, data)
            try:
                readiness.check_bench_gate_artifact(result, Path("."))
            finally:
                readiness.latest_bench_gate = original_latest
        actual = [item["name"] for item in result["checks"] if not item.get("ok") and item["name"].startswith("bench_gate_runtime_static")]
        ok = actual == expected
        return CaseResult(
            name="runtime_static_bench_checks_are_exposed_in_readiness",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "runtime static checks missing from readiness",
        )
    except Exception as exc:
        return CaseResult(
            name="runtime_static_bench_checks_are_exposed_in_readiness",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_saleae_static_fresh_named_check_case() -> CaseResult:
    expected = ["bench_gate_saleae_static_probe_fresh"]
    try:
        result = {"checks": []}
        data = {
            "ready_for_active_pwm": False,
            "failed": 1,
            "warnings": 0,
            "next_actions": ["refresh_saleae_static_probe"],
            "checks": [
                {
                    "name": "saleae_static_probe_fresh_for_build",
                    "ok": False,
                    "detail": "saleae static capture is older than latest build-only preflight",
                    "evidence": {
                        "build_summary": "tools/_preflight_exports/full_system_preflight_new/summary.json",
                        "capture_summary": "tools/_preflight_exports/saleae_highlevel_probe_old/summary.json",
                    },
                }
            ],
        }
        with _TempBenchGate(data) as bench_summary:
            original_latest = readiness.latest_bench_gate
            readiness.latest_bench_gate = lambda repo: (bench_summary, data)
            try:
                readiness.check_bench_gate_artifact(result, Path("."))
            finally:
                readiness.latest_bench_gate = original_latest
        actual = [item["name"] for item in result["checks"] if not item.get("ok") and item["name"].startswith("bench_gate_saleae")]
        ok = actual == expected
        return CaseResult(
            name="saleae_static_fresh_check_is_exposed_in_readiness",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "Saleae freshness check missing from readiness",
        )
    except Exception as exc:
        return CaseResult(
            name="saleae_static_fresh_check_is_exposed_in_readiness",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_saleae_static_failure_named_checks_case() -> CaseResult:
    expected = [
        "bench_gate_saleae_static_safe_flag",
        "bench_gate_saleae_strict_static_safe_exit",
        "bench_gate_saleae_static_pwm_lines_low",
        "bench_gate_saleae_sample_rate",
    ]
    try:
        result = {"checks": []}
        data = {
            "ready_for_active_pwm": False,
            "failed": 3,
            "warnings": 1,
            "next_actions": ["run_static_low_isolation_preflight"],
            "checks": [
                {
                    "name": "saleae_probe_pwm_static_safe_flag",
                    "ok": False,
                    "detail": "pattern=low_side_static_high",
                },
                {
                    "name": "saleae_strict_static_safe_exit",
                    "ok": False,
                    "detail": "exit_code=5 pattern=low_side_static_high",
                },
                {
                    "name": "saleae_static_pwm_lines_low",
                    "ok": False,
                    "detail": "CH1/PB13 CH3/PB14 CH5/PB15 HIGH",
                },
                {
                    "name": "saleae_static_sample_rate_meets_requested",
                    "ok": False,
                    "detail": "selected 500000 Hz while 24000000 Hz was requested",
                },
            ],
        }
        with _TempBenchGate(data) as bench_summary:
            original_latest = readiness.latest_bench_gate
            readiness.latest_bench_gate = lambda repo: (bench_summary, data)
            try:
                readiness.check_bench_gate_artifact(result, Path("."))
            finally:
                readiness.latest_bench_gate = original_latest
        actual = [item["name"] for item in result["checks"] if not item.get("ok") and item["name"].startswith("bench_gate_saleae")]
        severities = {item["name"]: item["severity"] for item in result["checks"] if item["name"] in actual}
        ok = actual == expected and severities.get("bench_gate_saleae_sample_rate") == "warn"
        return CaseResult(
            name="saleae_static_failure_checks_are_exposed_in_readiness",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else f"Saleae static checks missing or wrong severity: {severities}",
        )
    except Exception as exc:
        return CaseResult(
            name="saleae_static_failure_checks_are_exposed_in_readiness",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_static_low_named_checks_case() -> CaseResult:
    expected = [
        "bench_gate_static_low_preflight_present",
        "bench_gate_static_low_preflight_pass",
        "bench_gate_static_low_preflight_fresh",
        "bench_gate_static_low_runtime_restored",
        "bench_gate_static_low_diagnostic_conclusion",
    ]
    try:
        result = {"checks": []}
        data = {
            "ready_for_active_pwm": False,
            "failed": 5,
            "warnings": 0,
            "next_actions": ["run_static_low_isolation_preflight"],
            "checks": [
                {
                    "name": "latest_static_low_preflight_present",
                    "ok": False,
                    "detail": "no bluepill_static_low_preflight summary found",
                },
                {
                    "name": "latest_static_low_preflight_pass",
                    "ok": False,
                    "detail": "static-low diagnostic failed: pattern=low_side_static_high",
                },
                {
                    "name": "static_low_preflight_fresh_for_build",
                    "ok": False,
                    "detail": "static-low preflight is older than build",
                },
                {
                    "name": "static_low_runtime_restored",
                    "ok": False,
                    "detail": "runtime firmware was not restored",
                },
                {
                    "name": "static_low_diagnostic_conclusion_present",
                    "ok": False,
                    "detail": "diagnostic_conclusion missing",
                },
            ],
        }
        with _TempBenchGate(data) as bench_summary:
            original_latest = readiness.latest_bench_gate
            readiness.latest_bench_gate = lambda repo: (bench_summary, data)
            try:
                readiness.check_bench_gate_artifact(result, Path("."))
            finally:
                readiness.latest_bench_gate = original_latest
        actual = [item["name"] for item in result["checks"] if not item.get("ok") and item["name"].startswith("bench_gate_static_low")]
        ok = actual == expected
        return CaseResult(
            name="static_low_bench_checks_are_exposed_in_readiness",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "static-low checks missing from readiness",
        )
    except Exception as exc:
        return CaseResult(
            name="static_low_bench_checks_are_exposed_in_readiness",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


class _TempBenchGate:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.path = Path("_research_readiness_selftest_bench_gate.json")

    def __enter__(self) -> Path:
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def run_science_precharge_relay_disabled_case() -> CaseResult:
    expected = [
        "full_preflight_precharge_relay_stage_disabled",
        "full_preflight_precharge_relay_status_off",
        "disabled PB4 state",
    ]
    source = Path(readiness.__file__).read_text(encoding="utf-8")
    actual = [token for token in expected if token in source]
    return CaseResult(
        name="science_precharge_relay_disabled_state_is_required",
        ok=actual == expected,
        expected=expected,
        actual=actual,
        detail="" if actual == expected else "science readiness does not require the disabled PB4/K1 state",
    )


def run_theory_snapshot_integrity_case() -> CaseResult:
    class ScienceArgs:
        profile = "science"

    result: dict[str, Any] = {"checks": []}
    repo = Path(readiness.__file__).resolve().parents[1]
    readiness.check_theory_snapshot(result, repo, ScienceArgs())
    check = result["checks"][0]
    expected = ["mic_theory_snapshot_integrity", "True", "fail"]
    actual = [str(check.get("name")), str(check.get("ok")), str(check.get("severity"))]
    return CaseResult(
        name="science_theory_snapshot_integrity_is_required",
        ok=actual == expected,
        expected=expected,
        actual=actual,
        detail="" if actual == expected else str(check.get("detail", "")),
    )


def run_motor_identification_hardware_gate_case() -> CaseResult:
    class ScienceArgs:
        profile = "science"
        motor_identification_result = ""

    data: dict[str, Any] = {
        "schema": readiness.MOTOR_IDENTIFICATION_RESULT_SCHEMA,
        "accepted": True,
        "decision": "accepted",
        "source_kind": "synthetic",
        "blockers": [],
        "claims": {"hardware_dataset_accepted": False},
        "contract": {"pass": True},
        "acceptance": {"pass": True, "checks": {"rank": True, "validation": True}},
        "rank_gate_prior": {"identifiable": True, "numerical_rank": 7, "required_rank": 7},
        "rank_gate_fitted": {"identifiable": True, "numerical_rank": 7, "required_rank": 7},
        "dataset": {
            "fit_experiments": ["fit-a"],
            "validation_experiments": ["validation-a"],
            "fit_run_ids": ["fit-run-a"],
            "validation_run_ids": ["validation-run-a"],
            "validation_samples": 100,
        },
        "integration": {"mic_ai_legacy_loader_compatible": True},
        "estimated_params": {name: 1.0 for name in ("Rs", "Rr", "Ls", "Lr", "Lm", "J", "B")},
    }
    expected = ["motor_identification_hardware_source", "capture_motor_identification_dataset", "hardware-pass"]
    try:
        with _TempBenchGate(data) as result_path:
            original_latest = readiness.latest_motor_identification
            readiness.latest_motor_identification = lambda repo, explicit_path="": (result_path, data)
            try:
                result: dict[str, Any] = {"checks": []}
                readiness.check_motor_identification_artifact(
                    result,
                    Path("."),
                    ScienceArgs(),
                    {"mtime": 0.0, "path": "", "prefixes": [], "files": []},
                )
                failed = [item for item in result["checks"] if not item.get("ok")]
                synthetic_failure = failed[0]["name"] if len(failed) == 1 else ""
                action_ids_value = action_ids(readiness.build_next_actions(failed, [], Args()))

                hardware = dict(data)
                hardware["source_kind"] = "hardware"
                hardware["claims"] = {"hardware_dataset_accepted": True}
                readiness.latest_motor_identification = lambda repo, explicit_path="": (result_path, hardware)
                hardware_result: dict[str, Any] = {"checks": []}
                readiness.check_motor_identification_artifact(
                    hardware_result,
                    Path("."),
                    ScienceArgs(),
                    {"mtime": 0.0, "path": "", "prefixes": [], "files": []},
                )
                hardware_pass = all(item.get("ok") for item in hardware_result["checks"])
            finally:
                readiness.latest_motor_identification = original_latest
        actual = [
            synthetic_failure,
            action_ids_value[0] if action_ids_value else "",
            "hardware-pass" if hardware_pass else "hardware-fail",
        ]
        return CaseResult(
            name="science_motor_identification_requires_accepted_hardware_data",
            ok=actual == expected,
            expected=expected,
            actual=actual,
            detail="" if actual == expected else "motor identification hardware gate mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="science_motor_identification_requires_accepted_hardware_data",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def cases() -> list[CaseResult]:
    return [
        run_bench_action_propagation_case(),
        run_static_low_action_command_case(),
        run_runtime_static_action_command_case(),
        run_uart_loopback_action_detail_case(),
        run_hmi_safe_action_command_case(),
        run_runtime_static_named_checks_case(),
        run_saleae_static_fresh_named_check_case(),
        run_saleae_static_failure_named_checks_case(),
        run_static_low_named_checks_case(),
        run_science_precharge_relay_disabled_case(),
        run_theory_snapshot_integrity_case(),
        run_motor_identification_hardware_gate_case(),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "research_readiness_check_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

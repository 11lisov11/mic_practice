#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bench_gate_report as gate


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: list[str]
    actual: list[str]
    detail: str = ""


def action_ids(actions: list[dict[str, str]]) -> list[str]:
    return [str(item.get("id", "")) for item in actions]


def action_values(actions: list[dict[str, str]], fields: list[str]) -> list[str]:
    return [str(item.get(field, "")) for item in actions for field in fields]


def run_case(name: str, protocol: dict[str, Any] | None, loopback: dict[str, Any] | None, expected: list[str]) -> CaseResult:
    try:
        actual = action_ids(gate.uart_next_actions(protocol, loopback))
        ok = actual == expected
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "action id mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_action_value_case(name: str, protocol: dict[str, Any] | None, loopback: dict[str, Any] | None, expected: list[str]) -> CaseResult:
    try:
        actions = gate.uart_next_actions(protocol, loopback)
        actual = action_values(actions, ["id", "command"])
        ok = actual == expected
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "action value mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_action_contains_case(name: str, protocol: dict[str, Any] | None, loopback: dict[str, Any] | None, expected: list[str]) -> CaseResult:
    try:
        actions = gate.uart_next_actions(protocol, loopback)
        detail = " ".join(str(item.get("detail", "")) for item in actions)
        actual = [item for item in expected if item in detail]
        ok = actual == expected
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else detail)
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_next_action_priority_case() -> CaseResult:
    expected = [
        "run_full_build_only_preflight",
        "run_uart_loopback",
        "restore_hmi_safe_status",
        "run_runtime_static_preflight",
        "run_static_low_isolation_preflight",
        "refresh_saleae_static_probe",
    ]
    try:
        raw = [
            {"id": "run_runtime_static_preflight"},
            {"id": "run_static_low_isolation_preflight"},
            {"id": "run_uart_loopback"},
            {"id": "restore_hmi_safe_status"},
            {"id": "refresh_saleae_static_probe"},
            {"id": "run_full_build_only_preflight"},
        ]
        actual = action_ids(gate.ordered_next_actions(raw))
        ok = actual == expected
        return CaseResult(name="next_actions_prioritize_uart_before_hv_off_preflights", ok=ok, expected=expected, actual=actual, detail="" if ok else "next action priority mismatch")
    except Exception as exc:
        return CaseResult(name="next_actions_prioritize_uart_before_hv_off_preflights", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_check_dicts_by_severity_case() -> CaseResult:
    expected = ["hard_fail", "soft_warn"]
    try:
        checks = [
            gate.Check("passed", True),
            gate.Check("hard_fail", False, detail="blocks PWM", severity="fail"),
            gate.Check("soft_warn", False, detail="operator warning", severity="warn"),
        ]
        failed = gate.check_dicts_by_severity(checks, "fail")
        warnings = gate.check_dicts_by_severity(checks, "warn")
        actual = [str(item.get("name", "")) for item in failed + warnings]
        ok = actual == expected and len(failed) == 1 and len(warnings) == 1
        return CaseResult(name="summary_failed_warning_checks_are_machine_readable", ok=ok, expected=expected, actual=actual, detail="" if ok else "severity split mismatch")
    except Exception as exc:
        return CaseResult(name="summary_failed_warning_checks_are_machine_readable", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_freshness_case() -> CaseResult:
    expected = ["newer.py"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "summary.json"
            old_source = root / "old.py"
            new_source = root / "newer.py"
            reference.write_text("{}", encoding="utf-8")
            old_source.write_text("old", encoding="utf-8")
            ref_time = time.time() + 10.0
            os.utime(old_source, (ref_time - 10.0, ref_time - 10.0))
            os.utime(reference, (ref_time, ref_time))
            new_source.write_text("new", encoding="utf-8")
            os.utime(new_source, (ref_time + 10.0, ref_time + 10.0))
            actual_paths = gate.stale_sources(reference, [old_source, new_source])
            actual = [Path(p).name for p in actual_paths]
            ok = actual == expected
            return CaseResult(name="build_preflight_freshness_detects_newer_source", ok=ok, expected=expected, actual=actual, detail="" if ok else "stale source mismatch")
    except Exception as exc:
        return CaseResult(name="build_preflight_freshness_detects_newer_source", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_full_preflight_check_case() -> CaseResult:
    expected = ["latest_build_only_preflight_fresh"]
    try:
        checks = gate.check_full_preflight(Path("summary.json"), {"summary": {"build_only_pass": True}}, newer_sources=["changed.py"])
        actual = [check.name for check in checks if not check.ok]
        ok = actual == expected
        return CaseResult(name="build_preflight_freshness_is_hard_fail", ok=ok, expected=expected, actual=actual, detail="" if ok else "check mismatch")
    except Exception as exc:
        return CaseResult(name="build_preflight_freshness_is_hard_fail", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_latest_build_only_selection_case() -> CaseResult:
    expected = ["build_only"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_dir = root / "full_system_preflight_old"
            new_dir = root / "full_system_preflight_new"
            old_dir.mkdir()
            new_dir.mkdir()
            old_summary = old_dir / "summary.json"
            new_summary = new_dir / "summary.json"
            old_summary.write_text(json.dumps({"summary": {"build_only": True, "build_only_pass": True}}), encoding="utf-8")
            new_summary.write_text(json.dumps({"summary": {"build_only": False, "build_pass": True}}), encoding="utf-8")
            now = time.time() + 20.0
            os.utime(old_summary, (now - 10.0, now - 10.0))
            os.utime(new_summary, (now, now))
            selected = gate.latest_build_only_preflight(root)
            actual = ["build_only"] if selected == old_summary else [str(selected)]
            ok = actual == expected
            return CaseResult(name="latest_preflight_selects_build_only_summary", ok=ok, expected=expected, actual=actual, detail="" if ok else "wrong summary selected")
    except Exception as exc:
        return CaseResult(name="latest_preflight_selects_build_only_summary", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_latest_saleae_recursive_selection_case() -> CaseResult:
    expected = ["nested"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "bluepill_runtime_static_preflight_new" / "saleae_highlevel_probe_nested"
            nested.mkdir(parents=True)
            summary = nested / "summary.json"
            summary.write_text(json.dumps({"channels": list(range(7))}), encoding="utf-8")
            selected = gate.latest_saleae_probe(root, set(range(7)))
            actual = ["nested"] if selected == summary else [str(selected)]
            ok = actual == expected
            return CaseResult(name="latest_saleae_probe_finds_nested_runtime_capture", ok=ok, expected=expected, actual=actual, detail="" if ok else "wrong Saleae summary selected")
    except Exception as exc:
        return CaseResult(name="latest_saleae_probe_finds_nested_runtime_capture", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_latest_saleae_skips_failed_command_case() -> CaseResult:
    expected = ["good"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / "saleae_highlevel_probe_bad"
            good = root / "saleae_highlevel_probe_good"
            bad.mkdir()
            good.mkdir()
            (good / "summary.json").write_text(
                json.dumps({"channels": list(range(7)), "command_pass": True, "tag": "good"}),
                encoding="utf-8",
            )
            (bad / "summary.json").write_text(
                json.dumps({"channels": list(range(7)), "command_pass": False, "tag": "bad"}),
                encoding="utf-8",
            )
            now = time.time() + 20.0
            os.utime(good / "summary.json", (now - 10.0, now - 10.0))
            os.utime(bad / "summary.json", (now, now))
            selected = gate.latest_saleae_probe(root, set(range(7)))
            summary = json.loads(selected.read_text(encoding="utf-8")) if selected else {}
            actual = [str(summary.get("tag", ""))]
            ok = actual == expected
            return CaseResult(name="latest_saleae_probe_skips_failed_command_capture", ok=ok, expected=expected, actual=actual, detail="" if ok else str(selected))
    except Exception as exc:
        return CaseResult(name="latest_saleae_probe_skips_failed_command_capture", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_latest_uart_skips_inventory_only_case() -> CaseResult:
    expected = ["protocol"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            protocol_dir = root / "bluepill_uart_diagnose_protocol"
            inventory_dir = root / "bluepill_uart_diagnose_inventory"
            protocol_dir.mkdir()
            inventory_dir.mkdir()
            protocol_summary = protocol_dir / "summary.json"
            inventory_summary = inventory_dir / "summary.json"
            protocol_summary.write_text(json.dumps({"loopback_mode": False, "inventory_only": False, "tag": "protocol"}), encoding="utf-8")
            inventory_summary.write_text(json.dumps({"loopback_mode": False, "inventory_only": True, "tag": "inventory"}), encoding="utf-8")
            now = time.time() + 20.0
            os.utime(protocol_summary, (now - 10.0, now - 10.0))
            os.utime(inventory_summary, (now, now))
            selected = gate.latest_uart_diagnose(root, loopback_mode=False)
            summary = json.loads(selected.read_text(encoding="utf-8")) if selected else {}
            actual = [str(summary.get("tag", ""))]
            ok = actual == expected
            return CaseResult(
                name="latest_uart_diagnose_skips_inventory_only_summaries",
                ok=ok,
                expected=expected,
                actual=actual,
                detail="" if ok else str(selected),
            )
    except Exception as exc:
        return CaseResult(
            name="latest_uart_diagnose_skips_inventory_only_summaries",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_latest_uart_inventory_only_selection_case() -> CaseResult:
    expected = ["inventory"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            protocol_dir = root / "bluepill_uart_diagnose_protocol"
            inventory_dir = root / "bluepill_uart_diagnose_inventory"
            protocol_dir.mkdir()
            inventory_dir.mkdir()
            protocol_summary = protocol_dir / "summary.json"
            inventory_summary = inventory_dir / "summary.json"
            protocol_summary.write_text(json.dumps({"loopback_mode": False, "inventory_only": False, "tag": "protocol"}), encoding="utf-8")
            inventory_summary.write_text(json.dumps({"loopback_mode": False, "inventory_only": True, "tag": "inventory"}), encoding="utf-8")
            now = time.time() + 20.0
            os.utime(protocol_summary, (now - 10.0, now - 10.0))
            os.utime(inventory_summary, (now, now))
            selected = gate.latest_uart_inventory_only(root)
            summary = json.loads(selected.read_text(encoding="utf-8")) if selected else {}
            actual = [str(summary.get("tag", ""))]
            ok = actual == expected
            return CaseResult(
                name="latest_uart_inventory_only_selects_inventory_summary",
                ok=ok,
                expected=expected,
                actual=actual,
                detail="" if ok else str(selected),
            )
    except Exception as exc:
        return CaseResult(
            name="latest_uart_inventory_only_selects_inventory_summary",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_uart_check_includes_inventory_only_evidence_case() -> CaseResult:
    expected = [
        "protocol_fail.json",
        "inventory.json",
        "COM3",
        "pyserial=['COM3']",
    ]
    try:
        protocol_path = Path("protocol_fail.json")
        inventory_path = Path("inventory.json")
        checks = gate.check_uart(
            protocol_path,
            {
                "protocol_pass": False,
                "selected_port": "COM3",
                "selected_port_summary": "COM3: WCH USB serial device",
                "visible_ports_summary": "pyserial=['COM3']; windows_pnp=['COM3']",
                "next_actions": [{"id": "run_loopback"}],
            },
            None,
            None,
            False,
            inventory_path,
            {
                "selected_port": "COM3",
                "visible_ports_summary": "pyserial=['COM3']; windows_pnp=['COM3']",
            },
        )
        uart_check = next((check for check in checks if check.name == "stm32_uart_protocol_pass"), None)
        evidence = uart_check.evidence if uart_check else {}
        actual = [
            Path(str(evidence.get("summary", ""))).name,
            Path(str(evidence.get("latest_inventory_only_summary", ""))).name,
            str(evidence.get("latest_inventory_only_selected_port", "")),
            str(evidence.get("latest_inventory_only_visible_ports", "")).split(";")[0],
        ]
        ok = actual == expected
        return CaseResult(
            name="uart_check_includes_inventory_only_evidence",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else str(evidence),
        )
    except Exception as exc:
        return CaseResult(
            name="uart_check_includes_inventory_only_evidence",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_runtime_static_missing_case() -> CaseResult:
    expected = ["latest_runtime_static_preflight_present"]
    try:
        checks = gate.check_runtime_static_preflight(None, None, Path("build.json"))
        actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
        ok = actual == expected
        return CaseResult(name="runtime_static_preflight_missing_blocks_active_pwm", ok=ok, expected=expected, actual=actual, detail="" if ok else "check mismatch")
    except Exception as exc:
        return CaseResult(name="runtime_static_preflight_missing_blocks_active_pwm", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_runtime_static_pass_case() -> CaseResult:
    expected: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build.json"
            runtime = root / "runtime.json"
            build.write_text("{}", encoding="utf-8")
            runtime.write_text("{}", encoding="utf-8")
            now = time.time() + 20.0
            os.utime(build, (now - 10.0, now - 10.0))
            os.utime(runtime, (now, now))
            checks = gate.check_runtime_static_preflight(
                runtime,
                {"pass": True, "dry_run": False, "static_checks": {"pwm_lines_low": True, "pattern": "all_pwm_low_safe"}},
                build,
            )
            actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
            ok = actual == expected
            return CaseResult(name="runtime_static_preflight_fresh_pass_allows_gate_stage", ok=ok, expected=expected, actual=actual, detail="" if ok else "check mismatch")
    except Exception as exc:
        return CaseResult(name="runtime_static_preflight_fresh_pass_allows_gate_stage", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_runtime_static_fingerprint_match_case() -> CaseResult:
    expected: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build.json"
            runtime = root / "runtime.json"
            build.write_text("{}", encoding="utf-8")
            runtime.write_text("{}", encoding="utf-8")
            now = time.time() + 20.0
            os.utime(runtime, (now - 10.0, now - 10.0))
            os.utime(build, (now, now))
            fp = {"sha256": "same-source"}
            checks = gate.check_runtime_static_preflight(
                runtime,
                {
                    "pass": True,
                    "dry_run": False,
                    "source_fingerprint": fp,
                    "static_checks": {"pwm_lines_low": True, "pattern": "all_pwm_low_safe"},
                },
                build,
                {"source_fingerprint": fp},
            )
            actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
            ok = actual == expected
            return CaseResult(name="runtime_static_fingerprint_match_overrides_mtime_order", ok=ok, expected=expected, actual=actual, detail="" if ok else "check mismatch")
    except Exception as exc:
        return CaseResult(name="runtime_static_fingerprint_match_overrides_mtime_order", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_runtime_static_fingerprint_mismatch_case() -> CaseResult:
    expected = ["runtime_static_preflight_fresh_for_build"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build.json"
            runtime = root / "runtime.json"
            build.write_text("{}", encoding="utf-8")
            runtime.write_text("{}", encoding="utf-8")
            now = time.time() + 20.0
            os.utime(build, (now - 10.0, now - 10.0))
            os.utime(runtime, (now, now))
            checks = gate.check_runtime_static_preflight(
                runtime,
                {
                    "pass": True,
                    "dry_run": False,
                    "source_fingerprint": {"sha256": "runtime-source"},
                    "static_checks": {"pwm_lines_low": True, "pattern": "all_pwm_low_safe"},
                },
                build,
                {"source_fingerprint": {"sha256": "build-source"}},
            )
            actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
            ok = actual == expected
            return CaseResult(name="runtime_static_fingerprint_mismatch_blocks_even_when_newer", ok=ok, expected=expected, actual=actual, detail="" if ok else "check mismatch")
    except Exception as exc:
        return CaseResult(name="runtime_static_fingerprint_mismatch_blocks_even_when_newer", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_runtime_static_stale_failed_case() -> CaseResult:
    expected = [
        "latest_runtime_static_preflight_pass",
        "runtime_static_preflight_fresh_for_build",
        "runtime_static_pwm_lines_low",
    ]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build.json"
            runtime = root / "runtime.json"
            build.write_text("{}", encoding="utf-8")
            runtime.write_text("{}", encoding="utf-8")
            now = time.time() + 20.0
            os.utime(runtime, (now - 10.0, now - 10.0))
            os.utime(build, (now, now))
            checks = gate.check_runtime_static_preflight(
                runtime,
                {"pass": False, "dry_run": False, "static_checks": {"pwm_lines_low": False, "pattern": "low_side_static_high"}},
                build,
            )
            actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
            ok = actual == expected
            return CaseResult(name="runtime_static_preflight_stale_or_failed_blocks_active_pwm", ok=ok, expected=expected, actual=actual, detail="" if ok else "check mismatch")
    except Exception as exc:
        return CaseResult(name="runtime_static_preflight_stale_or_failed_blocks_active_pwm", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_runtime_static_dry_run_case() -> CaseResult:
    expected = [
        "latest_runtime_static_preflight_pass",
        "runtime_static_preflight_fresh_for_build",
        "runtime_static_pwm_lines_low",
    ]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build.json"
            runtime = root / "runtime.json"
            build.write_text("{}", encoding="utf-8")
            runtime.write_text("{}", encoding="utf-8")
            now = time.time() + 20.0
            os.utime(build, (now - 10.0, now - 10.0))
            os.utime(runtime, (now, now))
            checks = gate.check_runtime_static_preflight(
                runtime,
                {"pass": True, "dry_run": True},
                build,
            )
            actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
            details = " ".join(check.detail for check in checks if not check.ok and check.detail)
            ok = actual == expected and "dry-run only" in details
            return CaseResult(
                name="runtime_static_dry_run_blocks_active_pwm",
                ok=ok,
                expected=expected + ["dry-run only detail"],
                actual=actual + ([details] if details else []),
                detail="" if ok else "dry-run gate mismatch",
            )
    except Exception as exc:
        return CaseResult(name="runtime_static_dry_run_blocks_active_pwm", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_static_low_missing_when_required_case() -> CaseResult:
    expected = ["latest_static_low_preflight_present"]
    try:
        checks = gate.check_static_low_preflight(None, None, Path("build.json"), required=True)
        actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
        ok = actual == expected
        return CaseResult(
            name="static_low_preflight_missing_is_exposed_when_pwm_static_blocked",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "static-low missing check mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="static_low_preflight_missing_is_exposed_when_pwm_static_blocked",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_static_low_pass_fresh_case() -> CaseResult:
    expected: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build.json"
            static_low = root / "static_low.json"
            build.write_text("{}", encoding="utf-8")
            static_low.write_text("{}", encoding="utf-8")
            now = time.time() + 20.0
            os.utime(build, (now - 10.0, now - 10.0))
            os.utime(static_low, (now, now))
            fp = {"sha256": "same-source"}
            checks = gate.check_static_low_preflight(
                static_low,
                {
                    "pass": True,
                    "dry_run": False,
                    "restored": True,
                    "source_fingerprint": fp,
                    "static_checks": {"pass": True, "pattern": "all_pwm_low_safe"},
                    "diagnostic_conclusion": {"result": "static_low_pin_drive_path_ok"},
                },
                build,
                {"source_fingerprint": fp},
                required=True,
            )
            actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
            ok = actual == expected
            return CaseResult(
                name="static_low_preflight_pass_fresh_is_diagnostic_evidence",
                ok=ok,
                expected=expected,
                actual=actual,
                detail="" if ok else "static-low pass/fresh check mismatch",
            )
    except Exception as exc:
        return CaseResult(
            name="static_low_preflight_pass_fresh_is_diagnostic_evidence",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_static_low_failed_or_stale_case() -> CaseResult:
    expected = ["latest_static_low_preflight_pass", "static_low_preflight_fresh_for_build"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build.json"
            static_low = root / "static_low.json"
            build.write_text("{}", encoding="utf-8")
            static_low.write_text("{}", encoding="utf-8")
            now = time.time() + 20.0
            os.utime(static_low, (now - 10.0, now - 10.0))
            os.utime(build, (now, now))
            checks = gate.check_static_low_preflight(
                static_low,
                {
                    "pass": False,
                    "dry_run": False,
                    "restored": True,
                    "source_fingerprint": {"sha256": "old-source"},
                    "static_checks": {"pass": False, "pattern": "low_side_static_high"},
                    "diagnostic_conclusion": {"result": "static_low_pin_drive_path_failed"},
                },
                build,
                {"source_fingerprint": {"sha256": "new-source"}},
                required=True,
            )
            actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
            ok = actual == expected
            return CaseResult(
                name="static_low_preflight_failed_or_stale_is_exposed",
                ok=ok,
                expected=expected,
                actual=actual,
                detail="" if ok else "static-low failed/stale check mismatch",
            )
    except Exception as exc:
        return CaseResult(
            name="static_low_preflight_failed_or_stale_is_exposed",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_operator_steps_render_case() -> CaseResult:
    expected = [
        "Active PWM НЕ запускать",
        "Ошибки gate: 2",
        "Предупреждения: 1",
        "run_runtime_static_preflight",
        "Отключи HV/J7",
        "дождись разряда DC-шины",
        "bluepill_runtime_static_preflight.py --confirm-hv-off",
        "bluepill_static_low_preflight.py --confirm-hv-off",
        "run_uart_loopback",
        "Отключи TX/RX USB-UART от STM32",
        "изолированной стороне адаптера COM3",
        "uart_loopback_preflight.py --confirm-loopback-wired --port COM3",
    ]
    forbidden = [
        "Fail checks:",
        "Warnings:",
        "HV/J7 disconnected and DC bus discharged.",
        "Short USB-UART TX to RX on the isolated side.",
    ]
    try:
        text = gate.render_operator_steps_ru(
            {
                "ready_for_active_pwm": False,
                "failed": 2,
                "warnings": 1,
                "next_actions": [
                    {
                        "id": "run_runtime_static_preflight",
                        "detail": "HV/J7 disconnected and DC bus discharged.",
                        "command": "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
                    },
                    {
                        "id": "run_uart_loopback",
                        "detail": "Short USB-UART TX to RX on the isolated side.",
                        "command": "py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080",
                    },
                ],
            }
        )
        actual = [item for item in expected if item in text]
        leaked = [item for item in forbidden if item in text]
        ok = actual == expected and not leaked
        return CaseResult(
            name="operator_steps_ru_contains_required_commands_and_guards",
            ok=ok,
            expected=expected,
            actual=actual + ([f"forbidden={leaked}"] if leaked else []),
            detail="" if ok else text,
        )
    except Exception as exc:
        return CaseResult(name="operator_steps_ru_contains_required_commands_and_guards", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_operator_static_low_steps_render_case() -> CaseResult:
    expected = [
        "run_static_low_isolation_preflight",
        "изоляционный тест",
        "low_side_static_high",
        "не запускает TIM1",
        "автоматически восстанавливает runtime-прошивку",
        "PB13/PB14/PB15",
        "входы IPM",
        "bluepill_static_low_preflight.py --confirm-hv-off",
        "Не выполнять `bluepill_static_low_preflight.py --confirm-hv-off`",
    ]
    forbidden = [
        "Observed SAFE/static PWM input HIGH",
        "After a fresh runtime static preflight",
        "diagnostic firmware to drive",
    ]
    try:
        text = gate.render_operator_steps_ru(
            {
                "ready_for_active_pwm": False,
                "failed": 1,
                "warnings": 0,
                "next_actions": [
                    {
                        "id": "run_static_low_isolation_preflight",
                        "detail": (
                            "Observed SAFE/static PWM input HIGH (pattern=low_side_static_high). "
                            "After a fresh runtime static preflight, use this diagnostic firmware to drive lines low."
                        ),
                        "command": "py -3 -u .\\tools\\bluepill_static_low_preflight.py --confirm-hv-off",
                    },
                ],
            }
        )
        actual = [item for item in expected if item in text]
        leaked = [item for item in forbidden if item in text]
        ok = actual == expected and not leaked
        return CaseResult(
            name="operator_steps_ru_contains_static_low_isolation_action",
            ok=ok,
            expected=expected,
            actual=actual + ([f"forbidden={leaked}"] if leaked else []),
            detail="" if ok else text,
        )
    except Exception as exc:
        return CaseResult(name="operator_steps_ru_contains_static_low_isolation_action", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_uart_check_preserves_diagnostic_evidence_case() -> CaseResult:
    expected = [
        "COM3: WCH USB serial device",
        "pyserial=['COM3']; windows_pnp=['COM6', 'COM3']",
        "True",
        "protocol_attempts:COM3@460800 SerialTimeoutException: Write timeout",
    ]
    try:
        checks = gate.check_uart(
            Path("uart.json"),
            {
                "protocol_pass": False,
                "selected_port": "COM3",
                "selected_port_summary": "COM3: WCH USB serial device",
                "visible_ports_summary": "pyserial=['COM3']; windows_pnp=['COM6', 'COM3']",
                "dtr_rts_matrix": True,
                "attempt_counts": {"protocol": 1, "open_ok": 1, "write_ok": 0, "write_timeouts": 1},
                "attempt_error_digest": ["protocol_attempts:COM3@460800 SerialTimeoutException: Write timeout"],
                "next_actions": [{"id": "host_cannot_write_uart"}],
            },
            None,
            None,
            False,
        )
        uart_check = next((check for check in checks if check.name == "stm32_uart_protocol_pass"), None)
        evidence = uart_check.evidence if uart_check is not None and isinstance(uart_check.evidence, dict) else {}
        actual = [
            str(evidence.get("selected_port_summary", "")),
            str(evidence.get("visible_ports_summary", "")),
            str(evidence.get("dtr_rts_matrix", "")),
            str((evidence.get("attempt_error_digest") or [""])[0]),
        ]
        ok = actual == expected
        return CaseResult(name="uart_check_preserves_diagnostic_evidence", ok=ok, expected=expected, actual=actual, detail="" if ok else "UART evidence mismatch")
    except Exception as exc:
        return CaseResult(name="uart_check_preserves_diagnostic_evidence", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_saleae_static_pwm_level_case(name: str, levels: list[int], expected: list[str]) -> CaseResult:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "digital.csv"
            header = "Time [s]," + ",".join(f"Channel {ch}" for ch in range(7))
            row = "0.000000000," + ",".join(str(level) for level in levels)
            csv_path.write_text(header + "\n" + row + "\n", encoding="utf-8")
            probe = {
                "channels": list(range(7)),
                "edges": {str(ch): 0 for ch in range(7)},
                "csv": str(csv_path),
            }
            analysis = {"no_overlap_pass": True}
            checks = gate.check_saleae(root / "summary.json", probe, analysis)
            actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
            ok = actual == expected
            return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "saleae static level check mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_saleae_static_summary_level_case() -> CaseResult:
    expected = [
        "saleae_static_pwm_lines_low",
        "low_side_static_high",
        "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
        "PWM_STATIC_BLOCKER_RU.md",
        "CH1:PB13",
        "Measure PB13/PB14/PB15",
        "IPM logic input",
    ]
    try:
        probe = {
            "channels": list(range(7)),
            "edges": {str(ch): 0 for ch in range(7)},
            "levels": {
                str(ch): {"initial": level, "final": level}
                for ch, level in enumerate([0, 1, 0, 1, 0, 1, 0])
            },
        }
        analysis = {"no_overlap_pass": True}
        checks = gate.check_saleae(Path("summary.json"), probe, analysis)
        failing = next((check for check in checks if check.name == "saleae_static_pwm_lines_low"), None)
        actual = []
        if failing is not None and not failing.ok:
            actual.append(failing.name)
            if isinstance(failing.evidence, dict):
                actual.append(str(failing.evidence.get("pattern", "")))
                remediation = failing.evidence.get("remediation", {})
                if isinstance(remediation, dict):
                    actual.append(str(remediation.get("required_command", "")))
                    steps = remediation.get("steps", [])
                    if isinstance(steps, list) and any("PWM_STATIC_BLOCKER_RU.md" in str(step) for step in steps):
                        actual.append("PWM_STATIC_BLOCKER_RU.md")
                    channel_map = remediation.get("channel_map", [])
                    if isinstance(channel_map, list):
                        ch1 = next((item for item in channel_map if isinstance(item, dict) and item.get("channel") == "CH1"), {})
                        actual.append(f"CH1:{ch1.get('stm32', '')}")
                    measurement_points = remediation.get("measurement_points", [])
                    if isinstance(measurement_points, list):
                        if any("PB13/PB14/PB15" in str(item) for item in measurement_points):
                            actual.append("Measure PB13/PB14/PB15")
                        if any("IPM logic input" in str(item) for item in measurement_points):
                            actual.append("IPM logic input")
        ok = actual == expected
        return CaseResult(name="saleae_summary_levels_classify_low_side_high", ok=ok, expected=expected, actual=actual, detail="" if ok else "summary level pattern mismatch")
    except Exception as exc:
        return CaseResult(name="saleae_summary_levels_classify_low_side_high", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_saleae_failed_command_case() -> CaseResult:
    expected = ["saleae_probe_commands_passed"]
    try:
        probe = {
            "channels": list(range(7)),
            "command_pass": False,
            "commands": [{"cmd": "START", "ok": False}],
            "edges": {str(ch): 0 for ch in range(7)},
            "levels": {str(ch): {"initial": 0, "final": 0} for ch in range(7)},
        }
        analysis = {"no_overlap_pass": True}
        checks = gate.check_saleae(Path("summary.json"), probe, analysis)
        actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
        ok = actual == expected
        return CaseResult(name="saleae_failed_command_capture_blocks_static_evidence", ok=ok, expected=expected, actual=actual, detail="" if ok else "failed command check mismatch")
    except Exception as exc:
        return CaseResult(name="saleae_failed_command_capture_blocks_static_evidence", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_saleae_probe_static_flag_case() -> CaseResult:
    expected = ["saleae_probe_pwm_static_safe_flag"]
    try:
        probe = {
            "channels": list(range(7)),
            "command_pass": True,
            "edges": {str(ch): 0 for ch in range(7)},
            "levels": {str(ch): {"initial": 0, "final": 0} for ch in range(7)},
            "pwm_static_checks": {
                "pwm_static_safe_pass": False,
                "pattern": "low_side_static_high",
            },
        }
        analysis = {"no_overlap_pass": True}
        checks = gate.check_saleae(Path("summary.json"), probe, analysis)
        actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
        ok = actual == expected
        return CaseResult(name="saleae_probe_static_safe_flag_blocks_active_pwm", ok=ok, expected=expected, actual=actual, detail="" if ok else "static flag check mismatch")
    except Exception as exc:
        return CaseResult(name="saleae_probe_static_safe_flag_blocks_active_pwm", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_saleae_strict_static_exit_case() -> CaseResult:
    expected = ["saleae_strict_static_safe_exit"]
    try:
        probe = {
            "channels": list(range(7)),
            "command_pass": True,
            "require_static_safe": True,
            "require_static_safe_pass": False,
            "exit_code": 5,
            "exit_reason": "static-safe requirement failed: pattern=low_side_static_high",
            "edges": {str(ch): 0 for ch in range(7)},
            "levels": {str(ch): {"initial": 0, "final": 0} for ch in range(7)},
            "pwm_static_checks": {
                "pwm_static_safe_pass": True,
                "pattern": "all_pwm_low_safe",
            },
        }
        analysis = {"no_overlap_pass": True}
        checks = gate.check_saleae(Path("summary.json"), probe, analysis)
        actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
        ok = actual == expected
        return CaseResult(
            name="saleae_strict_static_safe_exit_blocks_active_pwm",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "strict static-safe exit check mismatch",
        )
    except Exception as exc:
        return CaseResult(name="saleae_strict_static_safe_exit_blocks_active_pwm", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_saleae_non_strict_exit_code_does_not_create_strict_fail_case() -> CaseResult:
    expected: list[str] = []
    try:
        probe = {
            "channels": list(range(7)),
            "command_pass": True,
            "require_static_safe": False,
            "require_static_safe_pass": None,
            "exit_code": 0,
            "edges": {str(ch): 0 for ch in range(7)},
            "levels": {str(ch): {"initial": 0, "final": 0} for ch in range(7)},
            "pwm_static_checks": {
                "pwm_static_safe_pass": True,
                "pattern": "all_pwm_low_safe",
            },
        }
        analysis = {"no_overlap_pass": True}
        checks = gate.check_saleae(Path("summary.json"), probe, analysis)
        actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
        ok = actual == expected
        return CaseResult(
            name="saleae_non_strict_exit_code_does_not_create_strict_fail",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "non-strict Saleae capture created hard fail",
        )
    except Exception as exc:
        return CaseResult(
            name="saleae_non_strict_exit_code_does_not_create_strict_fail",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_saleae_sample_rate_warning_case() -> CaseResult:
    expected = ["saleae_static_sample_rate_meets_requested"]
    try:
        probe = {
            "channels": list(range(7)),
            "command_pass": True,
            "requested_rate": 24_000_000,
            "selected_rate": 500_000,
            "selected_sample_period_ns": 2000.0,
            "edges": {str(ch): 0 for ch in range(7)},
            "levels": {str(ch): {"initial": 0, "final": 0} for ch in range(7)},
            "pwm_static_checks": {
                "pwm_static_safe_pass": True,
                "pattern": "all_pwm_low_safe",
            },
        }
        analysis = {"no_overlap_pass": True}
        checks = gate.check_saleae(Path("summary.json"), probe, analysis)
        actual = [check.name for check in checks if not check.ok and check.severity == "warn"]
        hard_fails = [check.name for check in checks if not check.ok and check.severity == "fail"]
        ok = actual == expected and hard_fails == []
        return CaseResult(
            name="saleae_degraded_sample_rate_is_warning_not_deadtime_proof",
            ok=ok,
            expected=expected,
            actual=actual + hard_fails,
            detail="" if ok else "sample-rate warning mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="saleae_degraded_sample_rate_is_warning_not_deadtime_proof",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_saleae_stale_for_build_case() -> CaseResult:
    expected = ["saleae_static_probe_fresh_for_build"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saleae_summary = root / "saleae_summary.json"
            build_summary = root / "build_summary.json"
            saleae_summary.write_text("{}", encoding="utf-8")
            build_summary.write_text("{}", encoding="utf-8")
            now = time.time() + 20.0
            os.utime(saleae_summary, (now - 10.0, now - 10.0))
            os.utime(build_summary, (now, now))
            probe = {
                "channels": list(range(7)),
                "command_pass": True,
                "edges": {str(ch): 0 for ch in range(7)},
                "levels": {str(ch): {"initial": 0, "final": 0} for ch in range(7)},
                "pwm_static_checks": {
                    "pwm_static_safe_pass": True,
                    "pattern": "all_pwm_low_safe",
                },
            }
            analysis = {"no_overlap_pass": True}
            checks = gate.check_saleae(saleae_summary, probe, analysis, build_summary)
            actual = [check.name for check in checks if not check.ok and check.severity == "fail"]
            ok = actual == expected
            return CaseResult(
                name="saleae_static_capture_must_be_fresh_for_latest_build",
                ok=ok,
                expected=expected,
                actual=actual,
                detail="" if ok else "Saleae freshness check mismatch",
            )
    except Exception as exc:
        return CaseResult(
            name="saleae_static_capture_must_be_fresh_for_latest_build",
            ok=False,
            expected=expected,
            actual=[],
            detail=f"{type(exc).__name__}: {exc}",
        )


def live_status_fail_names(status: dict[str, Any]) -> list[str]:
    return [check.name for check in gate.check_live_status(status) if not check.ok and check.severity == "fail"]


def run_live_status_unavailable_case() -> CaseResult:
    expected = ["live_hmi_status_available"]
    try:
        actual = live_status_fail_names({"ok": False, "error": "URLError: timed out"})
        ok = actual == expected
        return CaseResult(name="live_hmi_unavailable_blocks_active_pwm", ok=ok, expected=expected, actual=actual, detail="" if ok else "live status should be hard fail")
    except Exception as exc:
        return CaseResult(name="live_hmi_unavailable_blocks_active_pwm", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_live_status_safe_case() -> CaseResult:
    expected: list[str] = []
    try:
        actual = live_status_fail_names(
            {
                "ok": True,
                "data": {
                    "data": {
                        "state": "SAFE",
                        "pwm": 0,
                        "enable": False,
                        "estop": 0,
                        "bp_fault": 0,
                        "bp_bad_cnt": 0,
                    }
                },
            }
        )
        ok = actual == expected
        return CaseResult(name="live_hmi_safe_status_passes_gate_stage", ok=ok, expected=expected, actual=actual, detail="" if ok else "safe HMI status was rejected")
    except Exception as exc:
        return CaseResult(name="live_hmi_safe_status_passes_gate_stage", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_live_unoq_transport_proves_uart_case() -> CaseResult:
    expected = [True, "live_hmi_bluepill_status"]
    try:
        checks = gate.check_uart(
            Path("pc_uart_failed.json"),
            {"protocol_pass": False, "next_actions": [{"id": "write_ok_no_bluepill_response"}]},
            None,
            None,
            False,
            live_status={
                "ok": True,
                "data": {
                    "state": "SAFE",
                    "pwm": 0,
                    "bp_status": 1,
                    "bp_rsp_age_ms": 4,
                    "bp_good_cnt": 120,
                    "bp_bad_cnt": 0,
                    "bp_bad": 0,
                },
            },
        )
        uart = next(check for check in checks if check.name == "stm32_uart_protocol_pass")
        live = (uart.evidence or {}).get("live_transport") or uart.evidence or {}
        actual = [uart.ok, str(live.get("source", ""))]
        ok = actual == expected
        return CaseResult(name="live_unoq_transport_proves_uart", ok=ok, expected=expected, actual=actual, detail="" if ok else str(uart.evidence))
    except Exception as exc:
        return CaseResult(name="live_unoq_transport_proves_uart", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_live_status_unsafe_case() -> CaseResult:
    expected = [
        "live_hmi_safe_state",
        "live_hmi_not_running_pwm",
        "live_hmi_estop_clear",
        "live_hmi_bluepill_fault_clear",
        "live_hmi_bluepill_bad_count_clear",
    ]
    try:
        actual = live_status_fail_names(
            {
                "ok": True,
                "data": {
                    "state": "VF_RUN",
                    "pwm": 1,
                    "enable": True,
                    "estop": 1,
                    "bp_fault": 2,
                    "bp_bad": 3,
                },
            }
        )
        ok = actual == expected
        return CaseResult(name="live_hmi_unsafe_status_blocks_active_pwm", ok=ok, expected=expected, actual=actual, detail="" if ok else "unsafe HMI fail names mismatch")
    except Exception as exc:
        return CaseResult(name="live_hmi_unsafe_status_blocks_active_pwm", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def cases() -> list[CaseResult]:
    return [
        run_case("protocol_pass_has_no_action", {"protocol_pass": True}, None, []),
        run_case(
            "write_timeout_needs_loopback",
            {
                "protocol_pass": False,
                "next_actions": [
                    {"id": "host_cannot_write_uart"},
                    {
                        "id": "run_loopback",
                        "command": "py -3 -u .\\tools\\bluepill_uart_diagnose.py --port COM9 --loopback --bauds 115200 --timeout 0.5 --write-timeout 2.0",
                    },
                ],
            },
            None,
            ["run_uart_loopback"],
        ),
        run_action_value_case(
            "write_timeout_loopback_command_is_preserved",
            {
                "protocol_pass": False,
                "next_actions": [
                    {"id": "host_cannot_write_uart"},
                    {
                        "id": "run_loopback",
                        "command": "py -3 -u .\\tools\\bluepill_uart_diagnose.py --port COM9 --loopback --bauds 115200 --timeout 0.5 --write-timeout 2.0",
                    },
                ],
            },
            None,
            [
                "run_uart_loopback",
                "py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port COM9 --bauds 115200 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080",
            ],
        ),
        run_action_contains_case(
            "write_timeout_loopback_detail_preserves_inventory",
            {
                "protocol_pass": False,
                "next_actions": [
                    {
                        "id": "host_cannot_write_uart",
                        "detail": "Selected port: COM3: WCH USB serial device. Visible ports: pyserial=['COM3']; windows_pnp=['COM6', 'COM3'].",
                    },
                    {
                        "id": "run_loopback",
                        "command": "py -3 -u .\\tools\\bluepill_uart_diagnose.py --port COM3 --loopback --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0",
                    },
                ],
            },
            None,
            [
                "Selected port: COM3",
                "windows_pnp=['COM6', 'COM3']",
                "Disconnect USB-UART TX/RX from STM32",
                "uart_loopback_preflight.py",
                "starts PC-direct HMI again",
                "UART_LOOPBACK_STEPS_RU.md",
                "Do not run unoq_web_server",
            ],
        ),
        run_uart_check_preserves_diagnostic_evidence_case(),
        run_case(
            "loopback_failed_blocks_adapter",
            {"protocol_pass": False, "next_actions": [{"id": "host_cannot_write_uart"}, {"id": "run_loopback"}]},
            {"loopback_pass": False},
            ["fix_usb_uart_loopback"],
        ),
        run_case(
            "loopback_missing_confirm_keeps_run_loopback_action",
            {"protocol_pass": False, "next_actions": [{"id": "host_cannot_write_uart"}, {"id": "run_loopback"}]},
            {
                "loopback_pass": False,
                "blocked": True,
                "loopback_confirm_required_missing": True,
                "next_actions": [{"id": "confirm_loopback_wiring"}],
            },
            ["run_uart_loopback"],
        ),
        run_action_contains_case(
            "loopback_missing_confirm_detail_is_not_adapter_failure",
            {"protocol_pass": False, "next_actions": [{"id": "host_cannot_write_uart"}, {"id": "run_loopback"}]},
            {
                "loopback_pass": False,
                "blocked": True,
                "loopback_confirm_required_missing": True,
                "next_actions": [{"id": "confirm_loopback_wiring"}],
            },
            [
                "blocked before opening the COM port",
                "physical TX/RX loopback wiring was not confirmed",
                "Disconnect USB-UART TX/RX from STM32",
            ],
        ),
        run_case(
            "loopback_ok_needs_stm32_protocol_retry",
            {"protocol_pass": False, "next_actions": [{"id": "host_cannot_write_uart"}, {"id": "run_loopback"}]},
            {"loopback_pass": True},
            ["reconnect_stm32_uart_and_rerun_protocol"],
        ),
        run_case(
            "write_ok_no_response_checks_stm32_side",
            {"protocol_pass": False, "next_actions": [{"id": "write_ok_no_bluepill_response"}]},
            None,
            ["check_stm32_uart_wiring_or_firmware"],
        ),
        run_case(
            "port_open_error_closes_users",
            {"protocol_pass": False, "next_actions": [{"id": "port_open_error"}]},
            None,
            ["close_com_port_users"],
        ),
        run_case("unknown_uart_failure_requires_inspection", {"protocol_pass": False, "next_actions": []}, None, ["inspect_uart_diagnose_summary"]),
        run_next_action_priority_case(),
        run_check_dicts_by_severity_case(),
        run_freshness_case(),
        run_full_preflight_check_case(),
        run_latest_build_only_selection_case(),
        run_latest_saleae_recursive_selection_case(),
        run_latest_saleae_skips_failed_command_case(),
        run_latest_uart_skips_inventory_only_case(),
        run_latest_uart_inventory_only_selection_case(),
        run_uart_check_includes_inventory_only_evidence_case(),
        run_runtime_static_missing_case(),
        run_runtime_static_pass_case(),
        run_runtime_static_fingerprint_match_case(),
        run_runtime_static_fingerprint_mismatch_case(),
        run_runtime_static_stale_failed_case(),
        run_runtime_static_dry_run_case(),
        run_static_low_missing_when_required_case(),
        run_static_low_pass_fresh_case(),
        run_static_low_failed_or_stale_case(),
        run_operator_steps_render_case(),
        run_operator_static_low_steps_render_case(),
        run_saleae_static_pwm_level_case("saleae_safe_requires_pwm_lines_low", [0, 0, 0, 0, 0, 0, 0], []),
        run_saleae_static_pwm_level_case("saleae_low_side_static_high_blocks_pwm", [0, 1, 0, 1, 0, 1, 0], ["saleae_static_pwm_lines_low"]),
        run_saleae_static_summary_level_case(),
        run_saleae_failed_command_case(),
        run_saleae_probe_static_flag_case(),
        run_saleae_strict_static_exit_case(),
        run_saleae_non_strict_exit_code_does_not_create_strict_fail_case(),
        run_saleae_sample_rate_warning_case(),
        run_saleae_stale_for_build_case(),
        run_live_status_unavailable_case(),
        run_live_status_safe_case(),
        run_live_unoq_transport_proves_uart_case(),
        run_live_status_unsafe_case(),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "bench_gate_report_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

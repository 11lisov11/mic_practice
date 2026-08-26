#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import current_bench_status as status


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    expected: Any = None
    actual: Any = None


def add_case(results: list[CaseResult], name: str, ok: bool, detail: str = "", expected: Any = None, actual: Any = None) -> None:
    results.append(CaseResult(name=name, ok=bool(ok), detail=detail, expected=expected, actual=actual))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def run_red_gate_case(results: list[CaseResult]) -> None:
    expected = [
        "Active PWM сейчас **не запускать**",
        "Active PWM разрешен: **НЕТ**",
        "Build-only preflight свежий и прошел: **ДА**",
        "run_runtime_static_preflight",
        "Отключи HV/J7",
        "bluepill_runtime_static_preflight.py --confirm-hv-off",
        "run_uart_loopback",
        "Отключи TX/RX USB-UART от STM32",
        "Не запускай `unoq_web_server.py` на этом COM-порту",
        "Не держать HMI/serial monitor открытым во время UART loopback",
        "uart_loopback_preflight.py --confirm-loopback-wired --port COM3",
        "Bench-gate summary:",
        "Build-only summary:",
        "Readiness summary:",
    ]
    forbidden = [
        "Active PWM разрешен: **ДА**",
        "HV/J7 disconnected and DC bus discharged.",
        "Short USB-UART TX to RX on the isolated side.",
    ]
    with tempfile.TemporaryDirectory(prefix="current_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        bench_path = repo / "tools/_preflight_exports/bench_gate_report_20260704_010000/summary.json"
        readiness_path = repo / "tools/_readiness_exports/research_readiness_20260704_010001/summary.json"
        build_path = repo / "tools/_preflight_exports/full_system_preflight_20260704_010002/summary.json"
        steps_path = bench_path.parent / "NEXT_STEPS_RU.md"
        write_json(
            bench_path,
            {
                "ready_for_active_pwm": False,
                "failed": 5,
                "warnings": 2,
                "operator_steps_ru": str(steps_path),
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
            },
        )
        write_json(readiness_path, {"ready": False})
        write_json(build_path, {"summary": {"build_only": True, "build_only_pass": True}})
        text, payload = status.build_current_status(repo)
        actual = [item for item in expected if item in text]
        leaked = [item for item in forbidden if item in text]
        ok = actual == expected and not leaked and payload["next_actions"] == ["run_runtime_static_preflight", "run_uart_loopback"]
        add_case(
            results,
            "red_gate_renders_russian_operator_status",
            ok,
            detail="" if ok else text,
            expected=expected,
            actual=actual + ([f"forbidden={leaked}"] if leaked else []),
        )


def run_missing_gate_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="current_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        text, payload = status.build_current_status(repo)
        expected = [
            "Active PWM разрешен: **НЕТ**",
            "Нет готового списка `next_actions`",
            "bench_gate_report.py --url http://127.0.0.1:18080",
            "Bench-gate summary: `нет`",
        ]
        actual = [item for item in expected if item in text]
        ok = actual == expected and payload["bench_summary"] == "нет"
        add_case(results, "missing_gate_fails_closed", ok, detail="" if ok else text, expected=expected, actual=actual)


def run_nucleo_backend_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="current_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        bench_path = repo / "tools/_preflight_exports/bench_gate_report_20260704_010000/summary.json"
        readiness_path = repo / "tools/_readiness_exports/research_readiness_20260704_010001/summary.json"
        build_path = repo / "tools/_preflight_exports/full_system_preflight_20260704_010002/summary.json"
        write_json(
            bench_path,
            {
                "ready_for_active_pwm": False,
                "next_actions": [
                    {
                        "id": "run_runtime_static_preflight",
                        "command": "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
                    }
                ],
            },
        )
        write_json(
            readiness_path,
            {
                "ready": False,
                "active_motor_backend": "nucleo_mcsdk_acim",
                "latest_nucleo_mcsdk_preflight": "nucleo-build.json",
                "latest_nucleo_mcsdk_runtime_preflight": None,
                "failed_checks": [
                    {
                        "name": "nucleo_mcsdk_runtime_validation",
                        "detail": "hardware runtime proof is pending",
                    }
                ],
                "next_actions": [
                    {
                        "id": "validate_nucleo_mcsdk_hardware",
                        "detail": "Flash Nucleo and verify UART/static PWM.",
                    }
                ],
            },
        )
        write_json(build_path, {"summary": {"build_only": True, "build_only_pass": True}})
        text, payload = status.build_current_status(repo)
        expected = [
            "Активный motor backend: `nucleo_mcsdk_acim`",
            "validate_nucleo_mcsdk_hardware",
            "`nucleo_mcsdk_runtime_validation`",
            "Nucleo MCSDK build preflight: `nucleo-build.json`",
            "Nucleo MCSDK runtime preflight: `нет`",
        ]
        actual = [item for item in expected if item in text]
        forbidden = [
            "run_runtime_static_preflight",
            "bluepill_runtime_static_preflight.py",
            "Bench-gate operator steps:",
        ]
        leaked = [item for item in forbidden if item in text]
        ok = (
            actual == expected
            and not leaked
            and payload["active_motor_backend"] == "nucleo_mcsdk_acim"
            and payload["next_actions"] == ["validate_nucleo_mcsdk_hardware"]
        )
        add_case(
            results,
            "nucleo_backend_uses_active_readiness_actions",
            ok,
            detail="" if ok else text,
            expected=expected,
            actual=actual + ([f"forbidden={leaked}"] if leaked else []),
        )


def run_stale_build_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="current_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        bench_path = repo / "tools/_preflight_exports/bench_gate_report_20260704_011000/summary.json"
        build_path = repo / "tools/_preflight_exports/full_system_preflight_20260704_011001/summary.json"
        readiness_path = repo / "tools/_readiness_exports/research_readiness_20260704_011002/summary.json"
        write_json(
            bench_path,
            {
                "ready_for_active_pwm": False,
                "next_actions": [
                    {"id": "run_full_build_only_preflight"},
                    {
                        "id": "run_runtime_static_preflight",
                        "command": "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
                    },
                ],
            },
        )
        write_json(build_path, {"summary": {"build_only": True, "build_only_pass": True}})
        write_json(readiness_path, {"ready": False})
        text, payload = status.build_current_status(repo)
        expected = [
            "Build-only preflight свежий и прошел: **НЕТ**",
            "run_full_build_only_preflight",
            "run_runtime_static_preflight",
        ]
        forbidden = ["Build-only preflight свежий и прошел: **ДА**"]
        actual = [item for item in expected if item in text]
        leaked = [item for item in forbidden if item in text]
        ok = actual == expected and not leaked and payload.get("build_only_fresh_and_passed") is False
        add_case(
            results,
            "stale_build_action_marks_build_not_fresh",
            ok,
            detail="" if ok else text,
            expected=expected,
            actual=actual + ([f"forbidden={leaked}"] if leaked else []),
        )


def run_failure_digest_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="current_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        bench_path = repo / "tools/_preflight_exports/bench_gate_report_20260704_012000/summary.json"
        build_path = repo / "tools/_preflight_exports/full_system_preflight_20260704_012001/summary.json"
        readiness_path = repo / "tools/_readiness_exports/research_readiness_20260704_012002/summary.json"
        runtime_path = repo / "tools/_preflight_exports/bluepill_runtime_static_preflight_20260704_012003/summary.json"
        uart_path = repo / "tools/_preflight_exports/bluepill_uart_diagnose_20260704_012004/summary.json"
        uart_inventory_path = repo / "tools/_preflight_exports/bluepill_uart_diagnose_20260704_012004_inventory/summary.json"
        static_low_path = repo / "tools/_preflight_exports/bluepill_static_low_preflight_20260704_012006/summary.json"
        saleae_csv = repo / "tools/_preflight_exports/saleae_highlevel_probe_20260704_012005/digital.csv"
        write_json(
            uart_path,
            {
                "protocol_pass": False,
                "next_actions": [{"id": "host_cannot_write_uart"}, {"id": "run_loopback"}],
                "selected_port_summary": "COM3: WCH USB serial device; verify this is the isolated USB-UART wired to STM32 PA2/PA3",
                "visible_ports_summary": "pyserial=['COM3']; windows_pnp=['COM6', 'COM3', 'COM10']",
                "dtr_rts_matrix": True,
                "attempt_counts": {
                    "protocol": 16,
                    "open_ok": 16,
                    "write_returned": 0,
                    "write_ok": 0,
                    "flush_ok": 0,
                    "write_timeouts": 16,
                    "flush_timeouts": 0,
                    "no_response": 0,
                    "responses": 0,
                },
                "attempt_error_digest": [
                    "protocol_attempts:COM3@460800 SerialTimeoutException: Write timeout",
                    "protocol_attempts:COM3@115200 SerialTimeoutException: Write timeout",
                ],
                "protocol_attempts": [{"error": "SerialTimeoutException: Write timeout"}],
            },
        )
        write_json(runtime_path, {"pass": True, "dry_run": True})
        write_json(
            bench_path,
            {
                "ready_for_active_pwm": False,
                "evidence": {
                    "bluepill_runtime_static_preflight": str(runtime_path),
                    "bluepill_uart_protocol_diagnose": str(uart_path),
                    "bluepill_uart_inventory_only": str(uart_inventory_path),
                    "bluepill_static_low_preflight": str(static_low_path),
                },
                "checks": [
                    {"name": "latest_runtime_static_preflight_pass", "ok": False},
                    {
                        "name": "saleae_static_pwm_lines_low",
                        "ok": False,
                        "evidence": {
                            "pattern": "low_side_static_high",
                            "csv": str(saleae_csv),
                            "levels": {
                                "0": {"initial": 0, "final": 0},
                                "1": {"initial": 1, "final": 1},
                                "2": {"initial": 0, "final": 0},
                                "3": {"initial": 1, "final": 1},
                                "4": {"initial": 0, "final": 0},
                                "5": {"initial": 1, "final": 1},
                                "6": {"initial": 0, "final": 0},
                            },
                        },
                    },
                    {
                        "name": "latest_static_low_preflight_pass",
                        "ok": False,
                        "evidence": {
                            "summary": str(static_low_path),
                            "static_checks": {"pattern": "low_side_static_high"},
                            "diagnostic_conclusion": {"result": "static_low_pin_drive_path_failed"},
                        },
                    },
                    {
                        "name": "saleae_static_probe_fresh_for_build",
                        "ok": False,
                        "evidence": {
                            "saleae_summary": str(repo / "tools/_preflight_exports/saleae_highlevel_probe_20260704_012005/summary.json"),
                            "full_system_preflight": str(build_path),
                        },
                    },
                    {
                        "name": "saleae_strict_static_safe_exit",
                        "ok": False,
                        "evidence": {
                            "summary": str(repo / "tools/_preflight_exports/saleae_highlevel_probe_20260704_012005/summary.json"),
                            "require_static_safe": True,
                            "require_static_safe_pass": False,
                            "exit_code": 5,
                            "exit_reason": "static-safe requirement failed: pattern=low_side_static_high",
                        },
                    },
                    {
                        "name": "stm32_uart_protocol_pass",
                        "ok": False,
                        "evidence": {
                            "latest_inventory_only_summary": str(uart_inventory_path),
                            "latest_inventory_only_selected_port": "COM3",
                            "latest_inventory_only_visible_ports": "pyserial=['COM3']; windows_pnp=['COM3']",
                        },
                    },
                    {"name": "live_hmi_status_available", "ok": False, "detail": "URLError: timed out"},
                ],
                "next_actions": [
                    {
                        "id": "run_runtime_static_preflight",
                        "command": "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
                    },
                    {
                        "id": "run_uart_loopback",
                        "command": "py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080",
                    },
                ],
            },
        )
        write_json(build_path, {"summary": {"build_only": True, "build_only_pass": True}})
        write_json(readiness_path, {"ready": False})
        text, _payload = status.build_current_status(repo)
        expected = [
            "Почему gate красный",
            "Runtime-static:",
            "свежий build-only доказывает только сборку",
            "Blue Pill считается неподтвержденным",
            "low_side_static_high",
            "CH1/PB13",
            "CH3/PB14",
            "CH5/PB15",
            "require_static_safe_pass=False",
            "exit_code=5",
            "static-safe requirement failed: pattern=low_side_static_high",
            "UART STM32:",
            "host_cannot_write_uart,run_loopback",
            "COM3: WCH USB serial device",
            "pyserial=['COM3']; windows_pnp=['COM6', 'COM3', 'COM10']",
            "DTR/RTS matrix=tried",
            "write_timeouts=16",
            "write_returned=0",
            "flush_ok=0",
            "Saleae freshness:",
            "capture:",
            "build:",
            "static capture CH0..CH6",
            "Static-low isolation:",
            "static_low_pin_drive_path_failed",
            "protocol_attempts:COM3@460800 SerialTimeoutException: Write timeout",
            "SerialTimeoutException: Write timeout",
            "UART inventory-only:",
            "не доказывает protocol/link",
            "selected=COM3",
            "visible=pyserial=['COM3']; windows_pnp=['COM3']",
            "HMI /api/status",
        ]
        actual = [item for item in expected if item in text]
        ok = actual == expected
        add_case(
            results,
            "red_gate_failure_digest_renders_root_causes",
            ok,
            detail="" if ok else text,
            expected=expected,
            actual=actual,
        )


def run_check_mode_detects_stale_case(results: list[CaseResult]) -> None:
    with tempfile.TemporaryDirectory(prefix="current_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        status_path = repo / "CURRENT_BENCH_STATUS_RU.md"
        bench_path = repo / "tools/_preflight_exports/bench_gate_report_20260704_010000/summary.json"
        build_path = repo / "tools/_preflight_exports/full_system_preflight_20260704_010001/summary.json"
        readiness_path = repo / "tools/_readiness_exports/research_readiness_20260704_010002/summary.json"
        write_json(
            bench_path,
            {
                "ready_for_active_pwm": False,
                "next_actions": [
                    {
                        "id": "run_uart_loopback",
                        "command": "py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080",
                    }
                ],
            },
        )
        write_json(build_path, {"summary": {"build_only": True, "build_only_pass": True}})
        write_json(readiness_path, {"ready": False})
        text, _payload = status.build_current_status(repo)
        status_path.write_text(text, encoding="utf-8-sig")
        fresh_ok, fresh_payload = status.check_current_status(repo, status_path)

        stale_bench_path = repo / "tools/_preflight_exports/bench_gate_report_20260704_010100/summary.json"
        write_json(
            stale_bench_path,
            {
                "ready_for_active_pwm": False,
                "next_actions": [
                    {
                        "id": "run_runtime_static_preflight",
                        "command": "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
                    }
                ],
            },
        )
        stale_ok, stale_payload = status.check_current_status(repo, status_path)
        ok = fresh_ok and fresh_payload.get("check_pass") is True and not stale_ok and stale_payload.get("check_pass") is False
        add_case(
            results,
            "check_mode_detects_stale_status",
            ok,
            detail="" if ok else json.dumps({"fresh": fresh_payload, "stale": stale_payload}, ensure_ascii=False),
            expected={"fresh": True, "stale": False},
            actual={"fresh": fresh_ok, "stale": stale_ok},
        )


def run_cli_check_exit_codes_case(results: list[CaseResult]) -> None:
    script = Path(__file__).resolve().parent / "current_bench_status.py"
    with tempfile.TemporaryDirectory(prefix="current_bench_status_selftest_") as tmp:
        repo = Path(tmp)
        out_name = "CURRENT_BENCH_STATUS_RU.md"
        bench_path = repo / "tools/_preflight_exports/bench_gate_report_20260704_020000/summary.json"
        build_path = repo / "tools/_preflight_exports/full_system_preflight_20260704_020001/summary.json"
        readiness_path = repo / "tools/_readiness_exports/research_readiness_20260704_020002/summary.json"
        write_json(
            bench_path,
            {
                "ready_for_active_pwm": False,
                "next_actions": [
                    {
                        "id": "run_uart_loopback",
                        "command": "py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080",
                    }
                ],
            },
        )
        write_json(build_path, {"summary": {"build_only": True, "build_only_pass": True}})
        write_json(readiness_path, {"ready": False})

        write_proc = subprocess.run(
            [sys.executable, "-u", str(script), "--repo", str(repo), "--out", out_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20.0,
        )
        fresh_proc = subprocess.run(
            [sys.executable, "-u", str(script), "--repo", str(repo), "--out", out_name, "--check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20.0,
        )
        stale_bench_path = repo / "tools/_preflight_exports/bench_gate_report_20260704_020100/summary.json"
        write_json(
            stale_bench_path,
            {
                "ready_for_active_pwm": False,
                "next_actions": [
                    {
                        "id": "run_runtime_static_preflight",
                        "command": "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
                    }
                ],
            },
        )
        stale_proc = subprocess.run(
            [sys.executable, "-u", str(script), "--repo", str(repo), "--out", out_name, "--check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20.0,
        )
        try:
            fresh_payload = json.loads(fresh_proc.stdout or "{}")
        except Exception:
            fresh_payload = {}
        try:
            stale_payload = json.loads(stale_proc.stdout or "{}")
        except Exception:
            stale_payload = {}
        ok = (
            write_proc.returncode == 0
            and fresh_proc.returncode == 0
            and fresh_payload.get("check_pass") is True
            and stale_proc.returncode == 1
            and stale_payload.get("check_pass") is False
        )
        add_case(
            results,
            "cli_check_exit_codes_match_freshness",
            ok,
            detail=""
            if ok
            else json.dumps(
                {
                    "write_rc": write_proc.returncode,
                    "fresh_rc": fresh_proc.returncode,
                    "fresh_stdout": fresh_proc.stdout,
                    "fresh_stderr": fresh_proc.stderr,
                    "stale_rc": stale_proc.returncode,
                    "stale_stdout": stale_proc.stdout,
                    "stale_stderr": stale_proc.stderr,
                },
                ensure_ascii=False,
            ),
            expected={"write_rc": 0, "fresh_rc": 0, "stale_rc": 1},
            actual={"write_rc": write_proc.returncode, "fresh_rc": fresh_proc.returncode, "stale_rc": stale_proc.returncode},
        )


def run_atomic_write_keeps_old_file_on_failure_case(results: list[CaseResult]) -> None:
    old_factory = status.tempfile.NamedTemporaryFile

    class BrokenTempFile:
        def __init__(self, directory: str) -> None:
            self.path = Path(directory) / ".broken_atomic_status.tmp"
            self.name = str(self.path)

        def __enter__(self) -> "BrokenTempFile":
            self.path.write_text("partial", encoding="utf-8")
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

        def write(self, _text: str) -> int:
            raise OSError("simulated write failure")

        def flush(self) -> None:
            return None

        def fileno(self) -> int:
            raise OSError("unexpected fileno call")

    with tempfile.TemporaryDirectory(prefix="current_bench_status_selftest_") as tmp:
        root = Path(tmp)
        target = root / "CURRENT_BENCH_STATUS_RU.md"
        target.write_text("old intact", encoding="utf-8-sig")
        tmp_path = root / ".broken_atomic_status.tmp"

        def broken_factory(*_args, **kwargs):
            return BrokenTempFile(str(kwargs["dir"]))

        status.tempfile.NamedTemporaryFile = broken_factory
        try:
            try:
                status.write_text_atomic(target, "new content")
                add_case(results, "atomic_write_keeps_old_file_on_failure", False, detail="write unexpectedly succeeded")
                return
            except OSError:
                pass
        finally:
            status.tempfile.NamedTemporaryFile = old_factory

        old_text = target.read_text(encoding="utf-8-sig")
        ok = old_text == "old intact" and not tmp_path.exists()
        add_case(
            results,
            "atomic_write_keeps_old_file_on_failure",
            ok,
            detail="" if ok else f"old_text={old_text!r} tmp_exists={tmp_path.exists()}",
            expected={"target": "old intact", "tmp_exists": False},
            actual={"target": old_text, "tmp_exists": tmp_path.exists()},
        )


def main() -> int:
    results: list[CaseResult] = []
    run_red_gate_case(results)
    run_missing_gate_case(results)
    run_nucleo_backend_case(results)
    run_stale_build_case(results)
    run_failure_digest_case(results)
    run_check_mode_detects_stale_case(results)
    run_cli_check_exit_codes_case(results)
    run_atomic_write_keeps_old_file_on_failure_case(results)
    failed = [r for r in results if not r.ok]
    summary = {
        "tool": "current_bench_status_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [r.__dict__ for r in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

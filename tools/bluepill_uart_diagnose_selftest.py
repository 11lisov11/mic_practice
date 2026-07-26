#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

import bluepill_uart_diagnose as diag


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: list[str]
    actual: list[str]
    detail: str = ""


def action_ids(result: dict[str, Any]) -> list[str]:
    return [str(item.get("id", "")) for item in diag.classify(result)]


def action_field(result: dict[str, Any], action_id: str, field: str) -> str:
    action = next((item for item in diag.classify(result) if item.get("id") == action_id), {})
    return str(action.get(field, ""))


def base_result() -> dict[str, Any]:
    return {
        "serial_ports": [{"device": "COM3", "vid": 6790, "pid": 51745}],
        "selected_ports": ["COM3"],
        "bauds": [460800],
        "protocol_attempts": [],
        "loopback_attempts": [],
        "loopback_mode": False,
        "uart_wiring_contract": diag.UART_WIRING_CONTRACT,
        "port_inventory": {
            "pyserial_ports": [
                {
                    "device": "COM3",
                    "vid": 6790,
                    "pid": 51745,
                    "hint": "WCH USB serial device; verify this is the isolated USB-UART wired to STM32 PA2/PA3",
                }
            ],
            "pyserial_devices": ["COM3"],
            "windows_pnp_devices": ["COM3", "COM10"],
        },
    }


def run_case(name: str, result: dict[str, Any], expected: list[str]) -> CaseResult:
    try:
        actual = action_ids(result)
        ok = actual == expected
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "action id mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_action_field_case(name: str, result: dict[str, Any], action_id: str, field: str, expected: list[str]) -> CaseResult:
    try:
        actual = [action_field(result, action_id, field)]
        ok = actual == expected
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else "action field mismatch")
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_action_contains_case(name: str, result: dict[str, Any], action_id: str, field: str, expected: list[str]) -> CaseResult:
    try:
        actual_text = action_field(result, action_id, field)
        actual = [item for item in expected if item in actual_text]
        ok = actual == expected
        return CaseResult(name=name, ok=ok, expected=expected, actual=actual, detail="" if ok else actual_text)
    except Exception as exc:
        return CaseResult(name=name, ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_wiring_contract_case() -> CaseResult:
    expected = ["PA3 / USART2_RX", "PA2 / USART2_TX", "3.3V TTL UART only"]
    try:
        contract = diag.UART_WIRING_CONTRACT
        actual = [
            str(contract.get("pc_usb_uart_tx", "")).replace("STM32 ", ""),
            str(contract.get("pc_usb_uart_rx", "")).replace("STM32 ", ""),
            str(contract.get("signal_level", "")),
        ]
        ok = actual == expected
        return CaseResult(name="uart_wiring_contract_is_explicit", ok=ok, expected=expected, actual=actual, detail="" if ok else "wiring contract mismatch")
    except Exception as exc:
        return CaseResult(name="uart_wiring_contract_is_explicit", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_attempt_counts_case() -> CaseResult:
    expected = ["2", "1", "2", "1", "1", "1"]
    try:
        result = base_result()
        result["protocol_attempts"] = [
            {"open_ok": True, "write_ok": False, "response_ok": False, "error": "SerialTimeoutException: Write timeout"},
            {"open_ok": True, "write_ok": True, "response_ok": False, "error": "no response"},
        ]
        result["loopback_attempts"] = [
            {"open_ok": True, "write_ok": True, "ok": True},
        ]
        counts = diag.attempt_counts(result)
        actual = [
            str(counts.get("protocol")),
            str(counts.get("loopback")),
            str(counts.get("write_ok")),
            str(counts.get("write_timeouts")),
            str(counts.get("no_response")),
            str(counts.get("loopback_ok")),
        ]
        ok = actual == expected
        return CaseResult(name="attempt_counts_summarize_protocol_and_loopback", ok=ok, expected=expected, actual=actual, detail="" if ok else "attempt count mismatch")
    except Exception as exc:
        return CaseResult(name="attempt_counts_summarize_protocol_and_loopback", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_attempt_error_digest_case() -> CaseResult:
    expected = [
        "protocol_attempts:COM3@460800 SerialTimeoutException: Write timeout",
        "protocol_attempts:COM3@115200 no response",
        "loopback_attempts:COM3@460800 loopback mismatch",
    ]
    try:
        result = base_result()
        result["protocol_attempts"] = [
            {"port": "COM3", "baud": 460800, "error": "SerialTimeoutException: Write timeout"},
            {"port": "COM3", "baud": 460800, "error": "SerialTimeoutException: Write timeout"},
            {"port": "COM3", "baud": 115200, "error": "no response"},
        ]
        result["loopback_attempts"] = [
            {"port": "COM3", "baud": 460800, "error": "loopback mismatch"},
        ]
        actual = diag.attempt_error_digest(result)
        ok = actual == expected
        return CaseResult(name="attempt_error_digest_deduplicates_and_labels", ok=ok, expected=expected, actual=actual, detail="" if ok else "digest mismatch")
    except Exception as exc:
        return CaseResult(name="attempt_error_digest_deduplicates_and_labels", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_auto_port_selection_case() -> CaseResult:
    expected = [
        "COM3,COM9",
        "COM9",
        "COM6:Unknown",
    ]
    try:
        serial_ports = [{"device": "COM3", "vid": 0x1A86, "pid": 0xCA21}]
        pnp = {
            "ok": True,
            "stdout": json.dumps(
                [
                    {
                        "Status": "OK",
                        "FriendlyName": "USB-SERIAL CH340 (COM9)",
                        "InstanceId": "USB\\VID_1A86&PID_7523\\ABC",
                    },
                    {
                        "Status": "Unknown",
                        "FriendlyName": "USB-SERIAL CH340 (COM6)",
                        "InstanceId": "USB\\VID_1A86&PID_7523\\OLD",
                    },
                ]
            ),
        }
        selection = diag.auto_port_selection(serial_ports, pnp)
        skipped = selection.get("skipped_pnp_not_ok", [])
        first_skipped = skipped[0] if isinstance(skipped, list) and skipped else {}
        actual = [
            ",".join(selection.get("selected_ports", [])),
            ",".join(selection.get("added_pnp_ok_devices", [])),
            f"{first_skipped.get('device')}:{first_skipped.get('status')}",
        ]
        ok = actual == expected
        return CaseResult(
            name="auto_port_selection_adds_ok_pnp_and_skips_ghosts",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "auto port selection mismatch",
        )
    except Exception as exc:
        return CaseResult(name="auto_port_selection_adds_ok_pnp_and_skips_ghosts", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def run_pio_device_list_uses_python_module_case() -> CaseResult:
    expected = [sys.executable, "-m", "platformio", "device", "list"]
    old_run_capture = diag.run_capture
    captured: list[str] = []

    def fake_run_capture(cmd: list[str], timeout_s: float = 8.0) -> dict[str, Any]:
        captured[:] = [str(x) for x in cmd]
        return {"ok": True, "cmd": cmd, "timeout_s": timeout_s}

    try:
        diag.run_capture = fake_run_capture
        diag.pio_device_list()
        ok = captured == expected
        return CaseResult(
            name="pio_device_list_uses_python_module_platformio",
            ok=ok,
            expected=expected,
            actual=captured,
            detail="" if ok else "PlatformIO inventory command mismatch",
        )
    except Exception as exc:
        return CaseResult(name="pio_device_list_uses_python_module_platformio", ok=False, expected=expected, actual=captured, detail=f"{type(exc).__name__}: {exc}")
    finally:
        diag.run_capture = old_run_capture


def run_hmi_conflict_summary_case() -> CaseResult:
    expected = [
        "PC-direct HMI is already using selected serial port COM3",
        "pid=1234,serial=COM3",
        "pc_direct_hmi_service.py stop --port 18080",
    ]
    try:
        result = base_result()
        result["pc_direct_hmi"] = {
            "checked": True,
            "hmi_port": 18080,
            "hmi_processes": [
                {
                    "pid": 1234,
                    "name": "python.exe",
                    "serial": "COM3",
                    "command_line": r"python.exe -u .\tools\unoq_web_server.py --serial COM3 --port 18080",
                }
            ],
            "stop_command": r"py -3 -u .\tools\pc_direct_hmi_service.py stop --port 18080",
        }
        text = diag.pc_direct_hmi_conflict_summary(result)
        actual = [item for item in expected if item in text]
        ok = actual == expected
        return CaseResult(name="hmi_conflict_summary_reports_same_serial_stop_command", ok=ok, expected=expected, actual=actual, detail="" if ok else text)
    except Exception as exc:
        return CaseResult(name="hmi_conflict_summary_reports_same_serial_stop_command", ok=False, expected=expected, actual=[], detail=f"{type(exc).__name__}: {exc}")


def cases() -> list[CaseResult]:
    out: list[CaseResult] = []

    no_ports = base_result()
    no_ports["serial_ports"] = []
    no_ports["selected_ports"] = []
    no_ports["port_inventory"] = {
        "pyserial_ports": [],
        "pyserial_devices": [],
        "windows_pnp_ports": [],
        "windows_pnp_devices": [],
    }
    out.append(run_case("no_serial_ports", no_ports, ["no_serial_ports"]))

    inventory_only = base_result()
    inventory_only["inventory_only"] = True
    out.append(run_case("inventory_only_no_write_action", inventory_only, ["inventory_only_complete"]))
    out.append(
        run_action_contains_case(
            "inventory_only_detail_reports_without_opening_port",
            inventory_only,
            "inventory_only_complete",
            "detail",
            ["without opening or writing any COM port", "Selected candidate: COM3", "pyserial=['COM3']"],
        )
    )

    loop_ok = base_result()
    loop_ok["loopback_mode"] = True
    loop_ok["loopback_attempts"] = [{"ok": True, "baud": 460800}]
    out.append(run_case("loopback_ok", loop_ok, ["adapter_loopback_ok"]))

    loop_missing_confirm = base_result()
    loop_missing_confirm["loopback_mode"] = True
    loop_missing_confirm["loopback_confirm_required_missing"] = True
    loop_missing_confirm["confirm_loopback_wired"] = False
    out.append(run_case("loopback_requires_physical_confirmation", loop_missing_confirm, ["confirm_loopback_wiring"]))
    out.append(
        run_action_contains_case(
            "loopback_missing_confirm_detail_is_physical",
            loop_missing_confirm,
            "confirm_loopback_wiring",
            "detail",
            ["USB-UART TX/RX must be disconnected from STM32", "isolated adapter side"],
        )
    )

    loop_multi = base_result()
    loop_multi["loopback_mode"] = True
    loop_multi["bauds"] = [460800, 115200]
    loop_multi["loopback_attempts"] = [{"ok": True, "baud": 115200}]
    out.append(
        run_action_field_case(
            "loopback_multi_baud_command_preserves_list",
            loop_multi,
            "adapter_loopback_ok",
            "command",
            ["py -3 -u .\\tools\\bluepill_uart_diagnose.py --port COM3 --dtr-rts-matrix"],
        )
    )
    out.append(
        run_action_contains_case(
            "loopback_multi_baud_detail_reports_success_baud",
            loop_multi,
            "adapter_loopback_ok",
            "detail",
            ["baud(s) [115200]"],
        )
    )

    loop_fail = base_result()
    loop_fail["loopback_mode"] = True
    loop_fail["loopback_attempts"] = [{"ok": False, "error": "loopback mismatch"}]
    out.append(run_case("loopback_failed", loop_fail, ["adapter_loopback_failed"]))

    protocol_ok = base_result()
    protocol_ok["protocol_attempts"] = [{"response_ok": True, "pwm_active": False}]
    out.append(run_case("protocol_ok", protocol_ok, ["uart_protocol_ok"]))

    unsafe_pwm = base_result()
    unsafe_pwm["protocol_attempts"] = [{"response_ok": True, "pwm_active": True, "response": {"pwm_active": True}}]
    out.append(run_case("unsafe_pwm_active_on_safe_probe", unsafe_pwm, ["unsafe_pwm_active_on_safe_probe"]))

    write_timeout = base_result()
    write_timeout["protocol_attempts"] = [
        {"write_ok": False, "response_ok": False, "error": "SerialTimeoutException: Write timeout"},
        {"write_ok": False, "response_ok": False, "error": "SerialTimeoutException: Write timeout"},
    ]
    out.append(run_case("host_cannot_write_uart", write_timeout, ["host_cannot_write_uart", "run_loopback"]))
    out.append(
        run_action_contains_case(
            "write_timeout_detail_includes_port_inventory",
            write_timeout,
            "host_cannot_write_uart",
            "detail",
            ["write_timeouts=2/2", "Selected port: COM3", "pyserial=['COM3']", "windows_pnp=['COM3', 'COM10']"],
        )
    )
    write_timeout_hmi = base_result()
    write_timeout_hmi["pc_direct_hmi"] = {
        "checked": True,
        "hmi_port": 18080,
        "hmi_processes": [
            {
                "pid": 1234,
                "name": "python.exe",
                "serial": "COM3",
                "command_line": r"python.exe -u .\tools\unoq_web_server.py --serial COM3 --port 18080",
            }
        ],
        "stop_command": r"py -3 -u .\tools\pc_direct_hmi_service.py stop --port 18080",
    }
    write_timeout_hmi["protocol_attempts"] = [
        {"write_ok": False, "response_ok": False, "error": "SerialTimeoutException: Write timeout"},
    ]
    out.append(
        run_action_contains_case(
            "write_timeout_detail_reports_hmi_conflict",
            write_timeout_hmi,
            "host_cannot_write_uart",
            "detail",
            ["PC-direct HMI is already using selected serial port COM3", "pc_direct_hmi_service.py stop --port 18080"],
        )
    )
    out.append(
        run_action_contains_case(
            "run_loopback_detail_mentions_safe_wrapper",
            write_timeout_hmi,
            "run_loopback",
            "detail",
            ["uart_loopback_preflight.py", "stops PC-direct HMI", "starts PC-direct HMI again"],
        )
    )
    flush_timeout = base_result()
    flush_timeout["protocol_attempts"] = [
        {
            "write_returned": True,
            "write_ok": True,
            "flush_ok": False,
            "response_ok": False,
            "flush_error": "SerialTimeoutException: Write timeout",
            "error": "flush SerialTimeoutException: Write timeout",
        }
    ]
    out.append(run_case("host_cannot_write_uart_flush_timeout", flush_timeout, ["host_cannot_write_uart", "run_loopback"]))
    out.append(
        run_action_contains_case(
            "flush_timeout_detail_exposes_flush_stage",
            flush_timeout,
            "host_cannot_write_uart",
            "detail",
            ["write_returned=1", "write_ok=1", "flush_ok=0", "flush_timeouts=1"],
        )
    )
    out.append(
        run_action_field_case(
            "write_timeout_loopback_command",
            write_timeout,
            "run_loopback",
            "command",
            ["py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080"],
        )
    )
    write_timeout_multi = base_result()
    write_timeout_multi["bauds"] = [460800, 115200]
    write_timeout_multi["protocol_attempts"] = [
        {"write_ok": False, "response_ok": False, "error": "SerialTimeoutException: Write timeout"},
    ]
    out.append(
        run_action_field_case(
            "write_timeout_loopback_command_preserves_baud_list",
            write_timeout_multi,
            "run_loopback",
            "command",
            ["py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080"],
        )
    )

    no_response = base_result()
    no_response["protocol_attempts"] = [{"write_ok": True, "response_ok": False, "error": "no response"}]
    out.append(run_case("write_ok_no_bluepill_response", no_response, ["write_ok_no_bluepill_response"]))

    port_open = base_result()
    port_open["protocol_attempts"] = [{"write_ok": False, "response_ok": False, "error": "PermissionError: Access denied"}]
    out.append(run_case("port_open_error", port_open, ["port_open_error"]))

    pnp_only_open_error = base_result()
    pnp_only_open_error["serial_ports"] = []
    pnp_only_open_error["selected_ports"] = ["COM9"]
    pnp_only_open_error["port_inventory"] = {
        "pyserial_ports": [],
        "pyserial_devices": [],
        "windows_pnp_ports": [
            {
                "device": "COM9",
                "status": "OK",
                "hint": "WCH CH340/CH341 USB-UART",
            }
        ],
        "windows_pnp_devices": ["COM9"],
    }
    pnp_only_open_error["protocol_attempts"] = [
        {"port": "COM9", "baud": 460800, "write_ok": False, "response_ok": False, "error": "PermissionError: Access denied"}
    ]
    out.append(run_case("pnp_only_port_attempt_not_misclassified_as_no_ports", pnp_only_open_error, ["port_open_error"]))
    out.append(
        run_action_contains_case(
            "pnp_only_selected_port_summary_uses_pnp_hint",
            pnp_only_open_error,
            "port_open_error",
            "detail",
            ["COM port could not be opened cleanly", "Selected port: COM9", "Windows PnP status=OK", "windows_pnp=['COM9']"],
        )
    )
    actual_summary = diag.selected_port_summary(pnp_only_open_error)
    expected_summary = ["COM9", "Windows PnP status=OK", "WCH CH340/CH341 USB-UART"]
    out.append(
        CaseResult(
            name="selected_port_summary_falls_back_to_pnp_inventory",
            ok=all(item in actual_summary for item in expected_summary),
            expected=expected_summary,
            actual=[actual_summary],
            detail="" if all(item in actual_summary for item in expected_summary) else "PNP summary fallback mismatch",
        )
    )

    mixed = base_result()
    mixed["protocol_attempts"] = [
        {"write_ok": False, "response_ok": False, "error": "SerialTimeoutException: Write timeout"},
        {"write_ok": True, "response_ok": False, "error": "no response"},
    ]
    out.append(run_case("mixed_unknown", mixed, ["write_ok_no_bluepill_response"]))

    empty_attempts = base_result()
    out.append(run_case("empty_attempts_unknown", empty_attempts, ["uart_unknown_failure"]))
    out.append(run_wiring_contract_case())
    out.append(run_attempt_counts_case())
    out.append(run_attempt_error_digest_case())
    out.append(run_auto_port_selection_case())
    out.append(run_pio_device_list_uses_python_module_case())
    out.append(run_hmi_conflict_summary_case())

    pnp_rows = diag.windows_pnp_port_rows(
        {
            "ok": True,
            "stdout": json.dumps(
                [
                    {
                        "Status": "OK",
                        "FriendlyName": "USB-SERIAL CH340 (COM6)",
                        "InstanceId": "USB\\VID_1A86&PID_7523\\ABC",
                    }
                ]
            ),
        }
    )
    actual = [str(pnp_rows[0].get("device", "")), str(pnp_rows[0].get("hint", ""))]
    expected = ["COM6", "WCH CH340/CH341 USB-UART"]
    out.append(
        CaseResult(
            name="windows_pnp_rows_are_normalized",
            ok=actual == expected,
            expected=expected,
            actual=actual,
            detail="" if actual == expected else "PNP parsing mismatch",
        )
    )

    return out


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "bluepill_uart_diagnose_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import serial
from serial.tools import list_ports

import bluepill_direct_probe as proto
import pc_direct_hmi_service as hmi_service
from run_metadata import collect_run_metadata


UART_WIRING_CONTRACT = {
    "signal_level": "3.3V TTL UART only",
    "pc_usb_uart_tx": "STM32 PA3 / USART2_RX",
    "pc_usb_uart_rx": "STM32 PA2 / USART2_TX",
    "isolated_ground": "USB-UART isolated-side GND must be common with STM32 logic GND",
    "loopback_wiring": "Disconnect adapter TX/RX from STM32, then short adapter TX to adapter RX on the isolated side.",
    "safe_probe_frame": "MODE_OFF+CLEAR_FAULT only; this diagnostic never sends START or PWM enable.",
}
DEFAULT_BAUD_SWEEP = [460800, 115200, 230400, 921600]

USB_ID_HINTS = {
    (0x1A86, 0x7523): "WCH CH340/CH341 USB-UART",
    (0x1A86, 0x5523): "WCH CH340/CH341 USB-UART",
    (0x1A86, 0xCA21): "WCH USB serial device; verify this is the isolated USB-UART wired to STM32 PA2/PA3",
    (0x2341, 0x0078): "Arduino UNO Q USB interface; not the PC-to-STM32 UART unless intentionally bridged",
    (0x0483, 0x3748): "ST-LINK/V2; flashing/debug, not USART2 command UART",
    (0x0483, 0x374B): "ST-LINK/V2-1; flashing/debug, not USART2 command UART",
    (0x04E8, 0x6860): "Samsung/ADB device; not Blue Pill UART",
}


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"


def parse_int_list(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def available_ports() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in list_ports.comports():
        out.append(
            {
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "vid": p.vid,
                "pid": p.pid,
                "serial_number": p.serial_number,
                "location": p.location,
            }
        )
    return out


def usb_hint(vid: Any, pid: Any, description: str = "", hwid: str = "") -> str:
    try:
        key = (int(vid), int(pid))
    except Exception:
        key = None
    if key in USB_ID_HINTS:
        return USB_ID_HINTS[key]
    text = f"{description} {hwid}".lower()
    if "ch340" in text or "ch341" in text or "1a86" in text:
        return "WCH CH340/CH341-class USB serial; verify TX/RX/GND wiring"
    if "arduino" in text or "2341" in text:
        return "Arduino USB interface; not the PC-to-STM32 UART unless intentionally bridged"
    if "stlink" in text or "st-link" in text or "0483" in text:
        return "ST-LINK/debug interface; not USART2 command UART"
    return "unknown serial device; verify it is the isolated USB-UART to STM32"


def annotate_serial_port(port: dict[str, Any]) -> dict[str, Any]:
    out = dict(port)
    out["hint"] = usb_hint(port.get("vid"), port.get("pid"), str(port.get("description", "")), str(port.get("hwid", "")))
    out["selected_as_uart_candidate"] = "uart" in out["hint"].lower() or "serial" in out["hint"].lower()
    return out


def extract_com_name(text: str) -> str | None:
    match = re.search(r"\((COM\d+)\)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(r"\b(COM\d+)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def vid_pid_from_instance(instance_id: str) -> tuple[int | None, int | None]:
    match = re.search(r"VID_([0-9A-Fa-f]{4}).*PID_([0-9A-Fa-f]{4})", instance_id)
    if not match:
        return None, None
    return int(match.group(1), 16), int(match.group(2), 16)


def windows_pnp_port_rows(pnp: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not pnp or not pnp.get("ok"):
        return []
    raw = str(pnp.get("stdout") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        friendly = str(row.get("FriendlyName") or "")
        instance = str(row.get("InstanceId") or "")
        vid, pid = vid_pid_from_instance(instance)
        out.append(
            {
                "device": extract_com_name(friendly),
                "status": row.get("Status"),
                "friendly_name": friendly,
                "instance_id": instance,
                "vid": vid,
                "pid": pid,
                "hint": usb_hint(vid, pid, friendly, instance),
            }
        )
    return out


def port_inventory(serial_ports: list[dict[str, Any]], pnp: dict[str, Any] | None) -> dict[str, Any]:
    serial_hints = [annotate_serial_port(port) for port in serial_ports]
    pnp_hints = windows_pnp_port_rows(pnp)
    pyserial_devices = [str(port.get("device")) for port in serial_hints]
    pnp_devices = [str(row.get("device")) for row in pnp_hints if row.get("device")]
    pnp_ok_devices = [
        str(row.get("device"))
        for row in pnp_hints
        if row.get("device") and str(row.get("status", "")).upper() == "OK"
    ]
    pnp_not_ok = [
        {
            "device": row.get("device"),
            "status": row.get("status"),
            "friendly_name": row.get("friendly_name"),
            "hint": row.get("hint"),
        }
        for row in pnp_hints
        if row.get("device") and str(row.get("status", "")).upper() != "OK"
    ]
    return {
        "pyserial_ports": serial_hints,
        "windows_pnp_ports": pnp_hints,
        "pyserial_devices": pyserial_devices,
        "windows_pnp_devices": pnp_devices,
        "windows_pnp_ok_devices": pnp_ok_devices,
        "windows_pnp_not_ok": pnp_not_ok,
        "windows_pnp_only_devices": [dev for dev in pnp_devices if dev not in pyserial_devices],
        "candidate_notes": [
            "Use the isolated USB-UART connected to STM32 USART2: PC-TX -> PA3, PC-RX -> PA2, GND common.",
            "Arduino UNO Q, ST-LINK, phone/ADB, and Logic/Saleae devices are not the PC-to-STM32 command UART.",
        ],
    }


def auto_port_selection(serial_ports: list[dict[str, Any]], pnp: dict[str, Any] | None) -> dict[str, Any]:
    inventory = port_inventory(serial_ports, pnp)
    selected: list[str] = []
    for dev in inventory.get("pyserial_devices", []):
        if dev and dev not in selected:
            selected.append(str(dev))
    added_pnp_ok: list[str] = []
    for dev in inventory.get("windows_pnp_ok_devices", []):
        dev = str(dev)
        if dev and dev not in selected:
            selected.append(dev)
            added_pnp_ok.append(dev)
    skipped = inventory.get("windows_pnp_not_ok", [])
    return {
        "selected_ports": selected,
        "pyserial_devices": inventory.get("pyserial_devices", []),
        "windows_pnp_devices": inventory.get("windows_pnp_devices", []),
        "windows_pnp_ok_devices": inventory.get("windows_pnp_ok_devices", []),
        "added_pnp_ok_devices": added_pnp_ok,
        "skipped_pnp_not_ok": skipped,
        "notes": [
            "Auto mode probes all pyserial COM ports and additionally PnP COM ports whose Windows status is OK.",
            "PnP ports with non-OK status are reported but not probed; they are often stale/ghost entries or disconnected devices.",
        ],
    }


def run_capture(cmd: list[str], timeout_s: float) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s)
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "ok": proc.returncode == 0,
        }
    except Exception as exc:
        return {"cmd": cmd, "ok": False, "exception": type(exc).__name__, "error": str(exc)}


def windows_pnp_ports() -> dict[str, Any] | None:
    if not sys.platform.startswith("win"):
        return None
    script = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "$OutputEncoding=[System.Text.Encoding]::UTF8; "
        "Get-PnpDevice -Class Ports | Select-Object Status,FriendlyName,InstanceId | ConvertTo-Json -Depth 3"
    )
    return run_capture(["powershell", "-NoProfile", "-Command", script], timeout_s=8.0)


def pio_device_list() -> dict[str, Any]:
    return run_capture([sys.executable, "-m", "platformio", "device", "list"], timeout_s=8.0)


def commandline_serial_port(command_line: str) -> str | None:
    match = re.search(r"(?<!\S)--serial(?:=|\s+)([^\s\"']+)", str(command_line or ""), re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip().upper()


def pc_direct_hmi_snapshot(port: int = 18080, timeout_s: float = 5.0) -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {
            "checked": False,
            "reason": "windows_process_inventory_only",
            "hmi_port": int(port),
            "hmi_processes": [],
            "listeners": [],
        }
    proc_ok, processes, proc_detail = hmi_service.list_windows_processes(timeout_s=timeout_s)
    listener_ok, listeners, listener_detail = hmi_service.list_windows_listeners(port, timeout_s=timeout_s)
    hmi_processes = hmi_service.filter_hmi_processes(processes, port) if proc_ok else []
    for proc in hmi_processes:
        proc["serial"] = commandline_serial_port(str(proc.get("command_line", "")))
    return {
        "checked": True,
        "hmi_port": int(port),
        "process_query_ok": bool(proc_ok),
        "process_query_detail": "" if proc_ok else proc_detail,
        "listener_query_ok": bool(listener_ok),
        "listener_query_detail": "" if listener_ok else listener_detail,
        "hmi_processes": hmi_processes,
        "listeners": listeners if listener_ok else [],
        "stop_command": f"py -3 -u .\\tools\\pc_direct_hmi_service.py stop --port {int(port)}",
        "start_command": f"py -3 -u .\\tools\\pc_direct_hmi_service.py start --serial COM3 --baud 460800 --port {int(port)}",
    }


def pc_direct_hmi_conflict_summary(result: dict[str, Any]) -> str:
    snap = result.get("pc_direct_hmi") if isinstance(result.get("pc_direct_hmi"), dict) else {}
    if not snap or not snap.get("checked"):
        return ""
    selected = selected_port(result).upper()
    processes = snap.get("hmi_processes", [])
    if not isinstance(processes, list) or not processes:
        return "PC-direct HMI process: not running on managed port."
    same_serial: list[str] = []
    all_procs: list[str] = []
    for proc in processes:
        if not isinstance(proc, dict):
            continue
        pid = str(proc.get("pid", "?"))
        serial_name = str(proc.get("serial") or "?").upper()
        label = f"pid={pid},serial={serial_name}"
        all_procs.append(label)
        if serial_name == selected:
            same_serial.append(label)
    stop_cmd = snap.get("stop_command", "py -3 -u .\\tools\\pc_direct_hmi_service.py stop --port 18080")
    if same_serial:
        return (
            "PC-direct HMI is already using selected serial port "
            f"{selected} ({', '.join(same_serial)}). Stop it before loopback/standalone UART tests: `{stop_cmd}`."
        )
    return f"PC-direct HMI running on managed port but not on selected serial {selected}: {', '.join(all_procs)}."


def selected_port(result: dict[str, Any]) -> str:
    ports = result.get("selected_ports", [])
    if isinstance(ports, list) and ports:
        return str(ports[0])
    serial_ports = result.get("serial_ports", [])
    if isinstance(serial_ports, list) and serial_ports and isinstance(serial_ports[0], dict):
        return str(serial_ports[0].get("device", "COM3"))
    return "COM3"


def selected_bauds(result: dict[str, Any]) -> list[int]:
    bauds = result.get("bauds", [])
    if isinstance(bauds, list) and bauds:
        out: list[int] = []
        for baud in bauds:
            try:
                out.append(int(baud))
            except Exception:
                pass
        if out:
            return out
    return list(DEFAULT_BAUD_SWEEP)


def loopback_bauds(result: dict[str, Any]) -> list[int]:
    bauds = selected_bauds(result)
    # A write-timeout at the runtime baud is below the STM32 protocol layer.
    # When only the nominal runtime baud is known, sweep the usual fallback
    # rates so the adapter/isolator is proven broadly before reconnecting STM32.
    if bauds == [460800]:
        return list(DEFAULT_BAUD_SWEEP)
    return bauds


def diagnose_command(result: dict[str, Any], *, loopback: bool) -> str:
    port = selected_port(result)
    if loopback:
        baud_csv = ",".join(str(baud) for baud in loopback_bauds(result))
        return f"py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port {port} --bauds {baud_csv} --timeout 0.5 --write-timeout 2.0 --hmi-port 18080"
    return f"py -3 -u .\\tools\\bluepill_uart_diagnose.py --port {port} --dtr-rts-matrix"


def selected_port_summary(result: dict[str, Any]) -> str:
    selected = selected_port(result)
    inventory = result.get("port_inventory", {}) if isinstance(result.get("port_inventory"), dict) else {}
    py_ports = inventory.get("pyserial_ports", []) if isinstance(inventory.get("pyserial_ports"), list) else []
    for port in py_ports:
        if isinstance(port, dict) and str(port.get("device", "")).upper() == selected.upper():
            return f"{selected}: {port.get('hint', 'no hint')}"
    pnp_ports = inventory.get("windows_pnp_ports", []) if isinstance(inventory.get("windows_pnp_ports"), list) else []
    for port in pnp_ports:
        if isinstance(port, dict) and str(port.get("device", "")).upper() == selected.upper():
            status = port.get("status", "unknown")
            return f"{selected}: Windows PnP status={status}; {port.get('hint', 'no hint')}"
    return f"{selected}: not present in pyserial inventory"


def visible_port_summary(result: dict[str, Any]) -> str:
    inventory = result.get("port_inventory", {}) if isinstance(result.get("port_inventory"), dict) else {}
    py_devs = inventory.get("pyserial_devices", []) if isinstance(inventory.get("pyserial_devices"), list) else []
    pnp_devs = inventory.get("windows_pnp_devices", []) if isinstance(inventory.get("windows_pnp_devices"), list) else []
    return f"pyserial={py_devs or 'none'}; windows_pnp={pnp_devs or 'none'}"


def auto_port_selection_summary(result: dict[str, Any]) -> str:
    selection = result.get("auto_port_selection", {}) if isinstance(result.get("auto_port_selection"), dict) else {}
    if not selection:
        return ""
    selected = selection.get("selected_ports", [])
    added = selection.get("added_pnp_ok_devices", [])
    skipped = selection.get("skipped_pnp_not_ok", [])
    parts = [f"auto_selected={selected or 'none'}"]
    if added:
        parts.append(f"pnp_ok_added={added}")
    if isinstance(skipped, list) and skipped:
        skipped_text = []
        for item in skipped:
            if not isinstance(item, dict):
                continue
            dev = item.get("device") or "?"
            status = item.get("status") or "unknown"
            skipped_text.append(f"{dev}({status})")
        if skipped_text:
            parts.append("pnp_not_ok_skipped=" + ",".join(skipped_text))
    return "; ".join(parts)


def attempt_counts(result: dict[str, Any]) -> dict[str, int]:
    protocol_attempts = result.get("protocol_attempts", [])
    loopback_attempts = result.get("loopback_attempts", [])
    protocol = protocol_attempts if isinstance(protocol_attempts, list) else []
    loopback = loopback_attempts if isinstance(loopback_attempts, list) else []
    errors = [str(item.get("error", "")) for item in [*protocol, *loopback] if isinstance(item, dict)]
    flush_errors = [str(item.get("flush_error", "")) for item in [*protocol, *loopback] if isinstance(item, dict)]
    return {
        "protocol": len(protocol),
        "loopback": len(loopback),
        "open_ok": sum(1 for item in [*protocol, *loopback] if isinstance(item, dict) and item.get("open_ok")),
        "write_returned": sum(1 for item in [*protocol, *loopback] if isinstance(item, dict) and item.get("write_returned")),
        "write_ok": sum(1 for item in [*protocol, *loopback] if isinstance(item, dict) and item.get("write_ok")),
        "flush_ok": sum(1 for item in [*protocol, *loopback] if isinstance(item, dict) and item.get("flush_ok")),
        "write_timeouts": sum(1 for error in errors if "Write timeout" in error or "SerialTimeoutException" in error),
        "flush_timeouts": sum(1 for error in flush_errors if "Write timeout" in error or "SerialTimeoutException" in error),
        "no_response": sum(1 for item in protocol if isinstance(item, dict) and item.get("write_ok") and str(item.get("error")) == "no response"),
        "responses": sum(1 for item in protocol if isinstance(item, dict) and item.get("response_ok")),
        "loopback_ok": sum(1 for item in loopback if isinstance(item, dict) and item.get("ok")),
    }


def attempt_error_digest(result: dict[str, Any], limit: int = 6) -> list[str]:
    digest: list[str] = []
    seen: set[str] = set()
    for group_name in ("protocol_attempts", "loopback_attempts"):
        attempts = result.get(group_name, [])
        if not isinstance(attempts, list):
            continue
        for item in attempts:
            if not isinstance(item, dict):
                continue
            error = str(item.get("error", "")).strip()
            if not error:
                continue
            label = f"{group_name}:{item.get('port', '?')}@{item.get('baud', '?')} {error}"
            if label in seen:
                continue
            seen.add(label)
            digest.append(label)
            if len(digest) >= limit:
                return digest
    return digest


def protocol_attempt(port: str, baud: int, dtr: bool, rts: bool, attempts: int, timeout_s: float, write_timeout_s: float) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "port": port,
        "baud": baud,
        "dtr": dtr,
        "rts": rts,
        "attempts": attempts,
        "open_ok": False,
        "write_returned": False,
        "write_ok": False,
        "flush_ok": False,
        "response_ok": False,
        "safe_frame": "MODE_OFF+CLEAR_FAULT",
    }
    started = time.monotonic()
    try:
        ser = serial.Serial(
            port,
            baud,
            timeout=0.02,
            write_timeout=write_timeout_s,
            rtscts=False,
            dsrdtr=False,
            xonxoff=False,
        )
    except Exception as exc:
        rec["error"] = type(exc).__name__ + ": " + str(exc)
        rec["duration_s"] = time.monotonic() - started
        return rec
    rec["open_ok"] = True

    try:
        ser.dtr = dtr
        ser.rts = rts
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        for seq in range(1, attempts + 1):
            try:
                t0 = time.monotonic()
                frame = proto.build_cmd(seq, mode=proto.MODE_OFF, flags=proto.FLAG_CLEAR_FAULT)
                rec["expected_write_len"] = len(frame)
                written = ser.write(frame)
                rec["write_returned"] = True
                rec["written"] = int(written)
                rec["write_ok"] = int(written) == len(frame)
                if not rec["write_ok"]:
                    rec["error"] = f"short write {int(written)}/{len(frame)}"
                    break
                t_flush = time.monotonic()
                try:
                    ser.flush()
                    rec["flush_ok"] = True
                    rec["last_flush_ms"] = (time.monotonic() - t_flush) * 1000.0
                except Exception as exc:
                    rec["flush_error"] = type(exc).__name__ + ": " + str(exc)
                    rec["error"] = "flush " + rec["flush_error"]
                    break
                rec["last_write_ms"] = (time.monotonic() - t0) * 1000.0
            except Exception as exc:
                rec["error"] = type(exc).__name__ + ": " + str(exc)
                break
            rsp = proto.read_rsp(ser, timeout_s)
            if rsp is not None:
                parsed = proto.parse_rsp(rsp)
                rec["response"] = parsed
                rec["response_ok"] = bool(parsed.get("crc_ok"))
                rec["pwm_active"] = bool(parsed.get("pwm_active"))
                break
            time.sleep(0.03)
        if rec["write_ok"] and "response" not in rec and "error" not in rec:
            rec["error"] = "no response"
    finally:
        try:
            ser.close()
        except Exception:
            pass
    rec["duration_s"] = time.monotonic() - started
    return rec


def loopback_attempt(port: str, baud: int, timeout_s: float, write_timeout_s: float) -> dict[str, Any]:
    pattern = b"MIC_LOOPBACK_TEST_0123456789"
    rec: dict[str, Any] = {
        "port": port,
        "baud": baud,
        "pattern_hex": pattern.hex(" "),
        "expected_write_len": len(pattern),
        "expected_rx_len": len(pattern),
        "open_ok": False,
        "write_returned": False,
        "write_ok": False,
        "flush_ok": False,
        "ok": False,
    }
    started = time.monotonic()
    try:
        ser = serial.Serial(port, baud, timeout=0.02, write_timeout=write_timeout_s, rtscts=False, dsrdtr=False, xonxoff=False)
    except Exception as exc:
        rec["error"] = type(exc).__name__ + ": " + str(exc)
        rec["duration_s"] = time.monotonic() - started
        return rec
    rec["open_ok"] = True
    try:
        ser.dtr = False
        ser.rts = False
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        t0 = time.monotonic()
        written = ser.write(pattern)
        rec["write_returned"] = True
        rec["written"] = int(written)
        rec["write_ok"] = int(written) == len(pattern)
        if not rec["write_ok"]:
            rec["error"] = f"short write {int(written)}/{len(pattern)}"
        else:
            t_flush = time.monotonic()
            try:
                ser.flush()
                rec["flush_ok"] = True
                rec["last_flush_ms"] = (time.monotonic() - t_flush) * 1000.0
            except Exception as exc:
                rec["flush_error"] = type(exc).__name__ + ": " + str(exc)
                rec["error"] = "flush " + rec["flush_error"]
                rec["duration_s"] = time.monotonic() - started
                return rec
            rec["last_write_ms"] = (time.monotonic() - t0) * 1000.0
            deadline = time.monotonic() + timeout_s
            rx = bytearray()
            while time.monotonic() < deadline and len(rx) < len(pattern):
                chunk = ser.read(len(pattern) - len(rx))
                if chunk:
                    rx.extend(chunk)
            rec["rx_hex"] = bytes(rx).hex(" ")
            rec["rx_len"] = len(rx)
            rec["ok"] = bytes(rx) == pattern
            if not rec["ok"]:
                rec["error"] = "loopback mismatch"
    except Exception as exc:
        rec["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        try:
            ser.close()
        except Exception:
            pass
    rec["duration_s"] = time.monotonic() - started
    return rec


def classify(result: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    attempts = result.get("protocol_attempts", [])
    loopback_attempts = result.get("loopback_attempts", [])
    ports = result.get("serial_ports", [])
    counts = attempt_counts(result)

    if result.get("inventory_only"):
        hmi_summary = pc_direct_hmi_conflict_summary(result)
        hmi_sentence = f" {hmi_summary}" if hmi_summary else ""
        actions.append(
            {
                "id": "inventory_only_complete",
                "detail": (
                    "Serial inventory collected without opening or writing any COM port. "
                    f"Selected candidate: {selected_port_summary(result)}. Visible ports: {visible_port_summary(result)}."
                    f"{hmi_sentence}"
                ),
                "command": diagnose_command(result, loopback=False),
            }
        )
        return actions

    if result.get("loopback_mode") and result.get("loopback_confirm_required_missing"):
        port = selected_port(result)
        baud_csv = ",".join(str(baud) for baud in loopback_bauds(result))
        actions.append(
            {
                "id": "confirm_loopback_wiring",
                "detail": (
                    "Loopback mode is blocked until the operator confirms physical wiring: "
                    "USB-UART TX/RX must be disconnected from STM32 and shorted only on the isolated adapter side."
                ),
                "command": (
                    "py -3 -u .\\tools\\bluepill_uart_diagnose.py --loopback --confirm-loopback-wired "
                    f"--port {port} --bauds {baud_csv} --timeout 0.5 --write-timeout 2.0"
                ),
            }
        )
        return actions

    if result.get("loopback_mode"):
        loopback_ok = [a for a in loopback_attempts if a.get("ok")]
        if loopback_ok:
            ok_bauds = sorted({int(a.get("baud", 0)) for a in loopback_ok if a.get("baud")})
            actions.append(
                {
                    "id": "adapter_loopback_ok",
                    "detail": (
                        "USB-UART/isolator can write and read bytes on the isolated side "
                        f"at baud(s) {ok_bauds}. Reconnect TX/RX cross to STM32 and run protocol diagnosis next."
                    ),
                    "command": diagnose_command(result, loopback=False),
                }
            )
        else:
            actions.append(
                {
                    "id": "adapter_loopback_failed",
                    "detail": "Adapter loopback did not echo the test pattern. Fix USB-UART, isolator isolated-side power, USB cable, driver, or the TX/RX short before reconnecting STM32.",
                }
            )
        return actions

    selected_ports = result.get("selected_ports", [])
    if not ports and not selected_ports and not attempts and not loopback_attempts:
        actions.append(
            {
                "id": "no_serial_ports",
                "detail": "No pyserial COM ports are available. Replug USB-UART/isolator and check drivers.",
            }
        )
        return actions

    unsafe_pwm = [
        a
        for a in attempts
        if a.get("response_ok") and (a.get("pwm_active") or a.get("response", {}).get("pwm_active"))
    ]
    if unsafe_pwm:
        actions.append(
            {
                "id": "unsafe_pwm_active_on_safe_probe",
                "detail": "Blue Pill replied to a MODE_OFF+CLEAR_FAULT probe while reporting PWM active. Do not run HMI commands; force STOP/ESTOP at the bench and inspect firmware/state before continuing.",
            }
        )
        return actions

    if any(a.get("response_ok") for a in attempts):
        actions.append(
            {
                "id": "uart_protocol_ok",
                "detail": "Blue Pill replied to MODE_OFF+CLEAR_FAULT. Runtime HMI can use this port/baud.",
            }
        )
        return actions

    errors = [str(a.get("error", "")) for a in attempts]
    write_timeouts = [e for e in errors if "Write timeout" in e or "SerialTimeoutException" in e]
    no_responses = [a for a in attempts if a.get("write_ok") and str(a.get("error")) == "no response"]
    open_errors = [a for a in attempts if not a.get("write_ok") and a.get("error") and "timeout" not in str(a.get("error")).lower()]

    if write_timeouts and len(write_timeouts) == len(attempts):
        auto_summary = auto_port_selection_summary(result)
        auto_sentence = f" Auto selection: {auto_summary}." if auto_summary else ""
        hmi_summary = pc_direct_hmi_conflict_summary(result)
        hmi_sentence = f" {hmi_summary}" if hmi_summary else ""
        actions.append(
            {
                "id": "host_cannot_write_uart",
                "detail": (
                    "Every protocol attempt failed during write before any STM32 response could matter. "
                    f"Counts: protocol={counts['protocol']}, open_ok={counts['open_ok']}, "
                    f"write_returned={counts['write_returned']}, write_ok={counts['write_ok']}, "
                    f"flush_ok={counts['flush_ok']}, write_timeouts={counts['write_timeouts']}/{counts['protocol']}, "
                    f"flush_timeouts={counts['flush_timeouts']}. "
                    f"Selected port: {selected_port_summary(result)}. Visible ports: {visible_port_summary(result)}. "
                    f"{auto_sentence} "
                    f"{hmi_sentence} "
                    "Suspect USB isolator isolated-side power, USB-UART driver/cable, adapter TX path, wrong COM port, "
                    "or a stuck COM device before STM32 protocol."
                ),
            }
        )
        actions.append(
            {
                "id": "run_loopback",
                "detail": (
                    "Disconnect USB-UART TX/RX from STM32, short adapter TX to RX on the isolated side. "
                    "Run uart_loopback_preflight.py only after that physical preparation. "
                    "The wrapper stops PC-direct HMI if it uses the same COM port, runs adapter loopback, "
                    "and starts PC-direct HMI again."
                ),
                "command": diagnose_command(result, loopback=True),
            }
        )
    elif no_responses:
        actions.append(
            {
                "id": "write_ok_no_bluepill_response",
                "detail": "PC can write to the adapter but Blue Pill did not reply. Check TX/RX cross, common isolated GND, STM32 power, USART2 PA2/PA3 wiring, firmware baud.",
                "command": diagnose_command(result, loopback=False),
            }
        )
    elif open_errors:
        hmi_summary = pc_direct_hmi_conflict_summary(result)
        hmi_sentence = f" {hmi_summary}" if hmi_summary else ""
        actions.append(
            {
                "id": "port_open_error",
                "detail": (
                    "COM port could not be opened cleanly. "
                    f"Selected port: {selected_port_summary(result)}. Visible ports: {visible_port_summary(result)}. "
                    f"{hmi_sentence} "
                    "Close HMI/monitor processes or replug the adapter."
                ),
            }
        )
    else:
        actions.append(
            {
                "id": "uart_unknown_failure",
                "detail": "No protocol response and failure pattern is mixed. Inspect summary.json protocol_attempts.",
            }
        )

    return actions


def main() -> int:
    ap = argparse.ArgumentParser(description="Safe Blue Pill UART diagnostic. Sends only MODE_OFF+CLEAR_FAULT protocol frames.")
    ap.add_argument("--port", default="auto", help="COM port or auto")
    ap.add_argument("--bauds", default=",".join(str(baud) for baud in DEFAULT_BAUD_SWEEP))
    ap.add_argument("--dtr-rts-matrix", action="store_true", help="Try all DTR/RTS combinations.")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=0.15)
    ap.add_argument("--write-timeout", type=float, default=0.5)
    ap.add_argument(
        "--loopback",
        action="store_true",
        help="Explicit adapter-only loopback test. Disconnect STM32 TX/RX and short adapter TX to RX first.",
    )
    ap.add_argument(
        "--confirm-loopback-wired",
        action="store_true",
        help="Required with --loopback: STM32 TX/RX are disconnected and adapter TX/RX are shorted on the isolated side.",
    )
    ap.add_argument("--inventory-only", action="store_true", help="Collect serial/PnP/PIO inventory only; do not open or write any COM port.")
    ap.add_argument("--hmi-port", type=int, default=18080, help="PC-direct HMI HTTP port used for safe process conflict inventory.")
    ap.add_argument("--skip-hmi-process-check", action="store_true", help="Skip safe PC-direct HMI process inventory.")
    ap.add_argument("--out-root", default="tools/_preflight_exports")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    run_dir = (repo / args.out_root).resolve() / f"bluepill_uart_diagnose_{ts_tag()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"

    serial_ports = available_ports()
    pnp_info = windows_pnp_ports()
    auto_selection = auto_port_selection(serial_ports, pnp_info)
    selected_ports = auto_selection["selected_ports"] if args.port.lower() == "auto" else [args.port]
    bauds = parse_int_list(args.bauds)
    dtr_rts = list(itertools.product([False, True], [False, True])) if args.dtr_rts_matrix else [(False, False)]

    result: dict[str, Any] = {
        "tool": "bluepill_uart_diagnose",
        "run_dir": str(run_dir),
        "run_metadata": collect_run_metadata(repo),
        "safe_only": True,
        "serial_ports": serial_ports,
        "serial_port_hints": [annotate_serial_port(port) for port in serial_ports],
        "windows_pnp_ports": pnp_info,
        "port_inventory": port_inventory(serial_ports, pnp_info),
        "auto_port_selection": auto_selection,
        "pio_device_list": pio_device_list(),
        "pc_direct_hmi": (
            {"checked": False, "reason": "skipped_by_cli", "hmi_port": int(args.hmi_port)}
            if args.skip_hmi_process_check
            else pc_direct_hmi_snapshot(args.hmi_port)
        ),
        "selected_ports": selected_ports,
        "bauds": bauds,
        "dtr_rts_matrix": bool(args.dtr_rts_matrix),
        "loopback_mode": bool(args.loopback),
        "confirm_loopback_wired": bool(args.confirm_loopback_wired),
        "inventory_only": bool(args.inventory_only),
        "loopback_wiring_required": "Disconnect STM32 TX/RX. Short USB-UART TX to RX on the isolated side.",
        "uart_wiring_contract": UART_WIRING_CONTRACT,
        "protocol_attempts": [],
        "loopback_attempts": [],
    }

    if args.inventory_only:
        pass
    elif args.loopback:
        if not args.confirm_loopback_wired:
            result["blocked"] = True
            result["loopback_confirm_required_missing"] = True
            result["reason"] = (
                "missing --confirm-loopback-wired; refusing to open COM port until STM32 TX/RX are disconnected "
                "and adapter TX/RX are shorted on the isolated side"
            )
        else:
            for port in selected_ports:
                for baud in bauds:
                    result["loopback_attempts"].append(loopback_attempt(port, baud, args.timeout, args.write_timeout))
    else:
        for port in selected_ports:
            for baud in bauds:
                for dtr, rts in dtr_rts:
                    result["protocol_attempts"].append(
                        protocol_attempt(port, baud, dtr, rts, args.attempts, args.timeout, args.write_timeout)
                    )

    protocol_pass = any(a.get("response_ok") and not a.get("pwm_active") for a in result["protocol_attempts"])
    protocol_unsafe = any(a.get("response", {}).get("pwm_active") for a in result["protocol_attempts"] if isinstance(a.get("response"), dict))
    loopback_pass = any(a.get("ok") for a in result["loopback_attempts"])
    result["protocol_pass"] = bool(protocol_pass)
    result["protocol_unsafe_pwm_active"] = bool(protocol_unsafe)
    result["loopback_pass"] = bool(loopback_pass) if args.loopback else None
    result["pass"] = True if args.inventory_only else bool(loopback_pass) if args.loopback else bool(protocol_pass and not protocol_unsafe)
    result["selected_port"] = selected_port(result)
    result["selected_port_summary"] = selected_port_summary(result)
    result["visible_ports_summary"] = visible_port_summary(result)
    result["attempt_counts"] = attempt_counts(result)
    result["attempt_error_digest"] = attempt_error_digest(result)
    result["next_actions"] = classify(result)

    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "pass": result["pass"],
                "protocol_pass": result["protocol_pass"],
                "loopback_pass": result["loopback_pass"],
                "selected_port": result["selected_port"],
                "selected_port_summary": result["selected_port_summary"],
                "visible_ports": result["visible_ports_summary"],
                "pc_direct_hmi": pc_direct_hmi_conflict_summary(result),
                "attempt_counts": result["attempt_counts"],
                "attempt_error_digest": result["attempt_error_digest"],
                "summary": str(summary_path),
                "next_actions": [a["id"] for a in result["next_actions"]],
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
import importlib.util
from pathlib import Path
from typing import Any


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(url: str, body: dict | None = None, timeout_s: float = 1.0, attempts: int = 4) -> tuple[int, dict | None, str]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    headers["Connection"] = "close"
    last_error = ""
    for attempt in range(max(1, attempts)):
        req = urllib.request.Request(url, data=data, headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=timeout_s) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return int(resp.status), json.loads(text), text
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(text)
            except Exception:
                payload = None
            return int(exc.code), payload, text
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt + 1 < max(1, attempts):
                time.sleep(0.15 * (attempt + 1))
    return 0, None, last_error


def http_text(url: str, timeout_s: float = 1.0, attempts: int = 4) -> tuple[int, str]:
    last_error = ""
    for attempt in range(max(1, attempts)):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(url, headers={"Connection": "close"})
        try:
            with opener.open(req, timeout=timeout_s) as resp:
                return int(resp.status), resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt + 1 < max(1, attempts):
                time.sleep(0.15 * (attempt + 1))
    return 0, last_error


def wait_status(base: str, timeout_s: float = 5.0) -> tuple[bool, dict | None, str]:
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        try:
            code, payload, text = http_json(base + "/api/status", timeout_s=0.5)
            if code == 200 and payload and payload.get("ok"):
                return True, payload.get("data"), text
            last = text
        except Exception as exc:
            last = repr(exc)
        time.sleep(0.05)
    return False, None, last


def add_case(cases: list[CaseResult], name: str, ok: bool, detail: str = "", evidence: Any = None) -> None:
    cases.append(CaseResult(name=name, ok=bool(ok), detail=detail, evidence=evidence))


def load_server_module(repo: Path) -> Any:
    server_path = repo / "tools" / "unoq_web_server.py"
    spec = importlib.util.spec_from_file_location("unoq_web_server_under_test", server_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load unoq_web_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_rsp(mod: Any, *, status: int | None = None, bad: int = 0, fault: int = 0, vbus_raw: int | None = None) -> bytes:
    frame = bytearray(mod.FRAME_LEN)
    frame[0] = mod.RSP_HDR0
    frame[1] = mod.RSP_HDR1
    frame[3] = mod.STATUS_LINK_OK if status is None else status
    frame[5] = 1
    frame[6] = 0
    frame[7] = bad & 0xFF
    frame[8] = (bad >> 8) & 0xFF
    frame[9] = fault & 0xFF
    raw = mod.BP_VBUS_ZERO_RAW if vbus_raw is None else vbus_raw
    frame[17] = raw & 0xFF
    frame[18] = (raw >> 8) & 0xFF
    frame[mod.CRC_OFF] = mod.crc_xor(frame)
    return bytes(frame)


def prime_state(mod: Any, state: Any, rsp: bytes) -> None:
    state.link_ok = True
    state.last_rsp = rsp
    state.last_rx_time = time.monotonic()


def run_direct_guard_cases(repo: Path, cases: list[CaseResult]) -> None:
    mod = load_server_module(repo)

    def fake_bench_gate(ok: bool):
        def _runner(log_fn, url):
            if not ok and log_fn:
                log_fn(f"fake bench gate red url={url}")
            return ok

        return _runner

    no_link = mod.SharedState()
    ok, msg = mod.apply_cmd(no_link, "FAN PWM 0.25")
    add_case(cases, "direct_guard_rejects_fan_without_link", (not ok) and "link" in msg, msg)
    ok, msg = mod.apply_cmd(no_link, "FAN OFF")
    add_case(cases, "direct_guard_allows_fan_off_without_link", ok, msg)
    ok, msg = mod.apply_cmd(no_link, "BPFOC ON")
    add_case(cases, "direct_guard_rejects_bpfoc_without_link", (not ok) and "link" in msg, msg)
    ok, msg = mod.apply_cmd(no_link, "BPFOC OFF")
    add_case(cases, "direct_guard_allows_bpfoc_off_without_link", ok, msg)
    ok, msg = mod.apply_cmd(no_link, "MODE FOC")
    add_case(
        cases,
        "direct_mode_foc_without_link_does_not_enable_bpfoc_backend",
        ok and no_link.mode == mod.MODE_FOC and no_link.bp_foc_backend is False,
        msg,
    )
    no_link.uart_port = "COM_TEST"
    no_link.uart_baud = 460800
    no_link.uart_open = False
    no_link.uart_last_error = "SerialTimeoutException: Write timeout"
    no_link.uart_error_count = 2
    no_link.uart_last_error_time = time.monotonic()
    no_link_status = mod.status_payload(no_link)
    add_case(
        cases,
        "status_reports_uart_error_diagnostics",
        no_link_status.get("uart_port") == "COM_TEST"
        and no_link_status.get("uart_baud") == 460800
        and no_link_status.get("uart_open") is False
        and "Write timeout" in str(no_link_status.get("uart_last_error", ""))
        and no_link_status.get("uart_error_count") == 2
        and no_link_status.get("uart_last_error_age_s") is not None,
        evidence=no_link_status,
    )

    safe = mod.SharedState()
    prime_state(mod, safe, make_rsp(mod))
    ok, msg = mod.apply_cmd(safe, "FAN PWM 0.25")
    add_case(cases, "direct_guard_allows_safe_fan_pwm", ok and safe.fan_duty > 0.24, msg)
    high_raw_zero_scaled = mod.SharedState()
    prime_state(mod, high_raw_zero_scaled, make_rsp(mod, vbus_raw=1500))
    ok, msg = mod.apply_cmd(high_raw_zero_scaled, "FAN PWM 0.25")
    add_case(
        cases,
        "direct_guard_rejects_high_raw_with_zero_scaled_vbus",
        (not ok) and "raw DC bus" in msg,
        msg,
    )
    invalid_raw = mod.SharedState()
    prime_state(mod, invalid_raw, make_rsp(mod, vbus_raw=0))
    ok, msg = mod.apply_cmd(invalid_raw, "FAN PWM 0.25")
    add_case(cases, "direct_guard_rejects_invalid_raw_vbus", (not ok) and "invalid" in msg, msg)
    ok, msg = mod.apply_cmd(safe, "BPFOC ON")
    safe_bpfoc_frame = mod.build_frame(safe, 3)
    add_case(
        cases,
        "direct_guard_allows_safe_bpfoc_on_without_enable",
        ok and safe.mode == mod.MODE_FOC and safe.bp_foc_backend and not safe.enable and (safe_bpfoc_frame[3] & mod.FLAG_ENABLE) == 0,
        msg,
        {"frame_hex": safe_bpfoc_frame.hex(" ")},
    )
    ok, msg = mod.apply_cmd(safe, "MODE FOC")
    add_case(cases, "direct_mode_foc_preserves_explicit_bpfoc_backend", ok and safe.bp_foc_backend is True, msg)
    ok, msg = mod.apply_cmd(safe, "MODE VF")
    add_case(cases, "direct_mode_non_foc_clears_bpfoc_backend", ok and safe.mode == mod.MODE_SCALAR and safe.bp_foc_backend is False, msg)

    high_vdc = mod.SharedState()
    prime_state(mod, high_vdc, make_rsp(mod, vbus_raw=mod.BP_VBUS_CAL_RAW))
    ok, msg = mod.apply_cmd(high_vdc, "PRECHARGE ON")
    add_case(cases, "direct_rejects_removed_precharge_output", (not ok) and "not installed" in msg, msg)
    ok, msg = mod.apply_cmd(high_vdc, "BPFOC ON")
    add_case(cases, "direct_guard_rejects_bpfoc_high_vdc", (not ok) and "DC bus too high" in msg, msg)
    ok, msg = mod.apply_cmd(high_vdc, "MODE FOC")
    add_case(cases, "direct_mode_foc_high_vdc_does_not_enable_bpfoc_backend", ok and high_vdc.bp_foc_backend is False, msg)

    high_vdc_allow = mod.SharedState()
    high_vdc_allow.cmd_guard_allow_hv = True
    prime_state(mod, high_vdc_allow, make_rsp(mod, vbus_raw=mod.BP_VBUS_CAL_RAW))
    ok, msg = mod.apply_cmd(high_vdc_allow, "PRECHARGE ON")
    add_case(cases, "direct_allow_hv_does_not_restore_precharge", (not ok) and not high_vdc_allow.precharge, msg)

    high_vdc_disabled = mod.SharedState()
    high_vdc_disabled.cmd_guard_disabled = True
    prime_state(mod, high_vdc_disabled, make_rsp(mod, vbus_raw=mod.BP_VBUS_CAL_RAW))
    ok, msg = mod.apply_cmd(high_vdc_disabled, "PRECHARGE ON")
    add_case(cases, "direct_disabled_guard_does_not_restore_precharge", (not ok) and not high_vdc_disabled.precharge, msg)

    fault_disabled = mod.SharedState()
    fault_disabled.cmd_guard_disabled = True
    prime_state(mod, fault_disabled, make_rsp(mod, status=mod.STATUS_LINK_OK | mod.STATUS_FAULT, fault=5))
    ok, msg = mod.apply_cmd(fault_disabled, "PFC ON")
    add_case(cases, "direct_guard_disabled_still_rejects_fault", (not ok) and "fault" in msg, msg)

    link_loss = mod.SharedState()
    prime_state(mod, link_loss, make_rsp(mod))
    mod.apply_cmd(link_loss, "MODE VF")
    mod.apply_cmd(link_loss, "START")
    mod.apply_cmd(link_loss, "BPFOC ON")
    mod.apply_cmd(link_loss, "PRECHARGE ON")
    mod.apply_cmd(link_loss, "FAN PWM 0.5")
    mod.apply_cmd(link_loss, "BRAKE PWM 0.25")
    with link_loss.lock:
        mod.force_local_safe_outputs_locked(link_loss)
    snap = link_loss.snapshot()
    frame = mod.build_frame(link_loss, 7)
    ok = (
        snap["enable"] is False
        and snap["mode"] == mod.MODE_OFF
        and snap["diag"] is False
        and snap["bp_foc_backend"] is False
        and snap["ntc"] is False
        and snap["pfc"] is False
        and snap["precharge"] is False
        and snap["brake_pwm"] is False
        and snap["brake_duty"] == 0.0
        and snap["fan_duty"] == 0.0
        and snap["iotest"] is False
        and frame[3] == 0
        and frame[4] == mod.MODE_OFF
        and frame[14] == 0
        and frame[15] == 0
        and frame[16] == 0
        and frame[17] == 0
        and frame[18] == 0
    )
    add_case(cases, "direct_link_loss_clears_all_output_requests", ok, evidence={"snapshot": snap, "frame_hex": frame.hex(" ")})

    bad_counter = mod.SharedState()
    prime_state(mod, bad_counter, make_rsp(mod, bad=2))
    ok, msg = mod.apply_cmd(bad_counter, "PFC ON")
    add_case(cases, "direct_guard_rejects_bad_counter", (not ok) and "bad counter" in msg, msg)

    faulted = mod.SharedState()
    prime_state(mod, faulted, make_rsp(mod, status=mod.STATUS_LINK_OK | mod.STATUS_FAULT, fault=5))
    ok, msg = mod.apply_cmd(faulted, "PFC ON")
    add_case(cases, "direct_guard_rejects_fault", (not ok) and "fault" in msg, msg)

    start_state = mod.SharedState()
    start_state.mode = mod.MODE_SCALAR
    start_state.bench_gate_runner = fake_bench_gate(True)
    prime_state(mod, start_state, make_rsp(mod))
    ok, msg = mod.apply_cmd(start_state, "START")
    add_case(cases, "direct_guard_allows_start_when_safe_and_bench_gate_green", ok and start_state.enable, msg)

    mode_foc_start = mod.SharedState()
    mode_foc_start.bench_gate_runner = fake_bench_gate(True)
    prime_state(mod, mode_foc_start, make_rsp(mod))
    ok_mode, mode_msg = mod.apply_cmd(mode_foc_start, "MODE FOC")
    ok, msg = mod.apply_cmd(mode_foc_start, "START")
    add_case(
        cases,
        "direct_start_after_mode_foc_requires_explicit_bpfoc_on",
        ok_mode and (not ok) and "bpfoc backend off" in msg and not mode_foc_start.enable,
        f"mode={mode_msg}; start={msg}",
    )

    red_gate_state = mod.SharedState()
    red_gate_state.mode = mod.MODE_SCALAR
    red_gate_state.bench_gate_url = "http://127.0.0.1:18080"
    red_gate_state.bench_gate_runner = fake_bench_gate(False)
    prime_state(mod, red_gate_state, make_rsp(mod))
    ok, msg = mod.apply_cmd(red_gate_state, "START")
    add_case(cases, "direct_guard_rejects_start_when_bench_gate_red", (not ok) and "bench gate" in msg and not red_gate_state.enable, msg)

    high_vdc_start = mod.SharedState()
    high_vdc_start.mode = mod.MODE_SCALAR
    high_vdc_start.bench_gate_runner = fake_bench_gate(True)
    prime_state(mod, high_vdc_start, make_rsp(mod, vbus_raw=mod.BP_VBUS_CAL_RAW))
    ok, msg = mod.apply_cmd(high_vdc_start, "START")
    add_case(cases, "direct_guard_rejects_start_high_vdc_before_bench_gate", (not ok) and "DC bus too high" in msg and not high_vdc_start.enable, msg)

    disabled_red_gate_start = mod.SharedState()
    disabled_red_gate_start.mode = mod.MODE_SCALAR
    disabled_red_gate_start.cmd_guard_disabled = True
    disabled_red_gate_start.bench_gate_runner = fake_bench_gate(False)
    prime_state(mod, disabled_red_gate_start, make_rsp(mod, vbus_raw=mod.BP_VBUS_CAL_RAW))
    ok, msg = mod.apply_cmd(disabled_red_gate_start, "START")
    add_case(
        cases,
        "direct_guard_disabled_does_not_bypass_start_bench_gate",
        (not ok) and "bench gate" in msg and not disabled_red_gate_start.enable,
        msg,
    )


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    server_path = repo / "tools" / "unoq_web_server.py"
    port = free_tcp_port()
    base = f"http://127.0.0.1:{port}"
    cmd = [
        sys.executable,
        "-u",
        str(server_path),
        "--serial",
        "__NO_SUCH_PC_DIRECT_SERIAL__",
        "--baud",
        "460800",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--rx-timeout",
        "0.05",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    cases: list[CaseResult] = []
    unused_port = free_tcp_port()
    unavailable_code, unavailable_payload, unavailable_text = http_json(
        f"http://127.0.0.1:{unused_port}/api/status",
        timeout_s=0.05,
        attempts=1,
    )
    add_case(
        cases,
        "http_json_unavailable_returns_error_tuple",
        unavailable_code == 0 and unavailable_payload is None and bool(unavailable_text),
        unavailable_text,
        {"status": unavailable_code, "payload": unavailable_payload},
    )
    server_source = server_path.read_text(encoding="utf-8", errors="replace")
    add_case(
        cases,
        "http_server_is_threaded_for_bench_gate_reentry",
        "ThreadingHTTPServer((args.host, args.port), Handler)" in server_source,
        "START checks call bench_gate_report, which calls /api/status on this same HMI server",
    )
    output = ""
    try:
        ok, status, detail = wait_status(base)
        add_case(cases, "http_status_available_without_serial", ok, detail if not ok else "", status)
        if status is not None:
            add_case(cases, "status_reports_no_link", status.get("link") is False and status.get("state") == "NO_LINK", evidence=status)
            add_case(cases, "status_pwm_off_without_serial", int(status.get("pwm", 1)) == 0, evidence=status)
            add_case(cases, "status_no_enable_without_serial", status.get("enable") is False, evidence=status)
            add_case(cases, "status_bpfoc_off_without_serial", int(status.get("bp_foc_backend", 1)) == 0, evidence=status)

        code, html = http_text(base + "/", timeout_s=1.0)
        add_case(cases, "html_contains_bpfoc_controls", code == 200 and "BPFOC ON" in html and "BPFOC OFF" in html, evidence={"status": code})

        for cmd_text in ("STOP", "CLEAR", "DIAG ON", "DIAG OFF", "FAN PWM 0", "FAN OFF", "BPFOC OFF", "PFC OFF", "BRAKE OFF", "MODE VF"):
            code, payload, text = http_json(base + "/api/cmd", {"cmd": cmd_text}, timeout_s=1.0)
            add_case(
                cases,
                f"cmd_{cmd_text.replace(' ', '_').lower()}_accepted",
                code == 200 and bool(payload and payload.get("ok")),
                text,
                payload,
            )

        for cmd_text in ("FAN PWM 0.25", "FAN ON", "BPFOC ON", "PFC ON", "BRAKE PWM 0.25", "IOTEST ON"):
            code, payload, text = http_json(base + "/api/cmd", {"cmd": cmd_text}, timeout_s=1.0)
            add_case(
                cases,
                f"cmd_{cmd_text.replace(' ', '_').lower()}_rejected_without_link",
                code == 400 and bool(payload and not payload.get("ok")) and "link" in str(payload.get("error", "")),
                text,
                payload,
            )

        for cmd_text in ("PRECHARGE ON", "PRECHARGE OFF"):
            code, payload, text = http_json(base + "/api/cmd", {"cmd": cmd_text}, timeout_s=1.0)
            add_case(
                cases,
                f"cmd_{cmd_text.replace(' ', '_').lower()}_rejected_as_removed",
                code == 400 and bool(payload and not payload.get("ok")) and "not installed" in str(payload.get("error", "")),
                text,
                payload,
            )

        code, payload, text = http_json(base + "/api/cmd", {"cmd": "NTC ON"}, timeout_s=1.0)
        add_case(
            cases,
            "cmd_ntc_rejected_as_unsupported",
            code == 400 and bool(payload and not payload.get("ok")) and "not connected" in str(payload.get("error", "")),
            text,
            payload,
        )

        code, payload, text = http_json(base + "/api/cmd", {"cmd": "START"}, timeout_s=1.0)
        add_case(
            cases,
            "start_rejected_without_link_http",
            code == 400 and bool(payload and not payload.get("ok")) and any(
                token in str(payload.get("error", "")).lower()
                for token in ("link", "mode off", "bench gate", "bpfoc backend")
            ),
            text,
            payload,
        )

        run_direct_guard_cases(repo, cases)
    finally:
        proc.terminate()
        try:
            output, _ = proc.communicate(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate(timeout=3.0)

    failed = [c for c in cases if not c.ok]
    summary = {
        "tool": "pc_direct_hmi_selftest",
        "pass": len(failed) == 0,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "port": port,
        "server_cmd": cmd,
        "server_output_tail": output[-4000:],
        "cases": [c.__dict__ for c in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    raise SystemExit(main())

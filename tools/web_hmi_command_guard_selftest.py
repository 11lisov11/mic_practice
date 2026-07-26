#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


def add_case(cases: list[CaseResult], name: str, ok: bool, detail: str = "", evidence: Any = None) -> None:
    cases.append(CaseResult(name=name, ok=bool(ok), detail=detail, evidence=evidence))


def load_server_module(repo: Path) -> Any:
    server_path = repo / "web_hmi" / "server.py"
    spec = importlib.util.spec_from_file_location("web_hmi_server_under_test", server_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load web_hmi/server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_status(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "link": True,
        "state": "SAFE",
        "state_code": 0,
        "pwm": 0,
        "estop": 0,
        "bp_fault": 0,
        "bp_bad_cnt": 0,
        "bp_rsp_age_ms": 25,
        "bp_vdc": 0.0,
        "vdc": 0.0,
    }
    data.update(overrides)
    return data


def safe_status_without_vbus(**overrides: Any) -> dict[str, Any]:
    data = safe_status(**overrides)
    data.pop("vdc", None)
    data.pop("bp_vdc", None)
    return data


def guard(mod: Any, cmd: str, status: dict[str, Any] | None, **cfg_kwargs: Any) -> tuple[bool, str]:
    cfg = mod.CommandGuardConfig(max_vdc=60.0, **cfg_kwargs)
    return mod.command_guard_check(cmd, status, cfg)


def fake_bench_gate(ok: bool):
    def _runner(log_fn, url):
        if not ok and log_fn:
            log_fn(f"fake bench gate red url={url}")
        return ok

    return _runner


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    mod = load_server_module(repo)
    cases: list[CaseResult] = []

    class FakeTermios:
        B115200 = 115200
        B460800 = 460800

    original_termios = mod.termios
    try:
        mod.termios = FakeTermios
        add_case(cases, "termios_baud_460800_supported", mod.termios_baud_constant(460800) == 460800, "460800")
        unsupported_failed = False
        try:
            mod.termios_baud_constant(12345)
        except RuntimeError as exc:
            unsupported_failed = "12345" in str(exc)
        add_case(cases, "termios_baud_unsupported_fails_closed", unsupported_failed, "12345")
    finally:
        mod.termios = original_termios
    bridge = mod.RpcBridge("serial:/dev/null", serial_baud=460800)
    add_case(
        cases,
        "rpc_bridge_serial_baud_propagates",
        getattr(bridge._serial_text, "_baud", None) == 460800,
        "serial_baud=460800",
    )
    full_status = [0] * 70
    full_status[0] = 0
    full_status[1] = 1
    full_status[2] = 0
    full_status[3] = 12.3
    full_status[4] = 456.0
    full_status[5] = 1.1
    full_status[6] = 2.2
    full_status[7] = -3.3
    full_status[8] = 24.0
    full_status[9] = -0.1
    full_status[10] = 0.2
    full_status[11] = 2.7
    full_status[12] = 1
    full_status[13] = 0.33
    full_status[14] = 12.5
    full_status[15] = 10.0
    full_status[16] = 0
    full_status[17] = 1
    full_status[18] = 0
    full_status[19] = 1
    full_status[20] = 0.25
    full_status[21] = 2048
    full_status[22] = 1
    full_status[23] = 180.0
    full_status[24] = 100
    full_status[25] = 0
    full_status[26] = 30
    full_status[27] = 1
    full_status[28] = 0
    full_status[29] = 5
    full_status[30] = 77
    full_status[31] = 11
    full_status[32] = 22
    full_status[33] = 33
    full_status[34] = 123.0
    full_status[35] = 2.05
    full_status[36] = 4.10
    full_status[37] = 0
    full_status[38] = 1
    full_status[39] = 1
    full_status[40] = 2.0
    full_status[41] = 0.1
    full_status[42] = 0.5
    full_status[43] = 3
    full_status[44] = 4
    full_status[45] = 0
    full_status[46] = 0
    full_status[47] = 3256
    full_status[48] = 315.0
    full_status[49] = 44
    full_status[50] = 1500
    full_status[51] = 1.21
    full_status[52] = 27.8
    full_status[53] = 3
    full_status[54] = 1000
    full_status[55] = 1001
    full_status[56] = 1002
    full_status[57] = 0.81
    full_status[58] = 0.82
    full_status[59] = 0.83
    full_status[60] = 3
    full_status[61] = 55
    full_status[62] = 8
    full_status[63] = 0
    full_status[64] = 1
    full_status[65] = 0.42
    full_status[66] = 0.51
    full_status[67] = 1230.0
    full_status[68] = 1
    full_status[69] = 5
    bridge._call = lambda method, params, timeout=1.5, retries=1: [1, 42, None, full_status]  # type: ignore[method-assign]
    st_ok, st_data, st_err = bridge.get()
    mapping_ok = (
        st_ok
        and st_err is None
        and st_data is not None
        and st_data.get("mode") == "FOC"
        and st_data.get("bp_vdc") == 315.0
        and st_data.get("precharge") == 1
        and abs(float(st_data.get("fan_duty", -1.0)) - 0.42) < 0.001
        and abs(float(st_data.get("bp_fan_duty", -1.0)) - 0.51) < 0.001
        and st_data.get("bp_fan_rpm") == 1230.0
        and st_data.get("bp_foc_backend") == 1
        and st_data.get("bp_cmd_mode") == 5
        and st_data.get("bp_temp_valid") == 1
        and st_data.get("bp_temp_fault") == 1
        and st_data.get("bp_phase_valid") == 1
        and st_data.get("bp_phase_c_virtual") == 1
    )
    add_case(cases, "rpc_status_array_70_mapping", bool(mapping_ok), st_err or "", st_data)

    for cmd in ("START",):
        add_case(cases, f"start_detected_{cmd}", mod.command_requests_start(cmd), cmd)
    for cmd in ("STOP", "CLEAR", "MODE VF", "DIAG ON"):
        add_case(cases, f"start_not_detected_{cmd.replace(' ', '_').lower()}", not mod.command_requests_start(cmd), cmd)

    service_on = (
        "FAN ON",
        "FAN 0.25",
        "FAN PWM 0.25",
        "FAN DUTY 0.25",
        "PRECHARGE ON",
        "PFC ON",
        "BPFOC ON",
        "BRAKE 0.2",
        "BRAKE PWM 0.2",
        "IOTEST ON",
    )
    for cmd in service_on:
        add_case(cases, f"service_detected_{cmd.replace(' ', '_').lower()}", mod.command_requests_service_output(cmd), cmd)

    service_off = (
        "FAN OFF",
        "FAN 0",
        "FAN PWM 0",
        "PRECHARGE OFF",
        "PFC OFF",
        "BPFOC OFF",
        "BRAKE OFF",
        "BRAKE 0",
        "IOTEST OFF",
    )
    for cmd in service_off:
        add_case(cases, f"service_not_detected_{cmd.replace(' ', '_').lower()}", not mod.command_requests_service_output(cmd), cmd)

    ok, msg = guard(mod, "FAN PWM 0.25", safe_status())
    add_case(cases, "guard_allows_safe_service", ok, msg)
    ok, msg = guard(mod, "BPFOC ON", safe_status())
    add_case(cases, "guard_allows_safe_bpfoc_on", ok, msg)
    ok, msg = guard(mod, "START", safe_status())
    add_case(cases, "guard_rejects_start_without_bench_gate", (not ok) and "bench gate" in msg, msg)
    ok, msg = guard(mod, "START", safe_status(), bench_gate_url="http://127.0.0.1:18080", bench_gate_runner=fake_bench_gate(True))
    add_case(cases, "guard_allows_start_with_green_bench_gate", ok, msg)
    ok, msg = guard(mod, "START", safe_status(), bench_gate_url="http://127.0.0.1:18080", bench_gate_runner=fake_bench_gate(False))
    add_case(cases, "guard_rejects_start_with_red_bench_gate", (not ok) and "fake bench gate red" in msg, msg)
    ok, msg = guard(mod, "FAN OFF", safe_status(bp_fault=9, bp_bad_cnt=3, bp_rsp_age_ms=999999, vdc=315.0))
    add_case(cases, "guard_ignores_off_command", ok, msg)
    ok, msg = guard(mod, "BPFOC OFF", safe_status(bp_fault=9, bp_bad_cnt=3, bp_rsp_age_ms=999999, vdc=315.0))
    add_case(cases, "guard_ignores_bpfoc_off_command", ok, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", None)
    add_case(cases, "guard_rejects_missing_status", (not ok) and "unavailable" in msg, msg)
    ok, msg = guard(mod, "BPFOC ON", None)
    add_case(cases, "guard_rejects_bpfoc_missing_status", (not ok) and "unavailable" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(link=False))
    add_case(cases, "guard_rejects_link_down", (not ok) and "stale or down" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(bp_rsp_age_ms=5000))
    add_case(cases, "guard_rejects_stale_link", (not ok) and "stale or down" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(state="FAULT", state_code=4))
    add_case(cases, "guard_rejects_not_safe", (not ok) and "not SAFE" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(pwm=1))
    add_case(cases, "guard_rejects_pwm_active", (not ok) and "PWM" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(estop=1))
    add_case(cases, "guard_rejects_estop", (not ok) and "ESTOP" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(bp_fault=5))
    add_case(cases, "guard_rejects_fault", (not ok) and "fault" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(bp_bad_cnt=1))
    add_case(cases, "guard_rejects_bad_counter", (not ok) and "bad" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(bp_bad_cnt=0, bp_bad=1))
    add_case(cases, "guard_rejects_legacy_bad_counter", (not ok) and "bad" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status_without_vbus())
    add_case(cases, "guard_rejects_missing_vbus", (not ok) and "telemetry" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(vdc=315.0, bp_vdc=315.0))
    add_case(cases, "guard_rejects_high_vdc", (not ok) and "too high" in msg, msg)
    ok, msg = guard(mod, "BPFOC ON", safe_status(vdc=315.0, bp_vdc=315.0))
    add_case(cases, "guard_rejects_bpfoc_high_vdc", (not ok) and "too high" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(vdc=315.0, bp_vdc=315.0), allow_hv=True)
    add_case(cases, "guard_allow_hv_permits_high_vdc", ok, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(vdc=315.0, bp_vdc=315.0), disabled=True)
    add_case(cases, "guard_disabled_only_permits_high_vdc", ok, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status_without_vbus(), allow_hv=True)
    add_case(cases, "guard_allow_hv_still_rejects_missing_vbus", (not ok) and "telemetry" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status_without_vbus(), disabled=True)
    add_case(cases, "guard_disabled_still_rejects_missing_vbus", (not ok) and "telemetry" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(state="FAULT", bp_fault=5), disabled=True)
    add_case(cases, "guard_disabled_still_rejects_fault", (not ok) and "fault" in msg, msg)
    ok, msg = guard(mod, "START", safe_status(vdc=315.0, bp_vdc=315.0), disabled=True, bench_gate_runner=fake_bench_gate(False))
    add_case(cases, "guard_disabled_does_not_bypass_start_bench_gate", (not ok) and "bench gate" in msg, msg)

    class FakeRpc:
        def __init__(self, statuses: list[dict[str, Any] | None], stop_ok: bool = True) -> None:
            self.statuses = list(statuses)
            self.stop_ok = stop_ok
            self.commands: list[str] = []

        def cmd(self, cmd: str) -> tuple[bool, str]:
            self.commands.append(cmd)
            return (self.stop_ok, "" if self.stop_ok else "stop failed")

        def get(self) -> tuple[bool, dict[str, Any] | None, str]:
            if not self.statuses:
                return False, None, "no status"
            data = self.statuses.pop(0)
            if data is None:
                return False, None, "no status"
            return True, data, ""

    def firmware_update_safe(status: dict[str, Any] | None, max_vdc: float = 10.0) -> tuple[bool, dict[str, Any] | None, str, list[str]]:
        rpc = FakeRpc([status])
        app = type("FakeApp", (), {"rpc": rpc})()
        server = type("FakeServer", (), {"app": app})()
        handler = type("FakeHandler", (), {"server": server})()
        cfg = mod.FirmwareUpdateConfig(
            token_file=None,
            upload_dir="",
            remoteocd_bin="",
            remoteocd_cfg="",
            max_bytes=1024,
            timeout_sec=1.0,
            max_vdc=max_vdc,
        )
        old_sleep = mod.time.sleep
        try:
            mod.time.sleep = lambda _s: None
            ok, data, msg = mod.Handler._ensure_firmware_update_safe(handler, cfg)
        finally:
            mod.time.sleep = old_sleep
        return ok, data, msg, rpc.commands

    data = safe_status()
    data.pop("vdc", None)
    ok, _data, msg, commands = firmware_update_safe(data)
    add_case(cases, "firmware_update_allows_bp_vdc_without_legacy_vdc", ok and commands == ["STOP"], msg)

    ok, _data, msg, _commands = firmware_update_safe(safe_status_without_vbus())
    add_case(cases, "firmware_update_rejects_missing_vbus", (not ok) and "telemetry" in msg, msg)

    ok, _data, msg, _commands = firmware_update_safe(safe_status(vdc="bad", bp_vdc="bad"))
    add_case(cases, "firmware_update_rejects_invalid_vbus", (not ok) and "telemetry" in msg, msg)

    ok, _data, msg, _commands = firmware_update_safe(safe_status(vdc=0.0, bp_vdc=315.0))
    add_case(cases, "firmware_update_rejects_high_bp_vdc", (not ok) and "too high" in msg, msg)

    ok, _data, msg, _commands = firmware_update_safe(safe_status(bp_bad_cnt=1))
    add_case(cases, "firmware_update_rejects_bad_counter", (not ok) and "bad" in msg, msg)

    ok, _data, msg, _commands = firmware_update_safe(safe_status(bp_rsp_age_ms=5000))
    add_case(cases, "firmware_update_rejects_stale_bluepill_link", (not ok) and "stale or down" in msg, msg)

    failed = [c for c in cases if not c.ok]
    summary = {
        "tool": "web_hmi_command_guard_selftest",
        "pass": len(failed) == 0,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [c.__dict__ for c in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    raise SystemExit(main())

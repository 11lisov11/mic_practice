#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
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
        "bp_vbus_age_ms": 25,
        "bp_vbus_raw": 1966,
        "bp_temp_valid": 1,
        "bp_temp_fault": 0,
        "bp_temp_age_ms": 25,
        "bp_temp_c": 25.0,
        "bp_vdc": 0.0,
        "vdc": 0.0,
        "precharge": 0,
        "pfc": 0,
        "brake": 0,
        "brake_duty": 0.0,
        "fan_duty": 0.0,
        "bp_fan_duty": 0.0,
        "bp_ext": 0,
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

    now = 1000.0
    ok, msg = mod.validate_bench_gate_attestation(
        {"ready_for_active_pwm": True, "issued_at": 998.0, "expires_at": 1003.0},
        now=now,
    )
    add_case(cases, "bench_attestation_accepts_fresh_green", ok, msg)
    ok, msg = mod.validate_bench_gate_attestation(
        {"ready_for_active_pwm": False, "issued_at": 998.0, "expires_at": 1003.0},
        now=now,
    )
    add_case(cases, "bench_attestation_rejects_red", (not ok) and "not green" in msg, msg)
    ok, msg = mod.validate_bench_gate_attestation(
        {"ready_for_active_pwm": True, "issued_at": 980.0, "expires_at": 1003.0},
        now=now,
    )
    add_case(cases, "bench_attestation_rejects_stale", (not ok) and "stale" in msg, msg)
    ok, msg = mod.validate_bench_gate_attestation(
        {"ready_for_active_pwm": True, "issued_at": 998.0, "expires_at": 999.0},
        now=now,
    )
    add_case(cases, "bench_attestation_rejects_expired", (not ok) and "expired" in msg, msg)
    ok, msg = mod.validate_bench_gate_attestation(
        {"ready_for_active_pwm": True, "issued_at": 998.0, "expires_at": 1015.0},
        now=now,
    )
    add_case(cases, "bench_attestation_rejects_long_window", (not ok) and "too long" in msg, msg)

    ok, msg = mod.vbus_capture_precheck(safe_status())
    add_case(cases, "vbus_capture_accepts_safe_outputs_off", ok, msg)
    ok, msg = mod.vbus_capture_precheck(safe_status(pwm=1))
    add_case(cases, "vbus_capture_rejects_pwm", (not ok) and "PWM" in msg, msg)
    ok, msg = mod.vbus_capture_precheck(safe_status(bp_vbus_age_ms=1500))
    add_case(cases, "vbus_capture_rejects_stale_vbus", (not ok) and "stale" in msg, msg)
    ok, msg = mod.vbus_capture_precheck(safe_status(precharge=1))
    add_case(cases, "vbus_capture_rejects_active_relay", (not ok) and "precharge=1" in msg, msg)
    capture = mod.vbus_capture_summary(
        [safe_status(bp_vbus_raw=100, bp_vdc=0.0), safe_status(bp_vbus_raw=104, bp_vdc=0.8)],
        0.0,
    )
    add_case(
        cases,
        "vbus_capture_summary_records_raw_scaled_and_meter",
        capture["outputs_commanded"] is False
        and capture["meter_vdc"] == 0.0
        and capture["bp_vbus_raw"]["mean"] == 102.0
        and capture["bp_vdc"]["mean"] == 0.4,
        evidence=capture,
    )

    lv_cfg = mod.HvArmConfig(
        enabled=True,
        ttl_sec=30.0,
        min_vdc=0.0,
        max_vdc=10.0,
        confirm="ARM LV HV OFF",
        profile="lv",
    )
    ok, msg = mod.hv_arm_precheck(safe_status(vdc=0.0, bp_vdc=0.0), lv_cfg)
    add_case(cases, "lv_arm_accepts_clean_zero_bus", ok, msg)
    ok, msg = mod.hv_arm_precheck(safe_status(vdc=0.0, bp_vdc=0.0, bp_vbus_raw=3256), lv_cfg)
    add_case(cases, "lv_arm_rejects_high_raw_bus_with_zero_scaled", (not ok) and "raw DC bus" in msg, msg)
    ok, msg = mod.hv_arm_precheck(safe_status(vdc=0.0, bp_vdc=0.0, bp_vbus_raw=120), lv_cfg)
    add_case(cases, "lv_arm_rejects_raw_below_calibrated_zero", (not ok) and "raw DC bus" in msg, msg)
    ok, msg = mod.hv_arm_precheck(safe_status(vdc=12.0, bp_vdc=12.0), lv_cfg)
    add_case(cases, "lv_arm_rejects_bus_above_10v", (not ok) and "LV arm window" in msg, msg)
    ok, msg = mod.hv_runtime_check(safe_status(vdc=0.0, bp_vdc=0.0), lv_cfg)
    add_case(cases, "lv_runtime_accepts_clean_zero_bus", ok, msg)
    ok, msg = mod.hv_runtime_check(safe_status(vdc=315.0, bp_vdc=315.0), lv_cfg)
    add_case(cases, "lv_runtime_rejects_hv_bus", (not ok) and "LV runtime window" in msg, msg)
    lv_arm = mod.HvArmState(lv_cfg)
    ok, msg = lv_arm.arm("ARM 310V", safe_status())
    add_case(cases, "lv_arm_rejects_hv_confirmation_phrase", (not ok) and "mismatch" in msg, msg)
    ok, msg = lv_arm.arm("ARM LV HV OFF", safe_status())
    lv_snapshot = lv_arm.snapshot()
    add_case(
        cases,
        "lv_arm_snapshot_exposes_profile_and_phrase",
        ok
        and lv_snapshot["hmi_arm_profile"] == "lv"
        and lv_snapshot["hmi_arm_confirm"] == "ARM LV HV OFF",
        msg,
        lv_snapshot,
    )
    lv_arm.mark_started()
    lv_arm.mark_stopped()
    with lv_arm._lock:
        lv_arm._expires_at = mod._now_ts() - 1.0
    add_case(
        cases,
        "manual_service_off_prevents_false_expiry_estop",
        not lv_arm.take_expired_session_action(),
    )
    ok, msg = mod.arm_profile_switch_precheck(safe_status(), lv_cfg)
    add_case(cases, "arm_profile_switch_accepts_safe_lv_selection", ok, msg)
    ok, msg = mod.arm_profile_switch_precheck(safe_status(precharge=1), lv_cfg)
    add_case(cases, "arm_profile_switch_rejects_active_relay", (not ok) and "relay" in msg, msg)
    ok, msg = mod.arm_profile_switch_precheck(safe_status(vdc=315.0, bp_vdc=315.0), lv_cfg)
    add_case(cases, "arm_profile_switch_rejects_lv_with_hv_bus", (not ok) and "profile window" in msg, msg)
    hv_for_switch = mod.HvArmConfig(
        enabled=True,
        ttl_sec=30.0,
        min_vdc=100.0,
        max_vdc=400.0,
        confirm="ARM 310V",
        profile="hv",
    )
    switch_state = mod.HvArmState(hv_for_switch)
    switch_state.set_config(lv_cfg)
    switch_snapshot = switch_state.snapshot()
    add_case(
        cases,
        "arm_profile_config_switch_disarms_and_selects_lv",
        switch_snapshot["hmi_arm_profile"] == "lv" and switch_snapshot["hmi_hv_armed"] == 0,
        evidence=switch_snapshot,
    )

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "unoq.log"
        log_path.write_bytes(b"\x00\x002026-08-05 11:00:00 CMD STOP\n")
        store = mod.LogStore(max_bytes=4096, log_path=str(log_path), file_max_bytes=4096)
        lines = store.dump_since(0.0)
        add_case(
            cases,
            "persistent_log_strips_sparse_nul_bytes",
            lines == ["2026-08-05 11:00:00 CMD STOP"],
            evidence=lines,
        )

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
    full_status = [0] * 78
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
    full_status[70] = 2026082601
    full_status[71] = 0
    full_status[72] = 1
    full_status[73] = 1
    full_status[74] = 0
    full_status[75] = 2
    full_status[76] = 1
    full_status[77] = 1
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
        and st_data.get("bp_mcsdk_telemetry") == 1
        and st_data.get("bp_vbus_valid") == 1
        and st_data.get("bp_softstart_ready") == 1
        and st_data.get("bp_precharge_managed") == 0
        and st_data.get("rpc_schema_version") == 2
        and st_data.get("mc_supported_modes") == ["VF"]
        and st_data.get("mc_vdc") == st_data.get("bp_vdc")
    )
    add_case(cases, "rpc_status_array_78_mapping", bool(mapping_ok), st_err or "", st_data)

    transition_status = full_status[:75]
    transition_status[74] = 1
    bridge._call = lambda method, params, timeout=1.5, retries=1: [1, 43, None, transition_status]  # type: ignore[method-assign]
    transition_ok, transition_data, transition_err = bridge.get()
    add_case(
        cases,
        "rpc_status_array_75_transition_fails_closed",
        transition_ok
        and transition_err is None
        and transition_data is not None
        and transition_data.get("bp_softstart_ready") == 0
        and transition_data.get("rpc_schema_version") == 1
        and transition_data.get("mc_supported_modes") == [],
        transition_err or "",
        transition_data,
    )

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
        "MCFOC ON",
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
        "MCFOC OFF",
        "BPFOC OFF",
        "BRAKE OFF",
        "BRAKE 0",
        "IOTEST OFF",
    )
    for cmd in service_off:
        add_case(cases, f"service_not_detected_{cmd.replace(' ', '_').lower()}", not mod.command_requests_service_output(cmd), cmd)
        add_case(cases, f"service_release_detected_{cmd.replace(' ', '_').lower()}", mod.command_releases_service_output(cmd), cmd)

    add_case(cases, "safe_status_has_no_active_outputs", not mod.status_has_active_outputs(safe_status()))
    add_case(cases, "precharge_status_has_active_output", mod.status_has_active_outputs(safe_status(precharge=1, bp_ext=8)))
    add_case(cases, "pwm_status_has_active_output", mod.status_has_active_outputs(safe_status(pwm=1)))

    ok, msg = guard(mod, "FAN PWM 0.25", safe_status())
    add_case(cases, "guard_allows_safe_service", ok, msg)
    ok, msg = guard(mod, "MCFOC ON", safe_status())
    add_case(cases, "guard_allows_safe_mcfoc_on", ok, msg)
    ok, msg = guard(mod, "START", safe_status())
    add_case(cases, "guard_rejects_start_without_bench_gate", (not ok) and "bench gate" in msg, msg)
    ok, msg = guard(mod, "START", safe_status(), bench_gate_url="http://127.0.0.1:18080", bench_gate_runner=fake_bench_gate(True))
    add_case(cases, "guard_allows_start_with_green_bench_gate", ok, msg)
    ok, msg = guard(mod, "START", safe_status(), bench_gate_url="http://127.0.0.1:18080", bench_gate_runner=fake_bench_gate(False))
    add_case(cases, "guard_rejects_start_with_red_bench_gate", (not ok) and "fake bench gate red" in msg, msg)
    ok, msg = guard(mod, "START", safe_status(), local_bench_gate=True)
    add_case(cases, "guard_allows_start_with_explicit_local_gate", ok and "standalone" in msg, msg)
    ok, msg = guard(mod, "FAN OFF", safe_status(bp_fault=9, bp_bad_cnt=3, bp_rsp_age_ms=999999, vdc=315.0))
    add_case(cases, "guard_ignores_off_command", ok, msg)
    ok, msg = guard(mod, "MCFOC OFF", safe_status(bp_fault=9, bp_bad_cnt=3, bp_rsp_age_ms=999999, vdc=315.0))
    add_case(cases, "guard_ignores_mcfoc_off_command", ok, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", None)
    add_case(cases, "guard_rejects_missing_status", (not ok) and "unavailable" in msg, msg)
    ok, msg = guard(mod, "MCFOC ON", None)
    add_case(cases, "guard_rejects_mcfoc_missing_status", (not ok) and "unavailable" in msg, msg)
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
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(vdc=0.0, bp_vdc=0.0, bp_vbus_raw=3256))
    add_case(cases, "guard_rejects_high_raw_vbus_with_zero_scaled", (not ok) and "raw DC bus" in msg, msg)
    missing_raw = safe_status()
    missing_raw.pop("bp_vbus_raw", None)
    ok, msg = guard(mod, "FAN PWM 0.25", missing_raw)
    add_case(cases, "guard_rejects_missing_raw_vbus", (not ok) and "missing" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(bp_vbus_raw=0))
    add_case(cases, "guard_rejects_invalid_raw_vbus", (not ok) and "invalid" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", safe_status(bp_vbus_age_ms=5000))
    add_case(cases, "guard_rejects_stale_raw_vbus", (not ok) and "stale" in msg, msg)
    direct_status = safe_status(
        bp_vbus_raw=0,
        bp_vdc=0.0,
        vdc=0.0,
        bp_mcsdk_telemetry=1,
        bp_vbus_valid=1,
    )
    ok, msg = guard(mod, "FAN PWM 0.25", direct_status)
    add_case(cases, "guard_accepts_direct_mcsdk_zero_bus", ok, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", dict(direct_status, bp_vbus_valid=0))
    add_case(cases, "guard_rejects_invalid_direct_mcsdk_vbus", (not ok) and "not valid" in msg, msg)
    ok, msg = guard(mod, "FAN PWM 0.25", dict(direct_status, bp_vbus_raw=20))
    add_case(cases, "guard_rejects_disagreeing_direct_mcsdk_vbus", (not ok) and "disagree" in msg, msg)
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

    hv_cfg = mod.HvArmConfig(enabled=True, ttl_sec=30.0, min_vdc=100.0, max_vdc=400.0)
    hv_status = safe_status(vdc=315.0, bp_vdc=315.0, bp_vbus_raw=3459)
    ok, msg = mod.hv_arm_precheck(hv_status, hv_cfg)
    add_case(cases, "hv_arm_rejects_incomplete_vbus_calibration", (not ok) and "calibration" in msg, msg)
    mod.VBUS_HV_CALIBRATION_VALID = True
    ok, msg = mod.hv_arm_precheck(hv_status, hv_cfg)
    add_case(cases, "hv_arm_accepts_clean_315v_status", ok, msg)
    ok, msg = mod.hv_arm_precheck(safe_status(vdc=60.0, bp_vdc=60.0), hv_cfg)
    add_case(cases, "hv_arm_rejects_low_bus", (not ok) and "window" in msg, msg)
    ok, msg = mod.hv_arm_precheck(
        safe_status(vdc=315.0, bp_vdc=315.0, bp_vbus_raw=3459, bp_temp_c=-38.0), hv_cfg
    )
    add_case(cases, "hv_arm_rejects_implausible_temperature", (not ok) and "implausible" in msg, msg)
    ok, msg = mod.hv_arm_precheck(
        safe_status(vdc=315.0, bp_vdc=315.0, bp_vbus_raw=3459, bp_temp_fault=1), hv_cfg
    )
    add_case(cases, "hv_arm_rejects_temperature_fault", (not ok) and "temperature fault" in msg, msg)
    ok, msg = mod.hv_arm_precheck(safe_status(vdc=315.0, bp_vdc=315.0, bp_bad_cnt=1), hv_cfg)
    add_case(cases, "hv_arm_rejects_bad_uart_counter", (not ok) and "bad-frame counter" in msg, msg)
    ok, msg = mod.hv_runtime_check(hv_status, hv_cfg)
    add_case(cases, "hv_runtime_accepts_clean_315v_status", ok, msg)
    ok, msg = mod.hv_runtime_check(
        safe_status(vdc=315.0, bp_vdc=315.0, bp_vbus_raw=3459, bp_bad_cnt=1),
        hv_cfg,
        allow_nonzero_bad=True,
    )
    add_case(cases, "hv_runtime_can_delegate_bad_counter_to_burst_monitor", ok, msg)
    ok, msg = mod.hv_runtime_check(
        safe_status(vdc=315.0, bp_vdc=315.0, bp_vbus_raw=3459, bp_temp_age_ms=2000), hv_cfg
    )
    add_case(cases, "hv_runtime_rejects_stale_temperature", (not ok) and "stale" in msg, msg)

    bad_monitor = mod.HvRuntimeBadFrameMonitor(burst_limit=3, window_sec=1.0)
    ok1, msg1 = bad_monitor.observe(safe_status(bp_bad_cnt=1, bp_bad=0), now=10.0)
    ok2, msg2 = bad_monitor.observe(safe_status(bp_bad_cnt=2, bp_bad=0), now=10.2)
    ok3, msg3 = bad_monitor.observe(safe_status(bp_bad_cnt=3, bp_bad=0), now=10.4)
    add_case(
        cases,
        "hv_runtime_bad_monitor_allows_isolated_errors_but_trips_burst",
        ok1 and ok2 and (not ok3) and "error burst" in msg3,
        msg3,
        {"first": msg1, "second": msg2, "third": msg3},
    )
    ok4, msg4 = bad_monitor.observe(safe_status(bp_bad_cnt=4, bp_bad=0), now=11.6)
    add_case(cases, "hv_runtime_bad_monitor_window_expires", ok4, msg4)
    ok5, msg5 = bad_monitor.observe(safe_status(bp_bad_cnt=0, bp_bad=0), now=11.8)
    add_case(cases, "hv_runtime_bad_monitor_handles_counter_clear", ok5, msg5)

    original_now = mod._now_ts
    now_box = [1000.0]
    try:
        mod._now_ts = lambda: now_box[0]
        arm = mod.HvArmState(hv_cfg)
        ok, msg = arm.arm("WRONG", hv_status)
        add_case(cases, "hv_arm_rejects_wrong_phrase", (not ok) and "mismatch" in msg, msg)
        ok, msg = arm.arm(mod.DEFAULT_HV_ARM_CONFIRM, hv_status)
        snap = arm.snapshot()
        add_case(cases, "hv_arm_sets_bounded_window", ok and snap["hmi_hv_armed"] == 1 and snap["hmi_hv_remaining_s"] == 30.0, msg, snap)
        ok, msg = arm.command_allowed(safe_status(vdc=0.0, bp_vdc=0.0))
        add_case(cases, "hv_arm_rechecks_live_bus_before_output", (not ok) and "window" in msg, msg)
        ok, msg = arm.command_allowed(hv_status)
        add_case(cases, "hv_arm_allows_output_with_fresh_live_status", ok, msg)
        arm.mark_started()
        now_box[0] = 1031.0
        add_case(cases, "hv_arm_expiry_requests_safe_stop", arm.take_expired_session_action(), evidence=arm.snapshot())
        add_case(cases, "hv_arm_expiry_clears_arm", arm.snapshot()["hmi_hv_armed"] == 0, evidence=arm.snapshot())
    finally:
        mod._now_ts = original_now

    class FakeRpc:
        def __init__(
            self,
            statuses: list[dict[str, Any] | None],
            stop_ok: bool = True,
            command_results: dict[str, tuple[bool, str]] | None = None,
        ) -> None:
            self.statuses = list(statuses)
            self.stop_ok = stop_ok
            self.command_results = dict(command_results or {})
            self.commands: list[str] = []

        def cmd(self, cmd: str) -> tuple[bool, str]:
            self.commands.append(cmd)
            if cmd in self.command_results:
                return self.command_results[cmd]
            return (self.stop_ok, "" if self.stop_ok else "stop failed")

        def get(self) -> tuple[bool, dict[str, Any] | None, str]:
            if not self.statuses:
                return False, None, "no status"
            data = self.statuses.pop(0)
            if data is None:
                return False, None, "no status"
            return True, data, ""

    class FakeLogs:
        def __init__(self) -> None:
            self.items: list[str] = []

        def add(self, message: str) -> None:
            self.items.append(message)

    dual_guard = mod.CommandGuardConfig(max_vdc=60.0, allow_hv=True, local_bench_gate=True)
    dual_app = mod.AppState(
        FakeRpc([safe_status()]),
        FakeLogs(),
        status_log_interval=60.0,
        command_guard=dual_guard,
        hv_arm=mod.HvArmState(hv_cfg),
        start_runlimit_sec=15.0,
        arm_profiles={"hv": hv_cfg, "lv": lv_cfg},
        profile_runlimits={"hv": 15.0, "lv": 3.0},
        guard_max_vdc=60.0,
    )
    ok, msg = dual_app.switch_arm_profile("lv", safe_status())
    dual_lv_snapshot = dual_app.arm_snapshot(safe_status())
    add_case(
        cases,
        "dual_profile_switch_applies_lv_guard_and_runlimit",
        ok
        and dual_lv_snapshot["hmi_arm_profile"] == "lv"
        and dual_lv_snapshot["hmi_arm_profiles"] == ["hv", "lv"]
        and dual_app.start_runlimit_sec == 3.0
        and dual_guard.max_vdc == 10.0
        and not dual_guard.allow_hv,
        msg,
        dual_lv_snapshot,
    )
    ok, msg = dual_app.switch_arm_profile("hv", safe_status())
    add_case(
        cases,
        "dual_profile_switch_restores_hv_guard_and_runlimit",
        ok
        and dual_app.hv_arm.snapshot()["hmi_arm_profile"] == "hv"
        and dual_app.start_runlimit_sec == 15.0
        and dual_guard.max_vdc == 60.0
        and dual_guard.allow_hv,
        msg,
    )
    ok, msg = dual_app.switch_arm_profile("invalid", safe_status())
    add_case(cases, "dual_profile_switch_rejects_unknown_profile", (not ok) and "unsupported" in msg, msg)

    no_k1_arm = mod.HvArmState(lv_cfg)
    no_k1_arm.arm("ARM LV HV OFF", safe_status())
    no_k1_rpc = FakeRpc(
        [
            safe_status(),
            safe_status(state="VF_RUN", state_code=1, pwm=1, precharge=0, bp_ext=0),
        ]
    )
    no_k1_app = mod.AppState(
        no_k1_rpc,
        FakeLogs(),
        status_log_interval=60.0,
        command_guard=mod.CommandGuardConfig(max_vdc=10.0, local_bench_gate=True),
        hv_arm=no_k1_arm,
        start_runlimit_sec=3.0,
    )
    seq_ok, seq_msg, seq_status = no_k1_app.start_sequence(
        run_timeout_sec=0.0,
        poll_sec=0.0,
    )
    add_case(
        cases,
        "wifi_start_without_k1_requires_zero_legacy_bit_then_starts_pwm",
        seq_ok
        and no_k1_rpc.commands == ["SET RUNLIMIT 3.000", "START"]
        and seq_status is not None
        and seq_status.get("pwm") == 1
        and no_k1_app.arm_snapshot(seq_status)["hmi_precharge_relay_present"] == 0,
        seq_msg,
        {"commands": no_k1_rpc.commands, "status": seq_status},
    )

    softstart_arm = mod.HvArmState(lv_cfg)
    softstart_arm.arm("ARM LV HV OFF", safe_status())
    softstart_rpc = FakeRpc(
        [
            safe_status(
                bp_vbus_raw=0, bp_vdc=0.0, vdc=0.0,
                bp_mcsdk_telemetry=1, bp_vbus_valid=1, bp_softstart_ready=0,
            ),
            safe_status(
                state="VF_RUN", state_code=1, pwm=1, precharge=0, bp_ext=0,
                bp_status=0x01, bp_vbus_raw=0, bp_vbus_valid=1,
                bp_mcsdk_telemetry=1, bp_softstart_ready=0,
            ),
            safe_status(
                state="VF_RUN", state_code=1, pwm=1, precharge=0, bp_ext=0,
                bp_status=0x21, bp_vbus_raw=0, bp_vbus_valid=1,
                bp_mcsdk_telemetry=1, bp_softstart_ready=1,
            ),
        ]
    )
    softstart_app = mod.AppState(
        softstart_rpc,
        FakeLogs(),
        status_log_interval=60.0,
        command_guard=mod.CommandGuardConfig(max_vdc=10.0, local_bench_gate=True),
        hv_arm=softstart_arm,
        start_runlimit_sec=3.0,
    )
    seq_ok, seq_msg, seq_status = softstart_app.start_sequence(
        run_timeout_sec=0.1,
        poll_sec=0.0,
    )
    add_case(
        cases,
        "wifi_start_waits_for_external_softstart_and_actual_mcsdk_pwm",
        seq_ok
        and seq_status is not None
        and seq_status.get("bp_status") == 0x21
        and softstart_app.arm_snapshot(seq_status)["hmi_precharge_relay_present"] == 0
        and softstart_app.arm_snapshot(seq_status)["hmi_external_softstart_ready"] == 1,
        seq_msg,
        {"commands": softstart_rpc.commands, "status": seq_status},
    )

    reject_arm = mod.HvArmState(lv_cfg)
    reject_arm.arm("ARM LV HV OFF", safe_status())
    reject_rpc = FakeRpc(
        [safe_status(), safe_status()],
        command_results={"START": (False, "rejected")},
    )
    reject_app = mod.AppState(
        reject_rpc,
        FakeLogs(),
        status_log_interval=60.0,
        command_guard=mod.CommandGuardConfig(max_vdc=10.0, local_bench_gate=True),
        hv_arm=reject_arm,
        start_runlimit_sec=3.0,
    )
    seq_ok, seq_msg, _ = reject_app.start_sequence(
        relay_timeout_sec=0.0,
        relay_settle_sec=0.0,
        run_timeout_sec=0.0,
        poll_sec=0.0,
    )
    add_case(
        cases,
        "wifi_start_sequence_estops_when_start_rejected",
        (not seq_ok)
        and "START rejected" in seq_msg
        and reject_rpc.commands == ["SET RUNLIMIT 3.000", "START", "ESTOP"],
        seq_msg,
        reject_rpc.commands,
    )

    stop_rpc = FakeRpc([safe_status()])
    stop_app = mod.AppState(
        stop_rpc,
        FakeLogs(),
        status_log_interval=60.0,
    )
    stop_ok, stop_msg, _ = stop_app.stop_sequence(emergency=True, confirm_timeout_sec=0.0, poll_sec=0.0)
    add_case(
        cases,
        "wifi_emergency_stop_confirms_all_outputs_off",
        stop_ok and stop_rpc.commands == ["ESTOP"],
        stop_msg,
        stop_rpc.commands,
    )

    watchdog_arm = mod.HvArmState(hv_cfg)
    ok, msg = watchdog_arm.arm(mod.DEFAULT_HV_ARM_CONFIRM, hv_status)
    watchdog_arm.mark_started()
    watchdog_rpc = FakeRpc([safe_status(vdc=315.0, bp_vdc=315.0, bp_fault=6)])
    watchdog_logs = FakeLogs()
    watchdog_app = mod.AppState(
        watchdog_rpc,
        watchdog_logs,
        status_log_interval=60.0,
        hv_arm=watchdog_arm,
    )
    watchdog_app.start_safety_watchdog()
    time.sleep(0.35)
    watchdog_app.stop_safety_watchdog()
    add_case(
        cases,
        "hv_watchdog_forces_stop_and_estop_on_runtime_fault",
        ok and watchdog_rpc.commands == ["STOP", "ESTOP"],
        msg,
        {"commands": watchdog_rpc.commands, "logs": watchdog_logs.items},
    )
    add_case(
        cases,
        "hv_watchdog_disarms_on_runtime_fault",
        watchdog_arm.snapshot()["hmi_hv_armed"] == 0,
        evidence=watchdog_arm.snapshot(),
    )

    def firmware_update_safe(status: dict[str, Any] | None, max_vdc: float = 10.0) -> tuple[bool, dict[str, Any] | None, str, list[str]]:
        rpc = FakeRpc([status])
        app = type(
            "FakeApp",
            (),
            {"rpc": rpc, "_precharge_off": lambda _self: (True, "not-installed")},
        )()
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

    ok, _data, msg, _commands = firmware_update_safe(safe_status(vdc=0.0, bp_vdc=0.0, bp_vbus_raw=3256))
    add_case(cases, "firmware_update_rejects_high_raw_vbus", (not ok) and "raw DC bus" in msg, msg)

    update_missing_raw = safe_status()
    update_missing_raw.pop("bp_vbus_raw", None)
    ok, _data, msg, _commands = firmware_update_safe(update_missing_raw)
    add_case(cases, "firmware_update_rejects_missing_raw_vbus", (not ok) and "missing" in msg, msg)

    ok, _data, msg, _commands = firmware_update_safe(safe_status(bp_vbus_age_ms=5000))
    add_case(cases, "firmware_update_rejects_stale_raw_vbus", (not ok) and "stale" in msg, msg)

    ok, _data, msg, _commands = firmware_update_safe(safe_status(bp_bad_cnt=1))
    add_case(cases, "firmware_update_rejects_bad_counter", (not ok) and "bad" in msg, msg)

    ok, _data, msg, _commands = firmware_update_safe(safe_status(bp_rsp_age_ms=5000))
    add_case(cases, "firmware_update_rejects_stale_motor_controller_link", (not ok) and "stale or down" in msg, msg)

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

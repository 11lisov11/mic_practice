#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import unoq_web_server as hmi

OFF_FLAGS = 3
OFF_MODE = 4
OFF_SEQ = 5
OFF_EXT_FLAGS = 14
OFF_EXT_DUTY_LO = 15
OFF_EXT_DUTY_HI = 16
OFF_FAN_DUTY_LO = 17
OFF_FAN_DUTY_HI = 18
OFF_CRC = 31


class CheckError(RuntimeError):
    pass


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    frame_hex: str = ""


def u16(frame: bytes, off_lo: int) -> int:
    return int(frame[off_lo]) | (int(frame[off_lo + 1]) << 8)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise CheckError(msg)


def assert_eq(actual: Any, expected: Any, msg: str) -> None:
    if actual != expected:
        raise CheckError(f"{msg}: expected {expected!r}, got {actual!r}")


def mark_bluepill_ready(state: hmi.SharedState, *, status: int | None = None, fault: int = 0, vbus_raw: int | None = None) -> None:
    rsp = bytearray(hmi.FRAME_LEN)
    rsp[0] = hmi.RSP_HDR0
    rsp[1] = hmi.RSP_HDR1
    rsp[3] = int(hmi.STATUS_LINK_OK if status is None else status) & 0xFF
    rsp[4] = 1
    rsp[5] = 1
    rsp[9] = int(fault) & 0xFF
    rsp[10] = hmi.MODE_OFF
    # Keep the safe fixture tied to the firmware-mirrored physical zero.
    raw = hmi.BP_VBUS_ZERO_RAW if vbus_raw is None else int(vbus_raw)
    rsp[17] = raw & 0xFF
    rsp[18] = (raw >> 8) & 0xFF
    rsp[hmi.CRC_OFF] = hmi.crc_xor(rsp)
    hmi.parse_rsp(state, bytes(rsp), 1.0)


def fake_bench_gate(ok: bool):
    def _runner(log_fn, url):
        if not ok and log_fn:
            log_fn("fake bench gate red")
        return ok

    return _runner


def arm_green_bench_gate(state: hmi.SharedState) -> None:
    state.bench_gate_url = "http://127.0.0.1:18080"
    state.bench_gate_runner = fake_bench_gate(True)


def build_after(commands: list[str], seq: int = 42, *, bluepill_ready: bool = True) -> tuple[hmi.SharedState, bytes]:
    state = hmi.SharedState()
    arm_green_bench_gate(state)
    if bluepill_ready:
        mark_bluepill_ready(state)
    for cmd in commands:
        ok, msg = hmi.apply_cmd(state, cmd)
        assert_true(ok, f"{cmd!r} rejected: {msg}")
    frame = hmi.build_frame(state, seq)
    assert_eq(len(frame), hmi.FRAME_LEN, "frame length")
    assert_eq(frame[0], hmi.CMD_HDR0, "cmd header 0")
    assert_eq(frame[1], hmi.CMD_HDR1, "cmd header 1")
    assert_eq(frame[OFF_CRC], hmi.crc_xor(frame), "frame crc")
    assert_eq(frame[OFF_SEQ], seq & 0xFF, "sequence")
    return state, frame


def expect_no_motor_enable(frame: bytes, name: str) -> None:
    assert_true((frame[OFF_FLAGS] & hmi.FLAG_ENABLE) == 0, f"{name}: FLAG_ENABLE unexpectedly set")


def expect_service_clear(frame: bytes, name: str) -> None:
    assert_eq(frame[OFF_EXT_FLAGS], 0, f"{name}: ext_flags")
    assert_eq(u16(frame, OFF_EXT_DUTY_LO), 0, f"{name}: brake duty")
    assert_eq(u16(frame, OFF_FAN_DUTY_LO), 0, f"{name}: fan duty")


def expect_motion_payload_zero(frame: bytes, name: str) -> None:
    for idx in range(6, 14):
        assert_eq(frame[idx], 0, f"{name}: motion payload byte {idx}")


def case_clear_is_pure() -> bytes:
    _, frame = build_after(
        [
            "PFC ON",
            "BRAKE PWM 0.70",
            "FAN PWM 0.80",
            "CLEAR",
        ]
    )
    assert_eq(frame[OFF_FLAGS], hmi.FLAG_CLEAR_FAULT, "CLEAR flags")
    assert_eq(frame[OFF_MODE], hmi.MODE_OFF, "CLEAR mode")
    expect_no_motor_enable(frame, "CLEAR")
    expect_motion_payload_zero(frame, "CLEAR")
    expect_service_clear(frame, "CLEAR")
    return frame


def case_estop_clears_services() -> bytes:
    _, frame = build_after(
        [
            "PFC ON",
            "BRAKE PWM 0.60",
            "FAN PWM 1.00",
            "ESTOP",
        ]
    )
    assert_eq(frame[OFF_FLAGS], hmi.FLAG_ESTOP, "ESTOP flags")
    assert_eq(frame[OFF_MODE], hmi.MODE_OFF, "ESTOP mode")
    expect_no_motor_enable(frame, "ESTOP")
    expect_motion_payload_zero(frame, "ESTOP")
    expect_service_clear(frame, "ESTOP")
    return frame


def case_estop_clear_is_pure() -> bytes:
    _, frame = build_after(
        [
            "ESTOP",
            "ESTOP CLEAR",
        ]
    )
    assert_eq(frame[OFF_FLAGS], hmi.FLAG_CLEAR_FAULT, "ESTOP CLEAR flags")
    assert_eq(frame[OFF_MODE], hmi.MODE_OFF, "ESTOP CLEAR mode")
    expect_no_motor_enable(frame, "ESTOP CLEAR")
    expect_motion_payload_zero(frame, "ESTOP CLEAR")
    expect_service_clear(frame, "ESTOP CLEAR")
    return frame


def case_iotest_off_clears_services() -> bytes:
    _, frame = build_after(
        [
            "IOTEST ON",
            "PFC ON",
            "BRAKE PWM 0.20",
            "FAN PWM 0.50",
            "IOTEST OFF",
        ]
    )
    assert_eq(frame[OFF_FLAGS], 0, "IOTEST OFF flags")
    assert_eq(frame[OFF_MODE], hmi.MODE_OFF, "IOTEST OFF mode")
    expect_no_motor_enable(frame, "IOTEST OFF")
    expect_motion_payload_zero(frame, "IOTEST OFF")
    expect_service_clear(frame, "IOTEST OFF")
    return frame


def case_service_commands_do_not_start_motor() -> bytes:
    service_cases = [
        (["PFC ON"], hmi.EXT_PFC_SYNC, 0, 0),
        (["BRAKE PWM 0.25"], hmi.EXT_BRAKE_PWM, 1, 0),
        (["FAN PWM 0.40"], 0, 0, 1),
    ]
    last_frame = b""
    for commands, expected_ext, expect_brake, expect_fan in service_cases:
        _, frame = build_after(commands)
        last_frame = frame
        label = commands[-1]
        assert_eq(frame[OFF_MODE], hmi.MODE_OFF, f"{label}: mode")
        expect_no_motor_enable(frame, label)
        expect_motion_payload_zero(frame, label)
        assert_eq(frame[OFF_EXT_FLAGS], expected_ext, f"{label}: ext_flags")
        assert_true((u16(frame, OFF_EXT_DUTY_LO) > 0) == bool(expect_brake), f"{label}: brake duty presence")
        assert_true((u16(frame, OFF_FAN_DUTY_LO) > 0) == bool(expect_fan), f"{label}: fan duty presence")
    return last_frame


def case_removed_precharge_is_rejected() -> bytes:
    state = hmi.SharedState()
    arm_green_bench_gate(state)
    mark_bluepill_ready(state)
    ok, msg = hmi.apply_cmd(state, "PRECHARGE ON")
    assert_true(not ok and "not installed" in msg, "removed PRECHARGE output was accepted")
    frame = hmi.build_frame(state, 0x2A)
    assert_eq(frame[OFF_EXT_FLAGS] & hmi.EXT_PRECHARGE_RELAY, 0, "removed PRECHARGE bit")
    expect_no_motor_enable(frame, "removed PRECHARGE")
    return frame


def case_bpfoc_command_is_guarded_and_off_is_safe() -> bytes:
    no_link = hmi.SharedState()
    ok, msg = hmi.apply_cmd(no_link, "BPFOC ON")
    assert_true((not ok) and "link" in msg, f"BPFOC ON accepted without link: {msg}")

    high_vdc = hmi.SharedState()
    mark_bluepill_ready(high_vdc, vbus_raw=hmi.BP_VBUS_CAL_RAW)
    ok, msg = hmi.apply_cmd(high_vdc, "BPFOC ON")
    assert_true((not ok) and "DC bus too high" in msg, f"BPFOC ON accepted with high Vdc: {msg}")

    state = hmi.SharedState()
    arm_green_bench_gate(state)
    mark_bluepill_ready(state)
    ok, msg = hmi.apply_cmd(state, "BPFOC ON")
    assert_true(ok, f"BPFOC ON rejected in safe state: {msg}")
    assert_eq(state.mode, hmi.MODE_FOC, "BPFOC ON mode")
    assert_true(state.bp_foc_backend is True, "BPFOC ON did not set backend flag")
    assert_true(state.enable is False, "BPFOC ON enabled motor")
    frame_on = hmi.build_frame(state, 42)
    assert_eq(frame_on[OFF_MODE], hmi.MODE_FOC, "BPFOC ON frame mode")
    expect_no_motor_enable(frame_on, "BPFOC ON")

    ok, msg = hmi.apply_cmd(state, "START")
    assert_true(ok, f"BPFOC START rejected after green bench gate: {msg}")
    ok, msg = hmi.apply_cmd(state, "BPFOC OFF")
    assert_true(ok, f"BPFOC OFF rejected: {msg}")
    assert_eq(state.mode, hmi.MODE_OFF, "BPFOC OFF mode")
    assert_true(state.bp_foc_backend is False, "BPFOC OFF left backend flag set")
    assert_true(state.enable is False, "BPFOC OFF left motor enabled")
    frame_off = hmi.build_frame(state, 43)
    assert_eq(frame_off[OFF_MODE], hmi.MODE_OFF, "BPFOC OFF frame mode")
    expect_no_motor_enable(frame_off, "BPFOC OFF")
    expect_motion_payload_zero(frame_off, "BPFOC OFF")
    return frame_off


def case_start_rejected_during_estop() -> bytes:
    state = hmi.SharedState()
    mark_bluepill_ready(state)
    ok, msg = hmi.apply_cmd(state, "ESTOP")
    assert_true(ok, f"ESTOP rejected: {msg}")
    ok, _ = hmi.apply_cmd(state, "START")
    assert_true(not ok, "START accepted while estop latched")
    frame = hmi.build_frame(state, 42)
    assert_eq(frame[OFF_FLAGS], hmi.FLAG_ESTOP, "estop latch flags")
    expect_no_motor_enable(frame, "estop latched")
    expect_motion_payload_zero(frame, "estop latched")
    return frame


def case_start_rejected_without_link() -> bytes:
    state = hmi.SharedState()
    ok, msg = hmi.apply_cmd(state, "MODE VF")
    assert_true(ok, f"MODE VF rejected: {msg}")
    ok, _ = hmi.apply_cmd(state, "START")
    assert_true(not ok, "START accepted without Blue Pill link")
    frame = hmi.build_frame(state, 42)
    expect_no_motor_enable(frame, "no-link START")
    return frame


def case_start_rejected_in_mode_off() -> bytes:
    state = hmi.SharedState()
    mark_bluepill_ready(state)
    ok, _ = hmi.apply_cmd(state, "START")
    assert_true(not ok, "START accepted in MODE_OFF")
    frame = hmi.build_frame(state, 42)
    assert_eq(frame[OFF_MODE], hmi.MODE_OFF, "mode-off START mode")
    expect_no_motor_enable(frame, "mode-off START")
    return frame


def case_start_rejected_when_bench_gate_red() -> bytes:
    state = hmi.SharedState()
    state.bench_gate_url = "http://127.0.0.1:18080"
    state.bench_gate_runner = fake_bench_gate(False)
    mark_bluepill_ready(state)
    ok, msg = hmi.apply_cmd(state, "MODE VF")
    assert_true(ok, f"MODE VF rejected: {msg}")
    ok, msg = hmi.apply_cmd(state, "START")
    assert_true((not ok) and "bench gate" in msg, f"START was not blocked by red bench gate: {msg}")
    frame = hmi.build_frame(state, 42)
    expect_no_motor_enable(frame, "red bench-gate START")
    return frame


def case_start_rejected_on_fault_or_timeout() -> bytes:
    scenarios = [
        ("fault", hmi.STATUS_LINK_OK | hmi.STATUS_FAULT, 5),
        ("timeout", hmi.STATUS_LINK_OK | hmi.STATUS_TIMEOUT, 0),
        ("estop_status", hmi.STATUS_LINK_OK | hmi.STATUS_ESTOP, 0),
    ]
    last_frame = b""
    for label, status, fault in scenarios:
        state = hmi.SharedState()
        arm_green_bench_gate(state)
        mark_bluepill_ready(state, status=status, fault=fault)
        ok, msg = hmi.apply_cmd(state, "MODE VF")
        assert_true(ok, f"{label}: MODE VF rejected: {msg}")
        ok, _ = hmi.apply_cmd(state, "START")
        assert_true(not ok, f"{label}: START accepted on unsafe Blue Pill status")
        frame = hmi.build_frame(state, 42)
        last_frame = frame
        expect_no_motor_enable(frame, label)
    return last_frame


def case_diag_on_alias_is_compatible() -> bytes:
    _, frame = build_after(["DIAG ON", "START"], bluepill_ready=True)
    assert_eq(frame[OFF_MODE], hmi.MODE_DIAG, "DIAG ON mode")
    assert_true((frame[OFF_FLAGS] & hmi.FLAG_DIAG_PWM) != 0, "DIAG ON did not set FLAG_DIAG_PWM")
    assert_true((frame[OFF_FLAGS] & hmi.FLAG_ENABLE) != 0, "DIAG ON START did not set FLAG_ENABLE")
    state, frame_off = build_after(["DIAG ON", "DIAG OFF"], bluepill_ready=True)
    assert_eq(frame_off[OFF_MODE], hmi.MODE_OFF, "DIAG OFF mode")
    assert_true(not state.diag, "DIAG OFF did not clear diag state")
    expect_no_motor_enable(frame_off, "DIAG OFF")
    return frame


def case_mode_change_drops_enable() -> bytes:
    _, frame = build_after(["MODE VF", "START", "MODE FOC"], bluepill_ready=True)
    assert_eq(frame[OFF_MODE], hmi.MODE_FOC, "MODE FOC frame mode")
    expect_no_motor_enable(frame, "mode change")
    return frame


def case_duty_change_drops_non_duty_enable() -> bytes:
    _, frame = build_after(["MODE VF", "START", "DUTY 0.20 0.30 0.40"], bluepill_ready=True)
    assert_eq(frame[OFF_MODE], hmi.MODE_DUTY, "DUTY frame mode")
    expect_no_motor_enable(frame, "duty mode change")
    return frame


def case_start_sets_enable_only_for_run() -> bytes:
    _, frame = build_after(["MODE VF", "START"], bluepill_ready=True)
    assert_eq(frame[OFF_MODE], hmi.MODE_SCALAR, "START mode")
    assert_true((frame[OFF_FLAGS] & hmi.FLAG_ENABLE) != 0, "START did not set FLAG_ENABLE")
    assert_true((frame[OFF_FLAGS] & hmi.FLAG_ESTOP) == 0, "START set FLAG_ESTOP")
    return frame


CASES = [
    ("clear_is_pure", case_clear_is_pure),
    ("estop_clears_services", case_estop_clears_services),
    ("estop_clear_is_pure", case_estop_clear_is_pure),
    ("iotest_off_clears_services", case_iotest_off_clears_services),
    ("service_commands_do_not_start_motor", case_service_commands_do_not_start_motor),
    ("removed_precharge_is_rejected", case_removed_precharge_is_rejected),
    ("bpfoc_command_is_guarded_and_off_is_safe", case_bpfoc_command_is_guarded_and_off_is_safe),
    ("start_rejected_during_estop", case_start_rejected_during_estop),
    ("start_rejected_without_link", case_start_rejected_without_link),
    ("start_rejected_in_mode_off", case_start_rejected_in_mode_off),
    ("start_rejected_when_bench_gate_red", case_start_rejected_when_bench_gate_red),
    ("start_rejected_on_fault_or_timeout", case_start_rejected_on_fault_or_timeout),
    ("diag_on_alias_is_compatible", case_diag_on_alias_is_compatible),
    ("mode_change_drops_enable", case_mode_change_drops_enable),
    ("duty_change_drops_non_duty_enable", case_duty_change_drops_non_duty_enable),
    ("start_sets_enable_only_for_run", case_start_sets_enable_only_for_run),
]


def main() -> int:
    results: list[CaseResult] = []
    for name, fn in CASES:
        try:
            frame = fn()
            results.append(CaseResult(name=name, ok=True, frame_hex=frame.hex(" ")))
        except Exception as exc:
            results.append(CaseResult(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}"))

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    summary = {
        "tool": "protocol_safety_selftest",
        "pass": failed == 0,
        "passed": passed,
        "failed": failed,
        "cases": [r.__dict__ for r in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

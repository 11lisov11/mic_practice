#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bluepill_direct_probe as direct_probe
import protocol_safety_selftest as safety_selftest
import unoq_web_server as hmi


DEFINE_RE = re.compile(r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z0-9_xXa-fA-F]+)\b")


class CheckError(RuntimeError):
    pass


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


def parse_proto_h(path: Path) -> dict[str, int]:
    raw: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = DEFINE_RE.match(line)
        if match:
            raw[match.group(1)] = match.group(2)

    resolved: dict[str, int] = {}

    def resolve(name: str, stack: tuple[str, ...] = ()) -> int:
        if name in resolved:
            return resolved[name]
        if name in stack:
            raise CheckError(f"cyclic #define alias: {' -> '.join((*stack, name))}")
        if name not in raw:
            raise CheckError(f"missing #define {name}")
        token = raw[name]
        try:
            value = int(token, 0)
        except ValueError:
            value = resolve(token, (*stack, name))
        resolved[name] = value
        return value

    for name in raw:
        resolve(name)
    return resolved


def assert_eq(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise CheckError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(cond: bool, label: str) -> None:
    if not cond:
        raise CheckError(label)


def compare_module_constants(proto: dict[str, int], module: Any, names: list[str], prefix: str = "") -> dict[str, int]:
    evidence: dict[str, int] = {}
    for name in names:
        assert_true(hasattr(module, name), f"{prefix}{name}: missing in {module.__name__}")
        actual = int(getattr(module, name))
        expected = proto[name]
        assert_eq(actual, expected, f"{prefix}{name}")
        evidence[name] = actual
    return evidence


def mark_bluepill_ready(state: hmi.SharedState) -> None:
    rsp = bytearray(hmi.FRAME_LEN)
    rsp[0] = hmi.RSP_HDR0
    rsp[1] = hmi.RSP_HDR1
    rsp[3] = hmi.STATUS_LINK_OK
    rsp[4] = 1
    rsp[5] = 1
    rsp[9] = 0
    rsp[10] = hmi.MODE_OFF
    raw = hmi.BP_VBUS_ZERO_RAW
    rsp[17] = raw & 0xFF
    rsp[18] = (raw >> 8) & 0xFF
    rsp[hmi.CRC_OFF] = hmi.crc_xor(rsp)
    hmi.parse_rsp(state, bytes(rsp), 1.0)


def build_hmi_frame(commands: list[str], seq: int = 0x2A) -> bytes:
    state = hmi.SharedState()
    mark_bluepill_ready(state)
    for cmd in commands:
        ok, msg = hmi.apply_cmd(state, cmd)
        assert_true(ok, f"{cmd!r} rejected: {msg}")
    frame = hmi.build_frame(state, seq)
    assert_eq(len(frame), hmi.FRAME_LEN, "HMI frame length")
    assert_eq(frame[hmi.FRAME_LEN - 1], hmi.crc_xor(frame), "HMI frame crc")
    return frame


def u16(buf: bytes | bytearray, off: int) -> int:
    return int(buf[off]) | (int(buf[off + 1]) << 8)


def u32(buf: bytes | bytearray, off: int) -> int:
    return int(buf[off]) | (int(buf[off + 1]) << 8) | (int(buf[off + 2]) << 16) | (int(buf[off + 3]) << 24)


def case_hmi_constants(proto: dict[str, int]) -> dict[str, int]:
    names = [
        "FRAME_LEN",
        "CMD_HDR0",
        "CMD_HDR1",
        "RSP_HDR0",
        "RSP_HDR1",
        "FLAG_ENABLE",
        "FLAG_ESTOP",
        "FLAG_DIAG_PWM",
        "FLAG_CLEAR_FAULT",
        "FLAG_VECTOR_ROTATE",
        "MODE_OFF",
        "MODE_DIAG",
        "MODE_DUTY",
        "MODE_SCALAR",
        "MODE_VECTOR",
        "MODE_FOC",
        "EXT_RESERVED_0",
        "EXT_PFC_SYNC",
        "EXT_BRAKE_PWM",
        "EXT_PRECHARGE_RELAY",
        "STATUS_LINK_OK",
        "STATUS_ENABLED",
        "STATUS_ESTOP",
        "STATUS_FAULT",
        "STATUS_TIMEOUT",
        "STATUS_PWM_ACTIVE",
    ]
    evidence = compare_module_constants(proto, hmi, names, prefix="hmi.")
    alias_map = {
        "BP_TEMP_FLAG_VALID": "TEMP_FLAG_VALID",
        "BP_TEMP_FLAG_FAULT": "TEMP_FLAG_FAULT",
        "BP_PHASE_FLAG_VALID": "PHASE_FLAG_VALID",
        "BP_PHASE_FLAG_C_VIRTUAL": "PHASE_FLAG_C_VIRTUAL",
    }
    for py_name, c_name in alias_map.items():
        assert_eq(int(getattr(hmi, py_name)), proto[c_name], f"hmi.{py_name}")
        evidence[py_name] = int(getattr(hmi, py_name))
    return evidence


def case_direct_probe_constants(proto: dict[str, int]) -> dict[str, int]:
    names = [
        "FRAME_LEN",
        "CMD_HDR0",
        "CMD_HDR1",
        "RSP_HDR0",
        "RSP_HDR1",
        "FLAG_ENABLE",
        "FLAG_ESTOP",
        "FLAG_DIAG_PWM",
        "FLAG_CLEAR_FAULT",
        "MODE_OFF",
        "MODE_DIAG",
        "MODE_DUTY",
        "MODE_SCALAR",
        "STATUS_LINK_OK",
        "STATUS_ENABLED",
        "STATUS_ESTOP",
        "STATUS_FAULT",
        "STATUS_TIMEOUT",
        "STATUS_PWM_ACTIVE",
    ]
    return compare_module_constants(proto, direct_probe, names, prefix="direct_probe.")


def case_safety_selftest_offsets(proto: dict[str, int]) -> dict[str, int]:
    mapping = {
        "OFF_FLAGS": "CMD_OFF_FLAGS",
        "OFF_MODE": "CMD_OFF_MODE",
        "OFF_SEQ": "CMD_OFF_SEQ",
        "OFF_EXT_FLAGS": "CMD_OFF_EXT_FLAGS",
        "OFF_EXT_DUTY_LO": "CMD_OFF_EXT_DUTY_LO",
        "OFF_EXT_DUTY_HI": "CMD_OFF_EXT_DUTY_HI",
        "OFF_FAN_DUTY_LO": "CMD_OFF_FAN_DUTY_LO",
        "OFF_FAN_DUTY_HI": "CMD_OFF_FAN_DUTY_HI",
        "OFF_CRC": "CMD_OFF_CRC",
    }
    evidence: dict[str, int] = {}
    for py_name, c_name in mapping.items():
        actual = int(getattr(safety_selftest, py_name))
        expected = proto[c_name]
        assert_eq(actual, expected, f"safety_selftest.{py_name}")
        evidence[py_name] = actual
    return evidence


def case_nucleo_proto_matches(proto: dict[str, int]) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[1]
    nucleo_path = repo / "nucleo_g431_uart_bridge_pio" / "include" / "proto.h"
    nucleo = parse_proto_h(nucleo_path)
    missing = sorted(set(proto) - set(nucleo))
    assert_true(not missing, f"Nucleo proto missing defines: {missing}")
    mismatches = {
        name: {"bluepill": proto[name], "nucleo": nucleo[name]}
        for name in sorted(proto)
        if nucleo[name] != proto[name]
    }
    assert_true(not mismatches, f"Nucleo protocol mismatch: {mismatches}")
    return {"nucleo_proto_h": str(nucleo_path), "matching_defines": len(proto)}


def case_hmi_command_frame_layout(proto: dict[str, int]) -> dict[str, Any]:
    pre_state = hmi.SharedState()
    mark_bluepill_ready(pre_state)
    pre_ok, pre_msg = hmi.apply_cmd(pre_state, "PRECHARGE ON")
    assert_true(not pre_ok and "not installed" in pre_msg, "removed PRECHARGE output was accepted")
    pre = hmi.build_frame(pre_state, 0x2A)
    assert_eq(pre[proto["CMD_OFF_MODE"]], proto["MODE_OFF"], "PRECHARGE-disabled mode")
    assert_eq(pre[proto["CMD_OFF_EXT_FLAGS"]] & proto["EXT_PRECHARGE_RELAY"], 0, "PRECHARGE-disabled ext")
    assert_true((pre[proto["CMD_OFF_FLAGS"]] & proto["FLAG_ENABLE"]) == 0, "PRECHARGE-disabled enables motor")

    brake = build_hmi_frame(["BRAKE PWM 0.25"])
    assert_eq(brake[proto["CMD_OFF_EXT_FLAGS"]], proto["EXT_BRAKE_PWM"], "BRAKE ext")
    assert_true(u16(brake, proto["CMD_OFF_EXT_DUTY_LO"]) > 0, "BRAKE duty missing")
    assert_true((brake[proto["CMD_OFF_FLAGS"]] & proto["FLAG_ENABLE"]) == 0, "BRAKE enables motor")

    fan = build_hmi_frame(["FAN PWM 0.40"])
    assert_eq(fan[proto["CMD_OFF_EXT_FLAGS"]], 0, "FAN ext")
    assert_true(u16(fan, proto["CMD_OFF_FAN_DUTY_LO"]) > 0, "FAN duty missing")
    assert_true((fan[proto["CMD_OFF_FLAGS"]] & proto["FLAG_ENABLE"]) == 0, "FAN enables motor")

    clear = build_hmi_frame(["BRAKE PWM 0.25", "FAN PWM 0.40", "CLEAR"])
    assert_eq(clear[proto["CMD_OFF_FLAGS"]], proto["FLAG_CLEAR_FAULT"], "CLEAR flags")
    assert_eq(clear[proto["CMD_OFF_MODE"]], proto["MODE_OFF"], "CLEAR mode")
    for idx in range(proto["CMD_OFF_DU"], proto["CMD_OFF_EXT_FLAGS"]):
        assert_eq(clear[idx], 0, f"CLEAR motion byte {idx}")
    assert_eq(clear[proto["CMD_OFF_EXT_FLAGS"]], 0, "CLEAR ext")
    assert_eq(u16(clear, proto["CMD_OFF_EXT_DUTY_LO"]), 0, "CLEAR brake duty")
    assert_eq(u16(clear, proto["CMD_OFF_FAN_DUTY_LO"]), 0, "CLEAR fan duty")
    return {
        "precharge_rejected": pre_msg,
        "precharge_disabled_hex": pre.hex(" "),
        "brake_hex": brake.hex(" "),
        "fan_hex": fan.hex(" "),
        "clear_hex": clear.hex(" "),
    }


def case_pc_direct_motion_frame_layout(proto: dict[str, int]) -> dict[str, Any]:
    duty = build_hmi_frame(["DUTY 0.10 0.20 0.30"])
    assert_eq(duty[proto["CMD_OFF_MODE"]], proto["MODE_DUTY"], "DUTY mode")
    assert_eq(u16(duty, proto["CMD_OFF_DU"]), hmi.q15_from_unit(0.10), "DUTY du")
    assert_eq(u16(duty, proto["CMD_OFF_DV"]), hmi.q15_from_unit(0.20), "DUTY dv")
    assert_eq(u16(duty, proto["CMD_OFF_DW"]), hmi.q15_from_unit(0.30), "DUTY dw")
    assert_eq(u16(duty, proto["CMD_OFF_RESERVED"]), 0, "DUTY reserved")

    scalar = build_hmi_frame(["MODE SCALAR", "FREQ 12.345", "MAG 0.42"])
    assert_eq(scalar[proto["CMD_OFF_MODE"]], proto["MODE_SCALAR"], "SCALAR mode")
    assert_eq(u32(scalar, proto["CMD_OFF_DU"]), 12345, "SCALAR freq_millihz")
    assert_eq(u16(scalar, proto["CMD_OFF_DW"]), hmi.q15_from_unit(0.42), "SCALAR mag")
    assert_eq(u16(scalar, proto["CMD_OFF_RESERVED"]), 0, "SCALAR reserved")

    vector = build_hmi_frame(["MODE VECTOR", "VROT OFF", "ALPHA -0.25", "BETA 0.50"])
    assert_eq(vector[proto["CMD_OFF_MODE"]], proto["MODE_VECTOR"], "VECTOR mode")
    assert_true((vector[proto["CMD_OFF_FLAGS"]] & proto["FLAG_VECTOR_ROTATE"]) == 0, "VECTOR rotate flag")
    assert_eq(u16(vector, proto["CMD_OFF_DU"]), hmi.q15_from_signed(-0.25), "VECTOR alpha")
    assert_eq(u16(vector, proto["CMD_OFF_DV"]), hmi.q15_from_signed(0.50), "VECTOR beta")
    assert_eq(u16(vector, proto["CMD_OFF_DW"]), 0, "VECTOR unused dw")
    assert_eq(u16(vector, proto["CMD_OFF_RESERVED"]), 0, "VECTOR reserved")

    vector_rot = build_hmi_frame(["MODE VECTOR", "VROT ON", "FREQ 7.5", "MAG 0.33"])
    assert_eq(vector_rot[proto["CMD_OFF_MODE"]], proto["MODE_VECTOR"], "VECTOR_ROT mode")
    assert_true((vector_rot[proto["CMD_OFF_FLAGS"]] & proto["FLAG_VECTOR_ROTATE"]) != 0, "VECTOR_ROT flag")
    assert_eq(u32(vector_rot, proto["CMD_OFF_DU"]), 7500, "VECTOR_ROT freq_millihz")
    assert_eq(u16(vector_rot, proto["CMD_OFF_DW"]), hmi.q15_from_unit(0.33), "VECTOR_ROT mag")
    assert_eq(u16(vector_rot, proto["CMD_OFF_RESERVED"]), 0, "VECTOR_ROT reserved")

    foc = build_hmi_frame(["MODE FOC", "FREQ 13.25", "FOC_FREQ 11.5", "ID -0.20", "IQ 0.40"])
    assert_eq(foc[proto["CMD_OFF_MODE"]], proto["MODE_FOC"], "FOC mode")
    assert_eq(u16(foc, proto["CMD_OFF_DU"]), hmi.q15_from_signed(-0.20), "FOC id")
    assert_eq(u16(foc, proto["CMD_OFF_DV"]), hmi.q15_from_signed(0.40), "FOC iq")
    assert_eq(u32(foc, proto["CMD_OFF_DW"]), 11500, "FOC freq_millihz")

    bpfoc = build_hmi_frame(["BPFOC ON", "FOC_FREQ 6.5", "ID -0.10", "IQ 0.30"])
    assert_eq(bpfoc[proto["CMD_OFF_MODE"]], proto["MODE_FOC"], "BPFOC mode")
    assert_true((bpfoc[proto["CMD_OFF_FLAGS"]] & proto["FLAG_ENABLE"]) == 0, "BPFOC ON enables motor")
    assert_eq(u16(bpfoc, proto["CMD_OFF_DU"]), hmi.q15_from_signed(-0.10), "BPFOC id")
    assert_eq(u16(bpfoc, proto["CMD_OFF_DV"]), hmi.q15_from_signed(0.30), "BPFOC iq")
    assert_eq(u32(bpfoc, proto["CMD_OFF_DW"]), 6500, "BPFOC freq_millihz")

    return {
        "duty_hex": duty.hex(" "),
        "scalar_hex": scalar.hex(" "),
        "vector_hex": vector.hex(" "),
        "vector_rot_hex": vector_rot.hex(" "),
        "foc_hex": foc.hex(" "),
        "bpfoc_hex": bpfoc.hex(" "),
    }


def case_hmi_response_layout(proto: dict[str, int]) -> dict[str, Any]:
    rsp = bytearray(proto["FRAME_LEN"])
    rsp[proto["RSP_OFF_HDR0"]] = proto["RSP_HDR0"]
    rsp[proto["RSP_OFF_HDR1"]] = proto["RSP_HDR1"]
    rsp[proto["RSP_OFF_VER"]] = 0x02
    rsp[proto["RSP_OFF_STATUS"]] = proto["STATUS_LINK_OK"] | proto["STATUS_PWM_ACTIVE"]
    rsp[proto["RSP_OFF_SEQ"]] = 0x34
    rsp[proto["RSP_OFF_FAULT"]] = proto["FAULT_OK"]
    rsp[proto["RSP_OFF_LAST_MODE"]] = proto["MODE_DUTY"]
    rsp[proto["RSP_OFF_EXT_FLAGS"]] = proto["EXT_PRECHARGE_RELAY"] | proto["EXT_BRAKE_PWM"]
    rsp[proto["RSP_OFF_EXT_DUTY_LO"]] = 0x34
    rsp[proto["RSP_OFF_EXT_DUTY_HI"]] = 0x12
    rsp[proto["RSP_OFF_FAN_DUTY_Q8"]] = 128
    rsp[proto["RSP_OFF_FAN_TACH_X30"]] = 7
    rsp[proto["RSP_OFF_PHASE_FLAGS"]] = proto["PHASE_FLAG_VALID"] | proto["PHASE_FLAG_C_VIRTUAL"]
    rsp[proto["RSP_OFF_CRC"]] = hmi.crc_xor(rsp)

    state = hmi.SharedState()
    with state.lock:
        state.link_ok = True
        state.last_rsp = bytes(rsp)
        state.last_rx_time = time.monotonic()
    data = hmi.status_payload(state)
    assert_eq(data["pwm"], 1, "status pwm")
    assert_eq(data["bp_precharge"], 1, "status bp_precharge")
    assert_eq(data["bp_brake_pwm"], 1, "status bp_brake_pwm")
    assert_true(0.49 < float(data["bp_fan_duty"]) < 0.51, "status fan duty")
    assert_eq(data["bp_fan_rpm"], 210, "status fan rpm")
    assert_eq(data["bp_phase_valid"], 1, "status phase valid")
    assert_eq(data["bp_phase_c_virtual"], 1, "status phase c virtual")
    return {
        "rsp_hex": bytes(rsp).hex(" "),
        "decoded_subset": {
            "pwm": data["pwm"],
            "bp_precharge": data["bp_precharge"],
            "bp_brake_pwm": data["bp_brake_pwm"],
            "bp_fan_duty": data["bp_fan_duty"],
            "bp_fan_rpm": data["bp_fan_rpm"],
        },
    }


CASES = [
    ("nucleo_proto_matches", case_nucleo_proto_matches),
    ("hmi_constants", case_hmi_constants),
    ("direct_probe_constants", case_direct_probe_constants),
    ("safety_selftest_offsets", case_safety_selftest_offsets),
    ("hmi_command_frame_layout", case_hmi_command_frame_layout),
    ("pc_direct_motion_frame_layout", case_pc_direct_motion_frame_layout),
    ("hmi_response_layout", case_hmi_response_layout),
]


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    proto_path = repo / "bluepill_uart_pwm_pio" / "include" / "proto.h"
    proto = parse_proto_h(proto_path)

    results: list[CaseResult] = []
    for name, fn in CASES:
        try:
            results.append(CaseResult(name=name, ok=True, evidence=fn(proto)))
        except Exception as exc:
            results.append(CaseResult(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}"))

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    summary = {
        "tool": "protocol_contract_check",
        "proto_h": str(proto_path),
        "pass": failed == 0,
        "passed": passed,
        "failed": failed,
        "cases": [r.__dict__ for r in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

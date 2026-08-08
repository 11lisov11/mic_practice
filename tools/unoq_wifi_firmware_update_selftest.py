#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("unoq_wifi_firmware_update.py")
SPEC = importlib.util.spec_from_file_location("unoq_wifi_firmware_update", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> int:
    good = json.dumps(
        {
            "platforms": [
                {"id": "arduino:avr", "installed_version": "1.8.7"},
                {"id": "arduino:zephyr", "installed_version": "0.90.0"},
            ]
        }
    )
    assert MODULE.installed_core_version_from_json(good) == "0.90.0"
    assert MODULE.installed_core_version_from_json('{"platforms": []}') == ""
    try:
        MODULE.installed_core_version_from_json("not-json")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid JSON must be rejected")
    assert MODULE.read_expected_build_id("UNOQ_MOTOR", 1234) == 1234
    assert MODULE.read_expected_build_id("UNOQ_MOTOR", 0) == 2026080704

    cfg = (Path(__file__).resolve().parents[1] / "web_hmi" / "flash_unoq_sketch_090.cfg").read_text(
        encoding="utf-8"
    )
    assert "0x8100000" in cfg
    assert "0xCAFFEEEE" in cfg
    assert "0x80F0000" not in cfg

    statuses = iter([{"fw_build": 0}, {"fw_build": 2026080704, "state": "SAFE", "pwm": 0}])
    original_fetch = MODULE.fetch_status
    original_sleep = MODULE.time.sleep
    try:
        MODULE.fetch_status = lambda _url: next(statuses)
        MODULE.time.sleep = lambda _seconds: None
        activated = MODULE.wait_for_build("http://uno-q", 2026080704, 1.0)
    finally:
        MODULE.fetch_status = original_fetch
        MODULE.time.sleep = original_sleep
    assert activated["fw_build"] == 2026080704

    healthy = {
        "state": "SAFE",
        "pwm": 0,
        "estop": 0,
        "bp_fault": 0,
        "bp_bad": 0,
        "bp_bad_cnt": 0,
        "bp_status": 1,
        "bp_age_ms": 0,
        "precharge": 0,
        "bp_ext": 0,
    }
    assert MODULE.activation_health_error(healthy) == ""
    assert "bp_fault=2" in MODULE.activation_health_error({**healthy, "bp_fault": 2})

    recovery_statuses = iter([{**healthy, "bp_fault": 2}, healthy])
    clear_commands = []
    original_fetch = MODULE.fetch_status
    original_post = MODULE.post_command
    original_sleep = MODULE.time.sleep
    try:
        MODULE.fetch_status = lambda _url: next(recovery_statuses)
        MODULE.post_command = lambda _url, command: (clear_commands.append(command) is None, "")
        MODULE.time.sleep = lambda _seconds: None
        recovered = MODULE.wait_for_healthy_controller("http://uno-q", 1.0)
    finally:
        MODULE.fetch_status = original_fetch
        MODULE.post_command = original_post
        MODULE.time.sleep = original_sleep
    assert clear_commands == ["CLEAR"]
    assert recovered["bp_fault"] == 0
    print("PASS unoq_wifi_firmware_update_selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


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
    expected_build = 2026082601
    with tempfile.TemporaryDirectory() as tmp:
        sketch = Path(tmp) / (Path(tmp).name + ".ino")
        sketch.write_text(f"const uint32_t FW_BUILD_ID = {expected_build}UL;", encoding="utf-8")
        assert MODULE.read_expected_build_id(tmp, 0) == expected_build
        for bad_source in ("", "const uint32_t FW_BUILD_ID = invalid;"):
            sketch.write_text(bad_source, encoding="utf-8")
            try:
                MODULE.read_expected_build_id(tmp, 0)
            except SystemExit:
                pass
            else:
                raise AssertionError("missing/invalid build ID accepted")

    cfg = (Path(__file__).resolve().parents[1] / "web_hmi" / "flash_unoq_sketch_090.cfg").read_text(
        encoding="utf-8"
    )
    assert "0x8100000" in cfg
    assert "0xCAFFEEEE" in cfg
    assert "0x80F0000" not in cfg

    statuses = iter([{"fw_build": 0}, {"fw_build": expected_build, "state": "SAFE", "pwm": 0}])
    original_fetch = MODULE.fetch_status
    original_sleep = MODULE.time.sleep
    try:
        MODULE.fetch_status = lambda _url: next(statuses)
        MODULE.time.sleep = lambda _seconds: None
        activated = MODULE.wait_for_build("http://uno-q", expected_build, 1.0)
    finally:
        MODULE.fetch_status = original_fetch
        MODULE.time.sleep = original_sleep
    assert activated["fw_build"] == expected_build

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
    assert "bp_fault=5" in MODULE.activation_health_error({**healthy, "bp_fault": 5})
    for key in healthy:
        incomplete = {k: v for k, v in healthy.items() if k != key}
        assert MODULE.activation_health_error(incomplete), key
    for key in healthy.keys() - {"state"}:
        for bad in (None, float("nan"), float("inf"), -1, "0"):
            assert MODULE.activation_health_error({**healthy, key: bad}), (key, bad)
    for status in (3, 33, 35):
        assert MODULE.activation_health_error({**healthy, "bp_status": status})

    with patch.object(MODULE, "urlopen") as http:
        ok, error = MODULE.post_command("http://uno-q", "CLEAR", "")
        assert not ok and "control token" in error
        http.assert_not_called()
        http.return_value.__enter__.return_value.read.return_value = b'{"ok": true}'
        assert MODULE.post_command("http://uno-q", "CLEAR", "test-control-token")[0]
        req = http.call_args.args[0]
        headers = {k.lower(): v for k, v in req.header_items()}
        assert headers["x-unoq-control-token"] == "test-control-token"
        assert "x-unoq-update-token" not in headers

    recovery_statuses = iter([{**healthy, "bp_fault": 2}, healthy])
    clear_commands = []
    original_fetch = MODULE.fetch_status
    original_post = MODULE.post_command
    original_sleep = MODULE.time.sleep
    try:
        MODULE.fetch_status = lambda _url: next(recovery_statuses)
        MODULE.post_command = lambda _url, command, token: (clear_commands.append((command, token)) is None, "")
        MODULE.time.sleep = lambda _seconds: None
        recovered = MODULE.wait_for_healthy_controller("http://uno-q", 1.0, "test-control-token")
    finally:
        MODULE.fetch_status = original_fetch
        MODULE.post_command = original_post
        MODULE.time.sleep = original_sleep
    assert clear_commands == [("CLEAR", "test-control-token")]
    assert recovered["bp_fault"] == 0
    with patch.object(MODULE, "fetch_status", return_value={**healthy, "bp_fault": 2}), \
            patch.object(MODULE, "urlopen") as http:
        try:
            MODULE.wait_for_healthy_controller("http://uno-q", 1.0)
        except RuntimeError as exc:
            assert "control token required" in str(exc)
        else:
            raise AssertionError("unauthenticated recovery reported success")
        http.assert_not_called()
    print("PASS unoq_wifi_firmware_update_selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline checks for the low-voltage Wi-Fi command-path verifier."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from verify_wifi_command_path import get_wifi_logs, safe_off, verify


def idle(**overrides):
    value = {
        "vdc": 0.0, "bp_status": 9, "bp_age_ms": 10, "state": "SAFE",
        "mode": "VF", "pwm": 0, "hmi_hv_armed": 0, "bp_fault": 5,
        "freq_cmd": 0.0, "precharge": 0, "bp_ext": 0,
    }
    value.update(overrides)
    return value


class FakeHmi:
    opener = object()
    base = "http://192.0.2.1:8080"

    def __init__(self, states):
        self.states = iter(states)
        self.calls = []

    def status(self):
        self.calls.append("status")
        return next(self.states)

    def request(self, method, path, body):
        self.calls.append((method, path, body))
        if path == "/api/start-sequence":
            return 409, {"ok": False, "error": "motor-controller fault is active"}
        return 200, {"ok": True}

    def fail_safe_stop(self):
        self.calls.append("stop")
        return 200, {"ok": True}


class VerifyWifiCommandPathTest(unittest.TestCase):
    def test_wsl_logs_authenticated_text_without_native_http(self):
        hmi = Mock(via_wsl=True)
        hmi._request_via_wsl.return_value = (200, "CMD STOP\n")
        with patch("verify_wifi_command_path.get_logs") as native:
            self.assertEqual(get_wifi_logs(hmi, "test-token"), "CMD STOP\n")
            native.assert_not_called()
        hmi._request_via_wsl.assert_called_once_with(
            "GET", "/api/logs?hours=1.000", {"X-UNOQ-Control-Token": "test-token"},
            None, response_format="text",
        )

    def test_wsl_logs_reject_http_error_and_wrong_payload(self):
        for response in ((403, "denied"), (200, {})):
            hmi = Mock(via_wsl=True)
            hmi._request_via_wsl.return_value = response
            with self.assertRaises(RuntimeError):
                get_wifi_logs(hmi, "test-token")

    def test_safe_off_rejects_invalid_and_active_telemetry(self):
        self.assertTrue(safe_off(idle()))
        for change in ({"vdc": float("nan")}, {"bp_age_ms": float("nan")},
                       {"bp_age_ms": 300}, {"pwm": 1}, {"bp_status": 0x20},
                       {"bp_fault": 0}, {"hmi_hv_armed": 1},
                       {"precharge": 1}, {"bp_ext": 0x08}):
            with self.subTest(change=change):
                self.assertFalse(safe_off(idle(**change)))

    def test_successful_route_always_stops(self):
        hmi = FakeHmi([idle(), idle(), idle(freq_cmd=5), idle(freq_cmd=20),
                       idle(freq_cmd=0), idle()])
        after_logs = ("CMD MODE VF\nCMD SET FREQ 5\nCMD SET FREQ 20\n"
                      "CMD SET FREQ 0\nWIFI_START_REJECT\nWIFI_STOP_SEQUENCE\n")
        with tempfile.TemporaryDirectory() as root, patch(
            "verify_wifi_command_path.get_logs", side_effect=["", after_logs]
        ):
            result = verify(hmi, "test-token", Path(root) / "run")
            self.assertTrue((Path(root) / "run" / "report.json").is_file())
        self.assertTrue(result["pass"])
        self.assertEqual(hmi.calls[-2], "stop")

    def test_bad_preflight_sends_no_commands(self):
        hmi = FakeHmi([idle(vdc=10)])
        with tempfile.TemporaryDirectory() as root, patch(
            "verify_wifi_command_path.get_logs", return_value=""
        ):
            result = verify(hmi, "test-token", Path(root) / "run")
        self.assertFalse(result["pass"])
        self.assertEqual(hmi.calls, ["status"])

    def test_unexpected_output_causes_stop(self):
        hmi = FakeHmi([idle(), idle(pwm=1), idle()])
        with tempfile.TemporaryDirectory() as root, patch(
            "verify_wifi_command_path.get_logs", side_effect=["", "WIFI_STOP_SEQUENCE"]
        ):
            result = verify(hmi, "test-token", Path(root) / "run")
        self.assertFalse(result["pass"])
        self.assertIn("stop", hmi.calls)


if __name__ == "__main__":
    unittest.main()

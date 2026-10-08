#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collect_wifi_telemetry as collector


def sample(**changes):
    return {
        "state": "SAFE", "pwm": 0, "hmi_hv_armed": 0, "bp_status": 9,
        "bp_age_ms": 20, "bp_good": 100, "bp_bad": 1, "bp_bad_cnt": 0, "vdc": 0.0,
        "fw_build": 2026092702, "mc_fw_build": 2026091401, **changes,
    }


class CollectorTests(unittest.TestCase):
    def test_idle_counter_increment_fails_even_if_final_counter_recovers(self):
        rows = [{"status": sample(bp_bad=value)} for value in (1, 2, 1)]
        result = collector.summarize(rows, [], "line\n", True)
        self.assertFalse(result["pass"])
        self.assertFalse(result["checks"]["bp_bad_valid"])
        self.assertFalse(result["checks"]["no_new_uart_errors"])

    def test_missing_and_nonfinite_status_fail_closed(self):
        for bad in (None, "9", float("nan"), float("inf")):
            result = collector.summarize([{"status": sample(bp_status=bad)}], [], "", True)
            self.assertFalse(result["pass"])
            self.assertFalse(result["checks"]["idle_outputs_off"])
        self.assertFalse(collector.summarize([{"status": sample(bp_age_ms=301)}], [], "", False)["pass"])

    def test_detailed_uart_counters_are_reported_when_available(self):
        status = sample(bp_bad_integrity=0, bp_bad_sequence=2, bp_superseded=0, bp_clear_pending=0)
        result = collector.summarize([{"status": status}], [], "", True)
        self.assertTrue(result["detailed_uart_counters_available"])
        self.assertEqual(result["detailed_uart_counters"]["bp_bad_sequence"]["last"], 2)

    def test_voltage_limit_rejects_false_zero_bus(self):
        result = collector.summarize([{"status": sample(vdc=11.0)}], [], "", True, 2.0)
        self.assertFalse(result["pass"])
        self.assertFalse(result["checks"]["vdc_within_limit"])
        self.assertEqual(result["max_vdc"], 2.0)
        self.assertTrue(collector.summarize([{"status": sample(vdc=1.5)}], [], "", True, 2.0)["pass"])
        self.assertFalse(collector.summarize([{"status": sample(vdc=float("nan"))}], [], "", True, 2.0)["pass"])

    def test_collector_uses_get_only_and_keeps_token_out_of_output(self):
        requests = []

        class Opener:
            def open(self, request, timeout):
                requests.append(request)
                payload = json.dumps({"ok": True, "data": sample()}).encode() if request.full_url.endswith("/api/status") else b"log line\n"
                return io.BytesIO(payload)

        with tempfile.TemporaryDirectory() as tmp, patch.object(collector, "build_opener", return_value=Opener()):
            folder = Path(tmp) / "capture"
            result = collector.collect("http://192.168.1.138:8080", "secret-token-value", 0, 1, folder, True)
            self.assertTrue(result["pass"])
            self.assertEqual([request.get_method() for request in requests], ["GET", "GET"])
            self.assertEqual(requests[1].get_header("X-unoq-control-token"), "secret-token-value")
            self.assertNotIn("secret-token-value", (folder / "summary.json").read_text(encoding="utf-8"))
            self.assertNotIn("secret-token-value", (folder / "status.jsonl").read_text(encoding="utf-8"))
            self.assertEqual((folder / "logs.txt").read_text(encoding="utf-8"), "log line\n")

    def test_loopback_url_rejected(self):
        with self.assertRaises(ValueError):
            collector.validate_url("http://127.0.0.1:8080")


if __name__ == "__main__":
    unittest.main()

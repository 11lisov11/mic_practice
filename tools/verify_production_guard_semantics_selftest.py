"""Offline regression tests for the production guard test oracle."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from verify_production_guard_semantics import case_pass, production_off, verify


def status():
    return dict(vdc=0.0, bp_status=9, bp_age_ms=20, state="SAFE", pwm=0,
                hmi_hv_armed=0, bp_fault=5, precharge=0, bp_ext=0,
                mode="VF", fw_build=2026092901, mc_fw_build=2026100601,
                hmi_arm_profile="hv", freq_cmd=0.0)


class Guards(unittest.TestCase):
    def test_success_semantics(self):
        s = status()
        self.assertTrue(case_pass(401, {"ok": False}, s, "auth", 0))
        self.assertFalse(case_pass(403, {"ok": False}, s, "auth", 0))
        self.assertTrue(case_pass(200, {"ok": True}, s, "accepted", 0))
        s["freq_cmd"] = 50.0
        self.assertTrue(case_pass(200, {"ok": True}, s, "accepted", 50))
        self.assertFalse(case_pass(200, {"ok": True}, s, "accepted", 0))
        s["freq_cmd"] = float("nan")
        self.assertFalse(case_pass(200, {"ok": True}, s, "accepted", 0))

    def test_rejection_semantics(self):
        self.assertTrue(case_pass(500, {"ok": False, "error": "rejected"}, status(), "nonfinite", 0))
        self.assertFalse(case_pass(500, {"ok": False, "error": "RPC crashed"}, status(), "nonfinite", 0))
        self.assertTrue(case_pass(409, {"ok": False, "error": "mc_fault=5"}, status(), "start", 0))
        self.assertFalse(case_pass(409, {"ok": False, "error": "unrelated"}, status(), "start", 0))

    def test_off_state_required(self):
        for key, bad in (("pwm", 1), ("hmi_hv_armed", 1), ("vdc", 310.0),
                         ("vdc", float("nan")), ("bp_age_ms", 500),
                         ("mc_fw_build", 0), ("mode", "FOC"), ("hmi_arm_profile", "lv")):
            with self.subTest(key=key):
                s = status()
                s[key] = bad
                self.assertFalse(production_off(s))
                self.assertFalse(case_pass(200, {"ok": True}, s, "accepted", 0))

    def test_full_sequence_and_final_stop(self):
        hmi = FakeHmi()
        unauthenticated = FakeHmi(auth=False, shared=hmi)
        with tempfile.TemporaryDirectory() as folder, patch(
                "verify_production_guard_semantics.get_wifi_logs", return_value="logs"):
            r = verify(hmi, unauthenticated, "never-written", Path(folder) / "run")
            self.assertTrue(r["pass"])
            self.assertEqual(len(r["cases"]), 8)
            self.assertEqual(hmi.stops, 1)
            raw = (Path(folder) / "run" / "report.json").read_text()
            self.assertNotIn("never-written", raw)
            self.assertFalse(any("arm" in path for path, _ in hmi.requests))

    def test_stop_on_failed_guard(self):
        hmi = FakeHmi(bad_reply=True)
        with tempfile.TemporaryDirectory() as folder, patch(
                "verify_production_guard_semantics.get_wifi_logs", return_value="logs"):
            r = verify(hmi, FakeHmi(auth=False, shared=hmi), "token", Path(folder) / "run")
            self.assertFalse(r["pass"])
            self.assertEqual(hmi.stops, 1)
            self.assertTrue(r["final_safe"])

    def test_no_commands_on_wrong_image_or_nan_setpoint(self):
        for key, value in (("mc_fw_build", 0), ("freq_cmd", float("nan"))):
            hmi = FakeHmi()
            hmi.s[key] = value
            with tempfile.TemporaryDirectory() as folder:
                r = verify(hmi, hmi, "token", Path(folder) / "run")
                self.assertFalse(r["pass"])
                self.assertEqual(hmi.requests, [])


class FakeHmi:
    via_wsl = True

    def __init__(self, auth=True, shared=None, bad_reply=False):
        self.auth, self.shared, self.bad_reply = auth, shared, bad_reply
        self.s = status()
        self.requests = []
        self.stops = 0

    def status(self):
        return dict(self.s)

    def request(self, method, path, body):
        self.requests.append((path, body))
        if not self.auth:
            return 401, {"ok": False}
        cmd = body.get("cmd", "")
        if cmd == "SET FREQ 100000":
            self.s["freq_cmd"] = 50.0
        elif cmd == "SET FREQ -1":
            self.s["freq_cmd"] = 0.0
        elif cmd in ("SET FREQ nan", "SET FREQ inf"):
            return 500, {"ok": False, "error": "rejected"}
        elif cmd == "START" or path == "/api/start-sequence":
            return 409, {"ok": False, "error": "mc_fault=5"}
        return 200, {"ok": not self.bad_reply}

    def fail_safe_stop(self):
        self.stops += 1
        self.s["freq_cmd"] = 0.0
        return 200, {"ok": True}


if __name__ == "__main__":
    unittest.main()

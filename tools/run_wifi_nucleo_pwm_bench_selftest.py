#!/usr/bin/env python3
"""Synthetic waveform checks; does not access hardware or the network."""
import csv
import io
import json
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from run_wifi_nucleo_pwm_bench import (
    WifiHmi, analyze_active, analyze_external_break, analyze_software_break, analyze_static, capture,
    verify_unpowered_preflash,
)
from wifi_bench_scenarios import transition_checks, operator_keepalive
from saleae_pwm_analyze import load_csv


def fixture(path: Path, *, frequency_hz: int = 10_000, overlap: bool = False,
            em_stop: int = 0, startup_em_stop: bool = False,
            em_stop_during_pwm: bool = False) -> None:
    rate = 24_000_000
    period = rate // frequency_hz
    dead = 48  # 2 us
    events: dict[int, list[tuple[int, int]]] = {}
    for cycle in range(2_000):
        base = rate // 100 + cycle * period
        for pair in range(3):
            high = pair * 2
            low = high + 1
            for offset, channel, level in (
                (dead, high, 1),
                (period // 2, high, 0),
                (period // 2 + dead, low, 1),
                (period, low, 0),
            ):
                events.setdefault(base + offset, []).append((channel, level))
    if em_stop_during_pwm:
        events.setdefault(rate * 15 // 1000, []).append((6, 1))
        events.setdefault(rate * 16 // 1000, []).append((6, 0))
    state = [0] * 6 + [1 if startup_em_stop else em_stop]
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Time [s]", *[f"Channel {channel}" for channel in range(7)]])
        writer.writerow([0, *state])
        if startup_em_stop:
            state[6] = 0
            writer.writerow([0.001, *state])
        for tick, changes in sorted(events.items()):
            for channel, level in changes:
                state[channel] = level
            row = state.copy()
            if overlap:
                row[1] |= row[0]
            writer.writerow([f"{tick / rate:.12f}", *row])
        writer.writerow([0.25, *state])


class ActiveAnalysisTests(unittest.TestCase):
    def analyze(self, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "digital.csv"
            fixture(path, **kwargs)
            return analyze_active(path, require_em_stop=True)

    def test_accepts_10khz_complementary_pwm(self):
        self.assertTrue(self.analyze()["pass"])

    def test_rejects_overlap(self):
        self.assertFalse(self.analyze(overlap=True)["pass"])

    def test_rejects_wrong_carrier(self):
        self.assertFalse(self.analyze(frequency_hz=8_000)["pass"])

    def test_rejects_released_em_stop(self):
        self.assertFalse(self.analyze(em_stop=1)["pass"])

    def test_records_pre_pwm_em_stop_high_without_masking_active_check(self):
        result = self.analyze(startup_em_stop=True)
        self.assertTrue(result["pass"])
        self.assertFalse(result["checks"]["pa6_em_stop_held_low_raw"])
        self.assertTrue(result["checks"]["pa6_low_during_pwm"])

    def test_rejects_em_stop_high_between_pwm_edges(self):
        result = self.analyze(em_stop_during_pwm=True)
        self.assertFalse(result["pass"])
        self.assertFalse(result["checks"]["pa6_low_during_pwm"])

    def test_static_analysis_ignores_only_bounded_capture_warmup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "static.csv"
            with path.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Time [s]", *[f"Channel {channel}" for channel in range(7)]])
                writer.writerow([0.0, 1, 0, 1, 0, 1, 0, 1])
                writer.writerow([0.0001, 0, 0, 0, 0, 0, 0, 1])
                writer.writerow([0.1, 0, 0, 0, 0, 0, 0, 1])
            self.assertFalse(analyze_static(path)["pass"])
            self.assertTrue(analyze_static(path, settle_s=0.001)["pass"])


class SoftwareBreakAnalysisTests(unittest.TestCase):
    def test_accepts_pwm_then_latched_timer_break(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "digital.csv"
            rows = [[0.0, 0, 0, 0, 0, 0, 0, 1]]
            for group in (0.1, 1.2):
                for cycle in range(3):
                    base = group + cycle * 0.0001
                    rows.extend((
                        [base + 0.000002, 1, 0, 1, 0, 1, 0, 1],
                        [base + 0.00005, 0, 0, 0, 0, 0, 0, 1],
                        [base + 0.000052, 0, 1, 0, 1, 0, 1, 1],
                        [base + 0.0001, 0, 0, 0, 0, 0, 0, 1],
                    ))
            rows.append([1.7, 0, 0, 0, 0, 0, 0, 1])
            with path.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Time [s]", *(f"Channel {index}" for index in range(7))])
                writer.writerows(rows)
            result = analyze_software_break(path)
            self.assertTrue(result["pass"], result["checks"])
            rows[-1][-1] = 0
            with path.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Time [s]", *(f"Channel {index}" for index in range(7))])
                writer.writerows(rows)
            self.assertFalse(analyze_software_break(path)["pass"])


class ExternalBreakAnalysisTests(unittest.TestCase):
    def test_requires_physical_sd_edge_and_latched_low_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "digital.csv"
            rows = [[0.0, 0, 0, 0, 0, 0, 0, 1]]
            for cycle in range(300):
                base = 0.1 + cycle * 0.0001
                rows.extend((
                    [base + 0.000002, 1, 0, 1, 0, 1, 0, 1],
                    [base + 0.00005, 0, 0, 0, 0, 0, 0, 1],
                    [base + 0.000052, 0, 1, 0, 1, 0, 1, 1],
                    [base + 0.0001, 0, 0, 0, 0, 0, 0, 1],
                ))
            rows.extend((
                [0.13005, 0, 0, 0, 0, 0, 0, 0],
                [0.2, 0, 0, 0, 0, 0, 0, 1],
                [0.4, 0, 0, 0, 0, 0, 0, 1],
            ))

            def check(sample_rows):
                with path.open("w", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["Time [s]", *(f"Channel {i}" for i in range(7))])
                    writer.writerows(sample_rows)
                return analyze_external_break(path)

            self.assertTrue(check(rows)["pass"], check(rows)["checks"])
            bounced = [row.copy() for row in rows[:-3]] + [
                [0.13005, 0, 0, 0, 0, 0, 0, 0],
                [0.136, 0, 0, 0, 0, 0, 0, 1],
                [0.14, 0, 0, 0, 0, 0, 0, 0],
                [0.16, 0, 0, 0, 0, 0, 0, 1],
                [0.4, 0, 0, 0, 0, 0, 0, 1],
            ]
            self.assertTrue(check(bounced)["pass"])
            glitch = [row.copy() for row in rows[:-3]] + [
                [0.13005, 0, 0, 0, 0, 0, 0, 0],
                [0.130051, 0, 0, 0, 0, 0, 0, 1],
                [0.4, 0, 0, 0, 0, 0, 0, 1],
            ]
            self.assertFalse(check(glitch)["pass"])
            fragmented = [row.copy() for row in rows[:-3]]
            for pulse in range(25):
                base = 0.13005 + pulse * 0.002
                fragmented.extend((
                    [base, 0, 0, 0, 0, 0, 0, 0],
                    [base + 0.001, 0, 0, 0, 0, 0, 0, 1],
                ))
            fragmented.append([0.4, 0, 0, 0, 0, 0, 0, 1])
            fragmented_result = check(fragmented)
            self.assertGreater(fragmented_result["sd_low_total_ms"], 20)
            self.assertLess(fragmented_result["sd_low_longest_ms"], 2)
            self.assertFalse(fragmented_result["checks"]["sd_low_confirmed"])
            self.assertFalse(fragmented_result["pass"])
            no_trip = [row.copy() for row in rows]
            no_trip[-3][-1] = 1
            self.assertFalse(check(no_trip)["pass"])
            resumed = [row.copy() for row in rows]
            resumed.insert(-1, [0.25, 1, 0, 0, 0, 0, 0, 1])
            self.assertFalse(check(resumed)["pass"])

class CaptureRetryTests(unittest.TestCase):
    def check_capture(self, errors, succeeds):
        class DeviceError(Exception):
            pass

        automation = MagicMock()
        automation.errors.DeviceError = DeviceError
        manager = MagicMock()
        session = MagicMock()
        manager.start_capture.side_effect = [DeviceError(e) for e in errors] + [session]
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "sys.modules", {"saleae": MagicMock(automation=automation)}
        ), patch("run_wifi_nucleo_pwm_bench.time.sleep"):
            folder = Path(directory) / "capture"
            if succeeds:
                result = capture(manager, "physical-device", folder, 0.1)
                self.assertEqual(result, folder / "retry_1" / "csv" / "digital.csv")
            else:
                with self.assertRaises(DeviceError):
                    capture(manager, "physical-device", folder, 0.1)
            self.assertTrue((folder / "capture_errors.json").is_file())
        return manager.start_capture.call_count

    def test_read_timeout_is_retried_and_recorded(self):
        self.assertEqual(self.check_capture(["ReadTimeout"], True), 2)

    def test_three_timeouts_fail(self):
        self.assertEqual(self.check_capture(["ReadTimeout"] * 3, False), 3)

    def test_other_device_error_is_not_retried(self):
        self.assertEqual(self.check_capture(["Device disconnected"], False), 1)


class WifiWslTransportTests(unittest.TestCase):
    def test_reuses_wsl_process_and_sends_token_only_on_stdin(self):
        process = MagicMock()
        process.stdin = MagicMock()
        process.stdout = io.StringIO(
            json.dumps({"code": 200, "payload": {"ok": True, "data": {"state": "SAFE"}}}) + "\n"
            + json.dumps({"code": 200, "payload": {"ok": True}}) + "\n"
        )
        process.poll.return_value = None
        with patch("run_wifi_nucleo_pwm_bench.subprocess.Popen", return_value=process) as launch:
            hmi = WifiHmi("http://192.168.1.138:8080", "private-token", [], via_wsl=True)
            self.assertEqual(hmi.status()["state"], "SAFE")
            code, payload = hmi.request("POST", "/api/cmd", {"cmd": "STOP"})
            self.assertEqual((code, payload["ok"]), (200, True))
            self.assertEqual(launch.call_count, 1)
            self.assertNotIn("private-token", str(launch.call_args))
            sent = [json.loads(call.args[0]) for call in process.stdin.write.call_args_list]
            self.assertEqual(len(sent), 2)
            self.assertNotIn("X-UNOQ-Control-Token", sent[0]["headers"])
            self.assertEqual(sent[1]["headers"]["X-UNOQ-Control-Token"], "private-token")
            hmi.close()
            process.stdin.close.assert_called_once()
            process.wait.assert_called_once()


class UnpoweredPreflashTests(unittest.TestCase):
    def safe_status(self):
        return {"state": "SAFE", "pwm": 0, "hmi_hv_armed": 0,
                "bp_vbus_valid": 1, "bp_age_ms": 30, "vdc": 1.0}

    def test_accepts_fresh_disarmed_low_bus(self):
        verify_unpowered_preflash(self.safe_status())

    def test_rejects_energized_or_uncertain_bus(self):
        for voltage in (2.01, 3.0, 11.7, -0.1):
            with self.subTest(voltage=voltage), self.assertRaises(RuntimeError):
                verify_unpowered_preflash({**self.safe_status(), "vdc": voltage})

    def test_rejects_active_armed_stale_or_invalid(self):
        for update in ({"state": "RUN"}, {"pwm": 1}, {"hmi_hv_armed": 1},
                       {"bp_vbus_valid": 0}, {"bp_age_ms": 501}):
            with self.subTest(update=update), self.assertRaises(RuntimeError):
                verify_unpowered_preflash({**self.safe_status(), **update})


class TransitionTests(unittest.TestCase):
    def data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wave.csv"
            fixture(path)
            times, values = load_csv(path, list(range(6)))
        times = [0.0] + [t + 0.2 for t in times] + [1.5]
        values = {ch: [0] + v + [0] for ch, v in values.items()}
        return times, values

    def test_single_burst(self):
        self.assertTrue(transition_checks(*self.data())["pass"])

    def test_restarted_burst_rejected(self):
        times, values = self.data()
        times = times[:-1] + [0.8, 0.80001, 1.5]
        values = {ch: v[:-1] + [1, 0, 0] for ch, v in values.items()}
        self.assertFalse(transition_checks(times, values)["pass"])


    def test_high_tail_rejected(self):
        times, values = self.data()
        values[0][-1] = 1
        self.assertFalse(transition_checks(times, values)["pass"])


class KeepaliveTests(unittest.TestCase):
    def test_heartbeat_runs_during_blocking_capture_and_stops(self):
        sent = threading.Event()
        client = MagicMock()
        client.post.side_effect = lambda *args: sent.set()
        with patch("run_wifi_nucleo_pwm_bench.WifiHmi", return_value=client):
            with operator_keepalive(MagicMock()) as evidence:
                self.assertTrue(sent.wait(1))
            self.assertGreaterEqual(evidence["sent"], 1)
            self.assertEqual(evidence["errors"], [])

    def test_heartbeat_error_is_not_silenced(self):
        sent = threading.Event()
        client = MagicMock()
        def fail(*args):
            sent.set()
            raise RuntimeError("offline")
        client.post.side_effect = fail
        with patch("run_wifi_nucleo_pwm_bench.WifiHmi", return_value=client):
            with operator_keepalive(MagicMock()) as evidence:
                self.assertTrue(sent.wait(1))
            self.assertEqual(evidence["errors"], ["offline"])

if __name__ == "__main__":
    unittest.main()

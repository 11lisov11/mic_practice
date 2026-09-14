#!/usr/bin/env python3
"""Synthetic waveform checks; does not access hardware or the network."""
import csv
import tempfile
import unittest
from pathlib import Path

from run_wifi_nucleo_pwm_bench import analyze_active, analyze_static


def fixture(path: Path, *, frequency_hz: int = 10_000, overlap: bool = False, em_stop: int = 0) -> None:
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
    state = [0] * 6 + [em_stop]
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Time [s]", *[f"Channel {channel}" for channel in range(7)]])
        writer.writerow([0, *state])
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


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Synthetic tests only; no hardware access or firmware writes."""
import csv
import tempfile
import unittest
from pathlib import Path

from run_nucleo_pwm_diagnostic import analyze_burst


def fixture(path, *, silent=False, overlap=False, swapped=False, cycles=4800):
    rate, period, gap = 24000000, 1500, 32
    events = {}
    for cycle in range(cycles):
        base = rate // 10 + cycle * period
        for pair, width in enumerate((300, 750, 1200)):
            for offset, ch, level in ((gap, pair * 2, 1), (width, pair * 2, 0),
                                      (width + gap, pair * 2 + 1, 1), (period, pair * 2 + 1, 0)):
                events.setdefault(base + offset, []).append((ch, level))
    state = [0] * 6
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Time [s]", *[f"Channel {ch}" for ch in range(6)]])
        writer.writerow([0, *state])
        for tick, changes in sorted(events.items()):
            for ch, level in changes:
                state[ch] = level
            row = state.copy()
            if silent:
                row[5] = 0
            if overlap:
                row[1] |= row[0]
            if swapped:
                row[0:2], row[4:6] = row[4:6], row[0:2]
            writer.writerow([f"{tick / rate:.12f}", *row])
        writer.writerow([1.2, *([0] * 6)])


class BurstChecks(unittest.TestCase):
    def analyze(self, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "digital.csv"
            fixture(path, **kwargs)
            return analyze_burst(path, 24000000)

    def test_correct_burst(self):
        result = self.analyze()
        self.assertTrue(result["pass"], result["checks"])

    def test_silent_leg_rejected(self):
        self.assertFalse(self.analyze(silent=True)["pass"])

    def test_overlap_rejected(self):
        self.assertFalse(self.analyze(overlap=True)["pass"])

    def test_swapped_phases_rejected(self):
        self.assertFalse(self.analyze(swapped=True)["checks"]["duty_identifies_phase_pairs"])

    def test_wrong_duration_rejected(self):
        self.assertFalse(self.analyze(cycles=1600)["checks"]["burst_290_to_310_ms"])


if __name__ == "__main__":
    unittest.main()

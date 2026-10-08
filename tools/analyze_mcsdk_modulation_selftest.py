"""Check qualification with positive and deliberately wrong synthetic duties."""
import csv
from pathlib import Path
import tempfile
import unittest

import numpy as np

from analyze_mcsdk_modulation import analyze


def synthetic(path, frequency=20, phases=(0,-120,120), invert_v=False):
    events=[]
    period=1/16000
    for cycle in range(2800):
        center=(cycle+.5)*period
        for channel,phase in zip((0,2,4),phases):
            duty=.48+.2*np.cos(2*np.pi*frequency*center+phase*np.pi/180)
            if channel==2 and invert_v: duty=1-duty
            events.extend(((center-duty*period/2,channel,1),(center+duty*period/2,channel,0)))
    values=[0]*7
    with path.open("w",newline="") as stream:
        writer=csv.writer(stream)
        writer.writerow(["Time [s]",*[f"Channel {ch}" for ch in range(7)]])
        writer.writerow([0,*values])
        for time,channel,value in sorted(events):
            values[channel]=value
            writer.writerow([time,*values])
        writer.writerow([2800*period,*values])


class ModulationTests(unittest.TestCase):
    def run_case(self, **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"synthetic.csv"
            synthetic(path,**kwargs)
            return analyze(path,24_000_000,20)

    def test_correct_three_phase(self):
        self.assertTrue(self.run_case()["pass"])

    def test_wrong_frequency(self):
        result=self.run_case(frequency=10)
        self.assertFalse(result["pass"])
        self.assertFalse(result["checks"]["frequency_from_waveform_matches_command"])

    def test_swapped_V_W(self):
        result=self.run_case(phases=(0,120,-120))
        self.assertFalse(result["pass"])
        self.assertFalse(result["checks"]["positive_phase_rotation"])

    def test_wrong_high_low_channel(self):
        self.assertFalse(self.run_case(invert_v=True)["pass"])

    def test_identical_phases_rejected(self):
        with self.assertRaises(ValueError):
            self.run_case(phases=(0,0,0))


if __name__=="__main__":
    unittest.main()

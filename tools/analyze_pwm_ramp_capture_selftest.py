"""Adversarial waveform tests for acceleration and phase qualification."""
import csv
from pathlib import Path
import tempfile
import unittest
import math
from analyze_pwm_ramp_capture import analyze

def synthetic(path,acceleration=5/3,phases=(0,-120,120),start=0):
    events=[];period=1/1000
    for cycle in range(3000):
        center=(cycle+.5)*period
        angle=2*math.pi*(start*center+.5*acceleration*center*center)
        for ch,phase in zip((0,2,4),phases):
            duty=.48+.1*math.cos(angle+phase*math.pi/180)
            events.extend(((center-duty*period/2,ch,1),(center+duty*period/2,ch,0)))
    values=[0]*5
    with path.open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['Time [s]',*[f'Channel {ch}' for ch in range(5)]]);writer.writerow([0,*values])
        for t,ch,v in sorted(events):values[ch]=v;writer.writerow([t,*values])
        writer.writerow([3,*values])

class RampTests(unittest.TestCase):
    def case(self,**kwargs):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'known.csv';synthetic(p,**kwargs);return analyze(p)
    def test_correct(self):self.assertTrue(self.case()['pass_'])
    def test_wrong_acceleration(self):self.assertFalse(self.case(acceleration=1)['pass_'])
    def test_nonzero_start(self):self.assertFalse(self.case(start=1)['pass_'])
    def test_swapped_phases(self):self.assertFalse(self.case(phases=(0,120,-120))['pass_'])

if __name__=='__main__':unittest.main()

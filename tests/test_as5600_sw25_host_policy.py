"""Host accepts SW25 only with peripheral released and open-drain GPIOs."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import run_as5600_bounded_5hz as trial

class Sw25(unittest.TestCase):
    def setUp(self):
        self.old=trial.EXPECTED_SENSOR_MODE
        trial.EXPECTED_SENSOR_MODE=2
        r=json.loads((ROOT/'artifacts/live_bench_20261026/as5600_followup_r1/poll100_aligned_magnet_5hz_r1/report.json').read_text())
        self.s=dict(r['before'])
        self.s.update(enc_diag_mode=2,enc_diag_cr1=0,
            enc_diag_cfg_before=(self.s['enc_diag_cfg_before']&~0x3f)|0x35,
            enc_diag_cfg_after=(self.s['enc_diag_cfg_after']&~0x3f)|0x35)

    def tearDown(self):trial.EXPECTED_SENSOR_MODE=self.old

    def test_matching_released_open_drain_pins(self):
        self.assertTrue(trial.setup_ok(self.s))

    def test_reject_pin_ownership_setup_and_mode_changes(self):
        for key,value in [('enc_diag_cr1',1),('enc_diag_cr1',None),
                          ('enc_diag_cfg_before',0x3a),('enc_diag_cfg_after',0x3a),
                          ('enc_diag_cfg_before',5),('enc_diag_mode',4),
                          ('enc_diag_cfg_match',0),('enc_init_error',1),
                          ('enc_diag_thread_priority',14)]:
            with self.subTest(key=key,value=value):
                s=dict(self.s);s[key]=value
                self.assertFalse(trial.setup_ok(s))

    def test_observed_transfer_failure_does_not_change_pin_policy(self):
        self.s.update(enc_io_error=-5,enc_bus_ok=0,enc_diag_cause=2)
        self.assertTrue(trial.setup_ok(self.s))

if __name__=='__main__':unittest.main()

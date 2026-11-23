"""Nucleo ownership selection preserves the existing five-second run gates."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import run_as5600_bounded_5hz as trial


class NucleoSensor(unittest.TestCase):
    def setUp(self):
        self.pair=trial.t.checks.PAIR;self.mode=trial.EXPECTED_SENSOR_MODE
        self.s=json.loads((ROOT/'artifacts/live_bench_20261026/uart_rx_handoff_r1/runtime_telemetry_r2/report.json').read_text())['after']
        trial.configure(2026102603,'NUCLEO')

    def tearDown(self):
        trial.t.checks.PAIR=self.pair;trial.EXPECTED_SENSOR_MODE=self.mode

    def test_actual_remote_setup_accepted(self):
        self.assertTrue(trial.setup_ok(self.s))
        self.assertEqual(trial.t.checks.PAIR,(2026102603,2026102602))

    def test_wrong_owner_and_pair_rejected(self):
        for key,value in [('enc_source','uno_q_i2c2'),('enc_diag_mode',5),
                          ('enc_diag_cfg_match',0),('enc_init_error',-1),
                          ('fw_build',2026102601),('mc_fw_build',2026102510)]:
            with self.subTest(key=key):self.assertFalse(trial.setup_ok(dict(self.s,**{key:value})))
        for build,mode in [(2026102603,'POLL100'),(2026102518,'NUCLEO'),(1,'NUCLEO')]:
            with self.subTest(build=build,mode=mode):
                with self.assertRaises(ValueError):trial.configure(build,mode)

    def test_sensor_errors_are_observations_not_scalar_feedback(self):
        self.assertTrue(trial.setup_ok(dict(self.s,enc_io_error=-5,enc_bus_ok=0,enc_errors=1)))

    def test_retained_reset_fault_cannot_authorize_start(self):
        self.assertEqual(self.s['mc_transport_fault'],7)
        self.assertFalse(trial.t.ready(self.s))
        self.assertFalse(trial.completed(self.s,dict(run_id=0)))
        self.assertFalse(trial.starting_remote(self.s,dict(run_id=0),False))


if __name__=='__main__':unittest.main()

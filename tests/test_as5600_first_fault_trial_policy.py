"""Replay timed STOP handoff and guard the passive first-I2C capture."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import run_as5600_bounded_5hz as trial


class FirstFaultTrial(unittest.TestCase):
    def setUp(self):
        self.pair=trial.t.checks.PAIR;self.mode=trial.EXPECTED_SENSOR_MODE
        trial.configure(2026102605,'NUCLEO')
        r=json.loads((ROOT/'artifacts/live_bench_20261026/uart_rx_handoff_r1/powered_5hz_r1/trial/report.json').read_text())
        self.before=r['before']
        self.s=copy.deepcopy(next(x['status'] for x in r['samples']
            if x['status'].get('run_reason')==1 and x['status'].get('bp_status')==0x61))
        self.s.update(fw_build=2026102605,mc_fw_build=2026102604)

    def tearDown(self):
        trial.t.checks.PAIR=self.pair;trial.EXPECTED_SENSOR_MODE=self.mode

    def test_actual_deadline_handoff_only_allows_stop_not_final_off(self):
        self.assertEqual(self.s['run_elapsed_ms'],5000)
        self.assertTrue(trial.deadline_stop_observed(self.s,self.before))
        self.assertFalse(trial.completed(self.s,self.before))
        self.assertFalse(trial.t.checks.off(self.s))
        s=dict(self.s,bp_status=1,hmi_hv_armed=0)
        self.assertTrue(trial.completed(s,self.before))
        self.assertTrue(trial.t.checks.off(s))

    def test_fault_stale_active_or_wrong_timer_rejected(self):
        for key,value in [('bp_status',0x63),('bp_status',0),('pwm',1),('mc_age_ms',300),
            ('mc_fault',1),('mc_transport_fault',7),('estop',1),('run_id',0),
            ('run_reason',2),('run_elapsed_ms',4999),('run_elapsed_ms',True),
            ('run_limit_ms',6000),('run_stop_ms',self.s['run_stop_ms']+1),
            ('mc_current_zero_ready',0),('mc_bad_integrity',1)]:
            with self.subTest(key=key):self.assertFalse(trial.deadline_stop_observed(dict(self.s,**{key:value}),self.before))
        s=copy.deepcopy(self.s);s['mc_sd_live']['level']='LOW'
        self.assertFalse(trial.deadline_stop_observed(s,self.before))

    def test_new_pair_and_fresh_capture_slot(self):
        s=dict(self.s,enc_fault_decode_valid=1,enc_fault_bad=0,enc_fault_pwm_hex='-',enc_fault_records=[])
        self.assertTrue(trial.setup_ok(s));self.assertTrue(trial.capture_ready(s))
        for key,value in [('enc_fault_pwm_hex','00'*160),('enc_fault_decode_valid',0),('enc_fault_bad',1),('mc_fw_build',2026102602)]:
            with self.subTest(key=key):self.assertFalse(trial.capture_ready(dict(s,**{key:value})))
        with self.assertRaises(ValueError):trial.configure(2026102605,'FILTER100')

    def test_complete_pwm_record_required(self):
        s=dict(self.s,enc_fault_decode_valid=1,enc_fault_pwm_hex='00'*160,
            enc_fault_records=[dict(kind='first_with_pwm',pwm_moe=True,cause='BUSY')])
        self.assertTrue(trial.captured_pwm_fault(s))
        self.assertFalse(trial.captured_pwm_fault(dict(s,enc_fault_decode_valid=0)))
        self.assertFalse(trial.captured_pwm_fault(dict(s,enc_fault_pwm_hex='00')))
        self.assertFalse(trial.captured_pwm_fault(dict(s,enc_fault_records=[dict(kind='first_since_boot',pwm_moe=True)])))
        self.assertFalse(trial.captured_pwm_fault(dict(s,enc_fault_records=[dict(kind='first_with_pwm',pwm_moe=False)])))

    def test_rpc_boot_retry_pair_keeps_capture_and_stop_guards(self):
        trial.configure(2026102609,'NUCLEO')
        s=dict(self.s,fw_build=2026102609,enc_fault_decode_valid=1,enc_fault_bad=0,
            enc_fault_pwm_hex='-',enc_fault_records=[])
        self.assertTrue(trial.setup_ok(s))
        self.assertTrue(trial.capture_ready(s))
        self.assertTrue(trial.deadline_stop_observed(s,self.before))
        self.assertFalse(trial.completed(s,self.before))
        for changed in ({'mc_fw_build':2026102602},{'enc_fault_bad':1},
                        {'enc_fault_decode_valid':0},{'enc_fault_pwm_hex':'00'*160}):
            with self.subTest(changed=changed):self.assertFalse(trial.capture_ready(dict(s,**changed)))
        self.assertFalse(trial.deadline_stop_observed(dict(s,mc_transport_fault=7),self.before))
        self.assertFalse(trial.deadline_stop_observed(dict(s,mc_fault_current_mask=1),self.before))
        with self.assertRaises(ValueError):trial.configure(2026102609,'POLL100')

    def test_parked_i2c_pair_preserves_all_deadline_and_capture_checks(self):
        trial.configure(2026102701,'NUCLEO')
        s=dict(self.s,fw_build=2026102701,mc_fw_build=2026102702,
            enc_fault_decode_valid=1,enc_fault_bad=0,enc_fault_pwm_hex='-',enc_fault_records=[])
        self.assertTrue(trial.setup_ok(s))
        self.assertTrue(trial.capture_ready(s))
        self.assertTrue(trial.deadline_stop_observed(s,self.before))
        self.assertFalse(trial.completed(s,self.before))
        self.assertFalse(trial.capture_ready(dict(s,mc_fw_build=2026102604)))
        self.assertFalse(trial.setup_ok(dict(s,enc_diag_cfg_match=0)))
        for changed in ({'mc_current_zero_ready':0},{'mc_fault_current_mask':1},
                        {'mc_transport_fault':7},{'mc_age_ms':300},{'run_limit_ms':6000}):
            with self.subTest(changed=changed):self.assertFalse(trial.deadline_stop_observed(dict(s,**changed),self.before))
        with self.assertRaises(ValueError):trial.configure(2026102701,'FILTER100')


if __name__=='__main__':unittest.main()

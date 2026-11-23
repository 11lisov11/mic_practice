"""Replay the actual 12ms false abort and reject hazardous/late variants."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import run_as5600_bounded_5hz as trial
import run_current_shunt_5hz as t

class StartTransition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=ROOT/'artifacts/live_bench_20261026/as5600_followup_r1/poll100_powered_5hz_r1/report.json'
        cls.report=json.loads(p.read_text())
        cls.before=cls.report['before']
        cls.sample=next(x['status'] for x in cls.report['samples'] if x['status'].get('pwm')==1)

    def setUp(self):
        t.checks.PAIR=(2026102518,2026102510)
        trial.EXPECTED_SENSOR_MODE=4
        self.s=copy.deepcopy(self.sample)

    def test_recorded_local_start_is_not_remote_run(self):
        self.assertEqual(self.s['run_elapsed_ms'],12)
        self.assertFalse(t.checks.active(self.s))
        self.assertTrue(trial.starting_remote(self.s,self.before,False))

    def test_no_grace_after_confirmed_remote_run(self):
        self.assertFalse(trial.starting_remote(self.s,self.before,True))

    def test_reject_deadline_faults_staleness_and_wrong_run(self):
        variants=[('run_elapsed_ms',301),('run_elapsed_ms',-1),('run_elapsed_ms',True),
            ('run_id',0),('run_limit_ms',6000),('run_reason',2),('mc_age_ms',300),
            ('bp_status',0),('bp_status',9),('bp_status',3),('vdc',400),
            ('mc_transport_fault',4),('mc_bad_cnt',1),('mc_bad_integrity',1),
            ('mc_uart_error_flags',8),('estop',1),('hmi_hv_armed',0),
            ('mc_fault',3),('bp_fault',3),('mc_fault_current_mask',4),
            ('mc_fault_occurred_mask',1024),('manual_run_mode',1),('freq_cmd',10),
            ('bp_temp_c',80),('enc_diag_mode',5),('enc_init_error',1)]
        for key,value in variants:
            with self.subTest(key=key,value=value):
                s=copy.deepcopy(self.s);s[key]=value
                self.assertFalse(trial.starting_remote(s,self.before,False))

    def test_sd_zero_and_new_start_break_remain_fatal(self):
        for field,value in [('level','LOW'),('break_irq_enabled',False),('config_ok',False),('age_ms',300)]:
            s=copy.deepcopy(self.s);s['mc_sd_live'][field]=value
            self.assertFalse(trial.starting_remote(s,self.before,False))
        s=copy.deepcopy(self.s);s['mc_current_zero_ready']=0
        self.assertFalse(trial.starting_remote(s,self.before,False))
        s=copy.deepcopy(self.s)
        next(x for x in s['mc_break_snapshots'] if x['kind']=='first_start_window')['captured']=True
        self.assertFalse(trial.starting_remote(s,self.before,False))

if __name__=='__main__':unittest.main()

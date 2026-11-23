"""Replay delayed START: host must not truncate a healthy MCU five-second run."""
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from run_as5600_bounded_5hz import RunWatchdog

class Watchdog(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.w=RunWatchdog(100,{'run_id':1},lambda:self.calls.append('stop'))
        self.s={'run_id':2,'run_limit_ms':5000,'run_reason':0,'run_elapsed_ms':1258}

    def test_recorded_start_delay_does_not_consume_run_budget(self):
        r=json.loads((ROOT/'artifacts/live_bench_20261026/as5600_followup_r1/poll100_powered_5hz_r2/report.json').read_text())
        row=next(x for x in r['samples'] if x['status'].get('pwm')==1)
        now=100+row['host_monotonic_s']-r['request_monotonic_s']
        self.assertTrue(self.w.observe(row['status'],now))
        self.assertAlmostEqual(self.w.deadline,112.242,delta=.02)
        self.assertGreater(self.w.deadline,110)

    def test_only_one_anchor_frozen_status_cannot_extend(self):
        self.assertTrue(self.w.observe(self.s,107.5))
        deadline=self.w.deadline
        self.assertFalse(self.w.observe(self.s,109))
        self.assertEqual(self.w.deadline,deadline)

    def test_reject_old_wrong_and_expired_run(self):
        for key,value in [('run_id',1),('run_limit_ms',6000),('run_reason',2),('run_elapsed_ms',True),('run_elapsed_ms',5001)]:
            s=dict(self.s);s[key]=value
            self.assertFalse(self.w.observe(s,107))
        self.assertFalse(self.w.observe(self.s,110))
        self.assertEqual(self.w.deadline,110)

    def test_request_and_run_have_hard_bounds(self):
        self.s['run_elapsed_ms']=0
        self.assertTrue(self.w.observe(self.s,109.999))
        self.assertLessEqual(self.w.deadline,116)
        self.assertLessEqual(self.w.deadline-109.999,6)

    def test_worker_fires_and_cancel_prevents_stop(self):
        self.w.deadline=time.monotonic()-.01
        self.w.start();self.w.join(1)
        self.assertEqual(self.calls,['stop'])
        w=RunWatchdog(time.monotonic(),{'run_id':1},lambda:self.calls.append('unwanted'))
        w.start();w.cancel();w.join(1)
        self.assertFalse(w.thread.is_alive())
        self.assertEqual(self.calls,['stop'])

if __name__=='__main__':unittest.main()

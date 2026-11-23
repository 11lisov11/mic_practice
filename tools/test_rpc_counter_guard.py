"""Offline replay, fault injection and mocked runner STOP; no bench access."""
import copy
import hashlib
import io
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_telemetry_deadline_trial as runner
from rpc_counter_guard import RpcCounterGuard

ROOT=Path(__file__).resolve().parents[1]
SOURCE=runner.p.OUT/'autonomous_before_NIS_FOC_r1'
ROWS=[json.loads(line) for line in (SOURCE/'status_samples.jsonl').read_text(encoding='utf-8').splitlines()]
SAVED=[row['response']['data'] for row in ROWS]


class Clock:
    value=0.0
    def __call__(self):return self.value
    def sleep(self,seconds):self.value+=seconds


def make_guard():
    clock=Clock()
    return RpcCounterGuard(lambda s,**kw:runner.driver.boot.decode_boot(s,runner.p.NEW,**kw),clock=clock),clock


def advance(guard,clock,s,seconds=.2):
    clock.value+=seconds
    s['mc_good_cnt']+=4
    s['uno_rx_count']+=4
    return guard.observe(s)


def qualified():
    guard,clock=make_guard();s=copy.deepcopy(SAVED[0]);assert guard.observe(s)
    for _ in range(11):assert advance(guard,clock,s)
    assert guard.ready
    return guard,clock,s


class GuardTests(unittest.TestCase):
    def test_saved_twenty_responses(self):
        guard,clock=make_guard()
        for row in ROWS:
            clock.value=row['monotonic']-ROWS[0]['monotonic']
            self.assertTrue(guard.observe(row['response']['data']),guard.failure)
        self.assertTrue(guard.ready)
        self.assertEqual(guard.baseline,dict(rpc_response_timeouts=12,rpc_send_timeouts=0))

    def test_requires_quiet_period_and_progress(self):
        guard,clock=make_guard();s=copy.deepcopy(SAVED[0])
        self.assertFalse(guard.check(s));self.assertIsNone(guard.failure)
        advance(guard,clock,s);self.assertFalse(guard.ready)
        advance(guard,clock,s,1.81);self.assertTrue(guard.ready)

    def test_old_nonzero_both_counters_allowed(self):
        guard,clock=make_guard();s=copy.deepcopy(SAVED[0]);s['rpc_send_timeouts']=7
        self.assertTrue(guard.observe(s))
        for _ in range(11):advance(guard,clock,s)
        self.assertTrue(guard.check(s))

    def test_off_only_boot_page_expiry_does_not_abort_healthy_run(self):
        guard,clock,s=qualified()
        s.update(pwm=1,state='RUN');s['native_boot']['fresh']=False
        for _ in range(51):
            clock.value+=.1;s['mc_good_cnt']+=2;s['uno_rx_count']+=2
            self.assertTrue(guard.check(s),guard.failure)
        # A frozen boot page never substitutes for the live native link.
        s['mc_age_ms']=300
        self.assertFalse(guard.check(s))
        guard,clock=make_guard()
        self.assertFalse(guard.observe(s))

    def test_new_timeouts_and_drops_are_sticky(self):
        for key in RpcCounterGuard.KEYS:
            for value in (1,13,0xffffffff):
                with self.subTest(key=key,value=value):
                    guard,clock,s=qualified();old=s[key];s[key]=value
                    self.assertNotEqual(value,old)
                    self.assertFalse(guard.check(s));s[key]=old
                    self.assertFalse(guard.check(s));self.assertIsNotNone(guard.failure)

    def test_counter_wrap_is_new_event(self):
        guard,clock=make_guard();s=copy.deepcopy(SAVED[0]);s['rpc_response_timeouts']=0xffffffff
        guard.observe(s)
        for _ in range(11):advance(guard,clock,s)
        s['rpc_response_timeouts']=0
        self.assertFalse(guard.check(s))

    def test_malformed_counters_and_stale_link(self):
        for key in RpcCounterGuard.KEYS:
            for value in (None,-1,2**32,True,12.0,'12'):
                with self.subTest(key=key,value=value):
                    guard,clock,s=qualified();s[key]=value
                    self.assertFalse(guard.check(s))
        for value in (None,-1,300,float('nan'),True):
            guard,clock,s=qualified();s['mc_age_ms']=value
            self.assertFalse(guard.check(s))

    def test_boot_and_continuity_failures(self):
        for mutation in ('linux','native','packet_crc','tick','good','stalled','host_clock'):
            with self.subTest(mutation=mutation):
                guard,clock,s=qualified()
                if mutation=='linux':s['linux_boot_id']='a'*36
                if mutation=='native':s['native_boot']['retained_sequence']+=1
                if mutation=='packet_crc':s['mc_boot_packet_hex']='00'+s['mc_boot_packet_hex'][2:]
                if mutation=='tick':guard.last_tick+=1
                if mutation=='good':s['mc_good_cnt']-=1
                if mutation=='stalled':clock.value+=.301
                if mutation=='host_clock':clock.value-=.01
                self.assertFalse(guard.check(s))

    def test_legacy_strict_and_nonrpc_guards_unchanged(self):
        trial=runner.driver.trial
        guard,clock,s=qualified();s.update(vdc=325,algorithm_selected=2,algorithm_requested=2,
            mc_fault_current_mask=0,mc_fault_occurred_mask=0,mc_fault=0,bp_fault=0)
        with patch.object(trial,'RPC_GUARD',None):self.assertFalse(trial.link_power(s))
        with patch.object(trial,'RPC_GUARD',guard):
            self.assertTrue(trial.link_power(s));self.assertTrue(trial.healthy(s))
        mutations=dict(vdc=351,mc_bad_cnt=1,mc_bad_sequence=1,mc_last_uart_error_flags=2,
            uno_rx_hw_errors=1,uno_rx_dropped=1,mc_transport_fault=1,mc_uart_error_flags=2,
            mc_bad_integrity=1,bp_temp_valid=0,bp_temp_fault=1,bp_temp_c=80,estop=1,
            algorithm_fault=1,mc_current_zero_ready=0,mc_fault_current_mask=1,
            mc_fault_occurred_mask=1,mc_fault=1,bp_fault=1)
        for key,value in mutations.items():
            with self.subTest(key=key):
                guard,clock,_=qualified();bad=copy.deepcopy(s);bad[key]=value
                with patch.object(trial,'RPC_GUARD',guard):self.assertFalse(trial.healthy(bad))
        for key,value in (('level','LOW'),('config_ok',False),('break_irq_enabled',False)):
            guard,clock,_=qualified();bad=copy.deepcopy(s);bad['mc_sd_live'][key]=value
            with patch.object(trial,'RPC_GUARD',guard):self.assertFalse(trial.healthy(bad))
        for key,value in (('algorithm_fast_cycles',4001),('algorithm_observer_cycles',85001)):
            bad=copy.deepcopy(s);bad[key]=value;self.assertFalse(trial.off_timing_ready(bad))

    def test_get_only_preflight_archive_and_failure(self):
        for mode in ('stable','increment','disconnect'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                clock=Clock();calls=0
                def fetch():
                    nonlocal calls
                    calls+=1
                    if mode=='disconnect' and calls==2:raise OSError('simulated disconnect')
                    s=copy.deepcopy(SAVED[0]);s['mc_good_cnt']+=calls*4;s['uno_rx_count']+=calls*4
                    if mode=='increment' and calls>=2:s['rpc_response_timeouts']+=1
                    return dict(ok=True,data=s)
                out=Path(temp)/'preflight'
                if mode=='stable':
                    guard=runner.prepare_rpc_guard(fetch,out,clock=clock,sleep=clock.sleep)
                    self.assertTrue(guard.ready)
                else:
                    with self.assertRaises((RuntimeError,OSError)):
                        runner.prepare_rpc_guard(fetch,out,clock=clock,sleep=clock.sleep)
                    self.assertTrue(json.loads((out/'report.json').read_text(encoding='utf-8'))['failure'])

    def test_runtime_historical_timeout_success_and_new_timeout_stop(self):
        trial=runner.driver.trial
        for scenario,key in [('stable',None),('running',RpcCounterGuard.KEYS[0]),
                             ('running',RpcCounterGuard.KEYS[1]),('before_START',RpcCounterGuard.KEYS[0])]:
            with self.subTest(scenario=scenario,key=key),tempfile.TemporaryDirectory() as temp:
                guard,clock,s=qualified();calls=[];statuses=0
                s.update(vdc=325,algorithm_selected=2,algorithm_requested=2,
                    mc_fault_current_mask=0,mc_fault_occurred_mask=0,mc_fault=0,bp_fault=0,
                    freq_cmd=5,manual_run_mode=0)
                class Opener:
                    def open(self,request,timeout=8):
                        nonlocal statuses
                        path=request.full_url.split(':8080')[-1];calls.append((request.method,path,request.data))
                        data={}
                        if path=='/api/status':
                            statuses+=1;data=copy.deepcopy(s);data['mc_good_cnt']+=statuses*4;data['uno_rx_count']+=statuses*4
                            if scenario=='before_START' and statuses==2:data[key]+=1
                            if statuses==3 and scenario!='before_START':
                                if key is not None:data[key]+=1
                                data.update(pwm=1,bp_status=0x22,run_id=1)
                            if scenario=='stable' and statuses>=4:
                                data.update(run_id=1,run_reason=1,run_elapsed_ms=5000,foc_experiment_flags=5)
                        return io.StringIO(json.dumps(dict(ok=True,data=data)))
                class Heartbeat:
                    def __init__(self,*args):pass
                    def start(self):pass
                    def stop(self):pass
                    def healthy(self):return True
                    def snapshot(self):return dict(mock=True)
                with patch.object(trial,'RPC_GUARD',guard),patch.object(trial,'TrialHeartbeat',Heartbeat), \
                     patch.object(trial.urllib.request,'build_opener',return_value=Opener()), \
                     patch.object(sys,'argv',['offline','--confirm-autonomous-powered','--outdir',str(Path(temp)/'trial')]), \
                     patch.object(trial,'ADC_record_is_new',return_value=True):
                    # Runtime post-STOP collector must see a runtime record immediately.
                    s['foc_runtime']['source']='runtime_observer'
                    with patch.object(trial,'off_timing_ready',return_value=True):rc=trial.main()
                report=json.loads((Path(temp)/'trial/report.json').read_text(encoding='utf-8'))
                self.assertEqual(rc,0 if scenario=='stable' else 1)
                self.assertEqual(report['start_commands'],0 if scenario=='before_START' else 1)
                self.assertEqual(report['clear_commands'],0)
                if scenario=='running':self.assertIn('link fault',report['error'])
                if scenario!='before_START':self.assertTrue(any(path=='/api/stop-sequence' for _,path,_ in calls))
                self.assertEqual(bool(report['rpc_guard']['failure']),scenario!='stable')
                self.assertEqual(sum(path=='/api/start-sequence' for _,path,_ in calls),0 if scenario=='before_START' else 1)


def main():
    out=ROOT/'artifacts/live_bench_20261116/rpc_counter_guard_r3'
    out.mkdir(exist_ok=False)
    hashes=json.loads((runner.p.OUT/'preserved_capture_hashes.json').read_text(encoding='utf-8'))
    for path in SOURCE.rglob('*'):
        if path.is_file():hashes[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    def verify():
        for path,digest in hashes.items():
            assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
    verify()
    source_hashes=json.loads((runner.p.OUT/'source_hashes.json').read_text(encoding='utf-8'))
    def verify_firmware():
        for path,digest in source_hashes.items():
            assert hashlib.sha256((runner.p.OUT/path).read_bytes()).hexdigest()==digest,path
    verify_firmware()
    stream=io.StringIO()
    # Even an accidental live connection during imports/tested paths must fail.
    with patch.object(socket.socket,'connect',side_effect=AssertionError('Offline test forbids network')):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
    verify()
    verify_firmware()
    (out/'tests.log').write_text(stream.getvalue(),encoding='utf-8')
    report=dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),
        errors=len(result.errors),saved_statuses_replayed=len(ROWS),preserved_files_verified=len(hashes),
        release_sources_verified=len(source_hashes),
        live_network_access=False,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,
        thresholds_changed=False,firmware_changed=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(stream.getvalue());print(json.dumps(report))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())

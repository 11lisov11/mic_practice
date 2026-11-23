"""Run real trial orchestration against an intentionally delayed fake HTTP ACK."""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import run_as5600_bounded_5hz as trial
import prepare_as5600_bounded_io as package

def main():
    r=json.loads((package.BASE/'legacy_powered_5hz_r1/report.json').read_text())
    before=copy.deepcopy(r['before']);before.update(fw_build=2026102516,run_id=7,enc_diag_mode=4,enc_diag_thread_priority=4)
    active=next(copy.deepcopy(x['status']) for x in reversed(r['samples']) if x['status']['pwm']==1 and x['status'].get('mc_frequency_reference_hz')==5)
    active.update(fw_build=2026102516,run_id=8,enc_diag_mode=4,enc_diag_thread_priority=4)
    shared={'began':None,'starts':0,'clears':0,'stops':0,'armed':False,'response_done':False}
    lock=threading.Lock()
    class FakeHmi:
        base='http://fake';token='not-a-real-token'
        def __init__(self,*args):pass
        def close(self):pass
        def command(self,c):
            if c=='CLEAR':shared['clears']+=1;raise AssertionError('No automatic CLEAR')
            if c=='SET FREQ 5':before['freq_cmd']=5
        def post(self,path,body,label):
            if path=='/api/hv-arm':shared['armed']=True;return {'ok':True}
            assert path=='/api/start-sequence' and body=={'runlimit_s':5.0}
            with lock:shared['starts']+=1;shared['began']=time.monotonic()
            time.sleep(6.2) # Deliberately later than MCU's5s completion.
            shared['response_done']=True
            return {'ok':True,'status':dict(active)} # even an obsolete active HTTP snapshot
        def status(self):
            began=shared['began']
            if began is None:return copy.deepcopy(before)
            elapsed=time.monotonic()-began
            if elapsed<5:
                s=copy.deepcopy(active);s['run_elapsed_ms']=int(elapsed*1000)
                s['mc_current_window_tick_ms']=int(elapsed*5)*200+5000
                s['mc_current_window_ms']=200
                return s
            s=copy.deepcopy(before)
            s.update(run_id=8,run_start_ms=10000,run_stop_ms=15000,run_limit_ms=5000,
                run_elapsed_ms=5000,run_reason=1,hmi_hv_armed=int(shared['armed']))
            return s
        def fail_safe_stop(self):shared['stops']+=1;shared['armed']=False;return 200,{'ok':True}
    @contextmanager
    def heartbeat(h):yield {'errors':[]}
    trial.WifiHmi=FakeHmi;trial.read_token=lambda path:'fake';trial.operator_keepalive=heartbeat
    with tempfile.TemporaryDirectory() as d:
        args=sys.argv;sys.argv=['runner','--confirm-powered-ready','--outdir',str(Path(d)/'run')]
        try:code=trial.main()
        finally:sys.argv=args
        result=json.loads((Path(d)/'run/report.json').read_text())
        assert code==0 and result['passed'] and shared['starts']==1 and shared['clears']==0
        assert result['completion']['run_elapsed_ms']==5000 and result['completion']['hmi_hv_armed']==1
        assert 'host_backup_stop' not in result and shared['response_done']
        assert result['outputs_off_confirmed'] and result['final_status']['hmi_hv_armed']==0
        result={'passed':True,'fake_HTTP_delay_s':6.2,'MCU_completion_ms':5000,'one_start':True,
            'no_clear':True,'no_hold_after_HTTP_response':True,'ARM1_at_physical_OFF_handled':True,
            'actual_trial_script_executed':True,'hardware_commands':0}
        (package.OUT/'runner-selftest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()

"""One visual repeat after a completed trial, retaining same-boot OFF64 proof.

No CLEAR/reset/flash or firmware changes. Not a fresh-ADC qualification trial.
All live motor guards and independent five-second RUNLIMIT remain in force.
"""
import argparse,hashlib,json,queue,threading,time,urllib.request
from pathlib import Path
import run_observer_input_epoch_runtime as motor
from run_foc_boot_capture_trial import decode_boot
from rpc_counter_guard import RpcCounterGuard
from foc_trial_supervision import TrialHeartbeat

ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026111609,2026111606)
motor.PAIR=PAIR


def saved_proof(folder):
    folder=Path(folder)
    for name,digest in json.loads((folder/'saved_files_sha256.json').read_text(encoding='utf8')).items():
        target=(folder/name).resolve();assert target.parent==folder.resolve()
        assert hashlib.sha256(target.read_bytes()).hexdigest()==digest,name
    r=json.loads((folder/'report.json').read_text(encoding='utf8'))
    before=json.loads((folder/'before_START.json').read_text(encoding='utf8'))
    after=json.loads((folder/'final_status.json').read_text(encoding='utf8'))
    assert r['passed'] and r['completed_5s'] and r['Uno_limit_done']
    assert r['start_commands']==1 and r['prior_SD_record_retained']
    assert r['runtime_record_received'] and r['ADC_record_received']
    assert r['boot_evidence_audit']['passed'] and r['boot_evidence_audit']['native_identity_unchanged']
    assert motor.off_timing_ready(before),'Original OFF64/4000 qualification missing'
    a=decode_boot(before,PAIR);b=decode_boot(after,PAIR,require_fresh=False)
    assert a['identity']==b['identity'] and a['Linux_boot_id']==b['Linux_boot_id']
    assert after['run_elapsed_ms']==5000 and after['run_reason']==1 and motor.off(after)
    assert all(after[k]==0 for k in ('algorithm_fault','mc_fault_current_mask','mc_fault_occurred_mask'))
    assert after['foc_runtime']['first_fault'] is None and after['foc_runtime']['max_result_age_us']<2000
    return dict(before=before,after=after,boot=a,previous=folder.as_posix())


def admission(s,proof):
    """Reuse a valid boot-only qualification, never substitute it for live guards."""
    assert motor.off_timing_ready(proof['before']),'Saved OFF64/4000 qualification invalid'
    assert motor.off(s) and motor.healthy(s),'Live protection/profile/power/RPC not ready'
    assert s['hmi_hv_armed']==0 and s['mc_current_zero_stable']==3
    assert s['run_id']==proof['after']['run_id'] and s['run_start_ms']==proof['after']['run_start_ms'],'Previous run changed'
    assert s['run_elapsed_ms']==5000 and s['run_reason']==1 and s['freq_cmd'] in (0,5)
    assert s['manual_run_mode']==0,'Manual/unbounded mode is not permitted'
    b=decode_boot(s,PAIR)
    assert b['identity']==proof['boot']['identity'] and b['Linux_boot_id']==proof['boot']['Linux_boot_id'],'Boot changed'
    assert b['native_tick_ms']>=decode_boot(proof['after'],PAIR,require_fresh=False)['native_tick_ms']
    assert s['algorithm_profile_crc']==proof['before']['algorithm_profile_crc']
    assert s['foc_timing_cases']==64 and s['foc_experiment_flags']&1 and s['foc_timing_fault']==0
    perf=s['foc_runtime'];assert perf['source']=='runtime_observer' and perf['first_fault'] is None
    assert perf['meter_errors']==0 and perf['max_result_age_us']<2000
    assert 0<s['algorithm_fast_cycles']<5312,'Existing full RUN-path deadline exceeded'
    assert s['mc_break_wave_hex']==proof['after']['mc_break_wave_hex'],'SD evidence changed'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--confirm-visual-repeat',action='store_true',required=True)
    ap.add_argument('--previous',type=Path,required=True);ap.add_argument('--outdir',type=Path,required=True)
    a=ap.parse_args();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    proof=saved_proof(a.previous)
    guard=RpcCounterGuard(lambda s,**kw:decode_boot(s,PAIR,**kw));motor.RPC_GUARD=guard
    key=(ROOT/'.unoq_ssh/control_token').read_text().strip();op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    report=dict(passed=False,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,frequency_hz=5,runlimit_ms=5000,
        same_boot_OFF64_proof=proof['previous'],OFF_fast_cycles=proof['before']['algorithm_fast_cycles'],
        limits_unchanged=True,fresh_ADC_required=False,physical_rotation_verified=False)
    results=queue.Queue();heart=None;timer=None;started=None
    def save():
        report['RPC_guard']=guard.snapshot()
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    def request(path,body=None,timeout=8):
        assert body is None or path in ('/api/operator-heartbeat','/api/hv-arm','/api/start-sequence','/api/stop-sequence') or (path=='/api/cmd' and body=={'cmd':'SET FREQ 5'})
        q=urllib.request.Request('http://192.168.1.138:8080'+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json','X-UNOQ-Control-Token':key},method='GET' if body is None else 'POST')
        with op.open(q,timeout=timeout) as f:r=json.load(f)
        assert r.get('ok'),r.get('error');return r
    def status(label):
        s=request('/api/status')['data']
        with (out/'status.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(dict(label=label,status=s),ensure_ascii=False)+'\n')
        assert guard.observe(s),guard.failure
        return s
    def stop(label):
        try:results.put((label,request('/api/stop-sequence',{'emergency':False},timeout=10)))
        except Exception as e:results.put((label,dict(error=str(e))))
    try:
        for _ in range(12):
            s=status('preflight');assert motor.off(s),'Outputs must stay OFF during RPC baseline'
            if guard.ready:
                admission(s,proof);break
            time.sleep(.2)
        assert guard.ready,'RPC quiet baseline not ready'
        report['frequency_configuration']=request('/api/cmd',{'cmd':'SET FREQ 5'})
        s=status('configured');admission(s,proof);assert s['freq_cmd']==5
        (out/'before_START.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf8')
        next_id=s['run_id']+1
        heart=TrialHeartbeat(request);heart.start()
        report['ARM']=1;save();request('/api/hv-arm',{'action':'arm','confirm':'ARM 310V'})
        def start():
            try:results.put(('start_response',request('/api/start-sequence',{'manual':False,'runlimit_s':5.0},timeout=12)))
            except Exception as e:results.put(('start_error',str(e)))
        report['START']=1;save();began=time.monotonic()
        timer=threading.Timer(12,lambda:stop('host_backup_STOP'));timer.daemon=True;timer.start()
        started=threading.Thread(target=start,daemon=True);started.start();seen=False
        while time.monotonic()-began<16:
            s=status('running')
            assert heart.healthy() and motor.healthy(s),'Live motor/heartbeat protection failed'
            assert s['run_id'] in (next_id-1,next_id),'Unexpected run ID'
            if s['pwm']==1:seen=True
            if s['pwm']==0 and s['run_id']==next_id:
                assert motor.off(s) and s['run_reason']==1 and 5000<=s['run_elapsed_ms']<=5100,'Early/abnormal stop'
                report.update(passed=True,auto_stop_ms=s['run_elapsed_ms'],run_id=next_id,seen_PWM=seen)
                (out/'autostop.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf8');break
            time.sleep(.08)
        assert report['passed'],'No five-second stop acknowledgement'
    except Exception as e:report['error']=str(e)
    finally:
        if report['ARM'] or report['START']:stop('final_STOP')
        if timer:timer.cancel()
        if heart:heart.stop();report['heartbeat']=heart.snapshot()
        if started:started.join(timeout=1)
        while not results.empty():
            k,v=results.get();report[k]=v
        try:
            final=status('final');assert motor.off(final),'Outputs OFF not confirmed'
            (out/'final_status.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf8')
            assert final['mc_break_wave_hex']==proof['after']['mc_break_wave_hex'],'Prior SD changed'
            report['prior_SD_retained']=True
            report['ADC_record_is_new']=final.get('mc_adc_peak_hex')!=proof['after'].get('mc_adc_peak_hex')
            report['observer_record_is_new']=final.get('mc_observer_trace_hex')!=proof['after'].get('mc_observer_trace_hex')
        except Exception as e:report['passed']=False;report['final_status_error']=str(e)
        save();motor.RPC_GUARD=None
        (out/'saved_files_sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='saved_files_sha256.json'},indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('passed','START','CLEAR','auto_stop_ms','run_id','prior_SD_retained','error','final_status_error')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

"""One explicitly authorized CLEAR on1605/1606, J1 OFF. Never START/ARM/RESET."""
import argparse,json,time,urllib.request
from pathlib import Path
import prepare_clear_recovery as p
from rpc_counter_guard import RpcCounterGuard
from run_foc_boot_capture_trial import decode_boot


def disarmed(s):
    return (s.get('state')=='SAFE' and all(s.get(k)==0 for k in ('pwm','run_id','hmi_hv_armed'))
            and not s.get('bp_status',0x22)&0x22)


def preflight(s):
    assert (s.get('fw_build'),s.get('mc_fw_build'))==p.NEW
    assert disarmed(s) and 0<=s.get('vdc',999)<=20 and 0<=s.get('bp_vdc',999)<=20
    assert all(s.get(k)==0 for k in ('precharge','pfc','brake','bp_ext','algorithm_fault',
        'mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence',
        'uno_rx_hw_errors','uno_rx_dropped'))
    assert s.get('mc_transport_fault') in (0,7),'Unexpected transport cause; no CLEAR'
    sd=s.get('mc_sd_live') or {};assert sd.get('level')=='HIGH' and sd.get('config_ok') is True
    assert s.get('clear_recovery',{}).get('available') is False,'First CLEAR record already exists; no blind repeat'
    decode_boot(s,p.NEW)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirmed-one-clear-no-start',action='store_true',required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    a=parser.parse_args();out=a.outdir.resolve();assert p.OUT in out.parents
    out.mkdir(exist_ok=False)
    report=dict(passed=False,CLEAR=0,START=0,ARM=0,RESET=0,flash=0,SWD=0,
        operator_state='J1 OFF, both boards PCUSB, J4 ON; wiring unchanged',thresholds_changed=False)
    def save(name,obj):p.write(out/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    def checkpoint():save('report.json',report)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    def request(path,body=None):
        assert body is None or path=='/api/cmd' and body=={'cmd':'CLEAR'} and report['CLEAR']==1
        q=urllib.request.Request('http://127.0.0.1:18080'+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},
            method='GET' if body is None else 'POST')
        with opener.open(q,timeout=8) as response:r=json.load(response)
        assert r.get('ok') is True,r.get('error');return r
    rpc=RpcCounterGuard(lambda s,**kw:decode_boot(s,p.NEW,**kw))
    def status(label):
        r=request('/api/status');s=r['data']
        with (out/'status_samples.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(label=label,monotonic=time.monotonic(),response=r),ensure_ascii=False)+'\n')
        return s
    checkpoint();before=None;rows=[]
    preserved=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
    for folder in ('hardware_install_r1','post_install_idle_r1'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=p.sha(f)
    try:
        for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
        save('preserved_before_sha256.json',preserved)
        for _ in range(8):
            before=status('before_CLEAR');preflight(before)
            assert rpc.observe(before),rpc.failure
            if rpc.ready:break
            time.sleep(.2)
        assert rpc.ready,'RPC did not qualify; no CLEAR'
        save('before_CLEAR.json',before)
        wave=before.get('mc_break_wave_hex','-')
        if wave not in ('','-'):(out/'SD_before.bin').write_bytes(bytes.fromhex(wave))
        for name,path in (('SD_before.json','/api/break-snapshot'),('SD_trace_before.json','/api/bkin-trace')):
            save(name,request(path))
        # Durable intent precedes the ONLY POST. Never retry on any failure.
        report['CLEAR']=1;checkpoint()
        save('CLEAR_response.json',request('/api/cmd',{'cmd':'CLEAR'}))
        report['CLEAR_HTTP_acknowledged']=True;checkpoint()
        for _ in range(16):
            s=status('after_one_CLEAR');rows.append(s)
            assert disarmed(s) and 0<=s['vdc']<=20,'Outputs/bus changed; no further commands'
            assert rpc.check(s),rpc.failure
            assert s.get('mc_break_wave_hex','-')==wave,'Frozen first Break changed'
            time.sleep(.35)
        last=rows[-1];save('after_CLEAR.json',last)
        diag=last.get('clear_recovery') or {};save('CLEAR_diagnostic.json',diag)
        stable=rows[-4:]
        break_ok=all(s['mc_sd_live'].get('level')=='HIGH' and s['mc_sd_live'].get('config_ok') is True
            and s['mc_sd_live'].get('break_irq_enabled') is True for s in stable)
        transport_ok=all(s.get(k)==0 for s in stable for k in ('mc_transport_fault','mc_bad_cnt',
            'mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_last_uart_error_flags',
            'uno_rx_hw_errors','uno_rx_dropped')) and rpc.ready and rpc.failure is None
        mc_ok=all(s.get(k)==0 for s in stable for k in ('mc_fault','bp_fault','mc_fault_current_mask',
            'mc_fault_occurred_mask','estop','algorithm_fault'))
        report.update(diagnostic_received=bool(diag.get('available')),diagnostic=diag,
            Break_restored=break_ok,transport_restored=transport_ok,MCSDK_ready=mc_ok,
            passed=break_ok and transport_ok and mc_ok and diag.get('available') is True,
            expected_under_voltage_block=(diag.get('result_code')==4
                and diag.get('current_faults_at_attempt')==4 and last['vdc']<=20),
            SD_first_record_unchanged=True,samples=len(rows),rpc_guard=rpc.snapshot(),
            final_SD=last['mc_sd_live'],final_faults={k:last.get(k) for k in ('mc_fault','bp_fault',
                'mc_fault_current_mask','mc_fault_occurred_mask','mc_transport_fault','mc_bad_cnt')},
            zero_ready=last.get('mc_current_zero_ready'),full_start_readiness_confirmed=False)
    except Exception as error:report['error']=repr(error)
    finally:
        try:
            last=status('final_observation');save('final_status.json',dict(ok=True,data=last))
            report['final_outputs_off']=disarmed(last)
            for name,path in (('SD_after.json','/api/break-snapshot'),('SD_trace_after.json','/api/bkin-trace'),('repeat_break_after.json','/api/repeat-break')):
                save(name,request(path))
            for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
            report['preserved_files_verified']=len(preserved)
        except Exception as error:report['collection_error']=repr(error)
        report['rpc_guard']=rpc.snapshot();checkpoint()
        save('saved_files_sha256.json',{f.name:p.sha(f) for f in out.iterdir() if f.is_file()})
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

"""One authorized CLEAR after Uno-only recovery; archive and qualify live counters.

No RUN/ARM/reset/flash; retained fault counters are the subject of this CLEAR,
not motor admission. Any NEW counter change fails before the only POST.
"""
import json,time,urllib.request,urllib.error
import prepare_observer_current_window as p
from rpc_counter_guard import RpcCounterGuard
from run_foc_boot_capture_trial import decode_boot
OUT=p.OUT/'one_CLEAR_after_RPC_recovery_r1'
KEYS=('mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_last_bad_reason',
      'mc_transport_fault','uno_rx_hw_errors','uno_rx_dropped')
def off(s):
    assert (s['fw_build'],s['mc_fw_build'])==p.NEW
    assert s['state']=='SAFE' and all(s[k]==0 for k in ('pwm','run_id','hmi_hv_armed','precharge','pfc','brake','bp_ext'))
    assert not s['bp_status']&0x22 and 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20
    assert 0<=s['mc_age_ms']<300
    assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['config_ok']
    assert s['mc_sd_live']['break_irq_enabled']
    assert s['algorithm_fault']==0 and s['mc_current_zero_ready']==1
    assert all(s[k]==0 for k in ('mc_uart_error_flags','mc_last_uart_error_flags','uno_rx_hw_errors','uno_rx_dropped'))
    assert s['mc_transport_fault'] in (0,7)
    assert s['mc_fault_current_mask'] in (0,4) and s['mc_fault_occurred_mask'] in (0,4)
def main():
    prior=p.OUT/'one_CLEAR_idle_r1'
    assert json.loads(p.read(prior/'report.json'))['CLEAR']==0
    assert not any(f.name=='CLEAR_response.json' for f in prior.iterdir()),'CLEAR may already have been sent'
    OUT.mkdir(exist_ok=False)
    r=dict(passed=False,CLEAR=0,START=0,ARM=0,RESET=0,flash=0,
        operator_authorized_one_CLEAR=True,Uno_only_power_cycle_confirmed=True,
        thresholds_4000_2ms_unchanged=True)
    def save(name,obj):p.write(OUT/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    def checkpoint():save('report.json',r)
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path,body=None):
        assert body is None or path=='/api/cmd' and body=={'cmd':'CLEAR'} and r['CLEAR']==1
        q=urllib.request.Request('http://127.0.0.1:18080'+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'X-UNOQ-Control-Token':token,'Content-Type':'application/json'},
            method='GET' if body is None else 'POST')
        with op.open(q,timeout=8) as f:d=json.load(f)
        assert d.get('ok'),d.get('error');return d
    guard=RpcCounterGuard(lambda s,**kw:decode_boot(s,p.NEW,**kw))
    def status(label):
        s=request('/api/status')['data']
        with (OUT/'status.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(dict(label=label,status=s),ensure_ascii=False)+'\n')
        assert guard.observe(s),guard.failure
        off(s);return s
    preserved=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
    for folder in ('hardware_install_r1','post_install_idle_r1','installation_verified_r1','one_CLEAR_idle_r1'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=p.sha(f)
    rows=[];checkpoint()
    try:
        for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
        save('preserved_before_sha256.json',preserved)
        baseline=None
        for i in range(10):
            s=status('quiet_before_CLEAR')
            counters={k:s[k] for k in KEYS}
            if baseline is None:baseline=counters
            assert counters==baseline,'New UART errors during quiet baseline; no CLEAR'
            assert s.get('clear_recovery',{}).get('available') is False,'Prior CLEAR attempt; no repeat'
            time.sleep(.3)
        assert guard.ready and guard.failure is None
        save('before_CLEAR.json',s);r['retained_counters_before']=baseline
        wave=s.get('mc_break_wave_hex','-')
        for key,name in (('mc_break_wave_hex','SD_before.bin'),('mc_observer_trace_hex','observer_before.bin'),('mc_adc_peak_hex','ADC_before.bin')):
            if s.get(key,'-') not in ('','-'):(OUT/name).write_bytes(bytes.fromhex(s[key]))
        save('SD_before.json',request('/api/break-snapshot'));save('SD_trace_before.json',request('/api/bkin-trace'))
        # The durable counter is set BEFORE the one non-retrying POST.
        r['CLEAR']=1;checkpoint();save('CLEAR_response.json',request('/api/cmd',{'cmd':'CLEAR'}))
        r['CLEAR_HTTP_acknowledged']=True;checkpoint()
        for _ in range(16):
            s=status('after_one_CLEAR');rows.append(s)
            assert s.get('mc_break_wave_hex','-')==wave,'Old SD record changed'
            time.sleep(.3)
        save('after_CLEAR.json',s);diag=s.get('clear_recovery') or {};save('CLEAR_diagnostic.json',diag)
        stable=rows[-5:]
        uart_ok=all(x[k]==0 for x in stable for k in ('mc_transport_fault','mc_bad_cnt','mc_bad_integrity','mc_bad_sequence',
            'mc_uart_error_flags','mc_last_uart_error_flags','uno_rx_hw_errors','uno_rx_dropped'))
        break_ok=all(x['mc_sd_live']['break_irq_enabled'] and x['mc_sd_live']['level']=='HIGH' and x['mc_sd_live']['config_ok'] for x in stable)
        mc_ok=all(x[k]==0 for x in stable for k in ('mc_fault','bp_fault','mc_fault_current_mask','mc_fault_occurred_mask','estop','algorithm_fault'))
        r.update(UART_latch_cleared=uart_ok,Break_restored=break_ok,MCSDK_faults_cleared=mc_ok,
            diagnostic=diag,SD_record_unchanged=True,passed=uart_ok and break_ok and mc_ok and diag.get('result_code')==1,
            remaining_faults={k:s[k] for k in ('mc_fault','mc_fault_current_mask','mc_fault_occurred_mask')},
            powered_start_readiness_evaluated=False,operator_must_keep_J1_OFF=True)
    except Exception as e:r['error']=repr(e)
    finally:
        try:
            s=status('final_observation');save('final_status.json',s)
            r['outputs_off_confirmed']=s['pwm']==0 and not s['bp_status']&0x22
            for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
            r['preserved_files_verified']=len(preserved)
        except Exception as e:r['collection_error']=repr(e)
        r['rpc_guard']=guard.snapshot();checkpoint()
        save('saved_files_sha256.json',{f.name:p.sha(f) for f in OUT.iterdir() if f.is_file() and f.name!='saved_files_sha256.json'})
    print(json.dumps({k:r.get(k) for k in ('passed','CLEAR','UART_latch_cleared','Break_restored','MCSDK_faults_cleared','remaining_faults','error','collection_error')}))
    return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

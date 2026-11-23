"""GET-only powerbank boot/zero/observer-recorder verification; no commands."""
import json
import time
import urllib.error
import urllib.request
import prepare_observer_input_epoch as p


def main():
    out=p.OUT/'autonomous_before_FOC_r1';out.mkdir(exist_ok=False)
    report=dict(passed=False,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,SWD=0,
        operator_state='Both powerbanks, PC/Saleae detached,15VON,J1OFF; no START/RESET',
        observation_only=True)
    def save(name,obj):p.write(out/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    def get(path,as_json=True):
        req=urllib.request.Request('http://192.168.1.138:8080'+path,
            headers={'X-UNOQ-Control-Token':token},method='GET')
        with op.open(req,timeout=8) as r:return json.load(r) if as_json else r.read()
    try:
        attempts=[];deadline=time.monotonic()+45
        while True:
            try:
                d=get('/api/status');assert d.get('ok') and isinstance(d.get('data'),dict)
                break
            except Exception as error:
                attempts.append(dict(error=repr(error),at_monotonic=time.monotonic()))
                if time.monotonic()>=deadline:raise
                time.sleep(1)
        save('startup_attempts.json',attempts)
        rows=[];start=time.monotonic()
        for i in range(18):
            if i:d=get('/api/status')
            assert d['ok'];s=d['data'];rows.append(s)
            with (out/'status_samples.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(dict(monotonic=time.monotonic(),response=d),ensure_ascii=False)+'\n')
            assert (s['fw_build'],s['mc_fw_build'])==p.NEW
            assert s['state']=='SAFE' and s['pwm']==s['run_id']==s['hmi_hv_armed']==0
            assert not s['bp_status']&0x22 and 0<=s['vdc']<=20 and 0<=s['mc_age_ms']<300
            assert s['mc_current_zero_ready']==1
            assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011
            assert s['foc_experiment_flags']==1 and s['foc_timing_cases']==64 and s['foc_timing_fault']==0
            for k in ('mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_last_uart_error_flags',
                      'rpc_response_timeouts','rpc_send_timeouts'):
                assert s[k]==0,(k,s[k])
            assert s['observer_trace']==dict(available=False,reason='not_received')
            assert s['mc_observer_trace_hex']=='-' and s['mc_observer_trace_complete']==0
            assert s['mc_observer_trace_good']==s['mc_observer_trace_bad']==0
            assert s['repeat_break']['available'] and s['repeat_break']['fresh']
            assert s['native_boot']['available'] and s['native_boot']['fresh']
            assert s['mc_sd_live']['available'] and s['mc_sd_live']['config_ok']
            cpu=s['foc_runtime']
            assert cpu['source']=='OFF_synthetic_CPU_probe' and cpu['observer_steps']==64
            assert cpu['meter_errors']==0 and cpu['first_fault'] is None
            time.sleep(.4)
        assert rows[-1]['mc_good_cnt']>rows[0]['mc_good_cnt']
        assert len({s['mc_bad_cnt'] for s in rows})==1,'new rejected frames'
        assert len({s['linux_boot_id'] for s in rows})==1,'Linux reboot during observation'
        assert len({s['native_boot']['early_record_crc'] for s in rows})==1,'native epoch changed'
        assert rows[-1]['native_boot']['native_tick_ms']>rows[0]['native_boot']['native_tick_ms']
        save('final_status.json',dict(ok=True,data=s))
        for name,path in [('SD_snapshots.json','/api/break-snapshot'),('SD_trace.json','/api/bkin-trace')]:
            save(name,get(path))
        (out/'HMI_logs.txt').write_bytes(get('/api/logs',False))
        old=json.loads(p.read(p.OUT/'post_install_idle_r2/final_status.json'))['data']
        preserved=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
        for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
        zero=s.get('shunt_currents',{})
        report.update(passed=True,pair=list(p.NEW),samples=len(rows),duration_s=time.monotonic()-start,
            boot_changed_since_PC=s['linux_boot_id']!=old['linux_boot_id'],linux_boot_id=s['linux_boot_id'],
            native_boot=s['native_boot'],zero_ready=True,zero_attempts=s.get('mc_current_zero_attempts'),
            current_telemetry=zero,good_frame_increase=rows[-1]['mc_good_cnt']-rows[0]['mc_good_cnt'],
            bad_count=s['mc_bad_cnt'],transport_fault=s['mc_transport_fault'],
            SD=s['mc_sd_live'],active_fault_mask=s['mc_fault_current_mask'],saved_fault_mask=s['mc_fault_occurred_mask'],
            observer_capture_configured=True,observer_record_not_yet_produced=True,
            recorder_RAM_independently_read_this_boot=False,
            recorder_readiness_evidence='Previously verified installed image and empty recorder RAM; fresh boot,run_id0,no observer record,receiver counters0.',
            OFF_CPU=s['foc_runtime'],repeat_break=s['repeat_break'],preserved_files_verified=len(preserved),
            no_active_SD_block=s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled'],
            hardware_FOC_accuracy_validated=False)
    except Exception as error:report['error']=repr(error)
    save('report.json',report)
    save('saved_files_sha256.json',{f.name:p.sha(f) for f in out.iterdir() if f.is_file()})
    print(json.dumps({k:report.get(k) for k in ('passed','pair','samples','boot_changed_since_PC','zero_ready',
        'zero_attempts','good_frame_increase','bad_count','transport_fault','SD','active_fault_mask','saved_fault_mask',
        'observer_capture_configured','error')},ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

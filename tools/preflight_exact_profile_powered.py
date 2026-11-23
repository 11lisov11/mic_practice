"""GET-only powered readiness evidence for1503/1504; no CLEAR/START/configuration."""
import json,time,urllib.request
import prepare_exact_profile_budget as p


def main():
    out=p.OUT/'powered_preflight_FOC_r1';out.mkdir(exist_ok=False)
    report=dict(passed=False,GET_only=True,START=0,CLEAR=0,ARM=0,RESET=0,flash=0)
    def save(name,obj):p.write(out/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    def get(path):
        q=urllib.request.Request('http://192.168.1.138:8080'+path,
            headers={'X-UNOQ-Control-Token':token},method='GET')
        with op.open(q,timeout=8) as response:return json.load(response)
    try:
        rows=[]
        for i in range(6):
            response=get('/api/status');assert response['ok'];s=response['data'];rows.append(s)
            save(f'status_{i}.json',response)
            assert (s['fw_build'],s['mc_fw_build'])==p.NEW
            assert s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==s['run_id']==0
            time.sleep(.2)
        save('final_status.json',response)
        for name,path in [('SD_trace.json','/api/bkin-trace'),('SD_snapshots.json','/api/break-snapshot'),
                          ('repeat_break.json','/api/repeat-break')]:save(name,get(path))
        wave=s.get('mc_break_wave_hex','-')
        if wave not in ('','-'):(out/'SD_first_before.bin').write_bytes(bytes.fromhex(wave))
        checks=dict(pair=True,outputs_OFF=True,
            powered_bus=all(250<=s['vdc']<=350 for s in rows),
            link_fresh=all(0<=s['mc_age_ms']<300 for s in rows) and rows[-1]['mc_good_cnt']>rows[0]['mc_good_cnt'],
            UART_RPC_clean=all(s.get(k)==0 for s in rows for k in ('mc_bad_cnt','mc_bad_integrity',
                'mc_bad_sequence','mc_uart_error_flags','mc_last_uart_error_flags','mc_transport_fault',
                'rpc_response_timeouts','rpc_send_timeouts','uno_rx_hw_errors','uno_rx_dropped')),
            no_reboot=len({s['native_boot']['early_record_crc'] for s in rows})==1
                and len({s['linux_boot_id'] for s in rows})==1,
            autonull=all(s['mc_current_zero_ready']==1 for s in rows),
            CPU=all(s['foc_timing_cases']==64 and s['foc_timing_fault']==0
                and 0<s['algorithm_fast_cycles']<=4000 for s in rows),
            SD_HIGH=all(s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['config_ok'] for s in rows),
            break_IRQ=all(s['mc_sd_live']['break_irq_enabled'] for s in rows),
            fault_masks_clear=all(s[k]==0 for s in rows for k in ('mc_fault_current_mask',
                'mc_fault_occurred_mask','mc_fault','bp_fault','estop','algorithm_fault')))
        preserved=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
        for rel,digest in preserved.items():assert p.sha(p.ROOT/rel)==digest,rel
        report.update(passed=all(checks.values()),checks=checks,vdc=s['vdc'],
            selected_algorithm=s['algorithm_selected'],algorithm_profile_crc=s['algorithm_profile_crc'],
            fast_cycles=s['algorithm_fast_cycles'],observer_cycles=s['algorithm_observer_cycles'],
            zero_ready=s['mc_current_zero_ready'],SD=s['mc_sd_live'],
            active_fault_mask=s['mc_fault_current_mask'],saved_fault_mask=s['mc_fault_occurred_mask'],
            mc_fault=s['mc_fault'],bp_fault=s['bp_fault'],fault_reason=s.get('mc_fault_reason'),
            bad_frames=s['mc_bad_cnt'],UART_flags=s['mc_last_uart_error_flags'],
            transport=s['mc_transport_fault'],wave_saved=wave not in ('','-'),
            preserved_files_verified=len(preserved),thresholds_changed=False,
            first_snapshot=next((v for v in s.get('mc_break_snapshots',[]) if v.get('kind')=='first_since_boot'),None))
    except Exception as exc:report['error']=repr(exc)
    save('report.json',report)
    save('saved_files_sha256.json',{f.name:p.sha(f) for f in out.iterdir() if f.is_file()})
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':main()

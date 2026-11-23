"""Read-only target OFF timing and transport qualification for installed1801/1802."""
import json,struct,subprocess,time,urllib.request
from elftools.elf.elffile import ELFFile
import prepare_exact_nis_input_release as p
from install_bkin_boot_armed_pair import PROGRAMMER,STLINK_SERIAL
from probe_native_programming_state import inspect_layout
from rpc_counter_guard import RpcCounterGuard
from run_foc_boot_capture_trial import decode_boot


def main():
    out=p.OUT/'post_install_idle_r1';out.mkdir(exist_ok=False)
    r=dict(passed=False,pair=list(p.NEW),START=0,CLEAR=0,ARM=0,RESET=0,
           flash=0,halt=0,OFF_only=True,thresholds_changed=False)
    def save(name,obj):p.write(out/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    def read(addr,size,name):
        path=out/(name+'.bin')
        result=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=HOTPLUG',
            'sn='+STLINK_SERIAL,'-u',hex(addr),str(size),str(path)],capture_output=True,
            text=True,encoding='utf-8',errors='replace',timeout=25)
        p.write(out/(name+'.log'),result.stdout+result.stderr);result.check_returncode()
        raw=path.read_bytes();assert len(raw)==size
        return raw
    try:
        receipt=json.loads(p.read(p.OUT/'installation_acceptance.json'))
        assert receipt['installed'] and receipt['native_readback_verified'] and receipt['uno_readback_verified']
        install=json.loads(p.read(p.OUT/'hardware_install_r1/report.json'))
        assert install['passed'] and install['calibration_unchanged']
        expected=p.OUT/f'release/nucleo_{p.NEW[1]}_expected_readback.bin'
        assert read(0x08000000,expected.stat().st_size,'independent_native_readback')==expected.read_bytes()
        r['native_readback_verified']=True
        elf=p.OUT/f'release/nucleo_{p.NEW[1]}_exact_source.elf'
        symbols,_=inspect_layout(elf)
        with elf.open('rb') as stream:
            e=ELFFile(stream)
            sizes={s.name:int(s['st_size']) for s in e.get_section_by_name('.symtab').iter_symbols()}
        rows=[]
        for i in range(2):
            bdtr=struct.unpack('<I',read(0x40012c44,4,f'BDTR_{i}'))[0]
            dier=struct.unpack('<I',read(0x40012c0c,4,f'DIER_{i}'))[0]
            gpio=struct.unpack('<I',read(0x48000010,4,f'GPIOA_IDR_{i}'))[0]
            ram=read(0x20000000,32768,f'native_SRAM_{i}')
            def val(name,fmt='<I'):return struct.unpack_from(fmt,ram,symbols[name]-0x20000000)[0]
            start=symbols['observer_trace']-0x20000000
            empty=not any(ram[start:start+sizes['observer_trace']])
            perf=struct.unpack_from('<14I',ram,symbols['ma_perf']-0x20000000)
            row=dict(tick_ms=val('uwTick'),BKE=bool(bdtr&4096),MOE=bool(bdtr&32768),
                BIE=bool(dier&128),PA6_HIGH=bool(gpio&64),running=val('running','<B'),
                fe_trial_done=val('fe_trial_done','<B'),fe_complete=val('fe_complete','<B'),
                fe_case=val('fe_case','<B'),fe_fault=val('fe_fault','<B'),
                fast_cycles=val('fe_fast_cycles'),observer_cycles=val('fe_observer_cycles'),
                OFF_source=val('ma_perf_off','<B'),observer_steps=perf[12],meter_errors=perf[13],
                observer_max_wall_us=perf[4]/170,observer_max_CPU_upper_us=perf[6]/170,
                recorder_empty=empty,recorder_bytes=sizes['observer_trace'],
                clear_record_empty=val('mic_clear_diag_ready','<B')==0)
            rows.append(row);save('native_rows.json',rows)
            assert row['BKE'] and not row['MOE'] and not row['running']
            assert not row['fe_trial_done'] and row['recorder_empty'] and row['clear_record_empty']
            assert row['fe_complete']==1 and row['fe_case']==64 and row['fe_fault']==0
            assert 0<row['fast_cycles']<=4000 and 0<row['observer_cycles']<=85000
            assert row['OFF_source']==1 and row['observer_steps']==64 and row['meter_errors']==0
            time.sleep(.3)
        assert 100<((rows[1]['tick_ms']-rows[0]['tick_ms'])&0xffffffff)<15000
        r.update(CPU_qualified=True,native_rows=rows,fast_cycles=max(x['fast_cycles'] for x in rows),
                 OFF_fast_limit_cycles=4000,estimate_age_limit_ms=2)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
        def get(path,raw=False):
            req=urllib.request.Request('http://127.0.0.1:18080'+path,
                headers={'X-UNOQ-Control-Token':token},method='GET')
            with opener.open(req,timeout=8) as response:return response.read() if raw else json.load(response)
        statuses=[];guard=RpcCounterGuard(lambda s,**kw:decode_boot(s,p.NEW,**kw))
        for i in range(12):
            d=get('/api/status');assert d['ok'];s=d['data'];statuses.append(s)
            with (out/'status_samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(d,ensure_ascii=False)+'\n')
            assert (s['fw_build'],s['mc_fw_build'])==p.NEW
            decode_boot(s,p.NEW);assert guard.observe(s),guard.failure
            assert s['state']=='SAFE' and s['pwm']==s['run_id']==s['hmi_hv_armed']==0
            assert not s['bp_status']&0x22 and 0<=s['mc_age_ms']<300
            assert 0<=s['vdc']<20 and 0<=s['bp_vdc']<20
            assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011
            assert s['foc_timing_cases']==64 and s['foc_timing_fault']==0
            assert s['algorithm_fast_cycles']==r['fast_cycles']
            assert s['mc_current_zero_ready']==1 and s['mc_current_zero_stable']==3
            for k in ('mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence','uno_rx_dropped'):
                assert s[k]==0,(k,s[k])
            assert s['observer_trace']==dict(available=False,reason='not_received')
            assert not s.get('clear_recovery',{}).get('available',False)
            sd=s['mc_sd_live'];assert sd['level']=='HIGH' and sd['config_ok'] and sd['break_irq_enabled']
            assert s['repeat_break']['available'] and s['repeat_break']['fresh']
            time.sleep(.4)
        assert statuses[-1]['mc_good_cnt']>statuses[0]['mc_good_cnt']
        for k in ('mc_bad_cnt','mc_transport_fault','uno_rx_hw_errors'):
            assert len({s[k] for s in statuses})==1,(k,'new count/latch change')
        assert guard.ready and guard.failure is None
        fresh=all(0<=s.get('mc_current_age_ms',999999)<750 and
                  0<=s.get('mc_current_detail_age_ms',999999)<1500 and
                  0<=s.get('mc_current_quality_age_ms',999999)<1500 for s in statuses)
        assert fresh,'ordinary current telemetry stale'
        save('final_status.json',dict(ok=True,data=s))
        save('SD_snapshots.json',get('/api/break-snapshot'))
        save('SD_trace.json',get('/api/bkin-trace'))
        (out/'HMI_logs.txt').write_bytes(get('/api/logs',True))
        preserved=json.loads(p.read(p.OUT/'preserved_inputs_sha256.json'))
        for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
        r.update(passed=True,samples=len(statuses),RPC_guard=guard.snapshot(),ordinary_telemetry_fresh=fresh,
            zero_ready=True,zero_spans=s.get('mc_current_zero_spans'),SD=s['mc_sd_live'],
            active_fault_mask=s['mc_fault_current_mask'],saved_fault_mask=s['mc_fault_occurred_mask'],
            transport_latch=s['mc_transport_fault'],bad_count=s['mc_bad_cnt'],
            UART_clean_for_START=s['mc_transport_fault']==0 and s['uno_rx_hw_errors']==0,
            motor_start_readiness_evaluated=False,preserved_files_verified=len(preserved),
            full_adapter_under_PWM_measured=False,
            limitation='Synthetic OFF64 DWT work with MOE=0; no PWM/run, no physical NIS improvement proved. Stable programming-time latches remain visible and are not START authorization.')
    except Exception as error:r['error']=repr(error)
    save('report.json',r)
    save('saved_files_sha256.json',{f.name:p.sha(f) for f in out.iterdir() if f.is_file()})
    print(json.dumps(r,ensure_ascii=True))
    return 0 if r['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

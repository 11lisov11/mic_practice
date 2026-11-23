"""Read installed images and frozen OFF-DWT qualification; no writes or motor commands."""
import argparse,json,struct,subprocess,time,urllib.request
from pathlib import Path
from rpc_counter_guard import RpcCounterGuard
from run_foc_boot_capture_trial import decode_boot
from elftools.elf.elffile import ELFFile
import prepare_observer_current_window as p
from install_bkin_boot_armed_pair import PROGRAMMER,STLINK_SERIAL
from probe_native_programming_state import inspect_layout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,required=True)
    out=parser.parse_args().outdir.resolve();assert p.OUT in out.parents
    out.mkdir(exist_ok=False)
    report=dict(passed=False,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,halt=0,
        observation_only=True,PWM_test=False,pair=list(p.NEW),thresholds_changed=False)
    def save(name,obj):p.write(out/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    def read(addr,size,name):
        target=out/(name+'.bin')
        result=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=HOTPLUG',
            'sn='+STLINK_SERIAL,'-u',hex(addr),str(size),str(target)],capture_output=True,
            text=True,encoding='utf-8',errors='replace',timeout=25)
        p.write(out/(name+'.log'),result.stdout+result.stderr);result.check_returncode()
        raw=target.read_bytes();assert len(raw)==size
        return raw
    try:
        install=json.loads(p.read(p.OUT/'hardware_install_r1/report.json'))
        assert install['native_readback_verified'] and install['uno_readback_verified']
        assert install['calibration_unchanged']
        expected=p.OUT/f'release/nucleo_{p.NEW[1]}_expected_readback.bin'
        actual=read(0x08000000,expected.stat().st_size,'independent_native_readback')
        assert actual==expected.read_bytes()
        report['native_readback_verified']=True
        report['native_SHA256']=p.sha(out/'independent_native_readback.bin')
        elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
        syms,_=inspect_layout(elf)
        with elf.open('rb') as f:
            e=ELFFile(f)
            sizes={s.name:int(s['st_size']) for s in e.get_section_by_name('.symtab').iter_symbols()}
        ram_rows=[]
        for i in range(2):
            bdtr=struct.unpack('<I',read(0x40012c44,4,f'BDTR_{i}'))[0]
            dier=struct.unpack('<I',read(0x40012c0c,4,f'DIER_{i}'))[0]
            gpioa=struct.unpack('<I',read(0x48000010,4,f'GPIOA_IDR_{i}'))[0]
            ram=read(0x20000000,32768,f'native_SRAM_{i}')
            def val(name,fmt='<I'):
                return struct.unpack_from(fmt,ram,syms[name]-0x20000000)[0]
            start=syms['observer_trace']-0x20000000
            trace_empty=not any(ram[start:start+sizes['observer_trace']])
            perf=struct.unpack_from('<14I',ram,syms['ma_perf']-0x20000000)
            row=dict(tick_ms=val('uwTick'),BKE=bool(bdtr&4096),MOE=bool(bdtr&32768),
                BIE=bool(dier&128),PA6_HIGH=bool(gpioa&64),running=val('running','<B'),
                run_fault=val('run_fault','<B'),fe_trial_done=val('fe_trial_done','<B'),
                fe_complete=val('fe_complete','<B'),fe_case=val('fe_case','<B'),
                fe_fault=val('fe_fault','<B'),fast_cycles=val('fe_fast_cycles'),
                observer_cycles=val('fe_observer_cycles'),OFF_source=val('ma_perf_off','<B'),
                observer_steps=perf[12],meter_errors=perf[13],
                observer_max_wall_us=perf[4]/170,observer_max_CPU_upper_us=perf[6]/170,
                recorder_empty=trace_empty,clear_record_empty=val('mic_clear_diag_ready','<B')==0)
            ram_rows.append(row);save('native_rows.json',ram_rows)
            assert row['BKE'] and not row['MOE'] and not row['running']
            assert not row['fe_trial_done'] and trace_empty and row['clear_record_empty']
            time.sleep(.3)
        assert 100<((ram_rows[1]['tick_ms']-ram_rows[0]['tick_ms'])&0xffffffff)<15000
        report['native_rows']=ram_rows
        report['CPU_qualified']=all(r['fe_complete']==1 and r['fe_case']==64 and r['fe_fault']==0
            and 0<r['fast_cycles']<=4000 and 0<r['observer_cycles']<=85000
            and r['OFF_source']==1 and r['observer_steps']==64 and r['meter_errors']==0 for r in ram_rows)
        report['fast_cycles']=max(r['fast_cycles'] for r in ram_rows)
        report['budget_cycles']=4000
        report['predecessor_OFF_cycles']=3618
        report['observer_mean16_forecast_in_OFF_probe']=True
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
        def get(path,raw=False):
            req=urllib.request.Request('http://127.0.0.1:18080'+path,
                headers={'X-UNOQ-Control-Token':token},method='GET')
            with op.open(req,timeout=8) as result:return result.read() if raw else json.load(result)
        rows=[]
        rpc=RpcCounterGuard(lambda s,**kw:decode_boot(s,p.NEW,**kw))
        for _ in range(20):
            d=get('/api/status');assert d['ok'];s=d['data'];rows.append(s)
            with (out/'status_samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(d,ensure_ascii=False)+'\n')
            assert (s['fw_build'],s['mc_fw_build'])==p.NEW
            decode_boot(s,p.NEW)
            assert rpc.observe(s),rpc.failure
            assert s.get('clear_recovery',{}).get('available') is False,'Unexpected CLEAR record after programming'
            assert s['state']=='SAFE' and s['pwm']==s['run_id']==s['hmi_hv_armed']==0
            assert not s['bp_status']&0x22 and 0<=s['mc_age_ms']<300
            assert 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20
            assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011
            time.sleep(.35)
        save('final_status.json',dict(ok=True,data=s))
        report.update(samples=len(rows),fresh_link=rows[-1]['uno_rx_count']>rows[0]['uno_rx_count'],
            new_rejected_frames=len({s['mc_bad_cnt'] for s in rows})!=1,
            bad_counts=[s['mc_bad_cnt'] for s in rows],
            integrity_counts=[s['mc_bad_integrity'] for s in rows],
            sequence_counts=[s['mc_bad_sequence'] for s in rows],
            uart_flags=[s['mc_last_uart_error_flags'] for s in rows],
            transport_latches=[s['mc_transport_fault'] for s in rows],
            SD=s['mc_sd_live'],zero_ready=s['mc_current_zero_ready'],
            active_fault_mask=s['mc_fault_current_mask'],saved_fault_mask=s['mc_fault_occurred_mask'],
            motor_start_readiness_evaluated=False,full_adapter_under_PWM_measured=False)
        save('SD_snapshots.json',get('/api/break-snapshot'))
        save('SD_trace.json',get('/api/bkin-trace'))
        (out/'HMI_logs.txt').write_bytes(get('/api/logs',True))
        report['UART_clean']=all(s[k]==0 for s in rows for k in (
            'mc_uart_error_flags','mc_last_uart_error_flags','mc_transport_fault',
            'mc_bad_integrity','mc_bad_sequence','uno_rx_hw_errors','uno_rx_dropped'))
        report['RPC_stable']=rpc.ready and rpc.failure is None
        report['rpc_guard']=rpc.snapshot()
        preserved=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
        for rel,digest in preserved.items():assert p.sha(p.ROOT/rel)==digest,rel
        report['preserved_files_verified']=len(preserved)
        report['ordinary_telemetry_fresh']=all(0<=s.get('mc_current_age_ms',999999)<750
            and 0<=s.get('mc_current_detail_age_ms',999999)<1500
            and 0<=s.get('mc_current_quality_age_ms',999999)<1500
            and s.get('mc_current_zero_ready')==1 and s.get('mc_current_zero_stable')==3 for s in rows)
        report['current_age_rows']=[{k:s.get(k) for k in ('mc_current_age_ms','mc_current_detail_age_ms',
            'mc_current_quality_age_ms','mc_current_zero_ready','mc_current_zero_stable')} for s in rows]
        report['passed']=report['CPU_qualified'] and report['fresh_link'] and not report['new_rejected_frames'] and report['ordinary_telemetry_fresh'] and report['UART_clean'] and report['RPC_stable']
        report['limitation']='Synthetic OFF-DWT kernel, MOE=0, 64x8 cases; not a motor/PWM run or a stack high-water proof.'
    except Exception as exc:report['error']=repr(exc)
    save('report.json',report)
    save('saved_files_sha256.json',{f.name:p.sha(f) for f in out.iterdir() if f.is_file()})
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

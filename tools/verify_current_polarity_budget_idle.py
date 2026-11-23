"""Independent readback, OFF CPU qualification and GET-only link observation.

No START, CLEAR, ARM, configuration, flash, halt, or reset commands.
"""
import argparse
import json
import struct
import subprocess
import time
import urllib.request
from elftools.elf.elffile import ELFFile
import prepare_current_polarity_budget as p
from install_bkin_boot_armed_pair import PROGRAMMER, STLINK_SERIAL
from probe_native_programming_state import inspect_layout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=__import__('pathlib').Path,required=True)
    out=parser.parse_args().outdir.resolve();assert p.OUT in out.parents
    out.mkdir(exist_ok=False)
    report=dict(passed=False,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,halt=0,
                observation_only=True,PWM_test=False)
    def save(name,obj):p.write(out/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    def read(addr,size,name):
        path=out/(name+'.bin')
        cmd=[str(PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+STLINK_SERIAL,
             '-u',hex(addr),str(size),str(path)]
        r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
        p.write(out/(name+'.log'),r.stdout+r.stderr);r.check_returncode()
        raw=path.read_bytes();assert len(raw)==size
        return raw
    try:
        install=json.loads(p.read(p.OUT/'hardware_install_r1/report.json'))
        assert install['passed'] and install['native_readback_verified'] and install['uno_readback_verified']
        assert install['calibration_unchanged']
        expected=p.OUT/f'release/nucleo_{p.NEW[1]}_expected_readback.bin'
        raw=read(0x08000000,expected.stat().st_size,'independent_native_readback')
        assert raw==expected.read_bytes()
        report['independent_native_readback_SHA256']=p.sha(out/'independent_native_readback.bin')
        elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
        syms,_=inspect_layout(elf)
        with elf.open('rb') as stream:
            e=ELFFile(stream)
            size={s.name:int(s['st_size']) for s in e.get_section_by_name('.symtab').iter_symbols()}
        ram_rows=[]
        for i in range(2):
            bdtr=struct.unpack('<I',read(0x40012c44,4,f'BDTR_{i}'))[0]
            dier=struct.unpack('<I',read(0x40012c0c,4,f'DIER_{i}'))[0]
            assert bdtr&4096 and not bdtr&32768
            ram=read(0x20000000,32768,f'native_SRAM_{i}')
            def val(name,fmt='<I'):
                return struct.unpack_from(fmt,ram,syms[name]-0x20000000)[0]
            start=syms['observer_trace']-0x20000000
            assert not any(ram[start:start+size['observer_trace']]),'observer trace must be empty before any RUN'
            assert val('running','<B')==val('run_fault','<B')==val('fe_trial_done','<B')==0
            assert val('fe_complete','<B')==1 and val('fe_case','<B')==64 and val('fe_fault','<B')==0
            fast=val('fe_fast_cycles');observer=val('fe_observer_cycles')
            assert 0<fast<=4000 and 0<observer<=85000
            assert val('ma_perf_off','<B')==1
            perf=struct.unpack_from('<14I',ram,syms['ma_perf']-0x20000000)
            assert perf[12]==64 and perf[13]==0
            ram_rows.append(dict(tick_ms=val('uwTick'),BKE=True,MOE=False,BIE=bool(dier&128),
                fast_kernel_cycles=fast,observer_cycles=observer,probe_cases=64,
                observer_max_wall_us=perf[4]/170,observer_max_CPU_upper_us=perf[6]/170,
                recorder_empty=True,recorder_bytes=size['observer_trace']))
            time.sleep(.25)
        assert 100<((ram_rows[-1]['tick_ms']-ram_rows[0]['tick_ms'])&0xffffffff)<15000
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
        def get(path,as_json=True):
            req=urllib.request.Request('http://127.0.0.1:18080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
            with op.open(req,timeout=8) as r:return json.load(r) if as_json else r.read()
        rows=[]
        for _ in range(16):
            d=get('/api/status');assert d['ok'];s=d['data'];rows.append(s)
            with (out/'status_samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(d,ensure_ascii=False)+'\n')
            assert (s['fw_build'],s['mc_fw_build'])==p.NEW
            assert s['state']=='SAFE' and s['pwm']==s['run_id']==s['hmi_hv_armed']==0
            assert 0<=s['vdc']<=20 and not s['bp_status']&0x22 and 0<=s['mc_age_ms']<300
            assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011
            assert s['foc_experiment_flags']==1 and s['foc_timing_cases']==64 and s['foc_timing_fault']==0
            assert s['mc_current_zero_ready']==1
            for k in ('mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags',
                      'mc_last_uart_error_flags','rpc_response_timeouts','rpc_send_timeouts'):
                assert s[k]==0,(k,s[k])
            # Keep the saved programming-time LINK_TIMEOUT visible. This is
            # separate from proving new replies/CPU progress while disarmed;
            # it is NOT an exception to any motor START guard or a CLEAR.
            assert s['mc_transport_fault'] in (0,7),(s['mc_transport_fault'])
            assert s['observer_trace']==dict(available=False,reason='not_received')
            assert s['uno_stop_ready']==0,'No new stop event should exist without RUN'
            assert s['uno_stop_origin']==0
            assert s['mc_observer_trace_hex']=='-' and s['mc_observer_trace_complete']==0
            assert s['mc_observer_trace_good']==s['mc_observer_trace_bad']==0
            assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['config_ok'] and s['mc_sd_live']['break_irq_enabled']
            assert s['repeat_break']['available'] and s['repeat_break']['fresh']
            cpu=s['foc_runtime'];assert cpu['source']=='OFF_synthetic_CPU_probe' and cpu['observer_steps']==64
            assert cpu['meter_errors']==0 and cpu['first_fault'] is None
            time.sleep(.35)
        assert rows[-1]['mc_good_cnt']>rows[0]['mc_good_cnt']
        assert len({s['mc_bad_cnt'] for s in rows})==1,'new rejected frame during observation'
        assert len({s['mc_transport_fault'] for s in rows})==1,'transport latch changed during observation'
        assert rows[-1]['native_boot']['native_tick_ms']>rows[0]['native_boot']['native_tick_ms']
        save('final_status.json',dict(ok=True,data=s))
        save('SD_snapshots.json',get('/api/break-snapshot'))
        save('SD_trace.json',get('/api/bkin-trace'))
        (out/'HMI_logs.txt').write_bytes(get('/api/logs',False))
        preserved=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
        for rel,digest in preserved.items():assert p.sha(p.ROOT/rel)==digest,rel
        report.update(passed=True,pair=list(p.NEW),native_rows=ram_rows,samples=len(rows),
            local_Uno_fault=s.get('uno_local_fault'),stop_evidence_ready=s.get('uno_stop_ready'),
            local_stop_capture_not_triggered=True,
            CPU_source='OFF_synthetic_CPU_probe',fast_kernel_max_us=ram_rows[-1]['fast_kernel_cycles']/170,
            observer_max_wall_us=ram_rows[-1]['observer_max_wall_us'],
            observer_max_CPU_upper_us=ram_rows[-1]['observer_max_CPU_upper_us'],
            full_adapter_under_PWM_measured=False,zero_ready=True,SD=s['mc_sd_live'],
            active_fault_mask=s['mc_fault_current_mask'],saved_fault_mask=s['mc_fault_occurred_mask'],
            run_id=s['run_id'],preserved_files_verified=len(preserved),calibration_unchanged=True,
            UART_clean_for_START=s['mc_transport_fault']==0,
            latched_transport_fault=s['mc_transport_fault'],
            rejected_frame_count_unchanged=s['mc_bad_cnt'],
            motor_start_readiness_evaluated=False,
            thresholds_changed=False,limitation='Synthetic CPU work with MOE=0; not a motor run or hardware observer-accuracy validation.')
    except Exception as exc:report['error']=repr(exc)
    save('report.json',report)
    save('saved_files_sha256.json',{f.name:p.sha(f) for f in out.iterdir() if f.is_file()})
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

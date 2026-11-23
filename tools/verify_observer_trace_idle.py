"""Readback + GET-only inspection of 3015/3016; no START/CLEAR/config/reset."""
import hashlib,json,struct,subprocess,time,urllib.request
import prepare_observer_trace as p
from probe_native_programming_state import probe,inspect_layout
from install_bkin_boot_armed_pair import PROGRAMMER,STLINK_SERIAL


def main():
    out=p.OUT/'post_install_readback_r1';out.mkdir(exist_ok=False)
    report=dict(passed=False,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,configuration_commands=0)
    def write(name,obj):p.write(out/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    try:
        installed=json.loads(p.read(p.OUT/'hardware_install_r2/install_report.json'))
        assert installed['passed'] and installed['uno_readback_verified'] and installed['nucleo_readback_verified']
        report['independent_native_readback']=probe(p.OUT,out/'native_readback','user confirmed J1OFF/meter<20/both USB; passive readback')
        elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
        symbols,_=inspect_layout(elf)
        for name,addr,size in [('observer_trace_empty_state',symbols['observer_trace'],1804),
                              ('native_boot_record',symbols['mic_boot_retained'],32),('native_CSR',0x40021094,4)]:
            r=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=HotPlug','sn='+STLINK_SERIAL,
                '-u',hex(addr),str(size),str(out/(name+'.bin'))],capture_output=True,text=True,timeout=20)
            p.write(out/(name+'.log'),r.stdout+r.stderr);r.check_returncode()
        raw=(out/'observer_trace_empty_state.bin').read_bytes()
        assert len(raw)==1804 and not any(raw),'Observer recorder must be empty before first RUN'
        boot=struct.unpack('<8I',(out/'native_boot_record.bin').read_bytes())
        csr=struct.unpack('<I',(out/'native_CSR.bin').read_bytes())[0]
        assert boot[0]==0x31525442 and boot[1]==p.NEW[1] and boot[5]&4 and csr&0xfe000000==0
        token=p.read(p.ROOT/'.unoq_ssh/control_token').strip();op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def get(path,json_result=True):
            req=urllib.request.Request('http://127.0.0.1:18080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
            with op.open(req,timeout=8) as f:return json.load(f) if json_result else f.read()
        rows=[]
        for _ in range(10):
            r=get('/api/status');assert r['ok'];s=r['data'];rows.append(s)
            with (out/'status_samples.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(r,ensure_ascii=False)+'\n')
            assert (s['fw_build'],s['mc_fw_build'])==p.NEW
            assert s['state']=='SAFE' and s['pwm']==s['run_id']==s['hmi_hv_armed']==0 and s['vdc']<20
            assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011
            for k in ('mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_transport_fault','rpc_response_timeouts','rpc_send_timeouts'):
                assert s[k]==0,(k,s[k])
            for k in ('mc_observer_trace_complete','mc_observer_trace_good','mc_observer_trace_bad'):assert s[k]==0,(k,s[k])
            assert s['mc_observer_trace_hex']=='-' and s['observer_trace']==dict(available=False,reason='not_received')
            b=s['native_boot'];assert b['available'] and b['fresh'] and b['firmware']==boot[1]
            assert b['retained_sequence']==boot[2] and b['csr_raw']==boot[3] and b['early_record_crc']==boot[7]
            time.sleep(.35)
        assert rows[-1]['native_boot']['native_tick_ms']>rows[0]['native_boot']['native_tick_ms']
        write('final_status.json',dict(ok=True,data=s))
        for name,path in [('SD_trace_metadata','/api/bkin-trace'),('SD_snapshots','/api/break-snapshot')]:write(name+'.json',get(path))
        (out/'hmi_logs.txt').write_bytes(get('/api/logs',False))
        report.update(passed=True,pair=list(p.NEW),samples=len(rows),recorder_RAM_empty=True,
            raw_recorder_bytes=1804,observer_trace_status=s['observer_trace'],native_boot=s['native_boot'],
            current_CSR=csr,zero_ready=s['mc_current_zero_ready'],zero_attempts=s['mc_current_zero_attempts'],
            SD=s['mc_sd_live'],fault_masks=[s['mc_fault_current_mask'],s['mc_fault_occurred_mask']],
            OFF_CPU=s.get('foc_runtime'),calibration_unchanged=installed['calibration_unchanged'],
            real_observer_trace_requires_future_RUN=True,programming_boot_not_spontaneous_reset_evidence=True)
    except Exception as error:report['error']=repr(error)
    write('report.json',report)
    write('saved_files_sha256.json',{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file()})
    print(json.dumps({k:report.get(k) for k in ('passed','pair','recorder_RAM_empty','zero_ready','zero_attempts','fault_masks','SD','error')},ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

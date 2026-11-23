"""Independent readback and GET-only verification of the installed boot recorder."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import time
import urllib.request
import prepare_boot_reset_capture as p
from probe_native_programming_state import probe,inspect_layout
from install_bkin_boot_armed_pair import PROGRAMMER,STLINK_SERIAL


def main():
    out=p.OUT/'post_install_readback_r1';out.mkdir(exist_ok=False)
    report=dict(passed=False,START=0,CLEAR=0,ARM=0,RESET=0,flash=0)
    def write(name,obj):p.write(out/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    try:
        installed=json.loads(p.read(p.OUT/'hardware_install_r1/install_report.json'))
        assert installed['passed'] and installed['uno_readback_verified'] and installed['nucleo_readback_verified']
        report['independent_native_readback']=probe(p.OUT,out/'native_readback','after confirmed J1 OFF / meter below20 / both USB; GET/SWD only')
        elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
        symbols,_=inspect_layout(elf)
        for name,addr,size in [('native_boot_record',symbols['mic_boot_retained'],32),('native_CSR',0x40021094,4)]:
            r=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=HotPlug','sn='+STLINK_SERIAL,
                '-u',hex(addr),str(size),str(out/(name+'.bin'))],capture_output=True,text=True,timeout=20)
            p.write(out/(name+'.log'),r.stdout+r.stderr);r.check_returncode()
        words=list(struct.unpack('<8I',(out/'native_boot_record.bin').read_bytes()))
        csr=struct.unpack('<I',(out/'native_CSR.bin').read_bytes())[0]
        report['retained_record_words']=words;report['current_RCC_CSR']=csr
        assert words[0]==0x31525442 and words[1]==p.NEW[1] and words[2]>0
        assert words[5]&4 and csr&0xFE000000==0,'reset flags not confirmed cleared'
        token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def get(path):
            req=urllib.request.Request('http://127.0.0.1:18080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
            with opener.open(req,timeout=8) as response:return json.load(response)
        samples=[]
        for i in range(12):
            s=get('/api/status');assert s['ok'];d=s['data'];samples.append(d)
            with (out/'status_samples.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(s,ensure_ascii=False)+'\n')
            assert (d['fw_build'],d['mc_fw_build'])==p.NEW
            assert d['state']=='SAFE' and d['pwm']==0 and d['run_id']==0 and d['hmi_hv_armed']==0
            assert d['vdc']<20
            for key in ('mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_transport_fault',
                        'rpc_response_timeouts','rpc_send_timeouts'):
                assert d[key]==0,(key,d[key])
            boot=d.get('native_boot',{})
            if boot.get('available') and boot.get('fresh'):
                assert boot['firmware']==words[1] and boot['retained_sequence']==words[2]
                assert boot['csr_raw']==words[3] and boot['early_record_crc']==words[7]
                assert boot['current_flags_cleared']
            time.sleep(.4)
        ready=[d for d in samples if d.get('native_boot',{}).get('fresh')]
        assert len(ready)>=3,'new boot packet did not become fresh'
        assert ready[-1]['native_boot']['native_tick_ms']>ready[0]['native_boot']['native_tick_ms']
        write('final_status.json',dict(ok=True,data=samples[-1]))
        for name,path in [('SD_trace_metadata','/api/bkin-trace'),('SD_snapshots','/api/break-snapshot')]:
            write(name+'.json',get(path))
        req=urllib.request.Request('http://127.0.0.1:18080/api/logs',headers={'X-UNOQ-Control-Token':token},method='GET')
        with opener.open(req,timeout=8) as response:logs=response.read()
        (out/'hmi_logs.txt').write_bytes(logs)
        assert b'MC_BOOT_RECORD ' in logs,'no persisted boot event'
        report.update(passed=True,pair=list(p.NEW),samples=len(samples),fresh_boot_samples=len(ready),
            native_boot=ready[-1]['native_boot'],Linux_boot_id=ready[-1].get('linux_boot_id'),
            zero_ready=samples[-1].get('mc_current_zero_ready'),
            zero_attempts=samples[-1].get('mc_current_zero_attempts'),SD=samples[-1].get('mc_sd_live'),
            fault_masks=[samples[-1].get('mc_fault_current_mask'),samples[-1].get('mc_fault_occurred_mask')],
            calibration_unchanged=installed['calibration_unchanged'],motor_start_validated=False,
            programming_reset_must_not_be_interpreted_as_spontaneous=True)
    except Exception as e:
        report['error']=repr(e)
    write('report.json',report)
    hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file()}
    write('saved_files_sha256.json',hashes)
    print(json.dumps({k:report.get(k) for k in ('passed','pair','fresh_boot_samples','zero_ready','zero_attempts','native_boot','error')},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

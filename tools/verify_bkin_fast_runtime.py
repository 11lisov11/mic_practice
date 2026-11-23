"""Read-only checks of the installed recorder with physical J1/J4 off.

Uses ST-Link HOTPLUG memory reads, no halt/reset/register writes or actuation.
Sampling under motor load and capture of a real pulse remain separate tests.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import time

import install_bkin_fast_capture_pair as install

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-j1-j4-off-meter-below-20v',action='store_true')
    p.add_argument('--outdir',required=True,type=Path)
    args=p.parse_args()
    if not args.confirm_j1_j4_off_meter_below_20v:p.error('physical deenergized state required')
    install.verify_package()
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=True)
    report={'pass':False,'memory_reads_only':True,'start_commands':0,'clear_commands':0,
        'reset_commands':0,'mcu_flash_commands':0,'register_reads':[],'statuses':[]}
    def status():
        s=install.io.live_status();report['statuses'].append(s)
        ok,reason=install.precheck(s)
        if not ok or (s.get('fw_build'),s.get('mc_fw_build'))!=install.NEW:
            raise RuntimeError('installed pair/off state: '+reason)
        return s
    def read(address,words,label):
        command=[str(install.io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG',
            'sn='+install.io.STLINK_SERIAL,'-r32',hex(address),str(4*words)]
        start=time.monotonic()
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        stop=time.monotonic()
        text=result.stdout+result.stderr;(out/(label+'.log')).write_text(text,encoding='utf-8')
        if result.returncode:raise RuntimeError('memory read failed: '+label)
        values={}
        for line in text.splitlines():
            m=re.fullmatch(r'0x([0-9a-fA-F]{8})\s*:\s*((?:[0-9a-fA-F]{8}\s*)+)',line.strip())
            if m:
                for i,w in enumerate(m[2].split()):values[int(m[1],16)+4*i]=int(w,16)
        if len(values)!=words:raise RuntimeError('incomplete memory read: '+label)
        report['register_reads'].append({'label':label,'started_monotonic':start,
            'ended_monotonic':stop,'values':{hex(k):v for k,v in values.items()}})
        return values
    try:
        status()
        debug=install.C/'nucleo/STM32CubeIDE/Debug'
        source=(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map').read_text(encoding='utf-8-sig')
        def symbol(name):
            m=re.search(r' \.bss\.'+re.escape(name)+r'\s+(0x[0-9a-f]+)',source)
            if not m:raise RuntimeError('symbol missing: '+name)
            return int(m[1],16)
        # Read contiguous groups by symbols from this exact build's map.
        progress_base=symbol('mic_bkin_triggered')
        state_base=symbol('mic_bkin_record_ready')
        if symbol('mic_bkin_completed')!=progress_base+16 or symbol('mic_bkin_capture_state')!=state_base+16:
            raise RuntimeError('unexpected diagnostic layout')
        timer=read(0x40000000,12,'fast_timer_registers')
        if not (timer[0x40000000]&1 and timer[0x4000000c]&256 and
            timer[0x40000028]==0 and timer[0x4000002c]==33):
            raise RuntimeError('TIM2 does not request 5 MHz at configured 170 MHz')
        bdtr=read(0x40012c44,1,'fast_tim1_outputs')[0x40012c44]
        if bdtr&(1<<15):raise RuntimeError('TIM1 MOE unexpectedly enabled')
        completed=[];remaining=[]
        for i in range(4):
            state=read(state_base,5,'fast_capture_state_'+str(i))
            progress=read(progress_base,5,'fast_capture_progress_'+str(i))
            dma=read(0x40020400,6,'fast_dma_registers_'+str(i))
            if state[state_base]!=0 or state[state_base+16]!=1:
                raise RuntimeError('capture already frozen/error; preserve first record')
            if progress[progress_base]!=0 or progress[progress_base+4]!=0:
                raise RuntimeError('capture triggered or stream reports loss')
            ccr=dma[0x40020408]
            if dma[0x40020400]&8 or not ccr&1 or ((ccr>>8)&3)!=2 or ((ccr>>10)&3)!=1:
                raise RuntimeError('DMA not enabled/word-to-halfword or transfer error')
            if dma[0x40020410]!=0x48000010 or dma[0x40020414]!=symbol('mic_bkin_ring'):
                raise RuntimeError('DMA peripheral/memory address mismatch')
            if not 1<=dma[0x4002040c]<=8192:raise RuntimeError('invalid CNDTR')
            completed.append(progress[progress_base+16]);remaining.append(dma[0x4002040c])
            status()
        advances=[(b-a)&0xffffffff for a,b in zip(completed,completed[1:])]
        if any(not 0<x<100000000 for x in advances):raise RuntimeError('DMA progress not advancing')
        if len(set(remaining))<2:raise RuntimeError('DMA CNDTR not observed changing')
        good=[s['mc_good'] for s in report['statuses']]
        if good[-1]<=good[0]:raise RuntimeError('UART reply counter did not advance')
        initial=report['statuses'][0];final=report['statuses'][-1]
        for key in ('mc_bad_integrity','mc_bad_sequence','uno_rx_dropped','mc_bad'):
            if final[key]!=initial[key]:raise RuntimeError('new UART error: '+key)
        report.update(pass_=True,requested_sample_rate_hz=5000000,timer_psc=0,timer_arr=33,
            capture_state='RUNNING',capture_triggered=False,record_ready=False,stream_error=0,
            dma_interrupt_progress=completed,dma_remaining_samples=remaining,output_moe=False,
            fresh_uart=True,limitations=['No motor PWM or real fault pulse exercised',
                'Register/counter progress does not prove every 200-ns timer request was serviced'])
        report['pass']=report.pop('pass_')
    except Exception as exc:report['error']=str(exc)
    (out/'fast_recorder_runtime_verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('pass','capture_state','stream_error','fresh_uart','error')}))
    return 0 if report['pass'] else 1

if __name__=='__main__':raise SystemExit(main())

"""Read-only confirmation of exact live TX DMA setup and progressing whole frames."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import install_uart_tx_dma_pair as install
from wifi_stop_tail_probe import parse_registers

def main():
    global install
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-j1-off-usb-bus-below-20v',action='store_true',required=True)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--revision2',action='store_true')
    a=p.parse_args()
    if a.revision2:
        import install_uart_tx_dma_r2_pair as install
    install.verify_package()
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(pass_=False,memory_reads_only=True,motor_commands=0,clear_commands=0,reset_commands=0,
           flash_commands=0,register_writes=0,samples=[])
    def read(address,size,name):
        p=subprocess.run([str(install.io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+install.io.STLINK_SERIAL,
            '-r32',hex(address),str(size)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        (out/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        if p.returncode:raise RuntimeError('read failed: '+name)
        regs=parse_registers(p.stdout)
        if len(regs)!=size//4:raise RuntimeError('incomplete read: '+name)
        return regs
    try:
        text=(install.C/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.map').read_text(encoding='utf-8-sig')
        m=re.search(r' \.bss\.mic_uart_tx\s+(0x[0-9a-f]+)',text)
        if not m:raise RuntimeError('new TX symbol absent')
        address=int(m[1],16)
        fields=('head','tail','active','started_ms','late_reported','hard_error','queued','completed','timeouts','full_errors','dma_errors','last_status','early_tc')
        d=read(0x40020800,4,'dmamux_usart1_tx')
        if d[0x40020800]&127!=25:raise RuntimeError('DMAMUX request is not USART1_TX')
        for i in range(7):
            s=install.io.live_status();safe,reason=install.precheck(s)
            if not safe or (s['fw_build'],s['mc_fw_build'])!=install.NEW:raise RuntimeError(reason)
            values=read(address,52,'tx_state_'+str(i));tx=dict(zip(fields,(values[address+4*j] for j in range(13))))
            dma=read(0x40020000,24,'tx_dma_'+str(i))
            ccr=dma[0x40020008]
            if (ccr&0x7ff0)!=0x2090:raise RuntimeError('TX DMA must be normal, byte/byte, MINC, high priority, memory to peripheral')
            if dma[0x40020010]!=0x40013828:raise RuntimeError('DMA peripheral is not USART1 TDR')
            if not 0<=dma[0x4002000c]<=43:raise RuntimeError('invalid TX remaining bytes')
            if dma[0x40020000]&8:raise RuntimeError('DMA transfer error')
            if any(tx[k]!=0 for k in ('hard_error','timeouts','full_errors','dma_errors','last_status','early_tc')):
                raise RuntimeError('live TX failure/collision/stall observed')
            depth=(tx['head']-tx['tail'])&0xffffffff
            if not 0<=depth<=4:raise RuntimeError('invalid TX queue depth')
            r['samples'].append(dict(status=s,tx=tx,dma={hex(k):v for k,v in dma.items()}))
            time.sleep(.3)
        first,last=r['samples'][0],r['samples'][-1]
        if last['tx']['completed']<=first['tx']['completed']:raise RuntimeError('completed full-frame counter did not progress')
        for key in ('mc_bad','mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','uno_rx_dropped','mc_transport_fault'):
            if last['status'][key]!=first['status'][key]:raise RuntimeError('new UART error: '+key)
        r['pass_']=True;r['tx_symbol_address']=address;r['completed_delta']=last['tx']['completed']-first['tx']['completed']
    except Exception as exc:r['error']=str(exc)
    r['pass']=r.pop('pass_')
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('pass','completed_delta','error')}))
    return 0 if r['pass'] else 1
if __name__=='__main__':raise SystemExit(main())

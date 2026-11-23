"""Bounded read-only idle check of final TX-DMA pair; no commands to motor."""
import argparse
import json
from pathlib import Path
import time
import install_uart_tx_dma_r2_pair as install

def expected_off_fault(s):
    healthy=(s.get('mc_fault')==s.get('bp_fault')==0 and s.get('mc_fault_reason')==0
             and s.get('mc_fault_current_mask')==s.get('mc_fault_occurred_mask')==0)
    low_bus=(s.get('mc_fault')==s.get('bp_fault')==5 and s.get('mc_fault_reason')==8
             and s.get('mc_fault_current_mask') in (0,4) and s.get('mc_fault_occurred_mask')==4)
    return healthy or low_bus

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args()
    if not 10<=a.seconds<=120:p.error('duration outside10..120')
    install.verify_package();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(pass_=False,start_commands=0,clear_commands=0,reset_commands=0,flash_commands=0,
           calibration_writes=0,samples=[])
    began=time.monotonic()
    try:
        while time.monotonic()-began<a.seconds:
            s=install.io.live_status();r['samples'].append(s)
            with (out/'status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
            okay,reason=install.precheck(s);sd=s.get('mc_sd_live',{})
            if not okay or (s['fw_build'],s['mc_fw_build'])!=install.NEW:raise RuntimeError(reason)
            if not expected_off_fault(s):
                raise RuntimeError('fault or controller protection appeared')
            for k in ('mc_bad','mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_last_uart_error_flags',
                      'mc_transport_fault','uno_rx_dropped','uno_tx_short_writes','mc_uart_reject_bad_pages'):
                if s.get(k)!=0:raise RuntimeError('UART error: '+k)
            if not(sd.get('available') and sd.get('level')=='HIGH' and sd.get('config_ok') and sd.get('break_irq_enabled')
                   and sd.get('capture_running') and not sd.get('first_record_ready')):
                raise RuntimeError('SD/capture condition changed')
            time.sleep(.2)
        first,last=r['samples'][0],r['samples'][-1]
        r['elapsed_s']=time.monotonic()-began;r['good_reply_delta']=last['mc_good']-first['mc_good']
        if r['good_reply_delta']<=100:raise RuntimeError('too few progressing replies')
        r['pass_']=True
    except Exception as exc:r['error']=str(exc)
    r['pass']=r.pop('pass_')
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('pass','elapsed_s','good_reply_delta','error')}))
    return 0 if r['pass'] else 1
if __name__=='__main__':raise SystemExit(main())

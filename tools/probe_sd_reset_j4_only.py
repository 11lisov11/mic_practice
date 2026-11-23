"""One Nucleo reset at stable J4-only power after archiving the completed SD pulse."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import install_sd_live_diagnostics_pair as install


def ready(s):
    okay,_=install.precheck(s)
    sd=s.get('mc_sd_live',{})
    low_bus=(s.get('mc_fault_reason')==8 and s.get('mc_fault_current_mask') in (0,4)
             and s.get('mc_fault_occurred_mask')==4)
    no_fault=(s.get('mc_fault')==0 and s.get('bp_fault')==0 and s.get('mc_fault_reason')==0
              and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0)
    return bool(okay and (s.get('fw_build'),s.get('mc_fw_build'))==install.NEW
        and sd.get('available') and sd.get('level')=='HIGH' and sd.get('config_ok')
        and s.get('mc_transport_fault')==0 and s.get('mc_uart_error_flags')==0
        and (low_bus or no_fault))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-j1-off-j4-only-usb',action='store_true',required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();install.verify_package()
    archived=json.loads((a.archive/'read_only_report.json').read_text(encoding='utf-8'))
    wave=archived.get('wave',{})
    if not (archived['pass'] and archived['independent_decode_matches'] and
            archived['wave_tick_matches_first_snapshot'] and wave.get('pulse_complete') and
            wave.get('post_complete') and not any(wave.get(k) for k in
                ('dma_error','sampling_overrun','run_overflow','timeout')) and
            (a.archive/'bkin_wave.bin').is_file()):
        raise RuntimeError('completed first SD pulse must be archived before the one reset')
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(pass_=False,motor_commands=0,flash_commands=0,clear_commands=0,reset_commands=0,
           j1_off_j4_only_usb_user_confirmed=True,before=[],after=[])
    keys=('mc_bad','mc_bad_integrity','mc_bad_sequence','uno_rx_dropped')
    try:
        for i in range(8):
            s=install.io.live_status();r['before'].append(s)
            if not ready(s):raise RuntimeError('stable SD HIGH/off/low-bus baseline required')
            if i and any(s.get(k)!=r['before'][0].get(k) for k in keys):
                raise RuntimeError('UART counters still changing before RESET; preserve evidence')
            time.sleep(.35)
        sample=r['before'][-1]
        for key,value in [('pwm',1),('vdc',21),('mc_transport_fault',2),('mc_fault_occurred_mask',0x404)]:
            assert not ready(dict(sample,**{key:value})),key
        assert not ready(dict(sample,mc_sd_live=dict(sample['mc_sd_live'],level='LOW')))
        (out/'before_reset.json').write_text(json.dumps(sample,indent=2)+'\n',encoding='utf-8')
        r['reset_commands']=1
        result=subprocess.run([str(install.io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG',
            'sn='+install.io.STLINK_SERIAL,'-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        (out/'reset_only.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:raise RuntimeError('RESET command failed; do not retry automatically')
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            s=install.io.live_status();r['after'].append(s)
            with (out/'status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
            if s.get('state')!='SAFE' or s.get('pwm')!=0 or s.get('hmi_hv_armed')!=0:
                raise RuntimeError('unexpected active state after reset')
            time.sleep(.35)
        last=r['after'][-1];r['final_status']=last
        sd=last.get('mc_sd_live',{})
        fresh=r['after'][-7:]
        stable=(all(ready(x) for x in fresh) and len(fresh)==7 and
            all(not x.get('mc_sd_live',{}).get('first_record_ready') and
                x.get('mc_sd_live',{}).get('capture_running') and
                x.get('mc_sd_live',{}).get('break_irq_enabled') for x in fresh))
        empty=(last.get('mc_break_wave_hex')=='-' and len(last.get('mc_break_snapshots',[]))==2 and
               all(x.get('available') and not x.get('captured') for x in last['mc_break_snapshots']))
        unchanged=all(all(x.get(k)==fresh[0].get(k) for k in keys) for x in fresh)
        r.update(sd_high_stable=stable,first_capture_empty=empty,final_uart_counters_stable=unchanged,
                 retained_uno_reply_integrity_count=last.get('mc_bad_integrity'))
        r['pass_']=stable and empty and unchanged
        if not r['pass_']:raise RuntimeError('RESET outcome requires diagnosis; no automatic retry')
    except Exception as exc:r['pass_']=False;r['error']=str(exc)
    r['pass']=r.pop('pass_')
    (out/'report.json').write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('pass','reset_commands','sd_high_stable','first_capture_empty','final_uart_counters_stable','error')}))
    return 0 if r['pass'] else 1


if __name__=='__main__':raise SystemExit(main())

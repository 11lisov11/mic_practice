"""Archive and acknowledge the known programming-pause timeout; never START."""
import argparse
import json
from pathlib import Path
import time

from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi
from verify_wifi_command_path import get_wifi_logs


def safe(s):
    try:
        return ((s['fw_build'],s['mc_fw_build'])==(2026101104,2026101102)
            and s['state']=='SAFE' and s['pwm']==s['estop']==s['hmi_hv_armed']==0
            and not s['bp_status']&0x22 and s['bp_clear_pending']==0
            and all(type(s[k]) in (int,float) and 0<=s[k]<=2 for k in ('vdc','bp_vdc'))
            and all(0<=s[k]<300 for k in ('bp_age_ms','mc_age_ms','bp_vbus_age_ms'))
            and s['bp_vbus_valid']==1 and 0<=s['bp_vbus_raw']<=20
            and all(s[k]==0 for k in ('bp_bad','bp_bad_integrity','bp_bad_sequence',
                'uno_rx_dropped','uno_rx_hw_errors','mc_break_rx_bad','precharge','pfc','brake','bp_ext')))
    except (KeyError,TypeError): return False


def records(s): return [x.get('raw') for x in s.get('mc_break_snapshots',[]) if x.get('captured')]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--confirm-mains-j4-off',action='store_true')
    a=p.parse_args()
    if not a.confirm_mains_j4_off: p.error('Previously confirmed deenergized stand required')
    out=a.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    rep=dict(pass_=False,start_commands=0,commands=[],samples=[])
    h=WifiHmi('http://192.168.1.138:8080',read_token('.unoq_ssh/control_token'),rep['commands'],False)
    try:
        before=rep['before']=h.status()
        if not safe(before) or (before['bp_fault'],before['bp_transport_fault'],before['bp_bad_cnt'])!=(2,7,1):
            raise RuntimeError('Not the exact archived programming-pause timeout')
        saved=records(before)
        if not saved: raise RuntimeError('First-break record unavailable; archive before CLEAR')
        (out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
        (out/'before_logs.txt').write_text(get_wifi_logs(h,h.token),encoding='utf-8')
        h.command('CLEAR')
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            s=h.status(); rep['samples'].append(s)
            if s.get('pwm')!=0 or s.get('hmi_hv_armed')!=0: raise RuntimeError('Unexpected enabled outputs')
            if (safe(s) and s['bp_bad_cnt']==s['bp_transport_fault']==0
                    and s['bp_fault']==5 and s['mc_fault_current_mask']==4): break
            time.sleep(.2)
        else: raise RuntimeError('CLEAR delivery/timeout acknowledgement not confirmed')
        rep['after']=s
        rep['first_break_record_preserved']=records(s)==saved
        if not rep['first_break_record_preserved']: raise RuntimeError('First-break record changed')
        rep['expected_remaining_fault']='MCSDK undervoltage, DC bus 0 V; not disabled or hidden'
        rep['pass_']=True
    except Exception as exc: rep['error']=str(exc)
    finally:
        h.close(); rep['pass']=rep.pop('pass_')
        (out/'report.json').write_text(json.dumps(rep,indent=2)+'\n')
    print(json.dumps({k:rep.get(k) for k in ('pass','first_break_record_preserved','error')}))
    return 0 if rep['pass'] else 1


if __name__=='__main__': raise SystemExit(main())

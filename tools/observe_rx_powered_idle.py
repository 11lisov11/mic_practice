"""Observe powered SAFE telemetry; optional one-off gated ACK, never ARM or START."""
import argparse
import json
import math
from pathlib import Path
import time

from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import operator_keepalive


def powered_off(s):
    try:
        return ((s['fw_build'],s['mc_fw_build'])==(2026101104,2026101102)
            and s['state']=='SAFE' and s['mode']=='VF' and s['pwm']==s['hmi_hv_armed']==s['estop']==0
            and not s['bp_status']&0x22 and s['freq_cmd']==5
            and s['hmi_powered_trial_enabled']==s['hmi_vbus_hv_calibrated']==1
            and s['hmi_start_runlimit_s']==3 and s['hmi_powered_trial_remaining_s']>50
            and all(type(s[k]) in (int,float) and math.isfinite(s[k]) and 250<=s[k]<=360
                    for k in ('vdc','bp_vdc'))
            and type(s['bp_vbus_raw']) is int and abs(s['bp_vbus_raw']*.1-s['bp_vdc'])<=1
            and all(type(s[k]) in (int,float) and math.isfinite(s[k]) and 0<=s[k]<300
                    for k in ('bp_age_ms','mc_age_ms','bp_vbus_age_ms','bp_temp_age_ms'))
            and s['bp_temp_valid']==1 and -20<=s['bp_temp_c']<=80
            and all(type(s[k]) is int and s[k]==0 for k in ('bp_bad','bp_bad_integrity','bp_bad_sequence',
                'bp_bad_cnt','bp_transport_fault','uno_rx_dropped','uno_rx_hw_errors','uno_rx_hw_flags',
                'mc_break_rx_bad','mc_uart_error_flags','mc_last_uart_error_flags','uno_tx_short_writes',
                'mc_last_bad_reason','bp_temp_fault','precharge','pfc','brake','bp_ext')))
    except (KeyError,TypeError): return False


def eligible_idle_latch(s):
    if (not powered_off(s) or s.get('bp_fault')!=5 or s.get('mc_diag_valid')!=1
            or s.get('mc_fault_reason')!=8 or s.get('mc_fault_current_mask')!=4
            or s.get('mc_fault_occurred_mask')!=4): return False
    records=s.get('mc_break_snapshots',[])
    if len(records)!=2 or any(x.get('available') is not True for x in records): return False
    if records[1].get('captured') is not False: return False
    if records[0].get('captured') is False: return True
    raw=records[0].get('raw',{}); event=records[0].get('event',{})
    # Explicitly recorded pre-START zero-bus trip; never ACK an unexplained RUN trip.
    return (raw.get('start_window')==0 and raw.get('reference_speed_unit')==0
        and raw.get('vbus_v')==0 and raw.get('tim_ccr1')==raw.get('tim_ccr2')==raw.get('tim_ccr3')==0
        and event.get('bif') is True and event.get('b2if') is False
        and event.get('bke_at_irq') is True and event.get('moe_at_irq') is False
        and event.get('during_start_request_window') is False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-autonomous-ready',action='store_true')
    p.add_argument('--ack-idle-latch',action='store_true')
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args()
    if not a.confirm_autonomous_ready: p.error('Confirmed no PC wired links, secured motor and operator by switch required')
    out=a.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    rep=dict(pass_=False,commands=[],samples=[],start_commands=0,arm_commands=0,host_clear_requests=0)
    h=WifiHmi('http://192.168.1.138:8080',read_token('.unoq_ssh/control_token'),rep['commands'],False)
    try:
        rep['before']=s=h.status()
        (out/'before.json').write_text(json.dumps(s,indent=2)+'\n')
        (out/'before_logs.txt').write_text(get_wifi_logs(h,h.token),encoding='utf-8')
        before_record=[x.get('raw') for x in s.get('mc_break_snapshots',[]) if x.get('captured')]
        if not powered_off(s): raise RuntimeError('Powered output-off bus/link/trial checks failed')
        with operator_keepalive(h) as heartbeat:
            if s['bp_fault']!=0:
                if not a.ack_idle_latch or not eligible_idle_latch(s):
                    raise RuntimeError('Fault is not eligible for the single pre-run ACK')
                h.command('CLEAR'); rep['host_clear_requests']=1
                deadline=time.monotonic()+6
                while time.monotonic()<deadline:
                    s=h.status(); rep['samples'].append({'phase':'ack','status':s})
                    if not powered_off(s) or heartbeat['errors']: raise RuntimeError('State changed during ACK')
                    if s['bp_fault']==0 and s.get('bp_clear_pending')==0: break
                    time.sleep(.2)
                else: raise RuntimeError('Fault did not clear; no retry or START')
            started=time.monotonic(); first=s['bp_good']
            while True:
                s=h.status(); rep['samples'].append({'phase':'idle','elapsed_s':time.monotonic()-started,'status':s})
                if not powered_off(s) or s['bp_fault']!=0 or heartbeat['errors']:
                    raise RuntimeError('Powered idle protection/link check failed; no START')
                if time.monotonic()-started>=30: break
                time.sleep(.25)
            rep['after']=s
            rep['new_good_frames']=s['bp_good']-first
            rep['first_break_record_preserved']=[x.get('raw') for x in s.get('mc_break_snapshots',[]) if x.get('captured')]==before_record
            rep['heartbeat']=heartbeat
            if rep['new_good_frames']<100 or s.get('hmi_powered_trial_ready')!=1:
                raise RuntimeError('Powered idle trial gate did not qualify')
            if not rep['first_break_record_preserved']: raise RuntimeError('First-break record changed during idle')
            rep['pass_']=True
    except Exception as exc: rep['error']=f'{type(exc).__name__}: {exc}'
    finally:
        try: (out/'wifi_logs.txt').write_text(get_wifi_logs(h,h.token),encoding='utf-8')
        except Exception as exc: rep['log_error']=str(exc)
        h.close(); rep['pass']=rep.pop('pass_')
        (out/'report.json').write_text(json.dumps(rep,indent=2)+'\n')
    print(json.dumps({k:rep.get(k) for k in ('pass','host_clear_requests','new_good_frames',
        'first_break_record_preserved','start_commands','arm_commands','error')}))
    return 0 if rep['pass'] else 1


if __name__=='__main__': raise SystemExit(main())

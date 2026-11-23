"""One authorized bounded 5-Hz current trial; independent host and MCU STOP."""
import argparse
import json
from pathlib import Path
import threading
import time

import run_fast_bkin_short_scalar as checks
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token,get_logs
from wifi_bench_scenarios import operator_keepalive

checks.PAIR=(2026102411,2026102412)
ROOT=Path(__file__).resolve().parents[1]

def zero_ok(s):
    if (s.get('fw_build'),s.get('mc_fw_build'))==(2026102505,2026102506):
        from current_zero_quality import ready as new_zero_ready
        return new_zero_ready(s)
    try:
        return (s['mc_current_zero_ready']==1 and s['mc_current_zero_stable']==3
            and 3<=s['mc_current_zero_attempts']<=8 and 0<=s['mc_current_quality_age_ms']<1500
            and len(s['mc_current_zero_spans'])==4 and all(0<=x<=40 for x in s['mc_current_zero_spans'])
            and 0<=s['mc_current_age_ms']<750)
    except (KeyError,TypeError):return False

def sd_high(s,irq_required):
    q=s.get('mc_sd_live',{})
    return (q.get('available') is True and q.get('config_ok') is True and q.get('level')=='HIGH'
        and 0<=q.get('age_ms',999999)<300 and (not irq_required or q.get('break_irq_enabled') is True))

def archive_before_start(s):
    """A retained waveform limits waveform diagnosis, not hardware Break action.

    Only accept an event explicitly recorded with MOE off and outside START;
    never acknowledge a running-driver trip or an active protection input.
    """
    if s.get('mc_break_wave_hex')=='-':return True
    records={x.get('kind'):x for x in s.get('mc_break_snapshots',[])}
    first=records.get('first_since_boot',{});start=records.get('first_start_window',{})
    event=first.get('event',{});context=first.get('cached_context') or {}
    return (first.get('captured') is True and event.get('moe_at_irq') is False
        and event.get('during_start_request_window') is False and start.get('captured') is False
        and context.get('reference_speed_unit')==0 and context.get('motor_state')!=6)

def startup_uv_only(s):
    return (checks.off(s) and checks.transport_clean(s) and zero_ok(s) and sd_high(s,False)
        and s.get('estop')==0 and s.get('mc_fault')==s.get('bp_fault')==5
        and s.get('mc_fault_reason')==8 and s.get('mc_fault_current_mask')==0
        and s.get('mc_fault_occurred_mask')==4 and s.get('mc_last_bad_reason')==0
        and archive_before_start(s))

def ready(s):
    return checks.ready(s) and zero_ok(s) and sd_high(s,True) and archive_before_start(s)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True);p.add_argument('--confirm-powered-ready',action='store_true')
    a=p.parse_args()
    if not a.confirm_powered_ready:p.error('Fresh autonomous powered motor preparation required')
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(passed=False,start_commands=0,clear_commands=0,flash_commands=0,calibration_writes=0,
        target_hz=5,host_stop_s=5,host_stop_reference='START confirmation',host_hard_deadline_s=10,
        mcu_limit_s=7,commands=[],samples=[],collection_errors=[],
        current_scale_qualified=False,physical_rotation_verified=False,
        sd_waveform_limit='A retained pre-START SD waveform is saved; it cannot capture a second waveform until reboot. Hardware Break is rearmed and checked before START.')
    h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),r['commands'],False)
    expired=threading.Event();done=threading.Event();timer=None;hard_timer=None;collector=None
    write_lock=threading.Lock()
    def save(name,value):(out/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    def record(s,source):
        row=dict(host_monotonic_s=time.monotonic(),source=source,status=s)
        with write_lock:
            r['samples'].append(row)
            with (out/'status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
    def sample():
        s=h.status();record(s,'monitor')
        return s
    def collect():
        client=WifiHmi(h.base,h.token,[],False)
        while not done.is_set():
            try:record(client.status(),'collector')
            except Exception as exc:r['collection_errors'].append(str(exc))
            done.wait(.12)
        client.close()
    def deadline_stop(reason):
        expired.set();client=WifiHmi(h.base,h.token,[],False)
        code,body=client.fail_safe_stop();r.setdefault('deadline_stops',[]).append(dict(reason=reason,http=code,ok=body.get('ok')));client.close()
    try:
        s=sample();r['before']=s;save('before.json',s)
        # Every captured event is preserved before a legal startup UV acknowledgement.
        if not ready(s):
            if not startup_uv_only(s):raise RuntimeError('Preflight failed: no CLEAR and no START')
            h.command('CLEAR');r['clear_commands']=1
            deadline=time.monotonic()+5
            while True:
                s=sample()
                if ready(s):break
                if time.monotonic()>=deadline:raise RuntimeError('Single startup UV acknowledgement did not establish ready OFF')
                time.sleep(.15)
        save('after_startup_ack.json',s)
        with operator_keepalive(h) as heartbeat:
            h.command('MODE VF');h.command('SET FREQ 5')
            s=sample()
            if not ready(s) or s.get('freq_cmd')!=5 or heartbeat['errors']:raise RuntimeError('5Hz preparation failed')
            if s.get('hmi_arm_confirm')!='ARM 310V':raise RuntimeError('Unexpected arm contract')
            h.post('/api/hv-arm',{'action':'arm','confirm':'ARM 310V'},'ARM one bounded 5Hz current trial')
            collector=threading.Thread(target=collect);collector.daemon=True;collector.start()
            began=time.monotonic();r['start_monotonic_s']=began
            hard_timer=threading.Timer(10,deadline_stop,args=('hard deadline from request',));hard_timer.daemon=True;hard_timer.start()
            r['start_commands']=1
            r['start_response']=h.post('/api/start-sequence',{'runlimit_s':7.0},'single bounded START 5Hz')
            confirmed=time.monotonic();r['start_confirmed_monotonic_s']=confirmed
            timer=threading.Timer(5,deadline_stop,args=('5s after START confirmation',));timer.daemon=True;timer.start()
            print('START confirmed at5Hz; recording currents for5s, MCU backup7s',flush=True)
            while not expired.is_set() and time.monotonic()-confirmed<5:
                s=sample()
                if expired.is_set():break
                if not checks.active(s) or not zero_ok(s) or not sd_high(s,True) or heartbeat['errors'] or r['collection_errors']:
                    r['abort_status']=s;raise RuntimeError('Active controller/bus/SD/link health changed; STOP without retry')
                if time.monotonic()-confirmed>1.5 and s.get('mc_current_telemetry_valid')!=1:
                    r['abort_status']=s;raise RuntimeError('Current window did not become valid; STOP without retry')
                time.sleep(.08)
            r['stop_response']=h.post('/api/stop-sequence',{'emergency':False},'scheduled STOP after5Hz current observation')
            r['heartbeat']=heartbeat;r['passed']=True
    except Exception as exc:r['error']=str(exc)
    finally:
        code,body=h.fail_safe_stop();r['final_stop']=dict(http=code,ok=body.get('ok'))
        if timer:timer.cancel();timer.join(timeout=9)
        if hard_timer:hard_timer.cancel();hard_timer.join(timeout=9)
        done.set()
        if collector:collector.join(timeout=9)
        try:
            s=sample();r['final_status']=s
            def off(q):return q.get('pwm')==0 and q.get('state')=='SAFE' and q.get('hmi_hv_armed')==0 and not(q.get('bp_status',0x22)&0x22) and 0<=q.get('mc_age_ms',999999)<300
            if not off(s):
                r['emergency_stop']=h.post('/api/stop-sequence',{'emergency':True},'emergency STOP after off not confirmed')
                s=sample();r['final_status']=s
            r['outputs_off_confirmed']=off(s)
            r['passed']=r['passed'] and r['outputs_off_confirmed'] and code==200 and body.get('ok') is True
        except Exception as exc:r['passed']=False;r['final_status_error']=str(exc)
        valid=[row for row in r['samples'] if row['status'].get('pwm')==1 and row['status'].get('mc_current_telemetry_valid')==1]
        target=[row for row in valid if row['status'].get('mc_frequency_reference_valid')==1
            and abs(row['status'].get('mc_frequency_reference_hz',-1)-5)<=.11
            and row['status'].get('mc_current_window_ms',0)>=199 and not(row['status'].get('mc_current_flags',0)&4)]
        windows={row['status']['mc_current_window_tick_ms'] for row in target}
        r.update(valid_current_samples=len(valid),valid_5hz_current_samples=len(target),distinct_5hz_windows=len(windows))
        if len(windows)<2:r['passed']=False;r.setdefault('error','Fewer than two distinct valid5Hz current windows')
        try:
            time.sleep(2);save('after_diagnostics.json',h.status())
            (out/'logs.txt').write_text(get_logs(h.opener,h.base,h.token,.25),encoding='utf-8')
        except Exception as exc:r['log_error']=str(exc)
        save('report.json',r);h.close()
        print(json.dumps({k:r.get(k) for k in ('passed','error','start_commands','clear_commands','outputs_off_confirmed','valid_current_samples','valid_5hz_current_samples','distinct_5hz_windows')}),flush=True)
        if not r.get('outputs_off_confirmed'):print('OUTPUT OFF NOT CONFIRMED: operator must switch off power',flush=True)
    return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

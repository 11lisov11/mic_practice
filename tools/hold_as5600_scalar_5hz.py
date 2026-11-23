"""Explicitly authorized manual 5Hz hold; AS5600 observational, drive protections active.

No run-duration cap. STOP file, web STOP, drive/link/current failure or heartbeat
failure ends the hold. Exactly one individually authorized pre-start CLEAR.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import signal
import threading
import time

import run_current_shunt_5_10_5 as motor
from current_zero_quality import ready as zero_ready
from run_current_shunt_5hz import archive_before_start
from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi
from wifi_bench_scenarios import operator_keepalive

SHA='00ca7877e135c1b51f7fbcb922354e3740e450b3135ded17fe5377b31b81554d'
ROOT=Path(__file__).resolve().parents[1]
ACKNOWLEDGED_RUNNING_BREAK_RAW=None


def retained(s):
    try:return hashlib.sha256(bytes.fromhex(s['mc_break_wave_hex'])).hexdigest()==SHA
    except (KeyError,ValueError,TypeError):return False


def ready(s):
    return (motor.checks.ready(s) and zero_ready(s) and motor.sd_high(s,True)
            and archived_record_allowed(s) and retained(s))


def archived_record_allowed(s):
    if archive_before_start(s):return True
    if ACKNOWLEDGED_RUNNING_BREAK_RAW is None:return False
    try:
        q=next(x for x in s['mc_break_snapshots'] if x['kind']=='first_start_window')
        return q.get('available') is True and q.get('captured') is True and q['raw']==ACKNOWLEDGED_RUNNING_BREAK_RAW
    except (KeyError,TypeError,StopIteration):return False


def load_acknowledged_running_break(path):
    """Diagnostic memory admission only; never clears/disables a protection."""
    r=json.loads(Path(path).read_text(encoding='utf-8'))
    if not(r.get('passed') is True and r.get('clear_commands')==1 and r.get('start_commands')==0):
        raise ValueError('Expected completed single authorized ACK report')
    s=r['after'][-1]
    if not(motor.checks.ready(s) and zero_ready(s) and motor.sd_high(s,True) and retained(s)):
        raise ValueError('ACK did not restore clean protected OFF state')
    q=next(x for x in s['mc_break_snapshots'] if x['kind']=='first_start_window');raw=q['raw']
    if not(q.get('captured') is True and raw['tick_ms']==r['archived_running_break_tick']
           and raw['motor_state']==6 and raw['reference_speed_unit']==50
           and raw['current_faults']==raw['occurred_faults']==0 and q['event']['bif'] is True):
        raise ValueError('Unexpected archived running Break identity')
    return raw


def current_valid(s):
    try:
        return (s['mc_current_telemetry_valid']==1 and 95<=s['mc_current_coverage_pct']<=100
            and s['mc_current_flags']&11==11 and not(s['mc_current_flags']&(4|16|32))
            and 0<=s['mc_current_age_ms']<750
            and len(s['mc_current_rms_a'])==3
            and all(type(v) in (int,float) and math.isfinite(v) for v in s['mc_current_rms_a']))
    except (KeyError,ValueError,TypeError):return False


def active(s):
    # AS5600 validity deliberately does not enter this drive-health predicate.
    return motor.active(s,5) and retained(s) and archived_record_allowed(s)


def acknowledgeable(s):
    return (motor.checks.off(s) and motor.checks.transport_clean(s) and zero_ready(s)
        and motor.sd_high(s,False) and retained(s) and archive_before_start(s)
        and s.get('mc_fault')==s.get('bp_fault')==5 and s.get('mc_fault_reason')==8
        and s.get('mc_fault_sequence')==99 and s.get('mc_fault_current_mask')==0
        and s.get('mc_fault_occurred_mask')==1024 and s.get('estop')==0)


def main():
    global ACKNOWLEDGED_RUNNING_BREAK_RAW
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--confirm-fixed-sensor-hands-away',action='store_true')
    p.add_argument('--confirm-one-clear-and-continuous-5hz',action='store_true')
    p.add_argument('--confirm-continuous-5hz-no-clear',action='store_true')
    p.add_argument('--acknowledged-running-break-report',type=Path)
    args=p.parse_args()
    if not (args.confirm_fixed_sensor_hands_away and
            (args.confirm_one_clear_and_continuous_5hz != args.confirm_continuous_5hz_no_clear)):
        p.error('Explicit fixed-sensor and one-CLEAR/manual-hold authorization required')
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    motor.checks.PAIR=(2026102509,2026102510);motor.zero_ok=zero_ready
    if args.acknowledged_running_break_report:
        if not args.confirm_continuous_5hz_no_clear:p.error('A completed ACK record must use no-clear mode')
        ACKNOWLEDGED_RUNNING_BREAK_RAW=load_acknowledged_running_break(args.acknowledged_running_break_report)
    report=dict(state='PREPARING',start_commands=0,clear_commands=0,commands=[],
                frequency_hz=5,manual_no_duration_cap=True,operator_watchdog_s=3,
                encoder_observation_only=True,firmware_writes=0,source_sd_sha256=SHA)
    if args.acknowledged_running_break_report:
        report['acknowledged_running_break_report']=str(args.acknowledged_running_break_report.resolve())
        report['retained_running_break_tick_ms']=ACKNOWLEDGED_RUNNING_BREAK_RAW['tick_ms']
    stopped=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stopped.set())
    h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),report['commands'],False)
    def save(): (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def sample():
        s=h.status()
        with (out/'status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(host_monotonic_s=time.monotonic(),status=s))+'\n')
        (out/'latest.json').write_text(json.dumps(s,indent=2)+'\n',encoding='utf-8')
        return s
    try:
        before=[]
        for _ in range(3):
            s=sample();before.append(s)
            if args.confirm_one_clear_and_continuous_5hz:
                if not acknowledgeable(s):raise RuntimeError('New pre-start event/health mismatch; no CLEAR or START')
            elif not ready(s):raise RuntimeError('Not already ready; no CLEAR authorized and no START')
            time.sleep(.15)
        (out/'before_clear.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
        if args.confirm_one_clear_and_continuous_5hz:
            report['clear_commands']=1;save()
            (out/'clear_intent.json').write_text(json.dumps(dict(command='CLEAR',attempts=1,user_authorized=True,no_retry=True))+'\n',encoding='utf-8')
            h.command('CLEAR')
        deadline=time.monotonic()+6;stable=0
        while stable<8:
            s=sample()
            if not retained(s):raise RuntimeError('Archived SD record changed')
            stable=stable+1 if ready(s) else 0
            if not stable and time.monotonic()>deadline:raise RuntimeError('One CLEAR did not restore ready; no retry')
            time.sleep(.2)
        report['post_ack_ready_samples']=stable;save()
        with operator_keepalive(h) as heartbeat:
            report['heartbeat']=heartbeat
            for cmd in ('MODE VF','SET FREQ 5'):h.command(cmd)
            s=sample()
            if not ready(s) or s.get('freq_cmd')!=5 or heartbeat['errors']:raise RuntimeError('Manual preparation failed')
            if s.get('hmi_arm_confirm')!='ARM 310V':raise RuntimeError('Unexpected ARM contract')
            h.post('/api/hv-arm',dict(action='arm',confirm='ARM 310V'),'ARM manual 5Hz hold')
            report['start_commands']=1;report['start_monotonic_s']=time.monotonic();save()
            report['start_response']=h.post('/api/start-sequence',dict(manual=True),'one START manual 5Hz hold',timeout_s=12)
            began=time.monotonic();report['state']='RUNNING';save()
            print('RUNNING: manual scalar 5Hz; AS5600 monitoring only; STOP file or web STOP ends hold.',flush=True)
            last_print=0.;settled=False
            while not stopped.is_set() and not (out/'STOP').exists():
                s=sample();now=time.monotonic()
                if s.get('state')=='SAFE' and s.get('pwm')==0 and s.get('hmi_hv_armed')==0:
                    if s.get('mc_fault') or s.get('bp_fault') or s.get('estop'):
                        report['abort_status']=s
                        raise RuntimeError('Controller stopped on a fault or E-stop; no retry')
                    report['stop_reason']='external_web_or_controller_STOP';break
                if heartbeat['errors'] or not active(s):
                    report['abort_status']=s
                    reason='SD input LOW' if s.get('mc_sd_live',{}).get('level')=='LOW' else 'Drive/SD/link protection changed'
                    raise RuntimeError(reason+'; STOP, no retry')
                if now-began>1.5 and not current_valid(s):
                    report['abort_status']=s
                    raise RuntimeError('Current measurement health changed; STOP')
                if s.get('mc_frequency_reference_valid')==1 and abs(s.get('mc_frequency_reference_hz',-1)-5)<.11:settled=True
                if now-began>6 and not settled:raise RuntimeError('5Hz reference failed to settle; STOP')
                report['elapsed_s']=round(now-began,2);report['latest_sensor']={k:s.get(k) for k in ('enc_bus_ok','enc_ok','enc_status','enc_reads','enc_errors','enc_io_error','enc_age_ms','enc_deg','enc_rpm','enc_speed_ok')}
                if now-last_print>=10:
                    print(json.dumps(dict(elapsed_s=report['elapsed_s'],field_hz=s.get('mc_frequency_reference_hz'),pwm=s['pwm'],**report['latest_sensor'])),flush=True)
                    save();last_print=now
                stopped.wait(.15)
            report.setdefault('stop_reason','operator_STOP_request')
    except Exception as e:report['error']=str(e);report['stop_reason']='health_or_communication_failure'
    finally:
        code,body=h.fail_safe_stop();report['final_stop']=dict(http=code,ok=body.get('ok'))
        report['state']='STOPPED_UNCONFIRMED'
        try:
            s=sample();report['final_status']=s
            if not motor.outputs_off(s):
                report['emergency_stop']=h.post('/api/stop-sequence',dict(emergency=True),'emergency STOP after missing OFF')
                s=sample();report['final_status']=s
            report['outputs_off_confirmed']=motor.outputs_off(s)
            if report['outputs_off_confirmed']:report['state']='STOPPED'
        except Exception as e:report['stop_confirmation_error']=str(e)
        save();h.close();print(json.dumps({k:report.get(k) for k in ('state','start_commands','clear_commands','stop_reason','error','outputs_off_confirmed')}),flush=True)
    return 0 if report.get('outputs_off_confirmed') and not report.get('error') else 1


if __name__=='__main__':raise SystemExit(main())

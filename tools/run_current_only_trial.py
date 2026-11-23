"""One scalar current-only experiment with a fixed MCU deadline. No CLEAR/retry."""
import argparse
import json
from pathlib import Path
import threading
import time

import current_only_lab as lab
import current_zero_quality
from run_current_shunt_5hz import checks, sd_high, archive_before_start
from run_wifi_nucleo_pwm_bench import WifiHmi
from wifi_bench_scenarios import operator_keepalive
from collect_wifi_telemetry import read_token

ROOT=Path(__file__).resolve().parents[1]
lab.PAIR=(2026102911,2026102912)
checks.PAIR=lab.PAIR


def zero_ready(s):
    if (s.get('fw_build'),s.get('mc_fw_build')) != lab.PAIR:return False
    # Identical ADC/zero packet contract, tested byte-for-byte against the parent.
    # Adapt only the legacy helper's firmware allow-list, none of its quality gates.
    compatible=dict(s,fw_build=2026102703,mc_fw_build=2026102704)
    return current_zero_quality.ready(compatible)


def healthy(s):
    return (checks.physical_ok(s) and checks.transport_clean(s) and zero_ready(s)
            and sd_high(s,True) and archive_before_start(s)
            and s.get('research_profile')=='air56b2_current_only'
            and s.get('enc_source')=='disabled'
            and all(s.get(k)==0 for k in ('mc_fault','bp_fault','mc_fault_current_mask','mc_fault_occurred_mask','estop')))


def deadline_observed(s,before,duration_ms):
    elapsed=s.get('run_elapsed_ms')
    return (healthy(s) and s.get('state')=='SAFE' and s.get('pwm')==0
            and type(s.get('bp_status')) is int and not(s['bp_status']&2)
            and s.get('run_id')==((before['run_id']+1)&0xffffffff)
            and s.get('run_reason')==1 and s.get('run_limit_ms')==duration_ms
            and type(elapsed) is int and duration_ms<=elapsed<=duration_ms+100
            and ((s.get('run_stop_ms',0)-s.get('run_start_ms',0))&0xffffffff)==elapsed)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target-hz',type=int,choices=range(5,51,5),default=5)
    p.add_argument('--seconds',type=float,default=5)
    p.add_argument('--plan-only',action='store_true',help='Print the plan; no board access or commands')
    p.add_argument('--confirm-powered-unloaded-autonomous',action='store_true')
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args()
    if not 1<=a.seconds<=15:p.error('MCU-bounded duration 1..15 seconds')
    if a.seconds<a.target_hz/5+2:p.error('Allow the existing 5Hz/s ramp plus >=2s plateau')
    if a.plan_only:
        print(json.dumps(dict(pair=lab.PAIR,target_hz=a.target_hz,seconds=a.seconds,
                             native_auto_stop=True,hardware_commands=0,clear_commands=0)))
        return 0
    if not a.confirm_powered_unloaded_autonomous:p.error('Powered unloaded bench and one run must be authorized')
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(passed=False,commands=[],samples=[],start_commands=0,clear_commands=0,
           frequency_hz=a.target_hz,mcu_limit_ms=round(a.seconds*1000),
           physical_rotation_verified=False,ai_control_enabled=False)
    h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),r['commands'],False)
    timer=None
    def sample():
        s=h.status();r['samples'].append(s)
        with (out/'status.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(s,ensure_ascii=False)+'\n')
        return s
    def backup_stop():
        client=WifiHmi(h.base,h.token,[],False)
        try:
            code,body=client.fail_safe_stop();r['backup_stop']=dict(http=code,ok=body.get('ok'))
        finally:client.close()
    try:
        before=sample();r['before']=before
        if not healthy(before) or not checks.off(before):raise RuntimeError('Preflight failed; no CLEAR or START')
        if (before.get('accel_hz_per_s'),before.get('decel_hz_per_s'),before.get('downmode_coast'))!=(5,1,0):
            raise RuntimeError('Unexpected ramps; no automatic parameter changes')
        if before.get('hmi_start_runlimit_s',0)<a.seconds:raise RuntimeError('Requested duration exceeds installed limit')
        with operator_keepalive(h) as heartbeat:
            h.command('MODE VF');h.command('SET FREQ '+str(a.target_hz))
            prepared=sample()
            if not healthy(prepared) or prepared.get('freq_cmd')!=a.target_hz or heartbeat['errors']:raise RuntimeError('Preparation failed')
            h.post('/api/hv-arm',{'action':'arm','confirm':'ARM 310V'},'arm one bounded current trial')
            # Backup is independent of status polling; native deadline is on Uno.
            timer=threading.Timer(a.seconds+10,backup_stop);timer.daemon=True;timer.start()
            r['start_commands']=1
            r['start_response']=h.post('/api/start-sequence',{'manual':False,'runlimit_s':a.seconds},'one MCU-bounded scalar run',timeout_s=12)
            began=time.monotonic();remote_running=False;valid_windows=set()
            while time.monotonic()-began<a.seconds+2:
                s=sample()
                if deadline_observed(s,before,r['mcu_limit_ms']):
                    r['native_auto_stop_verified']=True;r['passed']=bool(valid_windows);break
                if not healthy(s) or heartbeat['errors']:raise RuntimeError('Health changed; STOP without retry')
                if s.get('state')!='VF_RUN' or s.get('pwm')!=1:raise RuntimeError('Run not confirmed')
                if (s.get('freq_cmd')!=a.target_hz or s.get('run_id')!=((before['run_id']+1)&0xffffffff)
                    or s.get('run_limit_ms')!=r['mcu_limit_ms'] or s.get('run_reason')!=0):
                    raise RuntimeError('Experiment command or native run identity changed; STOP')
                remote=s.get('bp_status',0)&0x22
                if remote!=0x22:
                    if remote_running or s.get('run_elapsed_ms',9999)>300:raise RuntimeError('Remote PWM not confirmed')
                else:remote_running=True
                row=lab.sample(s,out.name)
                if row['valid_for_learning']:valid_windows.add(row['window_tick_ms'])
                elif s.get('run_elapsed_ms',0)>1500:raise RuntimeError('Invalid current window; STOP')
                time.sleep(.1)
            r['valid_current_windows']=len(valid_windows)
            if not r['passed']:raise RuntimeError('Native auto-stop/current window proof incomplete')
    except Exception as exc:r['passed']=False;r['error']=str(exc)
    finally:
        code,body=h.fail_safe_stop();r['final_stop']=dict(http=code,ok=body.get('ok'))
        if timer:timer.cancel();timer.join(timeout=4)
        try:
            r['final_status']=sample()
            r['outputs_off_confirmed']=checks.off(r['final_status'])
            r['passed']=r['passed'] and r['outputs_off_confirmed'] and code==200 and body.get('ok') is True
        except Exception as exc:r['passed']=False;r['final_status_error']=str(exc)
        lab.dump(out/'report.json',r);h.close()
        print(json.dumps({k:r.get(k) for k in ('passed','error','native_auto_stop_verified','valid_current_windows','outputs_off_confirmed')},ensure_ascii=False))
    return 0 if r['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

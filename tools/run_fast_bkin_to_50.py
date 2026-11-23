"""One authorized online V/f staged run with first-Break capture.

Uses existing manual mode and its 3-s operator watchdog. A separate host timer
requests STOP at 100 s. No CLEAR, retry, firmware, or calibration writes.
"""
import argparse
import json
from pathlib import Path
import threading
import time
import urllib.request

from run_fast_bkin_short_scalar import ROOT,physical_ok,off,ERROR_KEYS,capture_free
from run_manual_scalar_powered import supervisory_uart_healthy
from collect_wifi_telemetry import read_token,get_logs
from run_wifi_nucleo_pwm_bench import WifiHmi
from wifi_bench_scenarios import operator_keepalive

PLAN=tuple((hz,12 if hz==5 else 10) for hz in range(5,51,5))
PROFILE='5-to-50-steps-of-5'
MAX_RUN_S=100
HOLD_S=2
POST_STOP_DIAG_WAIT_S=9
PREPARE_STARTUP=None

def transport_clean(s):
    # Match the installed manual-scalar policy. Zephyr's cumulative NOISE
    # advisory (bit 5) is not a rejected CRC-protected frame. Keep it visible;
    # framing/overrun/parity, dropped bytes, CRC, sequence and watchdog failures
    # still stop the run. No MCU or HMI protection thresholds are changed.
    fatal=tuple(k for k in ERROR_KEYS if k not in ('uno_rx_hw_errors','uno_rx_hw_flags'))
    return (s.get('mc_transport_fault')==0 and s.get('bp_transport_fault')==0
        and all(s.get(k)==0 for k in fatal) and supervisory_uart_healthy(s))

def ready(s):
    return (off(s) and transport_clean(s) and s.get('bp_fault')==0 and s.get('mc_fault')==0
        and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0 and s.get('estop')==0)

def active(s,target):
    return (physical_ok(s) and transport_clean(s) and s.get('state')=='VF_RUN'
        and s.get('pwm')==1 and s.get('bp_status',0)&0x22==0x22
        and s.get('bp_fault')==0 and s.get('mc_fault')==0
        and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0
        and s.get('estop')==0 and s.get('hmi_hv_armed')==1
        and abs(s.get('freq_cmd',-1)-target)<.01 and s.get('manual_run_mode')==1
        and s.get('mc_frequency_reference_valid')==1 and s.get('downmode_coast')==0)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-powered-ready',action='store_true')
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args()
    if not a.confirm_powered_ready:p.error('fresh operator authorization required')
    plan=PLAN;targets=[x[0] for x in plan]
    description=' -> '.join(str(x) for x in targets)+' Hz'
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r={'pass':False,'profile':PROFILE,'requested_targets_hz':targets,'start_commands':0,'clear_commands':0,
       'flash_commands':0,'calibration_writes':0,'manual_mode':True,'host_deadline_s':MAX_RUN_S,
       'hold_at_each_target_s':HOLD_S,
       'operator_watchdog_s':3,'commands':[],'settled_steps':[],
       'physical_rotation_confirmed':False,'speed_changes_confirmed':False,
       'rotor_speed_qualified':False,'phase_current_qualified':False}
    h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),r['commands'],False)
    rows=[];collect_errors=[];done=threading.Event();expired=threading.Event();thread=None;timer=None
    def save(name,data):(out/name).write_text(json.dumps(data,indent=2)+chr(10),encoding='utf-8')
    def sample():
        s=h.status();rows.append({'source':'monitor','host_monotonic_s':time.monotonic(),'status':s});return s
    def collect():
        client=WifiHmi(h.base,h.token,[],False)
        with (out/'status.jsonl').open('a',encoding='utf-8') as f:
            while not done.is_set():
                try:
                    s=client.status();row={'source':'collector','host_monotonic_s':time.monotonic(),'status':s};rows.append(row)
                    f.write(json.dumps(row)+chr(10));f.flush()
                except Exception as exc:collect_errors.append(str(exc))
                done.wait(.15)
        client.close()
    def timeout_stop():
        expired.set();client=WifiHmi(h.base,h.token,[],False)
        code,payload=client.fail_safe_stop();r['deadline_stop']={'http':code,'ok':payload.get('ok')};client.close()
    def diag(path):
        request=urllib.request.Request(h.base+path,headers={'X-UNOQ-Control-Token':h.token})
        with h.opener.open(request,timeout=8) as response:p=json.load(response)
        if p.get('ok') is not True:raise RuntimeError('diagnostic read failed')
        return p
    try:
        before=sample();r['before']=before;save('before.json',before)
        save('before_break_snapshot.json',diag('/api/break-snapshot'))
        save('before_bkin_trace.json',diag('/api/bkin-trace'))
        (out/'before_logs.txt').write_text(get_logs(h.opener,h.base,h.token,.25),encoding='utf-8')
        if PREPARE_STARTUP is not None:
            before=PREPARE_STARTUP(h,before,save,r)
        if not ready(before):raise RuntimeError('Not clean SAFE; no CLEAR and no START')
        if not capture_free(before):
            raise RuntimeError('First Break evidence already present; no START')
        if before.get('accel_hz_per_s')!=5 or before.get('decel_hz_per_s')!=1 or before.get('downmode_coast')!=0:
            raise RuntimeError('Unexpected existing ramp settings; no parameter changes')
        with operator_keepalive(h) as heartbeat:
            for cmd in ('MODE VF','SET FREQ '+str(targets[0])):h.command(cmd)
            prepared=sample();r['prepared']=prepared
            if not ready(prepared) or not capture_free(prepared) or prepared.get('freq_cmd')!=targets[0] or heartbeat['errors']:raise RuntimeError('Preparation failed')
            thread=threading.Thread(target=collect);thread.start()
            h.post('/api/hv-arm',{'action':'arm','confirm':prepared['hmi_arm_confirm']},'ARM one online '+description+' run')
            began=time.monotonic();r['start_monotonic_s']=began
            timer=threading.Timer(MAX_RUN_S,timeout_stop);timer.daemon=True;timer.start()
            r['start_commands']=1
            r['start_response']=h.post('/api/start-sequence',{'manual':True},'single manual START '+str(targets[0])+' Hz')
            print('START confirmed; recording '+description,flush=True)
            for step,(target,timeout_s) in enumerate(plan):
                if step:h.command('SET FREQ '+str(target))
                step_start=time.monotonic();stable_since=None;stable_samples=0;observed=[]
                while True:
                    s=sample();observed.append(s.get('mc_frequency_reference_hz'))
                    if not active(s,target) or heartbeat['errors'] or collect_errors or expired.is_set():
                        r['abort_status']=s;raise RuntimeError('Active health changed; STOP without retry')
                    now=time.monotonic();at_target=abs(s['mc_frequency_reference_hz']-target)<=.11
                    if at_target:
                        if stable_since is None:stable_since=now
                        stable_samples+=1
                    else:stable_since=None;stable_samples=0
                    if stable_since is not None and now-stable_since>=HOLD_S and stable_samples>=3:break
                    if now-step_start>timeout_s or now-began>=MAX_RUN_S:
                        raise RuntimeError('Target did not settle within observation limit')
                    time.sleep(.15)
                item={'step':step+1,'target_hz':target,'elapsed_s':time.monotonic()-step_start,
                    'reference_samples_hz':observed,'stable_samples':stable_samples}
                r['settled_steps'].append(item);save('progress.json',r)
                print('Controller field reference settled at '+str(target)+' Hz',flush=True)
            r['stop_response']=h.post('/api/stop-sequence',{'emergency':False},'scheduled STOP after '+description)
            r['heartbeat']=heartbeat;r['pass']=True
    except Exception as exc:r['error']=str(exc)
    finally:
        code,payload=h.fail_safe_stop();r['final_stop']={'http':code,'ok':payload.get('ok') is True}
        try:
            s=sample();r['final_status']=s
            # Output confirmation is independent of bus/temperature health.
            confirmed=(s.get('state')=='SAFE' and s.get('pwm')==0 and s.get('hmi_hv_armed')==0
                and not(s.get('bp_status',0x22)&0x22) and 0<=s.get('mc_age_ms',999999)<300)
            if not confirmed:
                r['emergency_stop']=h.post('/api/stop-sequence',{'emergency':True},'emergency STOP after missing off confirmation')
                s=sample();r['final_status']=s
                confirmed=s.get('pwm')==0 and s.get('hmi_hv_armed')==0 and not(s.get('bp_status',0x22)&0x22) and 0<=s.get('mc_age_ms',999999)<300
            r['outputs_off_confirmed']=confirmed
            r['pass']=r['pass'] and confirmed and code==200 and payload.get('ok') is True
        except Exception as exc:r['final_status_error']=str(exc);r['pass']=False
        if timer:timer.cancel();timer.join(timeout=10)
        done.set()
        if thread:thread.join(timeout=10)
        save('samples.json',rows)
        time.sleep(POST_STOP_DIAG_WAIT_S)
        for path,name in [('/api/bkin-trace','after_bkin_trace.json'),('/api/break-snapshot','after_break_snapshot.json'),('/api/uart-reject','after_uart_reject.json')]:
            try:save(name,diag(path))
            except Exception as exc:r[name+'_error']=str(exc)
        try:
            diagnostic_status=h.status();save('after_diagnostic_status.json',diagnostic_status)
            raw=diagnostic_status.get('mc_uart_reject_hex','-')
            if raw!='-':(out/'uart_reject.bin').write_bytes(bytes.fromhex(raw))
        except Exception as exc:r['raw_uart_reject_error']=str(exc)
        try:(out/'logs.txt').write_text(get_logs(h.opener,h.base,h.token,.25),encoding='utf-8')
        except Exception as exc:r['logs_error']=str(exc)
        r['collection_errors']=collect_errors
        active_rows=[x for x in rows if x['status'].get('pwm')==1]
        r['active_samples']=len(active_rows)
        r['controller_reference_max_hz']=max((x['status'].get('mc_frequency_reference_hz',0) for x in active_rows),default=0)
        if not r.get('outputs_off_confirmed'):print('OUTPUT OFF NOT CONFIRMED: operator must switch off power',flush=True)
        save('report.json',r);h.close()
        print(json.dumps({k:r.get(k) for k in ('pass','start_commands','clear_commands','settled_steps','error','outputs_off_confirmed','controller_reference_max_hz')}),flush=True)
        print(str(out),flush=True)
    return 0 if r['pass'] else 1
if __name__=='__main__':raise SystemExit(main())

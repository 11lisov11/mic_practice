"""One5Hz trial, five-second Uno MCU deadline; no HTTP-receipt-based hold."""
import argparse
import json
from pathlib import Path
import threading
import time
import run_current_shunt_5hz as t
from current_zero_quality import ready as zero_ready
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token,get_logs
from wifi_bench_scenarios import operator_keepalive

PAIR=(2026102516,2026102510)
EXPECTED_SENSOR_MODE=4
SENSOR_MODES={'SW25':2,'POLL100':4,'FILTER100':5,'NUCLEO':6}
PAIRS={2026102516:2026102510,2026102517:2026102510,2026102518:2026102510,
       2026102601:2026102602,2026102603:2026102602,2026102605:2026102604,2026102609:2026102604,2026102701:2026102702,2026102703:2026102704}
CAPTURE_PAIRS=((2026102605,2026102604),(2026102609,2026102604),(2026102701,2026102702),(2026102703,2026102704))
ROOT=Path(__file__).resolve().parents[1]
t.checks.PAIR=PAIR;t.zero_ok=zero_ready

def configure(uno_build,sensor_mode):
    """Select only an explicit installed pair and its actual sensor owner."""
    if uno_build not in PAIRS or sensor_mode not in SENSOR_MODES:
        raise ValueError('Unsupported firmware or sensor mode')
    remote=uno_build in (2026102601,2026102603,2026102605,2026102609,2026102701,2026102703)
    if remote != (sensor_mode=='NUCLEO'):
        raise ValueError('Sensor mode does not match firmware ownership')
    global EXPECTED_SENSOR_MODE
    EXPECTED_SENSOR_MODE=SENSOR_MODES[sensor_mode]
    t.checks.PAIR=(uno_build,PAIRS[uno_build])

class RunWatchdog:
    """Bound the request, then anchor once to the independently reported run.

    MCU RUNLIMIT remains 5000ms. The host allows one second for its STOP to
    be observed; slow HTTP preparation must not consume that five-second run.
    A single anchor cannot be extended by repeated or frozen status samples.
    """
    def __init__(self,began,before,callback):
        self.began=began;self.before=before;self.callback=callback
        self.deadline=began+10;self.anchored=False;self.cancelled=False;self.fired=False
        self.cv=threading.Condition();self.thread=threading.Thread(target=self._wait,daemon=True)

    def start(self):self.thread.start()

    def observe(self,s,now):
        # Called only after the full active or bounded START health predicate.
        with self.cv:
            if self.cancelled or self.fired or self.anchored or now>=self.deadline:return False
            elapsed=s.get('run_elapsed_ms')
            if not (s.get('run_id')==((self.before['run_id']+1)&0xffffffff)
                    and s.get('run_limit_ms')==5000 and s.get('run_reason')==0
                    and type(elapsed) is int and 0<=elapsed<=5000):return False
            self.deadline=min(self.began+16,now+(5000-elapsed)/1000+1)
            self.anchored=True;self.cv.notify_all();return True

    def _wait(self):
        with self.cv:
            while not self.cancelled:
                remaining=self.deadline-time.monotonic()
                if remaining<=0:
                    self.fired=True;break
                self.cv.wait(remaining)
            if self.cancelled:return
        self.callback()

    def cancel(self):
        with self.cv:self.cancelled=True;self.cv.notify_all()

    def join(self,timeout=None):self.thread.join(timeout)

def setup_ok(s):
    if EXPECTED_SENSOR_MODE==6:
        return ((s.get('fw_build'),s.get('mc_fw_build'))==t.checks.PAIR
            and t.checks.PAIR in ((2026102601,2026102602),(2026102603,2026102602),(2026102605,2026102604),(2026102609,2026102604),(2026102701,2026102702),(2026102703,2026102704))
            and s.get('enc_source')=='nucleo_g431_i2c1' and s.get('enc_diag_mode')==6
            and s.get('enc_diag_cfg_match')==1 and s.get('enc_init_error')==0)
    filtered=(EXPECTED_SENSOR_MODE!=5 or (20000000<=s.get('enc_diag_kernel_hz',0)<=160000000
        and s.get('enc_diag_timingr',0)>0 and s.get('enc_diag_cr1',0)&1
        and ((s.get('enc_diag_cr1',0)>>8)&15)>0 and not(s.get('enc_diag_cr1',0)&(1<<12))))
    software=(EXPECTED_SENSOR_MODE!=2 or (type(s.get('enc_diag_cr1')) is int
        and not(s['enc_diag_cr1']&1)
        and all(type(s.get(k)) is int and (s[k]&0x3f)==0x35
                for k in ('enc_diag_cfg_before','enc_diag_cfg_after'))))
    return (EXPECTED_SENSOR_MODE in SENSOR_MODES.values()
        and s.get('enc_diag_mode')==EXPECTED_SENSOR_MODE and s.get('enc_diag_thread_priority')==4
        and s.get('enc_diag_cfg_match')==1 and s.get('enc_init_error')==0 and filtered and software)

def deadline_stop_observed(s,before,require_request_off=False):
    # Match a newly completed MCU event and actual fresh remote OFF. Never
    # accept merely an HTTP200 or stale SAFE snapshot as timed-stop proof.
    # ARM may still be set until this observer sends STOP/disarm. It cannot
    # invalidate already measured physical OFF or postpone its recognition.
    # At the local deadline the remote PWM bit may already be OFF while its
    # last command-request bit remains ON until the next STOP exchange. This
    # observation only permits issuing STOP/disarm; final full remote OFF is
    # independently mandatory. No active PWM, stale peer or fault is accepted.
    remote=s.get('bp_status')
    remote_off=(type(remote) is int and (remote&1)==1 and not(remote&2)
        and (not require_request_off or not(remote&0x20)))
    healthy_off=(t.checks.physical_ok(s) and t.checks.transport_clean(s) and zero_ready(s)
        and t.sd_high(s,True) and t.archive_before_start(s) and s.get('state')=='SAFE'
        and s.get('pwm')==0 and remote_off and s.get('estop')==0
        and all(s.get(k)==0 for k in ('mc_fault','bp_fault','mc_fault_current_mask','mc_fault_occurred_mask')))
    return (healthy_off and setup_ok(s) and s.get('run_id')==((before['run_id']+1)&0xffffffff)
        and s.get('run_reason')==1 and s.get('run_limit_ms')==5000
        and type(s.get('run_elapsed_ms')) is int and 5000<=s['run_elapsed_ms']<=5100
        and ((s.get('run_stop_ms',0)-s.get('run_start_ms',0))&0xffffffff)==s['run_elapsed_ms'])

def completed(s,before):
    return deadline_stop_observed(s,before,require_request_off=True)

def capture_ready(s):
    return ((s.get('fw_build'),s.get('mc_fw_build')) in CAPTURE_PAIRS
        and s.get('enc_fault_decode_valid')==1 and s.get('enc_fault_pwm_hex')=='-'
        and s.get('enc_fault_bad')==0 and isinstance(s.get('enc_fault_records'),list))

def captured_pwm_fault(s):
    return ((s.get('fw_build'),s.get('mc_fw_build')) in CAPTURE_PAIRS
        and s.get('enc_fault_decode_valid')==1
        and isinstance(s.get('enc_fault_pwm_hex'),str) and len(s['enc_fault_pwm_hex'])==320
        and any(r.get('kind')=='first_with_pwm' and r.get('pwm_moe') is True
                for r in s.get('enc_fault_records',[]) if isinstance(r,dict)))
def starting_remote(s, before, remote_was_running):
    """Brief local START publication before the first running peer reply.

    Accept only the recorded fresh peer IDLE status, at most 300 ms into the
    new MCU-timed run. Never reuse this transition after remote RUN, and keep
    every physical, fault, UART, zero, and hardware Break check active.
    """
    return (not remote_was_running and t.checks.physical_ok(s)
        and t.checks.transport_clean(s) and zero_ready(s) and t.sd_high(s,True)
        and t.archive_before_start(s) and setup_ok(s)
        and s.get('state')=='VF_RUN' and s.get('pwm')==1 and s.get('bp_status')==1
        and s.get('estop')==0 and s.get('hmi_hv_armed')==1
        and s.get('manual_run_mode')==0 and s.get('freq_cmd')==5
        and all(s.get(k)==0 for k in ('mc_fault','bp_fault','mc_fault_current_mask','mc_fault_occurred_mask'))
        and s.get('run_id')==((before['run_id']+1)&0xffffffff)
        and s.get('run_reason')==0 and s.get('run_limit_ms')==5000
        and type(s.get('run_elapsed_ms')) is int and 0<=s['run_elapsed_ms']<=300)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-powered-ready',action='store_true');p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--uno-build',type=int,choices=tuple(PAIRS),default=2026102516)
    p.add_argument('--sensor-mode',choices=tuple(SENSOR_MODES),default='POLL100')
    p.add_argument('--collect-first-i2c-fault',action='store_true')
    a=p.parse_args()
    if not a.confirm_powered_ready:p.error('Fresh autonomous powered bench confirmation required')
    try:configure(a.uno_build,a.sensor_mode)
    except ValueError as exc:p.error(str(exc))
    if a.collect_first_i2c_fault and t.checks.PAIR not in CAPTURE_PAIRS:
        p.error('First I2C capture requires an explicitly qualified capture pair')
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(passed=False,start_commands=0,clear_commands=0,flash_commands=0,commands=[],samples=[],
        mcu_limit_ms=5000,host_hold_after_http_response_s=0,host_request_deadline_s=10,
        host_run_stop_grace_s=1,host_absolute_deadline_s=16,
        expected_pair=list(t.checks.PAIR),sensor_mode=a.sensor_mode,
        collect_first_i2c_fault=a.collect_first_i2c_fault,
        physical_rotation_verified=False,absolute_current_scale_qualified=False)
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),r['commands'],False)
    stop=threading.Event();timer=None;starter=None
    def deadline():
        stop.set();client=WifiHmi(h.base,h.token,[],False)
        code,body=client.fail_safe_stop();r['host_backup_stop']={'http':code,'ok':body.get('ok')};client.close()
    def sample():
        s=h.status();row={'host_monotonic_s':time.monotonic(),'status':s};r['samples'].append(row)
        with (out/'status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
        return s
    def request_start():
        client=WifiHmi(h.base,h.token,r['commands'],False)
        try:r['start_response']=client.post('/api/start-sequence',{'runlimit_s':5.0},'single MCU-timed5s START')
        except Exception as exc:r['start_response_error']=str(exc)
        finally:client.close()
    try:
        s=sample();r['before']=s;save()
        if not (t.ready(s) and setup_ok(s) and s.get('enc_bus_ok')==1 and s.get('enc_io_error')==0
                and s.get('enc_age_ms',9999)<100 and type(s.get('run_id')) is int):
            raise RuntimeError('Preflight failed; no automatic CLEAR or mode switching')
        if a.collect_first_i2c_fault and not capture_ready(s):
            raise RuntimeError('First-PWM capture is not empty/verified; no erase or automatic retry')
        with operator_keepalive(h) as heartbeat:
            h.command('MODE VF');h.command('SET FREQ 5');s=sample()
            if not t.ready(s) or not setup_ok(s) or s.get('freq_cmd')!=5 or heartbeat['errors']:
                raise RuntimeError('5Hz setup failed')
            if s.get('hmi_arm_confirm')!='ARM 310V':raise RuntimeError('Unexpected arm contract')
            h.post('/api/hv-arm',{'action':'arm','confirm':'ARM 310V'},'arm one MCU-timed5s trial')
            began=time.monotonic();r['request_monotonic_s']=began;r['start_commands']=1;save()
            timer=RunWatchdog(began,r['before'],deadline);timer.start()
            starter=threading.Thread(target=request_start,daemon=True);starter.start()
            seen_running=False;remote_was_running=False
            while not stop.is_set() and time.monotonic()-began<16:
                s=sample()
                if heartbeat['errors']:raise RuntimeError('Operator link health changed')
                if deadline_stop_observed(s,r['before']):
                    r['completion']=s;timer.cancel();break
                if s.get('pwm')==1:
                    seen_running=True
                    strict_active=(t.checks.active(s) and zero_ready(s) and t.sd_high(s,True) and setup_ok(s))
                    if strict_active:
                        remote_was_running=True
                    elif starting_remote(s,r['before'],remote_was_running):
                        r.setdefault('remote_start_transition_samples',[]).append(s)
                    else:
                        raise RuntimeError('Active drive/SD/UART health changed; STOP without retry')
                    if timer.observe(s,time.monotonic()):
                        r['host_run_deadline_monotonic_s']=timer.deadline
                    # Sensor errors are measured, never fed into scalar control.
                elif seen_running:
                    raise RuntimeError('Stopped without matching normal MCU deadline evidence')
                elif not t.checks.physical_ok(s) or s.get('estop') or s.get('mc_transport_fault'):
                    raise RuntimeError('Drive/link fault before first running sample')
                time.sleep(.12)
            if 'completion' not in r:raise RuntimeError('No verified MCU5s completion before host deadline')
            timer.cancel();r['passed']=True;r['heartbeat']=heartbeat
    except Exception as exc:r['error']=str(exc)
    finally:
        code,body=h.fail_safe_stop();r['final_stop']={'http':code,'ok':body.get('ok')}
        if timer:timer.cancel();timer.join(timeout=9)
        if starter:starter.join(timeout=9)
        try:
            s=sample();r['final_status']=s;r['outputs_off_confirmed']=t.checks.off(s)
            if not r['outputs_off_confirmed']:
                r['emergency_stop']=h.post('/api/stop-sequence',{'emergency':True},'OFF not confirmed')
                s=sample();r['final_status']=s;r['outputs_off_confirmed']=t.checks.off(s)
            r['passed']=r['passed'] and r['outputs_off_confirmed'] and code==200 and body.get('ok') is True
            active=[x['status'] for x in r['samples'] if x['status'].get('pwm')==1]
            windows={s['mc_current_window_tick_ms'] for s in active if s.get('mc_current_telemetry_valid')==1
                     and s.get('mc_frequency_reference_valid')==1 and s.get('mc_frequency_reference_hz')==5
                     and s.get('mc_current_window_ms',0)>=199 and not(s.get('mc_current_flags',0)&4)}
            r['distinct_valid5hz_windows']=len(windows)
            if len(windows)<2:r['passed']=False;r.setdefault('error','Timed OFF observed but fewer than2 valid5Hz current windows')
            if a.collect_first_i2c_fault and r['outputs_off_confirmed']:
                # Passive pages are sent only after PWM is off. Waiting here
                # never extends the five-second run or sends another START.
                end=time.monotonic()+12
                while time.monotonic()<end:
                    s=sample()
                    if not t.checks.off(s):
                        raise RuntimeError('OFF changed during passive capture collection')
                    r['after_capture_status']=s
                    if captured_pwm_fault(s):
                        r['first_i2c_pwm_fault']=s['enc_fault_records'];break
                    time.sleep(.2)
                r['first_i2c_pwm_fault_captured']=captured_pwm_fault(s)
                r['i2c_errors_delta']=s.get('enc_errors',0)-r['before'].get('enc_errors',0)
                (out/'first_i2c_capture.json').write_text(json.dumps(dict(
                    captured=r['first_i2c_pwm_fault_captured'],records=s.get('enc_fault_records',[]),
                    first_hex=s.get('enc_fault_first_hex'),pwm_hex=s.get('enc_fault_pwm_hex'),
                    pages_good=s.get('enc_fault_good'),pages_bad=s.get('enc_fault_bad')),
                    indent=2)+'\n',encoding='utf-8')
                if r['i2c_errors_delta']>0 and not r['first_i2c_pwm_fault_captured']:
                    r['passed']=False;r.setdefault('capture_error','I2C errors observed but no complete first-PWM record delivered')
                (out/'after_logs.txt').write_text(get_logs(h.opener,h.base,h.token,.5),encoding='utf-8')
        except Exception as exc:r['passed']=False;r['final_status_error']=str(exc)
        save();h.close()
        print(json.dumps({k:r.get(k) for k in ('passed','error','start_commands','clear_commands','outputs_off_confirmed','distinct_valid5hz_windows')}))
        if not r.get('outputs_off_confirmed'):print('OUTPUT OFF NOT CONFIRMED: switch off power')
    return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

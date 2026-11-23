"""One operator-prepared manual V/f 5 -> 10 -> 5 Hz test, followed by confirmed STOP."""
import argparse
import json
import math
import time
from pathlib import Path
from collect_wifi_telemetry import get_logs
from wifi_bench_scenarios import operator_keepalive
import pwm_filter_hardware_session as bench

ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026101505,2026101504)
ERRORS=('bp_bad_cnt','bp_bad_integrity','bp_bad_sequence','mc_uart_error_flags',
        'mc_last_uart_error_flags','uno_tx_short_writes','bp_break_rx_bad')

def supervisory_uart_healthy(s):
    # Zephyr UART_ERROR_NOISE is bit 5, unlike the wire protocol's UV3_NE bit 2.
    # The MCU already applies CRC, freshness, semantic checks, loss budget and watchdog.
    flags=s.get('uno_rx_hw_flags');count=s.get('uno_rx_hw_errors')
    return (type(flags) is int and type(count) is int and flags>=0 and count>=0
        and (flags & ~32)==0 and (count==0 or flags==32) and s.get('uno_rx_dropped')==0)

def healthy(s):
    return ((s.get('fw_build'),s.get('mc_fw_build'))==PAIR
        and all(math.isfinite(float(s.get(k,-1))) and 250<=float(s[k])<350 for k in ('vdc','bp_vdc'))
        and s.get('bp_age_ms',9999)<300 and s.get('bp_transport_fault')==0
        and all(s.get(k)==0 for k in ERRORS)
        and supervisory_uart_healthy(s)
        and s.get('bp_temp_valid')==1 and s.get('bp_temp_fault')==0 and s.get('bp_temp_c',1000)<80
        and s.get('bp_softstart_ready')==1 and s.get('hmi_vbus_hv_calibrated')==1
        and s.get('hmi_manual_scalar_supported')==1
        and all(s.get(k)==0 for k in ('precharge','pfc','brake','bp_ext')))

def startup_fault_acknowledgable(s):
    """Only the archived pre-START UV / driver-break startup record, after bus recovery."""
    try:
        if not (s['mc_fault_reason']==8 and s['mc_fault_current_mask'] in (0,4)
                and s['mc_fault_occurred_mask'] in (4,0x400,0x404)
                and s['mc_uart_error_flags']==s['mc_last_uart_error_flags']==s['mc_last_bad_reason']==0):
            return False
        if s['mc_fault_occurred_mask'] & 0x400:
            records={x['kind']:x for x in s['mc_break_snapshots']}
            first=records['first_since_boot'];start=records['first_start_window']
            return (first['captured'] and not first['event']['moe_at_irq']
                and not first['event']['during_start_request_window'] and not start['captured']
                and first['raw']['context_valid']==0 and s['mc_fault_sequence']==0
                and 0<=first['raw']['tick_ms']<=5000)
        return True
    except (KeyError,TypeError):
        return False

def run(profile='basic'):
    plans={'basic':((5,12),(10,10),(5,18)),
           'full50':((5,12),(20,20),(50,30),(20,95),(5,55))}
    plan=plans[profile]
    session=bench.Session(ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1')
    assert tuple(session.state['working_pair'])==PAIR==bench.PROD
    # These flags require a fresh response to the physical preparation request.
    assert session.state.get('manual_scalar_powered_preparation_confirmed')
    assert session.state.get('operator_powerbank_and_power_on_confirmed')
    assert session.state.get('pc_usb_disconnected') and session.state.get('saleae_all_probes_disconnected')
    assert session.state.get('mains_on') and session.state.get('j4_15v_on')
    package=Path(session.state['uart_recovery_candidate'])
    out=package/('powered_manual_'+str(time.time_ns()));out.mkdir()
    h=session.hmi(False);offset=len(h.commands)
    report=dict(pair=list(PAIR),pass_=False,firmware_writes=0,calibration_writes=0,
        start_commands=0,clear_commands=0,requested_targets_hz=[x[0] for x in plan],test_profile=profile,
        accel_hz_per_s=2,decel_hz_per_s=.5,automatic_stop=True,
        active_pwm_waveform_measured=False,rotor_speed_measured=False,
        current_telemetry_qualified=False,physical_rotation_confirmed=False)
    samples=[]
    def sample():
        s=h.status();samples.append(dict(host_monotonic_s=time.monotonic(),status=s));return s
    def active(s,hb):
        if not (healthy(s) and s['state']=='VF_RUN' and s['pwm']==1 and (s['bp_status']&0x22)==0x22
                and s['bp_fault']==0 and s['estop']==0 and s['hmi_hv_armed']==1
                and s.get('manual_run_mode')==1 and s.get('hmi_run_continuous')==1
                and s.get('mc_frequency_reference_valid')==1 and not hb['errors']):
            report['abort_status']=s;raise RuntimeError('Active health or controller reference changed; STOP')
    try:
        session.hashes('manual_powered_before_hashes')
        before=sample();report['before']=before
        (out/'before_clear_full.json').write_text(json.dumps(before,indent=2))
        (out/'before_logs.txt').write_text(get_logs(session.opener,h.base,session.token,1),encoding='utf-8')
        assert healthy(before) and before['state']=='SAFE' and before['pwm']==0 and not(before['bp_status']&0x22)
        assert before['hmi_hv_armed']==0
        if before['bp_fault']:
            assert startup_fault_acknowledgable(before)
        with operator_keepalive(h) as heartbeat:
            h.command('STOP')
            if before['bp_fault']:
                h.command('CLEAR');report['clear_commands']=1
            deadline=time.monotonic()+5
            while True:
                s=sample()
                if healthy(s) and s['state']=='SAFE' and s['pwm']==0 and s['bp_fault']==0 and s['estop']==0:break
                if time.monotonic()>deadline:raise RuntimeError('Single startup acknowledgement did not clear; no START')
                time.sleep(.2)
            for cmd in ('MODE VF','SET ACCEL 2','SET DECEL 0.5','SET DOWNMODE RAMP','SET FREQ 5'):h.command(cmd)
            prepared=sample();assert healthy(prepared) and prepared['freq_cmd']==5
            h.post('/api/hv-arm',{'action':'arm','confirm':prepared['hmi_arm_confirm']},'manual scalar ARM')
            began=time.monotonic();report['start_commands']=1;report['start_monotonic_s']=began
            report['start_response']=h.post('/api/start-sequence',{'manual':True},'manual scalar START at 5 Hz')
            print('Manual START confirmed; observing '+' -> '.join(str(x[0]) for x in plan)+' Hz',flush=True)
            report['settled_steps']=[]
            for target,timeout in plan:
                if target!=5 or report['settled_steps']:h.command('SET FREQ '+str(target))
                start_step=time.monotonic();stable_since=None;field=[]
                while True:
                    s=sample();active(s,heartbeat);field.append(s['mc_frequency_reference_hz'])
                    assert abs(s['freq_cmd']-target)<.01
                    reached=abs(s['mc_frequency_reference_hz']-target)<=.11
                    stable_since=(stable_since or time.monotonic()) if reached else None
                    if stable_since is not None and time.monotonic()-stable_since>=2:break
                    if time.monotonic()-start_step>timeout:raise RuntimeError('Controller field reference did not settle at '+str(target))
                    time.sleep(.15)
                report['settled_steps'].append(dict(target_hz=target,observed_elapsed_s=time.monotonic()-start_step,field_reference_samples_hz=field))
                print('Controller field reference settled at '+str(target)+' Hz',flush=True)
            # Also observe continuous operation beyond the former 30-second arm TTL.
            while time.monotonic()-began<36:
                active(sample(),heartbeat);time.sleep(.2)
            report['continuous_observed_until_s']=time.monotonic()-began
            report['stop_response']=h.post('/api/stop-sequence',{'emergency':False},'manual scalar final STOP')
            report['heartbeat']=heartbeat;report['pass_']=True
    except Exception as e:report['error']=type(e).__name__+': '+str(e)
    finally:
        code,result=h.fail_safe_stop();report['final_stop']=dict(http_status=code,ok=result.get('ok') is True)
        try:
            final=sample();report['final_status']=final
            report['outputs_off_confirmed']=final['state']=='SAFE' and final['pwm']==0 and not(final['bp_status']&0x22) and final['hmi_hv_armed']==0
            report['pass_']=report['pass_'] and report['outputs_off_confirmed'] and code==200 and result.get('ok') is True
        except Exception as e:report['final_status_error']=str(e);report['pass_']=False
        try:(out/'logs.txt').write_text(get_logs(session.opener,h.base,session.token,1),encoding='utf-8')
        except Exception as e:report['logs_error']=str(e)
        report['commands']=h.commands[offset:];report['pass']=report.pop('pass_')
        (out/'samples.json').write_text(json.dumps(samples,indent=2))
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        session.state.update(manual_scalar_powered_report=str(out/'report.json'),manual_scalar_powered_qualified=report['pass'])
        session.save();h.close();print(json.dumps({k:report.get(k) for k in ('pass','error','outputs_off_confirmed','continuous_observed_until_s')}),flush=True);print(str(out),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true')
    parser.add_argument('--profile',choices=('basic','full50'),default='basic');args=parser.parse_args()
    if args.run:run(args.profile)
    else:print('Prepared only. --run also requires fresh confirmed physical preparation flags.')

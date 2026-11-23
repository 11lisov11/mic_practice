"""One authorized normal 5 Hz powered run; retain UART recovery and always STOP."""
import json
import argparse
import math
import threading
import time
from pathlib import Path
from collect_wifi_telemetry import get_status, get_logs
from wifi_bench_scenarios import operator_keepalive
import pwm_filter_hardware_session as bench

ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026101413,2026101412)
ERRORS=('bp_bad_cnt','bp_bad_integrity','bp_bad_sequence','mc_uart_error_flags',
        'mc_last_uart_error_flags','uno_rx_hw_errors','uno_tx_short_writes','bp_break_rx_bad')

def transport_ok(s):
    return (s.get('bp_transport_fault')==0 and all(s.get(k)==0 for k in ERRORS)
            and 0<=s.get('bp_age_ms',9999)<300)

def physical_ok(s,check_transport=True):
    return ((s.get('fw_build'),s.get('mc_fw_build'))==PAIR
      and all(math.isfinite(float(s[k])) and 250<=float(s[k])<=360 for k in ('vdc','bp_vdc'))
      and s.get('bp_temp_valid')==1 and s.get('bp_temp_fault')==0 and s.get('bp_temp_c',1000)<80
      and s.get('bp_softstart_ready')==1 and s.get('hmi_vbus_hv_calibrated')==1
      and all(s.get(k)==0 for k in ('precharge','pfc','brake','bp_ext'))
      and (transport_ok(s) or not check_transport))

def main(previous_path=None):
    global PAIR
    session=bench.Session(ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1')
    PAIR=tuple(session.state['working_pair'])
    assert PAIR==bench.PROD and PAIR in ((2026101413,2026101412),(2026101415,2026101414))
    assert session.state.get('operator_powerbank_and_power_on_confirmed')
    assert session.state.get('pc_usb_disconnected') and session.state.get('mains_on') and session.state.get('j4_15v_on')
    package=Path(session.state['uart_recovery_candidate'])
    out=package/('powered_vf_'+str(time.time_ns()));out.mkdir()
    report=dict(schema='mic_ai.uart_recovery_powered_vf.v1',pair=list(PAIR),pass_=False,
        requested_frequency_hz=5,host_stop_after_s=10,controller_backup_limit_s=15,
        firmware_writes=0,calibration_writes=0,clear_commands=0,start_commands=0,
        one_shot_gate_used=False,uses_speed_sensor=False,physical_rotation_verified=False,
        measured_rotor_speed_verified=False,current_telemetry_qualified=False,commands=[])
    hmi=session.hmi(False);command_offset=len(hmi.commands)
    stop=threading.Event();samples=[];collection_errors=[]
    def collect():
        while not stop.is_set():
            try:
                s=get_status(session.opener,hmi.base)
                samples.append(dict(host_monotonic_s=time.monotonic(),status=s))
            except Exception as e:collection_errors.append(str(e))
            stop.wait(.15)
    thread=None
    try:
        session.hashes('uart_recovery_before_powered_start_hashes')
        before=hmi.status();report['before']=before
        (out/'before_clear_full.json').write_text(json.dumps(before,indent=2))
        assert physical_ok(before,check_transport=previous_path is None) and before['state']=='SAFE' and before['pwm']==0
        assert not(before['bp_status']&0x22) and before['hmi_hv_armed']==0
        retry_owned=False
        if previous_path is not None:
            previous=json.loads(previous_path.read_text());old=previous['final_status']
            keys=('fw_build','mc_fw_build','mc_fault_reason','mc_fault_sequence','mc_fault_motor_state',
              'mc_fault_current_mask','mc_fault_occurred_mask','mc_last_bad_reason',
              'mc_uart_error_flags','mc_last_uart_error_flags','bp_bad_cnt','bp_transport_fault',
              'bp_ne_observed','bp_ne_accepted','bp_recovered_drops')
            assert previous['start_commands']==1 and previous['outputs_off_confirmed']
            assert before['mc_fault_reason']==12 and before['mc_fault_motor_state']==6
            assert before['mc_fault_current_mask']==before['mc_fault_occurred_mask']==0
            assert before['bp_transport_fault']==5 and before['mc_uart_error_flags']==4
            assert before['bp_bad_cnt']==1 and before['estop']==1 and before['bp_fault']==1
            assert all(before[k]==old[k] for k in keys)
            assert not any(x['captured'] for x in before['mc_break_snapshots'] if x['kind']=='first_start_window')
            retry_owned=True;report['operator_requested_one_repeat']=True
            report['previous_fault_record']=str(previous_path)
        if before['bp_fault'] and not retry_owned:
            assert before['mc_fault_reason']==8 and before['mc_uart_error_flags']==0
            assert before['mc_fault_current_mask'] in (0,4)
            occurred=before['mc_fault_occurred_mask']
            assert occurred in (0,4,0x404)
            if occurred==0x404:
                records={x['kind']:x for x in before['mc_break_snapshots']}
                first=records['first_since_boot'];start=records['first_start_window']
                assert first['captured'] and not first['event']['moe_at_irq']
                assert not first['event']['during_start_request_window'] and not start['captured']
                assert first['raw']['context_valid']==0 and before['mc_fault_sequence']==0
        with operator_keepalive(hmi) as heartbeat:
            hmi.command('STOP')
            if before['bp_fault']:
                hmi.command('CLEAR');report['clear_commands']=1
            deadline=time.monotonic()+5
            while True:
                after=hmi.status()
                if physical_ok(after) and after['state']=='SAFE' and after['pwm']==0 and after['bp_fault']==0 and after['estop']==0:break
                if time.monotonic()>deadline:raise RuntimeError('One CLEAR did not produce clean SAFE; no retry or START')
                time.sleep(.1)
            report['after_clear']=after
            hmi.command('MODE VF');hmi.command('SET FREQ 5')
            prepared=hmi.status();assert physical_ok(prepared) and prepared['bp_fault']==0
            report['prepared']=prepared
            thread=threading.Thread(target=collect);thread.start()
            hmi.post('/api/hv-arm',{'action':'arm','confirm':prepared['hmi_arm_confirm']},'normal repaired UART HV ARM')
            assert not heartbeat['errors']
            began=time.monotonic();report['start_monotonic_s']=began;report['start_commands']=1
            report['start_response']=hmi.post('/api/start-sequence',{'runlimit_s':15},'normal repaired UART 5 Hz START')
            print('START confirmed: 5 Hz run in progress',flush=True)
            while time.monotonic()-began<10:
                s=hmi.status();samples.append(dict(host_monotonic_s=time.monotonic(),status=s))
                if not(physical_ok(s) and s['state']=='VF_RUN' and s['pwm']==1
                       and (s['bp_status']&0x22)==0x22 and s['bp_fault']==0 and s['estop']==0
                       and s['freq_cmd']==5 and s['hmi_hv_armed']==1 and not heartbeat['errors']):
                    report['abort_status']=s;raise RuntimeError('Active physical/transport health changed')
                time.sleep(.15)
            report['stop_response']=hmi.post('/api/stop-sequence',{'emergency':False},'normal repaired UART host STOP')
            report['heartbeat']=heartbeat
            report['pass_']=True
    except Exception as e:
        report['error']=type(e).__name__+': '+str(e)
    finally:
        code,result=hmi.fail_safe_stop();report['final_stop']=dict(http_status=code,ok=result.get('ok') is True)
        try:
            final=hmi.status();report['final_status']=final
            off=final['state']=='SAFE' and final['pwm']==0 and not(final['bp_status']&0x22)
            report['outputs_off_confirmed']=off
            report['pass_']=report['pass_'] and off and transport_ok(final) and code==200 and result.get('ok') is True
        except Exception as e:
            report['final_status_error']=str(e);report['pass_']=False
        stop.set()
        if thread:thread.join(timeout=12)
        active=[x for x in samples if x['status'].get('pwm')==1]
        report['active_samples']=len(active)
        report['active_observed_span_s']=round(active[-1]['host_monotonic_s']-active[0]['host_monotonic_s'],3) if active else 0
        report['reported_reference_frequency_max_hz']=max((x['status'].get('freq',0) for x in active),default=0)
        report['collection_errors']=collection_errors
        if samples:
            report['uart_recovered_drops_final']=samples[-1]['status'].get('bp_recovered_drops')
            report['ne_accepted_final']=samples[-1]['status'].get('bp_ne_accepted')
            report['ne_observed_final']=samples[-1]['status'].get('bp_ne_observed')
        try:(out/'logs.txt').write_text(get_logs(session.opener,hmi.base,session.token,1))
        except Exception as e:report['logs_error']=str(e)
        report['pass']=report.pop('pass_')
        report['commands']=hmi.commands[command_offset:]
        (out/'samples.json').write_text(json.dumps(samples,indent=2))
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        session.state.update(uart_recovery_powered_report=str(out/'report.json'),uart_recovery_powered_test_complete=report['pass'])
        session.save();hmi.close()
        print(json.dumps({k:report.get(k) for k in ['pass','error','active_samples','active_observed_span_s','reported_reference_frequency_max_hz','outputs_off_confirmed','ne_observed_final','ne_accepted_final','uart_recovered_drops_final']}),flush=True)
        print(str(out),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retry-previous',type=Path)
    main(parser.parse_args().retry_previous)

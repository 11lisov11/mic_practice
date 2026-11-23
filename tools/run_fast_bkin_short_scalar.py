"""One authorized 5-Hz trial; host STOP 5 s after START confirmation, MCU 7 s.

No firmware/calibration writes, no service outputs, no repeat after failure.
"""
import argparse
import json
import math
from pathlib import Path
import threading
import time
import urllib.request

from collect_wifi_telemetry import read_token,get_logs
from run_wifi_nucleo_pwm_bench import WifiHmi
from wifi_bench_scenarios import operator_keepalive
from run_manual_scalar_powered import supervisory_uart_healthy

ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026101805,2026101804)
ERROR_KEYS=('mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags',
    'mc_last_uart_error_flags','uno_rx_hw_errors','uno_rx_hw_flags','uno_rx_dropped',
    'uno_tx_short_writes','mc_break_rx_bad','mc_break_wave_bad_pages')

def physical_ok(s):
    try:
        return ((s['fw_build'],s['mc_fw_build'])==PAIR and s['mode']=='VF'
          and s['rpc_schema_version']==3 and s['mc_capabilities']==1
          and s['bp_mcsdk_telemetry']==1 and s['bp_vbus_valid']==1
          and s['bp_softstart_ready']==1 and s['hmi_vbus_hv_calibrated']==1
          and s['hmi_bounded_start_request_supported']==1
          and s['hmi_arm_profile']=='hv'
          and all(type(s[k]) in (int,float) and math.isfinite(s[k]) and 250<=s[k]<=350 for k in ('vdc','bp_vdc'))
          and abs(s['bp_vbus_raw']*.1-s['vdc'])<=1
          and all(type(s[k]) in (int,float) and 0<=s[k]<300 for k in ('mc_age_ms','bp_vbus_age_ms','bp_temp_age_ms'))
          and s['bp_temp_valid']==1 and s['bp_temp_fault']==0 and math.isfinite(s['bp_temp_c']) and s['bp_temp_c']<80
          and all(s[k]==0 for k in ('precharge','pfc','brake','bp_ext')))
    except (KeyError,TypeError,ValueError,OverflowError):return False

def off(s):
    return (physical_ok(s) and s.get('state')=='SAFE' and s.get('pwm')==0
        and s.get('hmi_hv_armed')==0 and not(s.get('bp_status',0x22)&0x22))

def transport_clean(s):
    # Same advisory policy as the already-used manual scalar runner. CRC,
    # sequence, framing/overrun/parity, transport and loss remain fatal.
    fatal=tuple(k for k in ERROR_KEYS if k not in ('uno_rx_hw_errors','uno_rx_hw_flags'))
    return (s.get('mc_transport_fault')==0 and s.get('bp_transport_fault')==0
        and all(s.get(k)==0 for k in fatal) and supervisory_uart_healthy(s))

def capture_free(s):
    records=s.get('mc_break_snapshots',[])
    return (s.get('mc_break_wave_hex')=='-' and len(records)==2
        and all(x.get('available') and not x.get('captured')
            and x.get('reason')=='no_recorded_break' for x in records))

def ready(s):
    return (off(s) and transport_clean(s) and s.get('bp_fault')==0 and s.get('mc_fault')==0
        and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0 and s.get('estop')==0)

def active(s):
    return (physical_ok(s) and transport_clean(s) and s.get('state')=='VF_RUN'
        and s.get('pwm')==1 and s.get('bp_status',0)&0x22==0x22
        and s.get('bp_fault')==0 and s.get('mc_fault')==0
        and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0
        and s.get('estop')==0 and s.get('hmi_hv_armed')==1
        and abs(s.get('freq_cmd',-1)-5)<.01 and s.get('manual_run_mode')==0
        and s.get('mc_frequency_reference_valid')==1)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-powered-ready',action='store_true')
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args()
    if not a.confirm_powered_ready:p.error('fresh operator authorization and autonomous powered bench required')
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    rep={'pass':False,'start_commands':0,'clear_commands':0,'flash_commands':0,'calibration_writes':0,
        'frequency_hz':5,'host_stop_after_s':5,'mcu_backup_limit_s':7,'commands':[],
        'host_stop_reference':'START confirmation',
        'physical_rotation_confirmed':False,'rotor_speed_qualified':False,'phase_current_qualified':False}
    h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),rep['commands'],False)
    samples=[];collection_errors=[];done=threading.Event();thread=None;timer=None
    deadline_stop=threading.Event()
    def stop_at_deadline():
        deadline_stop.set();client=WifiHmi(h.base,h.token,[],False)
        code,result=client.fail_safe_stop()
        rep['deadline_stop']={'http':code,'ok':result.get('ok') is True}
        client.close()
    def collect():
        client=WifiHmi(h.base,h.token,[],False)
        with (out/'status.jsonl').open('a',encoding='utf-8') as f:
            while not done.is_set():
                try:
                    row={'host_monotonic_s':time.monotonic(),'status':client.status()};samples.append(row)
                    f.write(json.dumps(row)+chr(10));f.flush()
                except Exception as exc:collection_errors.append(str(exc))
                done.wait(.15)
        client.close()
    def save(name,data): (out/name).write_text(json.dumps(data,indent=2)+chr(10),encoding='utf-8')
    def diag(path):
        request=urllib.request.Request(h.base+path,headers={'X-UNOQ-Control-Token':h.token})
        with h.opener.open(request,timeout=8) as response: payload=json.load(response)
        if payload.get('ok') is not True:raise RuntimeError('diagnostic read rejected')
        return payload
    try:
        before=h.status();rep['before']=before;save('before_clear.json',before)
        save('before_break_snapshot.json',diag('/api/break-snapshot'))
        save('before_bkin_trace.json',diag('/api/bkin-trace'))
        (out/'before_logs.txt').write_text(get_logs(h.opener,h.base,h.token,.5),encoding='utf-8')
        if not ready(before) or not capture_free(before):raise RuntimeError('Not clean SAFE with free first capture; no START/CLEAR')
        with operator_keepalive(h) as heartbeat:
            for cmd in ('MODE VF','SET FREQ 5'):h.command(cmd)
            s=h.status();rep['prepared']=s
            if not ready(s) or not capture_free(s) or s.get('freq_cmd')!=5 or heartbeat['errors']:raise RuntimeError('5-Hz preparation failed')
            if s.get('hmi_arm_confirm')!='ARM 310V':raise RuntimeError('Unexpected arm contract')
            thread=threading.Thread(target=collect);thread.start()
            h.post('/api/hv-arm',{'action':'arm','confirm':'ARM 310V'},'arm one bounded 5 Hz trial')
            began=time.monotonic();rep['start_monotonic_s']=began;rep['start_commands']=1
            # The existing endpoint sets BOUNDED and MCU RUNLIMIT before START.
            rep['start_response']=h.post('/api/start-sequence',{'runlimit_s':7.0},'single bounded START 5 Hz')
            confirmed=time.monotonic();rep['start_confirmed_monotonic_s']=confirmed
            timer=threading.Timer(5,stop_at_deadline);timer.daemon=True;timer.start()
            print('START confirmed at 5 Hz; recording until automatic host STOP',flush=True)
            while time.monotonic()-confirmed<5 and not deadline_stop.is_set():
                s=h.status()
                if deadline_stop.is_set():break
                if not active(s) or heartbeat['errors'] or collection_errors:
                    rep['abort_status']=s;raise RuntimeError('Active status changed; stopping without retry')
                time.sleep(.15)
            rep['stop_response']=h.post('/api/stop-sequence',{'emergency':False},'scheduled STOP 5 s after confirmation')
            rep['heartbeat']=heartbeat;rep['pass']=True
    except Exception as exc:rep['error']=str(exc)
    finally:
        if timer:timer.cancel()
        code,result=h.fail_safe_stop();rep['final_stop']={'http':code,'ok':result.get('ok') is True}
        try:
            s=h.status();rep['final_status']=s
            rep['outputs_off_confirmed']=off(s)
            if not rep['outputs_off_confirmed']:
                rep['emergency_stop']=h.post('/api/stop-sequence',{'emergency':True},'emergency STOP: ordinary off not confirmed')
                s=h.status();rep['final_status']=s;rep['outputs_off_confirmed']=off(s)
            rep['pass']=rep['pass'] and rep['outputs_off_confirmed'] and code==200 and result.get('ok') is True
        except Exception as exc:rep['final_status_error']=str(exc);rep['pass']=False
        done.set()
        if thread:thread.join(timeout=10)
        # After OFF, allow one full diagnostic-page cycle before concluding
        # that a fault wave was not recorded. No CLEAR/rearm/retry here.
        time.sleep(5)
        for path,name in [('/api/bkin-trace','after_bkin_trace.json'),('/api/break-snapshot','after_break_snapshot.json')]:
            try:save(name,diag(path))
            except Exception as exc:rep[name+'_error']=str(exc)
        try:(out/'logs.txt').write_text(get_logs(h.opener,h.base,h.token,.5),encoding='utf-8')
        except Exception as exc:rep['logs_error']=str(exc)
        active_rows=[x for x in samples if x['status'].get('pwm')==1]
        rep['active_samples']=len(active_rows)
        rep['active_observed_span_s']=(active_rows[-1]['host_monotonic_s']-active_rows[0]['host_monotonic_s']) if len(active_rows)>1 else 0
        rep['controller_reference_max_hz']=max((x['status'].get('mc_frequency_reference_hz',0) for x in active_rows),default=0)
        rep['target_samples']=sum(x['status'].get('mc_frequency_reference_valid')==1 and
            abs(x['status'].get('mc_frequency_reference_hz',-1)-5)<=.11 for x in active_rows)
        if rep['target_samples']<2:rep['pass']=False;rep.setdefault('error','5-Hz field reference not confirmed twice')
        rep['collection_errors']=collection_errors
        if rep.get('outputs_off_confirmed') is not True:print('OUTPUT OFF NOT CONFIRMED: operator must switch off power',flush=True)
        save('report.json',rep);h.close()
        print(json.dumps({k:rep.get(k) for k in ('pass','start_commands','clear_commands','error','outputs_off_confirmed','active_samples','active_observed_span_s','controller_reference_max_hz')}),flush=True)
        print(str(out),flush=True)
    return 0 if rep['pass'] else 1
if __name__=='__main__':raise SystemExit(main())

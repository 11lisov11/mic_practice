"""Existing bounded5s runner, stationary sensor, motor disconnected by operator.

Keeps the raw stale Uno diagnostic cache intact. New errors are counted from
the reset Nucleo counters; an old cached fault is never called a new capture.
"""
import argparse,json,sys,time
from pathlib import Path
import run_persistent_pe_as5600_5hz as existing
import cold_boot_sd_trial as cold
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token

ROOT=Path(__file__).resolve().parents[1]
RUN_FIELDS=cold.ZERO_RUN
OLD=ROOT/'artifacts/live_bench_20261028/dir_fixed_powered_5hz_r1/trial'

def stamp(s):
 return {k:s.get(k) for k in RUN_FIELDS}

def boot_proof_ok(proof,old):
 try:
  s=proof['status'];r=proof['report'];c=old['completion'];reset=proof['reset']
  reset_seen=(reset['after_initial_reads']<reset['before_reset_reads'] and reset['after_initial_errors']==0<reset['before_reset_errors'] and reset['after_initial_UART_bad']==0 and reset['before_and_after_peer']==2026102710)
  return (r['passed'] and r['Nucleo_B2_operator_confirmed'] and r['motor_J3_disconnected_operator_confirmed'] and r['PC_Saleae_disconnected_operator_confirmed'] and reset_seen and old['passed'] and old['outputs_off_confirmed'] and c['run_reason']==1 and c['run_limit_ms']==c['run_elapsed_ms']==5000 and ((c['run_stop_ms']-c['run_start_ms'])&0xffffffff)==5000 and stamp(s)==stamp(c) and s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==0 and 0<=s['vdc']<20 and s['enc_errors']==s['mc_bad_cnt']==s['mc_uart_error_flags']==0)
 except (KeyError,TypeError):return False

def capture_identity_ok(s,boot):
 # Empty current captures or the EXACT old, archived Uno cache are allowed
 # for this counter comparison. Do not replace raw status values with '-'.
 return all(s.get(k) in ('-',boot.get(k)) for k in ('enc_fault_first_hex','enc_fault_pwm_hex','enc_release_first_hex','enc_release_pwm_hex'))

def clear_ok(s,boot,m):
 return (stamp(s)==stamp(boot) and capture_identity_ok(s,boot) and m.t.checks.off(s) and m.t.checks.transport_clean(s) and m.zero_ready(s) and m.setup_ok(s) and m.t.sd_high(s,False) and s.get('enc_errors')==0 and s.get('enc_bus_ok')==s.get('enc_ok')==1 and s.get('enc_age_ms',9999)<100 and s.get('estop')==0 and s.get('mc_fault')==s.get('bp_fault')==5 and s.get('mc_fault_reason')==8 and s.get('mc_fault_current_mask')==4 and s.get('mc_fault_occurred_mask') in (4,1028) and s.get('mc_last_bad_reason')==0)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--confirm-powered-openload-ready',action='store_true');ap.add_argument('--boot-proof',type=Path,required=True);ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
 if not a.confirm_powered_openload_ready:ap.error('Fresh motor-disconnected, autonomous powered operator confirmation required')
 proof={k:json.loads((a.boot_proof/name).read_text()) for k,name in (('report','report.json'),('status','saved_status.json'),('reset','reset_identity_evidence.json'))}
 prior=json.loads((OLD/'report.json').read_text());assert boot_proof_ok(proof,prior),'No reset Nucleo / completed Uno-run proof'
 boot=proof['status'];out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 (out/'low_bus_reset_proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 m=existing.load_trial();m.configure(2026102709,'NUCLEO');original=m.t.archive_before_start
 original_ready=m.t.ready
 m.t.ready=lambda s:(original_ready(s) and s.get('enc_errors')==0 and s.get('enc_bus_ok')==s.get('enc_ok')==1 and s.get('enc_age_ms',9999)<100 and capture_identity_ok(s,boot))
 commands=[];h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),commands,False)
 result={'passed':False,'CLEAR_commands':0,'START_commands':0,'flash_commands':0,'motor_connected':False,'raw_old_records_erased':False,'commands':commands}
 def sample(label):
  s=h.status();(out/(label+'.json')).write_text(json.dumps(s,indent=2)+'\n');return s
 try:
  before=sample('before_ack')
  assert stamp(before)==stamp(boot) and capture_identity_ok(before,boot) and before['enc_errors']==0,'New operation/error since reset proof'
  # A new pre-START SD event can appear on power-up after an empty low-bus
  # capture. Its independent no-RUN evidence is the unchanged completed Uno
  # run stamp plus the operator-confirmed fresh Nucleo reset and zero counters.
  if not original(before):
   fingerprint=cold.identity(before);base=boot['run_id']
   def preserved_startup(s):
    try:return s.get('run_id') in (base,(base+1)&0xffffffff) and cold.identity(s)==fingerprint
    except (KeyError,TypeError,ValueError):return False
   m.t.archive_before_start=lambda s:original(s) or preserved_startup(s)
   (out/'pre_START_SD_identity.json').write_text(json.dumps({'identity':fingerprint,'Uno_prior_completed_run_id':base,'Nucleo_reset_proved':True})+'\n')
  if not m.t.ready(before):
   assert clear_ok(before,boot,m),'No legal startup CLEAR; no automatic retry'
   time.sleep(.3);fresh=sample('fresh_before_ack')
   assert clear_ok(fresh,boot,m) and fresh['enc_reads']>before['enc_reads']
   result['CLEAR_commands']=1;h.command('CLEAR');deadline=time.monotonic()+5
   while True:
    s=sample('after_ack')
    if m.t.ready(s) and m.setup_ok(s):break
    if time.monotonic()>=deadline:raise RuntimeError('Single CLEAR did not establish protected ready OFF')
    time.sleep(.15)
  result['passed']=True
 except Exception as e:result['error']=str(e) or type(e).__name__
 finally:
  h.close();(out/'ack_report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='commands'}),flush=True)
 if not result['passed']:return 1
 # Use the existing documented mode WITHOUT demanding an empty diagnostic
 # cache. The motor, zero, live SD/BKIN, UART, voltage and MCU/host STOP checks
 # are unchanged. Raw before/after captures remain visible for CRC comparison.
 old_argv=sys.argv;sys.argv=[old_argv[0],'--confirm-powered-ready','--outdir',str(out/'trial'),'--uno-build','2026102709','--sensor-mode','NUCLEO']
 try:code=m.main()
 finally:sys.argv=old_argv
 r=json.loads((out/'trial/report.json').read_text());new=r.get('after_capture_status') or r.get('final_status',{})
 summary={'motor_connected':False,'stationary_sensor_test':True,'physical_rotation_test':False,'trial_exit':code,'outputs_off_confirmed':r.get('outputs_off_confirmed'),
  'I2C_error_delta':new.get('enc_errors',-1)-r['before'].get('enc_errors',0),'old_Uno_cache_preserved':boot.get('enc_fault_pwm_hex'),
  'new_fault_record_replaces_old_cache':new.get('enc_fault_pwm_hex','-') not in ('-',boot.get('enc_fault_pwm_hex')),
  'new_first_fault_evidence_available':False}
 summary['new_first_fault_evidence_available']=summary['I2C_error_delta']>0 and summary['new_fault_record_replaces_old_cache']
 (out/'openload_scope.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='old_Uno_cache_preserved'}),flush=True)
 return code

if __name__=='__main__':raise SystemExit(main())

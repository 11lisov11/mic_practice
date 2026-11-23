"""One confirmed 2026111401/1402 FOC trial, with frozen CPU/IRQ and fault collection."""
import argparse,hashlib,json,threading,time,urllib.error,urllib.request
from pathlib import Path
from foc_trial_supervision import TrialHeartbeat
from foc_saved_retry import load_saved_retry,require_fresh_native_epoch,ADC_record_is_new
from configure_multi_algorithm import crc32c
ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026111401,2026111402)

def off(s):return s.get('state')=='SAFE' and s.get('pwm')==0 and not(s.get('bp_status',0x22)&0x22)

def profile_config(s):
 return ((s.get('fw_build'),s.get('mc_fw_build'))==PAIR and
  s.get('algorithm_selected')==s.get('algorithm_requested')==2 and
  s.get('algorithm_qualification')==128 and s.get('algorithm_profile_crc')==1354279011 and
  s.get('research_native_valid')==1 and 0<=s.get('mc_age_ms',9999)<300 and
  s.get('foc_experiment_flags',0)&1 and s.get('foc_timing_fault')==0 and
  s.get('foc_timing_cases')==64 and s.get('algorithm_fault')==0)

def profile(s):
 return profile_config(s) and s.get('mc_current_zero_ready')==1

def runtime_profile(s):
 if not profile_config(s):return False
 if s.get('mc_current_zero_ready')==1:return True
 # The HMI resets its derived zero flag when BOTH current packets expire.
 # That is unknown telemetry, not a fresh zero_ready=0 from the ADC state.
 # During RUN the native fast loop still checks the real sample.zero/valid,
 # 187.5us ADC age, raw1.35A and2ms estimate age on every PWM frame.
 # START always retains the separate fresh-zero precondition above.
 if s.get('pwm')==1:
  return (s.get('bp_status',0)&0x22)==0x22 and s.get('mc_current_good',0)>0 and (
   s.get('mc_current_age_ms',-1)>=750 and s.get('mc_current_detail_age_ms',-1)>=1500)
 return off(s) and bool(s.get('foc_experiment_flags',0)&4) and s.get('run_reason')==1

def link_power(s):
 return (250<=s.get('vdc',0)<=350 and s.get('mc_transport_fault')==0 and
  s.get('mc_uart_error_flags')==0 and s.get('mc_bad_integrity')==0 and
  s.get('bp_temp_valid')==1 and s.get('bp_temp_fault')==0)

def healthy(s):
 sd=s.get('mc_sd_live') or {}
 return ((runtime_profile(s) if s.get('pwm')==1 else profile(s)) and link_power(s) and s.get('estop')==0 and
  all(s.get(k)==0 for k in ('mc_fault_current_mask','mc_fault_occurred_mask','mc_fault','bp_fault')) and
  sd.get('level')=='HIGH' and sd.get('config_ok') is True and sd.get('break_irq_enabled') is True)

def off_timing_ready(s):
 d=s.get('foc_runtime') or {}
 return (d.get('available') is True and d.get('source')=='OFF_synthetic_CPU_probe' and
  d.get('observer_steps')==64 and d.get('meter_errors')==0 and d.get('first_fault') is None and
  0<s.get('algorithm_fast_cycles',0)<=4000 and 0<s.get('algorithm_observer_cycles',0)<=85000)

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--confirm-autonomous-powered',action='store_true')
 ap.add_argument('--clear-once',action='store_true',help='Use only when the human explicitly requested one CLEAR')
 ap.add_argument('--saved-previous-trial',type=Path,help='Explicitly requested repeat only: saved host-aborted trial; requires fresh Nucleo epoch/OFF64 and a changed ADC record')
 ap.add_argument('--repeat-saved-current-trip',action='store_true',help='Only after an explicit new repeat request for the archived near-threshold current event; fresh Nucleo reset/OFF64 and zero active fault masks required')
 ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
 if not a.confirm_autonomous_powered:ap.error('Current human confirmation of isolated powered bench is required')
 if a.repeat_saved_current_trip and not a.saved_previous_trial:ap.error('Archived previous trial is required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 token=(ROOT/'.unoq_ssh/control_token').read_text().strip()
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 report=dict(passed=False,pair=list(PAIR),start_commands=0,clear_commands=0,arm_commands=0,
  flash_commands=0,reset_commands=0,trial=dict(algorithm='FOC',frequency_hz=5,limit_ms=5000),
  physical_rotation_verified=False,thresholds_changed=False)
 def write(name,obj):
  (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 def save():write('report.json',report)
 def request(path,body=None,timeout=8):
  req=urllib.request.Request('http://192.168.1.138:8080'+path,
   data=None if body is None else json.dumps(body).encode(),
   headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},method='GET' if body is None else 'POST')
  try:
   with opener.open(req,timeout=timeout) as f:d=json.load(f)
  except urllib.error.HTTPError as e:
   try:d=json.load(e)
   except Exception:raise RuntimeError(f'{path}: HTTP{e.code}') from e
  if not d.get('ok'):raise RuntimeError(path+': '+str(d.get('error','rejected')))
  return d
 def status(label):
  s=request('/api/status')['data']
  with (out/'status.jsonl').open('a',encoding='utf-8') as f:
   f.write(json.dumps(dict(label=label,monotonic=time.monotonic(),status=s),ensure_ascii=False)+'\n')
  return s
 def cmd(c):
  report.setdefault('commands',[]).append(c);save();request('/api/cmd',{'cmd':c})
 def stop(label):
  try:report[label]=request('/api/stop-sequence',{'emergency':False},timeout=10)
  except Exception as e:report[label]=dict(error=str(e))
 timer=starter=None;sd_before=None;sd_current=False;heartbeat=TrialHeartbeat(request);retry=None;expected_idle_id=0;expected_new_id=1
 try:
  if a.saved_previous_trial:
   retry=load_saved_retry(a.saved_previous_trial,PAIR,allow_saved_current_trip=a.repeat_saved_current_trip)
   expected_idle_id=retry['expected_idle_run_id'];expected_new_id=expected_idle_id+1
   report['saved_retry_proof']=retry;report['expected_new_run_id']=expected_new_id
  s=status('before_CLEAR');write('before_CLEAR.json',s)
  assert off(s) and profile(s) and link_power(s) and off_timing_ready(s),'OFF/profile/power/timing preflight failed'
  if retry:
   report['fresh_native_epoch']=require_fresh_native_epoch(s,retry,PAIR,crc32c)
   expected_idle_id=s['run_id'];expected_new_id=expected_idle_id+1
   report['expected_new_run_id']=expected_new_id
  else:assert s['run_id']==s['run_start_ms']==0,'Only the first trial of this boot is permitted'
  sd=s.get('mc_sd_live') or {};assert sd.get('level')=='HIGH' and sd.get('config_ok') is True
  sd_current=bool(sd.get('first_record_ready'))
  sd_before=s.get('mc_break_wave_hex','-')
  if sd.get('first_record_ready') or s.get('mc_fault_occurred_mask',0)&1024:
   assert sd_before not in ('','-'),'Frozen SD record has not arrived completely; no CLEAR/START'
  if sd_before not in ('','-'):
   raw=bytes.fromhex(sd_before);(out/'SD_before.bin').write_bytes(raw)
   if sd_current or not retry:
    first=next(x for x in s['mc_break_snapshots'] if x['kind']=='first_since_boot')
    assert first['captured'] and not first['event']['moe_at_irq'] and not first['event']['during_start_request_window']
   else:report['SD_before_is_cached_previous_epoch']=True
   write('SD_before_decoded.json',request('/api/bkin-trace')['data'])
  if a.clear_once:
   assert s['mc_fault_current_mask'] in (0,4) and s['mc_fault_occurred_mask'] in (0,4,1024,1028),'Unexpected fault; no CLEAR/START'
   report['clear_commands']=1;cmd('CLEAR')
   deadline=time.monotonic()+4
   while True:
    s=status('after_one_CLEAR')
    if off(s) and healthy(s):break
    if time.monotonic()>deadline:raise RuntimeError('One CLEAR did not restore protections; no retry')
    time.sleep(.1)
   if sd_current:assert s.get('mc_break_wave_hex','-')==sd_before,'Previous frozen SD record changed'
   write('after_CLEAR.json',s)
  else:assert healthy(s),'Protections not restored; no CLEAR authorized and no START sent'
  for c in ('MODE VF','SET RUNMODE BOUNDED','SET ACCEL 5','SET DECEL 1','SET RUNLIMIT 5','SET FREQ 5'):cmd(c)
  s=status('before_START');write('before_START.json',s)
  assert off(s) and healthy(s) and off_timing_ready(s) and s['freq_cmd']==5 and s['manual_run_mode']==0
  assert s['run_id']==expected_idle_id
  heartbeat.start()
  report['arm_commands']=1;save();request('/api/hv-arm',{'action':'arm','confirm':'ARM 310V'})
  def start_request():
   try:report['start_response']=request('/api/start-sequence',{'manual':False,'runlimit_s':5.0},timeout=12)
   except Exception as e:report['start_response_error']=str(e)
  report['start_commands']=1;save();began=time.monotonic()
  timer=threading.Timer(12,lambda:stop('host_backup_STOP'));timer.daemon=True;timer.start()
  starter=threading.Thread(target=start_request,daemon=True);starter.start()
  seen=False;settling=None
  while time.monotonic()-began<16:
   s=status('running')
   if any(s.get(k) for k in ('estop','mc_fault_current_mask','mc_fault_occurred_mask','algorithm_fault')):
    raise RuntimeError('Protection or FOC fault; stop without retry')
   if not heartbeat.healthy():raise RuntimeError('Operator heartbeat failed; stop without retry')
   if not runtime_profile(s) or not link_power(s):raise RuntimeError('Profile, power or link fault; stop without retry')
   if s['pwm']==1:
    if not healthy(s):raise RuntimeError('Live SD/Break protection not healthy; stop without retry')
    seen=True
   elif s.get('run_id')==expected_new_id:
    elapsed=s.get('run_elapsed_ms',0);native_done=bool(s.get('foc_experiment_flags',0)&4)
    timed_done=s.get('run_reason')==1 and 5000<=elapsed<=5100
    if 4800<=elapsed<=5500 and (native_done or timed_done):
     if off(s):
      report.update(passed=True,completed_5s=True,seen_PWM_running=seen,native_done=native_done,Uno_limit_done=timed_done)
      write('autostop.json',s);break
     if settling is None:settling=time.monotonic()
     if time.monotonic()-settling>.3:raise RuntimeError('Outputs-off acknowledgement did not settle')
    elif seen or s.get('run_reason'):raise RuntimeError('Early stop, five-second trial not completed')
   if report.get('start_response_error') and s.get('run_id')==expected_idle_id:raise RuntimeError(report['start_response_error'])
   time.sleep(.08)
  if not report['passed']:raise RuntimeError('No confirmed five-second completion')
 except Exception as e:report['error']=str(e)
 finally:
  if report['arm_commands'] or report['start_commands']:stop('final_STOP')
  heartbeat.stop();report['operator_heartbeat']=heartbeat.snapshot()
  if timer:timer.cancel()
  if starter:starter.join(timeout=1)
  # Frozen runtime pages and the35ADC pages are delivered after OFF. GET only.
  try:
   deadline=time.monotonic()+20;s=None
   while True:
    s=status('post_STOP_capture');assert off(s),'Post-trial outputs-off not confirmed'
    d=s.get('foc_runtime') or {}
    got_runtime=d.get('available') is True and d.get('source')=='runtime_observer'
    got_adc=ADC_record_is_new(s,retry)
    if (not report['start_commands']) or (got_runtime and got_adc) or time.monotonic()>deadline:break
    time.sleep(.1)
   write('final_status.json',s);report['after']=s;write('CPU_IRQ_and_first_fault.json',s.get('foc_runtime'))
   report['runtime_record_received']=got_runtime;report['ADC_record_received']=got_adc
   for key,name in [('mc_adc_peak_hex','ADC_peak.bin'),('mc_break_wave_hex','SD_after.bin')]:
    value=s.get(key,'-')
    if value not in ('','-'):
     raw=bytes.fromhex(value);(out/name).write_bytes(raw);report[name+'_sha256']=hashlib.sha256(raw).hexdigest()
   report['prior_SD_record_retained']=sd_before in (None,'','-') or s.get('mc_break_wave_hex')==sd_before
   if not report['prior_SD_record_retained'] and sd_current:report['passed']=False
   if not sd_current and retry:report['cached_previous_SD_archived_before_new_epoch']=sd_before in (None,'','-') or (out/'SD_before.bin').exists()
   if report['start_commands'] and (not got_runtime or not got_adc):
    report['passed']=False;report['runtime_record_error']='Incomplete runtime CPU/IRQ or ADC record'
  except Exception as e:report['post_stop_collection_error']=str(e)
  save()
 print(json.dumps({k:report.get(k) for k in ('passed','clear_commands','start_commands','runtime_record_received','ADC_record_received','error','post_stop_collection_error')}))
 return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

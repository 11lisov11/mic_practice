"""One authorized FOC5Hz/5s repeat after a verified scalar run; same profile and native guards."""
import json,time,threading,urllib.request,hashlib,argparse
from pathlib import Path
from foc_trial_supervision import TrialHeartbeat
from run_foc_boot_capture_trial import decode_boot
from run_repeat_break_foc_runtime import profile_config as foc_profile_config, runtime_profile as foc_runtime_profile, off_timing_ready

ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026111401,2026111402)
FOC=ROOT/'artifacts/live_bench_20261114/powered_FOC_1401_1402_r1'

def off(s):
 return s.get('state')=='SAFE' and s.get('pwm')==0 and not(s.get('bp_status',0x22)&0x22)

def healthy(s,algorithm=2):
 sd=s.get('mc_sd_live') or {}
 return ((s.get('fw_build'),s.get('mc_fw_build'))==PAIR and
  s.get('algorithm_selected')==s.get('algorithm_requested')==algorithm and
  s.get('research_native_valid')==1 and s.get('enc_source')=='disabled' and
  250<=s.get('vdc',0)<=350 and 0<=s.get('mc_age_ms',999999)<300 and
  s.get('bp_temp_valid')==1 and s.get('bp_temp_fault')==0 and s.get('bp_temp_c',999)<80 and
  all(s.get(k)==0 for k in ('mc_fault_current_mask','mc_fault_occurred_mask','mc_fault','bp_fault','algorithm_fault',
   'estop','mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_last_uart_error_flags',
   'mc_transport_fault','uno_rx_hw_errors','uno_rx_dropped','rpc_response_timeouts','rpc_send_timeouts',
   'precharge','pfc','brake','bp_ext')) and sd.get('level')=='HIGH' and
  sd.get('config_ok') is True and sd.get('break_irq_enabled') is True and
  (algorithm!=2 or foc_profile_config(s)))

def valid_window(s,old_tick,live):
 return (s.get('mc_current_telemetry_valid')==s.get('mc_current_zero_ready')==1 and
  s.get('mc_current_coverage_pct')==100 and s.get('mc_current_window_ms',0)>0 and
  0<=s.get('mc_current_age_ms',999999)<750 and
  0<((s.get('mc_current_window_tick_ms',old_tick)-old_tick)&0xffffffff)<0x80000000 and
  (not live or s.get('mc_current_frozen')==0) and
  all(isinstance(s.get(k),list) and len(s[k])==3 for k in ('mc_current_rms_a','mc_current_peak_a')))

def deadline_reported(s,expected_id):
 return (s.get('state')=='SAFE' and s.get('pwm')==0 and s.get('run_id')==expected_id and
  s.get('run_reason')==1 and s.get('run_limit_ms')==5000 and
  5000<=s.get('run_elapsed_ms',0)<=5100 and
  ((s.get('run_stop_ms',0)-s.get('run_start_ms',0))&0xffffffff)==s.get('run_elapsed_ms'))

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--confirm-one-powered-foc-run',action='store_true');ap.add_argument('--outdir',type=Path,required=True)
 ap.add_argument('--repeat-saved-scalar',type=Path,required=True,help='One explicitly authorized repeat after a recorded successful5s scalar stop; no reset/CLEAR')
 a=ap.parse_args()
 if not a.confirm_one_powered_foc_run:ap.error('One powered scalar run must be explicitly authorized')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 token=(ROOT/'.unoq_ssh/control_token').read_text().strip();op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 report=dict(passed=False,pair=PAIR,START=0,CLEAR=0,ARM=0,RESET=0,flash_commands=0,thresholds_changed=False,
   frequency_hz=5,runlimit_ms=5000,physical_rotation_verified=False,commands=[],valid_live_windows=[])
 def save(name,obj):(out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
 def request(path,body=None,timeout=8):
  r=urllib.request.Request('http://192.168.1.138:8080'+path,data=None if body is None else json.dumps(body).encode(),
   headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},method='GET' if body is None else 'POST')
  with op.open(r,timeout=timeout) as f:d=json.load(f)
  if not d.get('ok'):raise RuntimeError(str(d.get('error','Request rejected')))
  return d
 def status(label):
  s=request('/api/status')['data']
  with (out/'status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(label=label,monotonic=time.monotonic(),status=s),ensure_ascii=False)+'\n')
  return s
 def cmd(c):
  report['commands'].append(c);save('report.json',report);request('/api/cmd',{'cmd':c})
 def stop(label):
  try:report[label]=request('/api/stop-sequence',{'emergency':False},timeout=10)
  except Exception as e:report[label]={'error':str(e)}
 heartbeat=TrialHeartbeat(request);timer=starter=None;before=None;boot_before=None
 try:
  hashes=json.loads((FOC/'saved_files_sha256.json').read_text(encoding='utf-8'))
  for name,h in hashes.items():assert hashlib.sha256((FOC/name).read_bytes()).hexdigest()==h,name
  previous=json.loads((FOC/'report.json').read_text(encoding='utf-8'));assert previous['passed'] and previous['physical_rotation_verified']
  initial_algorithm=1
  if a.repeat_saved_scalar:
   prevdir=a.repeat_saved_scalar.resolve()
   for name,h in json.loads((prevdir/'saved_files_sha256.json').read_text(encoding='utf-8')).items():
    assert hashlib.sha256((prevdir/name).read_bytes()).hexdigest()==h,name
   previous=json.loads((prevdir/'report.json').read_text(encoding='utf-8'))
   if (prevdir/'recorded_trial_audit.json').exists():
    audit=json.loads((prevdir/'recorded_trial_audit.json').read_text(encoding='utf-8'))
    assert audit['passed'] and audit['actual_auto_stop_verified'] and audit['final_native_OFF_confirmed'] and audit['faults_zero']
   else:
    assert previous['passed'] and previous['auto_stop_verified'] and 5000<=previous['elapsed_ms']<=5100
    assert off(previous['after']) and healthy(previous['after'],1) and previous['fresh_scalar_current_window']
    assert deadline_reported(previous['after'],previous['after']['run_id'])
   assert previous['START']==1 and previous['CLEAR']==previous['RESET']==previous['flash_commands']==0 and previous['boot_unchanged']
   initial_algorithm=1;report['authorized_repeat_parent']=str(prevdir)
  before=status('before');save('before.json',before)
  assert off(before) and healthy(before,initial_algorithm) and before['hmi_hv_armed']==0 and before['mc_current_zero_ready']==1
  assert before['run_id']==previous['after']['run_id'] and before['run_start_ms']==previous['after']['run_start_ms']
  boot_before=decode_boot(before,PAIR);prior_boot=decode_boot(previous['after'],PAIR)
  assert boot_before['identity']==prior_boot['identity'] and boot_before['Linux_boot_id']==prior_boot['Linux_boot_id']
  original_preflight=json.loads((FOC/'before_START.json').read_text(encoding='utf-8'))
  assert off_timing_ready(original_preflight),'Original same-boot OFF64 timing proof invalid'
  original_boot=decode_boot(original_preflight,PAIR)
  assert original_boot['identity']==boot_before['identity'] and original_boot['Linux_boot_id']==boot_before['Linux_boot_id']
  report['timing_qualification_source']='Verified same-boot original OFF64 record; native FE_READY/case64 and unchanged calculated profile rechecked; runtime deadlines unchanged'
  old_tick=before['mc_current_window_tick_ms'];expected_id=(before['run_id']+1)&0xffffffff
  save('FOC_ADC_preserved.json',dict(sha256=hashlib.sha256(bytes.fromhex(before['mc_adc_peak_hex'])).hexdigest(),note='Frozen first-run raw ADC belongs to FOC, not this scalar run'))
  save('algorithm_response.json',request('/api/algorithm',{'algorithm':2}))
  for _ in range(8):
   s=status('algorithm_ack')
   if off(s) and healthy(s):break
   time.sleep(.2)
  assert off(s) and healthy(s),'FOC selection/profile not confirmed'
  for c in ('MODE VF','SET RUNMODE BOUNDED','SET ACCEL 5','SET DECEL 1','SET RUNLIMIT 5','SET FREQ 5'):cmd(c)
  s=status('before_START');save('before_START.json',s)
  assert off(s) and healthy(s) and s['mc_current_zero_ready']==1 and s['freq_cmd']==5 and s['manual_run_mode']==0 and s['run_id']==before['run_id']
  heartbeat.start();report['ARM']=1;save('report.json',report);request('/api/hv-arm',{'action':'arm','confirm':'ARM 310V'})
  def start():
   try:report['start_response']=request('/api/start-sequence',{'manual':False,'runlimit_s':5.0},timeout=12)
   except Exception as e:report['start_response_error']=str(e)
  report['START']=1;save('report.json',report);began=time.monotonic()
  timer=threading.Timer(12,lambda:stop('backup_STOP'));timer.daemon=True;timer.start()
  starter=threading.Thread(target=start,daemon=True);starter.start();seen=False;settling=None
  while time.monotonic()-began<16:
   s=status('running')
   if not healthy(s) or not heartbeat.healthy():raise RuntimeError('Protection, bus, UART or heartbeat failed; no retry')
   if s['pwm']==1:
    assert foc_runtime_profile(s),'Native FOC run/ADC validity metadata changed'
    seen=True
    assert s['run_id']==expected_id and s['run_limit_ms']==5000 and s['freq_cmd']==5
    if valid_window(s,old_tick,True):
     tick=s['mc_current_window_tick_ms']
     if tick not in report['valid_live_windows']:report['valid_live_windows'].append(tick)
     if max(s['mc_current_peak_a'])>1.35:raise RuntimeError('Observed phase-current peak above1.35A; STOP')
    # Native FOC checks real ADC validity/187.5us age,1.35A and2ms on every frame.
    # Live RMS may be unavailable during FOC; a new valid post-STOP window is mandatory.
   elif s.get('run_id')==expected_id:
    elapsed=s.get('run_elapsed_ms',0)
    if deadline_reported(s,expected_id):
     if off(s):
      report.update(auto_stop_verified=True,elapsed_ms=elapsed,seen_PWM_running=seen);save('autostop.json',s);break
     if settling is None:settling=time.monotonic()
     if time.monotonic()-settling>.3:raise RuntimeError('Native OFF acknowledgement did not settle')
    elif seen or s.get('run_reason'):raise RuntimeError('FOC stopped early; no retry')
   if report.get('start_response_error') and s.get('run_id')==before['run_id']:raise RuntimeError(report['start_response_error'])
   time.sleep(.08)
  if not report.get('auto_stop_verified'):raise RuntimeError('No confirmed5s auto-stop')
 except Exception as e:report['error']=str(e)
 finally:
  if report['ARM'] or report['START']:stop('final_STOP')
  heartbeat.stop();report['heartbeat']=heartbeat.snapshot()
  if timer:timer.cancel()
  if starter:starter.join(timeout=1)
  try:
   end=time.monotonic()+15
   while True:
    s=status('after_STOP');assert off(s),'Outputs-off not confirmed'
    fresh=before is not None and valid_window(s,before['mc_current_window_tick_ms'],False)
    if fresh or not report['START'] or time.monotonic()>end:break
    time.sleep(.2)
   save('final_status.json',s);report['after']=s;report['fresh_FOC_current_window']=fresh
   report['FOC_ADC_unchanged']=before is None or before['mc_adc_peak_hex']==s['mc_adc_peak_hex']
   if boot_before:
    after=decode_boot(s,PAIR);report['boot_unchanged']=boot_before['identity']==after['identity'] and boot_before['Linux_boot_id']==after['Linux_boot_id']
   report['passed']=bool(report.get('auto_stop_verified') and fresh and healthy(s) and report.get('boot_unchanged') and report['FOC_ADC_unchanged'])
  except Exception as e:report['collection_error']=str(e)
  save('report.json',report)
  save('saved_files_sha256.json',{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file() and f.name!='saved_files_sha256.json'})
 print(json.dumps({k:report.get(k) for k in ('passed','START','CLEAR','auto_stop_verified','elapsed_ms','valid_live_windows','fresh_FOC_current_window','FOC_ADC_unchanged','boot_unchanged','error','collection_error')}))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

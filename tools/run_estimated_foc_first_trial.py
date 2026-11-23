"""One explicitly authorized CLEAR and one protected FOC5Hz/5s trial. No retries."""
import argparse,hashlib,json,threading,time,urllib.error,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026102951,2026102952)
CRC=1354279011
SD_PROOF=ROOT/'artifacts/live_bench_20261029/estimated_foc_trial_r5/autonomous_before_first_FOC_r1'


def off(s):
 return s.get('state')=='SAFE' and s.get('pwm')==0 and not(s.get('bp_status',0x22)&0x22)


def profile(s):
 return ((s.get('fw_build'),s.get('mc_fw_build'))==PAIR and
   s.get('algorithm_selected')==s.get('algorithm_requested')==2 and
   s.get('algorithm_qualification')==128 and s.get('algorithm_profile_crc')==CRC and
   s.get('research_native_valid')==1 and 0<=s.get('mc_age_ms',9999)<300 and
   s.get('foc_experiment_flags',0)&1 and s.get('foc_timing_fault')==0 and
   s.get('foc_timing_cases')==64 and s.get('mc_current_zero_ready')==1)


def link_and_power(s):
 return (250<=s.get('vdc',0)<=350 and s.get('mc_transport_fault')==0 and
  s.get('mc_uart_error_flags')==0 and s.get('mc_bad_integrity')==0 and
  s.get('bp_temp_valid')==1 and s.get('bp_temp_fault')==0)


def healthy(s):
 sd=s.get('mc_sd_live') or {}
 return (profile(s) and link_and_power(s) and s.get('estop')==0 and
  all(s.get(k)==0 for k in ('mc_fault_current_mask','mc_fault_occurred_mask','mc_fault','bp_fault')) and
  sd.get('level')=='HIGH' and sd.get('config_ok') is True and sd.get('break_irq_enabled') is True)


def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--confirm-user-powered-autonomous-and-one-clear',action='store_true')
 ap.add_argument('--outdir',type=Path,required=True)
 a=ap.parse_args()
 if not a.confirm_user_powered_autonomous_and_one_clear:ap.error('Explicit current human authorization is required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 token=(ROOT/'.unoq_ssh/control_token').read_text().strip()
 report=dict(passed=False,source_kind='hardware',commands=[],clear_commands=0,start_commands=0,
  arm_commands=0,flash_commands=0,reset_commands=0,physical_rotation_verified=False,
  absolute_current_scale_qualified=False,trial=dict(algorithm='FOC',frequency_hz=5,duration_s=5))
 def save():
  (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 def request(path,body=None,timeout=8):
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  req=urllib.request.Request('http://192.168.1.138:8080'+path,
   data=None if body is None else json.dumps(body).encode(),
   headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},
   method='GET' if body is None else 'POST')
  try:
   with opener.open(req,timeout=timeout) as response:answer=json.load(response)
  except urllib.error.HTTPError as e:
   try:answer=json.load(e)
   except Exception:raise RuntimeError(f'{path}: HTTP{e.code}') from e
  if answer.get('ok') is not True:raise RuntimeError(path+': '+str(answer.get('error','rejected')))
  return answer
 def status(label='monitor'):
  s=request('/api/status')['data']
  with (out/'status.jsonl').open('a',encoding='utf-8') as f:
   f.write(json.dumps(dict(label=label,host_monotonic_s=time.monotonic(),status=s),ensure_ascii=False)+'\n')
  return s
 def archive(name,s):
  (out/(name+'.json')).write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 def cmd(command):
  report['commands'].append(command);save();request('/api/cmd',{'cmd':command})
 def stop(label):
  try:report[label]=request('/api/stop-sequence',{'emergency':False},timeout=10)
  except Exception as e:report[label]=dict(error=str(e))
 starting=threading.Event();starter=None;timer=None
 try:
  s=status('powered_before_CLEAR');archive('before_CLEAR',s)
  assert off(s) and profile(s) and link_and_power(s),'Powered OFF/profile/link preflight failed'
  assert s['run_id']==s['run_start_ms']==0,'Not the first trial in this boot'
  sd=s.get('mc_sd_live') or {}
  assert sd.get('level')=='HIGH' and sd.get('config_ok') is True,'SD is not recovered'
  assert s['mc_fault_current_mask'] in (0,4) and s['mc_fault_occurred_mask'] in (1024,1028),'Unexpected fault latch'
  oldproof=SD_PROOF
  proof=json.loads((oldproof/'saved_status.json').read_text(encoding='utf-8'))
  raw=bytes.fromhex(s['mc_break_wave_hex']);assert raw==(oldproof/'startup_SD_wave.bin').read_bytes()
  first=lambda v:next(x for x in v['mc_break_snapshots'] if x['kind']=='first_since_boot')
  assert first(s)['raw']==first(proof)['raw'] and not first(s)['event']['moe_at_irq']
  assert not first(s)['event']['during_start_request_window']
  (out/'startup_SD_preserved.bin').write_bytes(raw)
  report['startup_SD_sha256']=hashlib.sha256(raw).hexdigest()
  archive('startup_SD_decoded',request('/api/bkin-trace')['data']);save()
  report['clear_commands']=1;cmd('CLEAR')
  deadline=time.monotonic()+4
  while True:
   s=status('after_single_CLEAR')
   if off(s) and healthy(s):break
   if time.monotonic()>deadline:raise RuntimeError('Single CLEAR did not recover native protections; no START')
   time.sleep(.1)
  assert s['mc_break_wave_hex']==proof['mc_break_wave_hex'] and first(s)['raw']==first(proof)['raw'],'Saved SD changed during CLEAR'
  archive('after_CLEAR',s)
  for command in ('MODE VF','SET RUNMODE BOUNDED','SET ACCEL 5','SET DECEL 1','SET RUNLIMIT 5','SET FREQ 5'):
   cmd(command)
  s=status('final_powered_preflight');archive('before_START',s)
  assert off(s) and healthy(s) and s['freq_cmd']==5 and s['manual_run_mode']==0
  assert s['algorithm_fast_cycles']<=4000 and s['algorithm_observer_cycles']<=85000
  report['arm_commands']=1;report['commands'].append('HV ARM one bounded trial');save()
  request('/api/hv-arm',{'action':'arm','confirm':'ARM 310V'})
  def start_request():
   starting.set()
   try:report['start_response']=request('/api/start-sequence',{'manual':False,'runlimit_s':5.0},timeout=12)
   except Exception as e:report['start_response_error']=str(e)
  report['start_commands']=1;report['commands'].append('START FOC5Hz limit5s');save()
  began=time.monotonic();report['request_monotonic_s']=began
  timer=threading.Timer(12,lambda:stop('host_deadline_STOP'));timer.daemon=True;timer.start()
  starter=threading.Thread(target=start_request,daemon=True);starter.start()
  seen=False;running_since=None;finished=False
  while time.monotonic()-began<16:
   s=status()
   if s['run_id'] or s['pwm']==1:
    if running_since is None:running_since=time.monotonic()
    if s['pwm']==1:seen=True
   if not profile(s) or not link_and_power(s):raise RuntimeError('Profile, bus or UART fault during trial')
   if any(s.get(k) for k in ('estop','mc_fault_current_mask','mc_fault_occurred_mask','algorithm_fault')):
    raise RuntimeError('Protection or FOC fault during trial; stop without retry')
   if s['pwm']==1:
    if not healthy(s) and running_since is not None and time.monotonic()-running_since>.3:
     raise RuntimeError('Active SD/protection health did not recover within startup transition')
   elif s['run_id']==1:
    elapsed=s.get('run_elapsed_ms',0)
    native_done=bool(s.get('foc_experiment_flags',0)&4)
    timed_done=s.get('run_reason')==1 and 5000<=elapsed<=5100
    if off(s) and 4800<=elapsed<=5500 and (native_done or timed_done):
     archive('auto_STOP',s);report.update(completion=s,seen_PWM_running=seen,
      native_trial_done=native_done,Uno_run_limit_stop=timed_done);finished=True;break
    if seen or s.get('run_reason'):raise RuntimeError('Early stop without verified five-second completion')
   if report.get('start_response_error') and not s.get('run_id'):
    raise RuntimeError(report['start_response_error'])
   time.sleep(.08)
  if not finished:raise RuntimeError('No five-second completion before backup deadline')
  timer.cancel();report['passed']=True
 except Exception as e:report['error']=str(e)
 finally:
  if report['start_commands'] or report['arm_commands']:stop('final_STOP')
  if timer:timer.cancel()
  if starter:starter.join(timeout=1)
  try:
   s=status('final');archive('final_status',s);report['after']=s
   if s.get('mc_adc_peak_complete')==1 and s.get('mc_adc_peak_hex','-')!='-':
    raw=bytes.fromhex(s['mc_adc_peak_hex']);(out/'ADC_peak.bin').write_bytes(raw)
    report['ADC_peak_sha256']=hashlib.sha256(raw).hexdigest()
   report['startup_SD_retained_after_trial']=s.get('mc_break_wave_hex')==proof['mc_break_wave_hex']
  except Exception as e:report['final_status_error']=str(e)
  save()
 print(json.dumps({k:report.get(k) for k in ('passed','clear_commands','start_commands','seen_PWM_running','native_trial_done','Uno_run_limit_stop','error','startup_SD_retained_after_trial')}))
 return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

"""Verify installed calculated FOC while OFF; only stopped configuration commands."""
import argparse,json,time,urllib.request
from pathlib import Path
import prepare_estimated_foc_trial as p
from configure_multi_algorithm import load,crc32c

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--url',default='http://192.168.1.138:8080')
 ap.add_argument('--outdir',type=Path,required=True);ap.add_argument('--configure-stopped',action='store_true');a=ap.parse_args()
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 token=(p.ROOT/'.unoq_ssh/control_token').read_text().strip()
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def request(path,body=None):
  r=urllib.request.Request(a.url.rstrip('/')+path,
   data=None if body is None else json.dumps(body).encode(),
   headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},
   method='GET' if body is None else 'POST')
  with opener.open(r,timeout=8) as f:answer=json.load(f)
  if answer.get('ok') is not True:raise RuntimeError(str(answer.get('error','rejected')))
  return answer
 _,raw,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
 expected_crc=crc32c(raw);rows=[];commands=[]
 report=dict(passed=False,start_commands=0,clear_commands=0,arm_commands=0,commands=commands)
 def status():
  s=request('/api/status')['data'];rows.append(s)
  assert (s['fw_build'],s['mc_fw_build'])==p.NEW
  assert s['state']=='SAFE' and s['pwm']==0 and not(s['bp_status']&0x22) and s['hmi_hv_armed']==0
  assert s['vdc']<=20 and 0<=s['mc_age_ms']<300
  assert s['research_native_valid']==1 and s['research_native_caps']==15
  assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==expected_crc
  return s
 try:
  s=status()
  assert s['foc_timing_fault']==0,('FOC timing fault',s['foc_timing_fault'])
  assert s['foc_experiment_flags']==1 and s['foc_timing_cases']==64,('FOC timing flags/cases',s['foc_experiment_flags'],s['foc_timing_cases'])
  assert 0<s['algorithm_fast_cycles']<=4000,s['algorithm_fast_cycles']
  assert 0<s['algorithm_observer_cycles']<=85000,s['algorithm_observer_cycles']
  if a.configure_stopped:
   for command in ('MODE VF','SET RUNMODE BOUNDED','SET ACCEL 5','SET DECEL 1','SET RUNLIMIT 5','SET FREQ 5'):
    status();request('/api/cmd',{'cmd':command});commands.append(command)
   status();request('/api/algorithm',{'algorithm':2});commands.append('SET ALGORITHM FOC')
   until=time.monotonic()+4
   while True:
    s=status()
    if s['algorithm_selected']==s['algorithm_requested']==2:break
    if time.monotonic()>until:raise RuntimeError('No FOC selection acknowledgement')
    time.sleep(.15)
  first_good=s['research_native_good'];first_bad=s['research_native_bad']
  for i in range(16):
   s=status();assert s['research_native_bad']==first_bad;time.sleep(.15)
  assert s['research_native_good']>first_good
  assert s['mc_current_zero_ready']==1
  assert s.get('mc_sd_live',{}).get('level')=='HIGH'
  report.update(passed=True,pair=list(p.NEW),profile_crc=expected_crc,
   calculated_profile_loaded=True,target_timing_measured=True,
   fast_kernel_cycles=s['algorithm_fast_cycles'],observer_cycles=s['algorithm_observer_cycles'],
   offline_timing_cases=s['foc_timing_cases'],no_pwm_or_motor_start=True,
   algorithm_selected=s['algorithm_selected'],commands_are_stopped_configuration_only=True,
   active_fault_mask=s['mc_fault_current_mask'],occurred_fault_mask=s['mc_fault_occurred_mask'],
   after=s)
 except Exception as e:report['error']=str(e)
 (out/'status.jsonl').write_text(''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in rows),encoding='utf-8')
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:report.get(k) for k in ('passed','profile_crc','target_timing_measured','fast_kernel_cycles','observer_cycles','algorithm_selected','active_fault_mask','error')}))
 return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

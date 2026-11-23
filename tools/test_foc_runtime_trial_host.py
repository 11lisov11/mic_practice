"""Run the actual host script against a fake HTTP service; never contact boards."""
import contextlib,copy,io,json,sys
from pathlib import Path
from unittest.mock import patch
import run_foc_runtime_trial as trial

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'artifacts/live_bench_20261029/foc_runtime_fix_r1'

class Response:
 def __init__(self,obj):self.raw=json.dumps(obj).encode()
 def __enter__(self):return io.BytesIO(self.raw)
 def __exit__(self,*args):return False

class FakeThread:
 def __init__(self,target,**kw):self.target=target
 def start(self):self.target()
 def join(self,**kw):pass

class FakeTimer:
 def __init__(self,*args,**kw):pass
 def start(self):pass
 def cancel(self):pass

class Network:
 def __init__(self,scenario,base):
  self.scenario=scenario;self.base=copy.deepcopy(base);self.started=False;self.stopped=False;self.reads=0;self.calls=[]
  self.base['vdc']=320;self.base['estop']=0
  for k in ('mc_fault_current_mask','mc_fault_occurred_mask','mc_fault','bp_fault'):self.base[k]=0
  self.base['mc_break_wave_hex']='-';self.base['mc_sd_live']['first_record_ready']=False
  if scenario in ('failed_clear','denied_clear'):
   self.base['mc_sd_live']['break_irq_enabled']=False
   self.base['mc_fault_current_mask']=self.base['mc_fault_occurred_mask']=4
 def open(self,request,timeout=None):
  path=request.full_url.split(':8080',1)[1];body=json.loads(request.data) if request.data else None
  self.calls.append((path,body))
  if path=='/api/cmd':return Response(dict(ok=True))
  if path=='/api/hv-arm':return Response(dict(ok=True))
  if path=='/api/start-sequence':self.started=True;return Response(dict(ok=True))
  if path=='/api/stop-sequence':self.stopped=True;return Response(dict(ok=True))
  assert path=='/api/status',path
  s=copy.deepcopy(self.base)
  if self.started:
   self.reads+=1;s['run_id']=1;s['run_start_ms']=1234
   s['foc_runtime']['source']='runtime_observer';s['foc_runtime']['observer_steps']=5000
   s['mc_adc_peak_complete']=1;s['mc_adc_peak_hex']='00'*1024
   if self.scenario=='runtime_fault':
    s['algorithm_fault']=3;s['mc_fault_current_mask']=s['mc_fault_occurred_mask']=128
    s['run_elapsed_ms']=99;s['run_reason']=2
    s['foc_runtime']['first_fault']={'reason_code':4,'reason_ru':'synthetic estimate age'}
   elif self.reads==1 and not self.stopped:
    s['state']='FOC_RUN';s['pwm']=1;s['bp_status']=2;s['run_elapsed_ms']=1000
   else:
    s['foc_experiment_flags']=5;s['run_elapsed_ms']=5000;s['run_reason']=1
  return Response(dict(ok=True,data=s))

def main():
 out=PACKAGE/'FOC_CPU_IRQ_trial_preparation_r1/host_script_tests';out.mkdir(exist_ok=False)
 base=json.loads((PACKAGE/'idle_link_confirm_r1/report.json').read_text(encoding='utf-8'))['after']
 fake_root=out/'fake_workspace';(fake_root/'.unoq_ssh').mkdir(parents=True)
 (fake_root/'.unoq_ssh/control_token').write_text('unit-test-token',encoding='ascii')
 scenarios={}
 for case,allow_clear in [('success',True),('failed_clear',True),('runtime_fault',True),('success_without_clear',False),('denied_clear',False)]:
  network=Network(case,base);clock=[0.]
  def now():clock[0]+=.2;return clock[0]
  argv=['run_foc_runtime_trial.py','--confirm-autonomous-powered','--outdir',str(out/case)]
  if allow_clear:argv.append('--clear-once')
  with patch.object(trial,'ROOT',fake_root),patch.object(sys,'argv',argv),\
       patch.object(trial.urllib.request,'build_opener',return_value=network),\
       patch.object(trial.threading,'Thread',FakeThread),patch.object(trial.threading,'Timer',FakeTimer),\
       patch.object(trial.time,'monotonic',side_effect=now),patch.object(trial.time,'sleep',return_value=None),\
       contextlib.redirect_stdout(io.StringIO()):
   rc=trial.main()
  r=json.loads((out/case/'report.json').read_text(encoding='utf-8'))
  clear=sum(body=={'cmd':'CLEAR'} for path,body in network.calls)
  starts=sum(path=='/api/start-sequence' for path,body in network.calls)
  assert clear<=1 and starts<=1
  if case.startswith('success'):assert rc==0 and r['passed'] and starts==1 and r['runtime_record_received']
  else:assert rc==1 and not r['passed']
  if case in ('failed_clear','denied_clear'):assert starts==0
  if case=='runtime_fault':assert starts==1 and r['after']['foc_runtime']['first_fault']['reason_code']==4
  if not allow_clear:assert clear==0
  scenarios[case]=dict(passed=True,simulated_clear=clear,simulated_START=starts)
 report=dict(passed=True,network_fully_mocked=True,hardware_commands=0,new_motor_runs=0,scenarios=scenarios)
 (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()

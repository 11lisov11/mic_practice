"""Verify real stopped commissioning transport; never authorize/start/clear."""
import hashlib,json,time,urllib.request,subprocess
import prepare_standstill_commissioning as p
from standstill_measurement import configuration
from current_only_lab import get_status
URL='http://127.0.0.1:18080'
def main():
 out=p.OUT/'hardware_install_r1/idle_verification';out.mkdir(exist_ok=False)
 report=dict(passed=False,start_commands=0,clear_commands=0,arm_commands=0,execute_commands=0,states=[],config_commands=0)
 token=(p.ROOT/'.unoq_ssh/control_token').read_text(encoding='utf-8').strip()
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def status():
  s=get_status(URL)
  assert (s.get('fw_build'),s.get('mc_fw_build'))==p.NEW,'unexpected pair'
  assert s.get('state')=='SAFE' and s.get('pwm')==0 and not(s.get('bp_status',0x22)&0x22),'not stopped'
  assert s.get('hmi_hv_armed')==0 and 0<=s.get('mc_age_ms',9999)<300,'not fresh/disarmed'
  assert 0<=s.get('vdc',999)<=20,'not low bus'
  assert s.get('research_native_valid')==1 and s.get('research_native_caps')==15,'missing capabilities'
  assert s.get('algorithm_qualification')==0 and s.get('algorithm_profile_crc')==0,'unexpected FOC qualification'
  assert s.get('mc_transport_fault')==0,'transport error'
  return s
 def post(path,body):
  request=urllib.request.Request(URL+path,data=json.dumps(body).encode(),method='POST',
   headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token})
  with opener.open(request,timeout=6) as r:reply=json.load(r)
  assert reply.get('ok') is True,reply
 def wait(predicate,seconds=5):
  end=time.monotonic()+seconds
  while True:
   s=status()
   if predicate(s):return s
   if time.monotonic()>=end:raise RuntimeError('native acknowledgement timed out')
   time.sleep(.15)
 try:
  first=status();p.write(out/'before.json',json.dumps(first,ensure_ascii=False,indent=2))
  point=configuration('dc',0,0,.06,12.23)
  p.write(out/'configuration_only.json',json.dumps(point,indent=2))
  for cmd in point['commands']:
   assert cmd.startswith(('IDENT SET ','IDENT COMMIT '));post('/api/cmd',{'cmd':cmd});report['config_commands']+=1;time.sleep(.12)
  configured=wait(lambda s:s.get('id_valid')==1 and s.get('id_flags')==1 and s.get('id_config_crc')==point['config_crc'])
  report['configuration_crc_confirmed']=True
  for algorithm in (1,2,3,4,1):
   post('/api/algorithm',{'algorithm':algorithm})
   s=wait(lambda s:s.get('algorithm_selected')==s.get('algorithm_requested')==algorithm)
   for key in ('mc_fault_current_mask','mc_fault_occurred_mask'):assert s.get(key)==first.get(key),'protection latch changed'
   assert s.get('id_flags')==1 and s.get('id_complete')==0,'measurement unexpectedly ran'
   report['states'].append(dict(algorithm=algorithm,pwm=s['pwm'],id_flags=s['id_flags'],native_age_ms=s['mc_age_ms']))
  samples=[]
  for _ in range(20):samples.append(status());time.sleep(.2)
  p.write(out/'idle_samples.json',json.dumps(samples,ensure_ascii=False,indent=2))
  assert all(s.get('research_native_bad')==0 and s.get('id_wire_bad')==0 for s in samples),'native decoder error'
  assert all(s.get('algorithm_selected')==1 and s.get('id_flags')==1 and s.get('id_complete')==0 for s in samples),'state changed'
  report.update(passed=True,final_status=samples[-1],maximum_native_age_ms=max(s['mc_age_ms'] for s in samples),
    configuration_staged_only=True,nonce_not_authorized=True)
 except Exception as exc:report['error']=str(exc)
 p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:report.get(k) for k in ('passed','states','configuration_crc_confirmed','start_commands','execute_commands','error')}))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

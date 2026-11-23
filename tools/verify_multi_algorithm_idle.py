"""Verify real native algorithm selection over HTTP, with no START/CLEAR/ARM."""
import hashlib,json,time,urllib.request
from pathlib import Path
from prepare_multi_algorithm import ROOT,OUT,NEW,read,write
from current_only_lab import get_status
URL='http://127.0.0.1:18080'
def checked_status():
 s=get_status(URL)
 assert (s.get('fw_build'),s.get('mc_fw_build'))==NEW,'unexpected pair'
 assert s.get('state')=='SAFE' and s.get('pwm')==0 and not (s.get('bp_status',0x22)&0x22),'outputs not stopped'
 assert s.get('hmi_hv_armed')==0 and 0<=s.get('mc_age_ms',9999)<300,'not disarmed/fresh'
 assert 0<=s.get('vdc',999)<=20 and s.get('research_native_valid')==1,'bus/capability evidence missing'
 assert s.get('research_native_caps')==7,'compiled algorithms not confirmed'
 assert s.get('algorithm_qualification')==0,'unexpected physical qualification'
 return s
def main():
 dest=OUT/'hardware_install_r1/mode_verification_r1';dest.mkdir(exist_ok=False)
 report=dict(passed=False,hardware_mode_commands=0,start_commands=0,clear_commands=0,arm_commands=0,
             expected_order=['VF','FOC','ADAPTIVE_PWM','VF'],states=[],errors=[])
 token=(ROOT/'.unoq_ssh/control_token').read_text(encoding='utf-8').strip()
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 try:
  first=checked_status();write(dest/'before.json',json.dumps(first,ensure_ascii=False,indent=2))
  for algorithm in (1,2,3,1):
   before=checked_status()
   request=urllib.request.Request(URL+'/api/algorithm',data=json.dumps({'algorithm':algorithm}).encode(),
      method='POST',headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token})
   report['hardware_mode_commands']+=1
   with opener.open(request,timeout=4) as response:reply=json.load(response)
   assert reply.get('ok') is True,'configuration rejected'
   end=time.monotonic()+5;samples=[];confirmed=False
   while time.monotonic()<end:
    s=checked_status();samples.append(s)
    if s.get('algorithm_selected')==algorithm and s.get('algorithm_requested')==algorithm:
     confirmed=True;break
    time.sleep(.15)
   write(dest/f'algorithm_{len(report["states"])+1}_{algorithm}.json',json.dumps(samples,ensure_ascii=False,indent=2))
   assert confirmed,'native configuration acknowledgement missing'
   assert s.get('mc_transport_fault')==before.get('mc_transport_fault')==0,'transport fault changed'
   for key in ('mc_fault_current_mask','mc_fault_occurred_mask'):
    assert s.get(key)==first.get(key),'protection latch changed: '+key
   assert s.get('algorithm_profile_crc')==0,'a motor profile was installed unexpectedly'
   report['states'].append(dict(algorithm=algorithm,selected=s['algorithm_selected'],requested=s['algorithm_requested'],
       native_good=s['research_native_good'],native_bad=s['research_native_bad'],pwm=s['pwm'],
       active_faults=s['mc_fault_current_mask'],occurred_faults=s['mc_fault_occurred_mask']))
  # Observe fresh UART/reply/capability traffic after returning to the default.
  idle=[]
  for _ in range(24):idle.append(checked_status());time.sleep(.22)
  write(dest/'idle_samples.json',json.dumps(idle,ensure_ascii=False,indent=2))
  assert idle[-1]['research_native_good']>idle[0]['research_native_good'],'capability stream stalled'
  assert all(s['research_native_bad']==0 and s['mc_transport_fault']==0 for s in idle),'UART/capability error'
  assert all(s['algorithm_selected']==1 and s['algorithm_requested']==1 for s in idle),'default not restored'
  for rel,digest in json.loads(read(OUT/'hardware_install_r1/preserved_captures_sha256.json')).items():
   assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest,rel
  report.update(passed=True,archived_captures_unchanged=True,final_algorithm='VF',maximum_native_age_ms=max(s['mc_age_ms'] for s in idle),
    final_status=idle[-1],physical_foc_qualification=False)
 except Exception as exc:report['errors'].append(str(exc))
 write(dest/'report.json',json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:report.get(k) for k in ('passed','states','hardware_mode_commands','start_commands','clear_commands','maximum_native_age_ms','errors')}))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

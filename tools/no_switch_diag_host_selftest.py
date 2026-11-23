"""Run the real host orchestration with all probe/sleep operations replaced."""
import copy,json,sys
import run_no_switch_diag as run
from no_switch_diag_io import PACKAGE
def main():
 root=PACKAGE/'verification/host_cases';root.mkdir(exist_ok=False)
 original=(run.Probe,run.read_report,run.time.sleep,sys.argv)
 case={'mode':'','writes':[],'reads':0}
 base=dict(state=0,attempted=0,clock_hz=170000000,actual_bus_v=10,phase_pins_gpio_low=1,
  TIM1_BDTR=0x1000,TIM1_CR1=1,adc_seen=1000,guard_flags=0,local_stop=0,
  sequence=2,encoder={'reads':1000,'errors':0})
 class FakeProbe:
  def __init__(self,logs):pass
  def request(self,addr,cancel=False):
   case['writes'].append('cancel' if cancel else 'request')
   if case['mode']=='write_timeout':raise TimeoutError('fake ambiguous write result')
  def read(self,addr,size,label):case['reads']+=1;return bytes(size)
 def report(pr,addr,out,label):
  s=copy.deepcopy(base)
  if label.startswith('before'):
   if case['mode']=='bad_bus':s['actual_bus_v']=20
   if label=='before_fresh':s['sequence']=4;s['adc_seen']+=4800
   return s
  s.update(state=1 if case['mode']=='still_running' else 2,reason=0,elapsed_ms=5000.1,
   tim_updates=80000,adc_calls=80000,adc_accepted=79999,medium_updates=2500,adc_quality_flags=1,
   encoder={'reads':2000,'errors':0})
  return s
 try:
  run.Probe=FakeProbe;run.read_report=report;run.time.sleep=lambda _:None
  results=[]
  for mode,request,expected,code in [('preflight',False,[],0),('one',True,['request'],0),('bad_bus',True,[],1),('write_timeout',True,['request'],1),('still_running',True,['request','cancel'],1)]:
   case.update(mode=mode,writes=[],reads=0)
   sys.argv=['selftest','--confirm-j1-j4-off-meter-below20-nucleo-usb','--outdir',str(root/mode)]+(['--request-once'] if request else [])
   rc=run.main();assert rc==code and case['writes']==expected,(mode,rc,case)
   # Annotate the simulated host reports so retrieval cannot mistake a mock
   # success for a physical Nucleo test. The real runner remains unchanged.
   f=root/mode/'report.json';d=json.loads(f.read_text(encoding='utf-8'))
   d['selftest_with_fake_probe']=True;d['actual_hardware_calls']=0;d['hardware_tested']=False
   f.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8')
   results.append(dict(case=mode,exit=rc,mailbox_writes=list(case['writes'])))
  r=dict(passed=True,cases=results,actual_hardware_calls=0,ambiguous_write_not_retried=True,motor_start_clear_flash_reset_commands=0)
  (PACKAGE/'verification/host_selftest.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps(r))
 finally:run.Probe,run.read_report,run.time.sleep,sys.argv=original
if __name__=='__main__':main()

"""Fake Saleae/probe tests: never contact a device or accept an unrecorded run."""
import json,struct,sys,types,shutil
from pathlib import Path
import logic_edges_diag_io as io
import run_logic_edges_diag as trial
import run_no_switch_diag as base

def main():
 root=io.PACKAGE/'verification/capture_host_cases';root.mkdir(exist_ok=False)
 # This synthetic manifest is only a host fixture, not a firmware claim.
 fixture=root/'synthetic_package';(fixture/'verification').mkdir(parents=True)
 (fixture/'verification/symbols.json').write_text(json.dumps(dict(mic_logic_edge_report={'address':0x20000000})))
 state=dict(mode='',writes=0,saved=0,waits=0,read_while_running=False,captured=False)
 real=(io.PACKAGE,io.Probe,base.main,sys.argv,sys.modules.get('saleae'))
 class Probe:
  def __init__(self,logs):self.logs=logs
  def read(self,addr,size,label):
   if state['captured'] and not state['waits']:state['read_while_running']=True
   w=[0x3147454c,2026102793]+[0]*10;w[11]=io.crc32c(struct.pack('<11I',*w[:11]));return struct.pack('<12I',*w)
  def request(self,addr,cancel=False):
   assert state['captured'];state['writes']+=1
   if state['mode']=='ambiguous':raise TimeoutError('synthetic ambiguous mailbox result')
 class Capture:
  def wait(self):state['waits']+=1
  def save_capture(self,path):state['saved']+=1;Path(path).write_text('synthetic only')
  def export_raw_data_csv(self,directory,**kwargs):
   Path(directory,'digital.csv').write_text('Time [s],'+','.join('Channel '+str(x) for x in range(8))+'\n0,0,0,0,1,1,1,1,0\n10,0,0,0,1,1,1,1,0\n')
  def close(self):pass
 class Manager:
  @staticmethod
  def connect(**kwargs):return Manager()
  def get_devices(self):
   return [] if state['mode']=='absent' else [types.SimpleNamespace(device_id=trial.DEVICE,is_simulation=False)]
  def start_capture(self,**kwargs):
   if state['mode']=='capture_failure':raise RuntimeError('synthetic capture failure')
   state['captured']=True;return Capture()
  def close(self):pass
 automation=types.SimpleNamespace(Manager=Manager,LogicDeviceConfiguration=lambda **k:k,
  CaptureConfiguration=lambda **k:k,TimedCaptureMode=lambda **k:k)
 fake=types.ModuleType('saleae');fake.automation=automation
 def fake_main():
  out=Path(sys.argv[sys.argv.index('--outdir')+1]);out.mkdir();(out/'logs').mkdir()
  (out/'report.json').write_text(json.dumps(dict(selftest_with_fake_probe=True,actual_hardware_calls=0)))
  if '--request-once' not in sys.argv:return 0
  try:base.Probe(out/'logs').request(0x20000040)
  except Exception:return 1
  return 0
 results=[]
 try:
  io.PACKAGE=fixture;io.Probe=Probe;base.main=fake_main;sys.modules['saleae']=fake
  for mode in ('preflight','capture_failure','absent','ambiguous','one'):
   state.update(mode=mode,writes=0,saved=0,waits=0,read_while_running=False,captured=False)
   sys.argv=['tools/run_logic_edges_diag.py','--confirm-j1-j4-off-meter-below20-nucleo-usb','--confirm-sd-pa6-pd2-jumper-and-probes','--outdir',str(root/mode)]+([] if mode=='preflight' else ['--request-once'])
   try:rc=trial.main()
   except RuntimeError:rc=1
   assert state['writes']==(1 if mode in ('ambiguous','one') else 0),state
   assert state['saved']==(1 if mode in ('ambiguous','one') else 0),state
   assert not state['read_while_running'],state
   results.append(dict(case=mode,exit=rc,mailbox_writes=state['writes'],waveforms_saved=state['saved']))
  # Test CRC and actual PWM evidence separately, with negative controls.
  er=[0x3147454c,2026102793,100,510000100,0,0,400,0,1000,0,3,0]
  er[11]=io.crc32c(struct.pack('<11I',*er[:11]));raw=struct.pack('<12I',*er)
  assert io.decode_edges(raw)['edge_ms']==3000
  negative=0
  for i in range(48):
   broken=bytearray(raw);broken[i]^=1
   try:io.decode_edges(broken)
   except ValueError:negative+=1
   else:raise AssertionError('Corrupt edge record accepted')
  from analyze_logic_edges_diag import analyze
  def waveform(path,marker=True,pwm=True,sd=True,outside=False):
   events={0:[(i,v) for i,v in enumerate([int(outside),0,0,1,1,int(sd),int(sd),0])],9:[]}
   if marker:events[2]=[(7,1)];events[5]=[(7,0)]
   if pwm:
    for n in range(48000):
     t=2+n/16000;events.setdefault(t,[]).extend((ch,1) for ch in range(3));events.setdefault(t+1/32000,[]).extend((ch,0) for ch in range(3))
   for n in range(200):events.setdefault(n/100+0.1,[]).append((3,n%2))
   v=[0]*8
   with path.open('w') as f:
    f.write('Time [s],'+','.join('Channel '+str(x) for x in range(8))+'\n')
    for t,changes in sorted(events.items()):
     for ch,value in changes:v[ch]=value
     f.write(str(t)+','+','.join(map(str,v))+'\n')
  f=root/'synthetic_pwm.csv';waveform(f);assert analyze(f)['physical_edges_verified']
  for kwargs in [dict(marker=False),dict(pwm=False),dict(sd=False),dict(outside=True)]:
   waveform(f,**kwargs);assert not analyze(f)['physical_edges_verified']
  r=dict(passed=True,actual_hardware_calls=0,cases=results,edge_CRC_negative_cases=negative,
   waveform_positive_and_negative_cases=5,readout_during_load=False)
  (root/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps(r))
 finally:
  io.PACKAGE,io.Probe,base.main,sys.argv,mod=real
  if mod is None:sys.modules.pop('saleae',None)
  else:sys.modules['saleae']=mod
if __name__=='__main__':main()

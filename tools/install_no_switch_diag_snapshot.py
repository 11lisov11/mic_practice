"""One2791 install after archiving2790; no load request or motor command."""
import argparse,json,hashlib,subprocess,time
from pathlib import Path
from no_switch_diag_snapshot_io import PACKAGE,PROGRAMMER,SERIAL,Probe,read_report
from wifi_stop_tail_probe import parse_registers
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--confirm-j1-j4-off-meter-below20-nucleo-usb',action='store_true');p.add_argument('--outdir',type=Path,required=True)
 a=p.parse_args()
 if not a.confirm_j1_j4_off_meter_below20_nucleo_usb:p.error('Fresh OFF/meter/USB confirmation required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);logs=out/'logs';logs.mkdir()
 m=json.loads((PACKAGE/'manifest.json').read_text(encoding='utf-8'));assert m['built'] and m['offline_verified']
 for rel,d in m['sealed_sha256'].items():assert hashlib.sha256((PACKAGE/rel).read_bytes()).hexdigest()==d,rel
 for rel,d in m['tool_sha256'].items():assert hashlib.sha256((PACKAGE.parents[2]/rel).read_bytes()).hexdigest()==d,rel
 before_symbols=json.loads((PACKAGE.with_name('no_switch_diag_r2')/'verification/symbols.json').read_text(encoding='utf-8'))
 pr=Probe(logs);before=read_report(pr,before_symbols['mic_load_report']['address'],out,'before2791')
 # Programming-only admission for the identified failed pin-setup image.
 # These conditions never authorize a load/PWM run or bypass runtime guards.
 assert before['build']==2026102791 and before['state']==3 and before['attempted']==1 and before['reason']==8
 assert before['actual_bus_v']<20 and not(before['TIM1_BDTR']&0x8000)
 for name in ('fault_record','release_probe'):
  d=before_symbols[name];(out/('before_'+name+'.bin')).write_bytes(pr.read(d['address'],d['bytes'],name))
 r=dict(passed=False,flash_commands=0,readback_verified=False,diagnostic_requests=0,motor_start_commands=0,clear_commands=0,uno_flash_commands=0)
 def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
 try:
  image=PACKAGE/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
  r['flash_commands']=1;save()
  q=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=UR','reset=HWrst','sn='+SERIAL,'-w',str(image),'-v','-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
  (logs/'flash_and_readback.log').write_text(q.stdout+q.stderr,encoding='utf-8')
  if q.returncode or 'Download verified successfully' not in q.stdout:raise RuntimeError('2792 write/readback not confirmed; no retry')
  r['readback_verified']=True;time.sleep(3)
  symbols=json.loads((PACKAGE/'verification/symbols.json').read_text(encoding='utf-8'))
  d=read_report(pr,symbols['mic_load_report']['address'],out,'boot2792')
  assert d['build']==2026102792 and d['state']==0 and d['attempted']==0
  assert d['actual_bus_v']<20 and d['phase_pins_gpio_low']==1 and not(d['TIM1_BDTR']&0x8000) and d['guard_flags']==0
  words=parse_registers(pr.call(['-r32','0x48000000','44','-r32','0x48000400','44','-r32','0x40012c00','104'],'read_pins_and_protection'))
  for base,pins in [(0x48000000,[7,8,9,10]),(0x48000400,[0,1])]:
   for pin in pins:
    assert (words[base]>>(2*pin))&3==1 and not(words[base+16]&(1<<pin)) and not(words[base+20]&(1<<pin))
    assert words[base+28]&(1<<pin) and words[base+28]&0x10000
  assert d['TIM1_BDTR']&0x1000
  (out/'GPIO_TIM_registers.json').write_text(json.dumps({hex(k):hex(v) for k,v in words.items()},indent=2)+'\n',encoding='utf-8')
  r.update(passed=True,boot=d,GPIO_LOW_and_locks_verified=True,BKIN_enabled=True)
 except Exception as e:r['error']=str(e) or type(e).__name__
 finally:save();print(json.dumps({k:v for k,v in r.items() if k!='boot'}))
 return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

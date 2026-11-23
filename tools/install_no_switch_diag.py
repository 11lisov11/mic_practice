"""Install only the sealed Nucleo diagnostic. Never START, CLEAR or reset Uno."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
from no_switch_diag_io import PACKAGE,PROGRAMMER,SERIAL,Probe,read_report
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--confirm-j1-j4-off-meter-below20-nucleo-usb',action='store_true');p.add_argument('--outdir',type=Path,required=True)
 a=p.parse_args()
 if not a.confirm_j1_j4_off_meter_below20_nucleo_usb:p.error('Operator OFF/meter/USB confirmation required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);logs=out/'logs';logs.mkdir()
 m=json.loads((PACKAGE/'manifest.json').read_text(encoding='utf-8'));assert m['built'] and m['offline_verified']
 for rel,sha in m['sealed_sha256'].items():assert hashlib.sha256((PACKAGE/rel).read_bytes()).hexdigest()==sha,rel
 image=PACKAGE/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
 # Preserve fresh live records before this single Nucleo programming operation.
 from run_wifi_nucleo_pwm_bench import WifiHmi
 from collect_wifi_telemetry import read_token
 h=WifiHmi('http://192.168.1.138:8080',read_token(str(PACKAGE.parents[2]/'.unoq_ssh/control_token')),[],False)
 try:
  s=h.status();(out/'before_full_status.json').write_text(json.dumps(s,indent=2)+'\n',encoding='utf-8')
  assert s.get('state')=='SAFE' and s.get('pwm')==0 and s.get('hmi_hv_armed')==0 and 0<=s.get('vdc',999)<20
  assert (s.get('fw_build'),s.get('mc_fw_build'))==(2026102709,2026102710)
 finally:h.close()
 r=dict(passed=False,flash_commands=0,start_commands=0,clear_commands=0,uno_flash_commands=0,diagnostic_load_requests=0)
 def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
 try:
  r['flash_commands']=1;save()
  q=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=UR','reset=HWrst','sn='+SERIAL,'-w',str(image),'-v','-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
  (logs/'flash_and_readback.log').write_text(q.stdout+q.stderr,encoding='utf-8')
  if q.returncode or 'Download verified successfully' not in q.stdout:raise RuntimeError('Programming/readback not confirmed; no retry')
  r['readback_verified']=True;time.sleep(3)
  symbols=json.loads((PACKAGE/'verification/symbols.json').read_text(encoding='utf-8'))
  d=read_report(Probe(logs),symbols['mic_load_report']['address'],out,'boot')
  assert d['state']==0 and d['attempted']==0 and d['actual_bus_v']<20 and d['phase_pins_gpio_low']==1 and not(d['TIM1_BDTR']&0x8000)
  r.update(passed=True,boot=d)
 except Exception as e:r['error']=str(e)
 finally:save();print(json.dumps({k:v for k,v in r.items() if k!='boot'}))
 return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

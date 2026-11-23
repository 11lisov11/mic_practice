"""Archive2792 records, program2793 once, verify readback; never run the test."""
import argparse,json,hashlib,subprocess,time
import logic_edges_diag_io as io
from pathlib import Path
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--confirm-j1-j4-off-meter-below20-nucleo-usb',action='store_true')
 p.add_argument('--confirm-sd-pa6-pd2-jumper-and-probes',action='store_true')
 p.add_argument('--outdir',type=Path,required=True);a=p.parse_args()
 if not a.confirm_j1_j4_off_meter_below20_nucleo_usb or not a.confirm_sd_pa6_pd2_jumper_and_probes:p.error('OFF/discharge/USB and completed diagnostic jumper/probe map required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);logs=out/'logs';logs.mkdir()
 m=json.loads((io.PACKAGE/'manifest.json').read_text(encoding='utf-8'));assert m['built'] and m['offline_verified']
 for rel,h in m['sealed_sha256'].items():assert hashlib.sha256((io.PACKAGE/rel).read_bytes()).hexdigest()==h,rel
 for rel,h in m['tool_sha256'].items():assert hashlib.sha256((io.PACKAGE.parents[2]/rel).read_bytes()).hexdigest()==h,rel
 old=io.PACKAGE.with_name('no_switch_diag_r3')
 symbols=json.loads((old/'verification/symbols.json').read_text(encoding='utf-8'))
 pr=io.Probe(logs);before=io.read_report(pr,symbols['mic_load_report']['address'],out,'before2792')
 assert before['build']==2026102792 and before['state']==2 and before['reason']==0 and before['attempted']==1
 assert before['actual_bus_v']<20 and before['phase_pins_gpio_low']==1 and not(before['TIM1_BDTR']&0x8000)
 for name in ('fault_record','release_probe'):
  s=symbols[name];(out/(name+'_before.bin')).write_bytes(pr.read(s['address'],s['bytes'],name))
 r=dict(passed=False,flash_commands=1,readback_verified=False,diagnostic_requests=0,motor_start_commands=0,clear_commands=0,uno_flash_commands=0)
 try:
  image=io.PACKAGE/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
  (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
  q=subprocess.run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','reset=HWrst','sn='+io.SERIAL,'-w',str(image),'-v','-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
  (logs/'flash_and_readback.log').write_text(q.stdout+q.stderr,encoding='utf-8')
  if q.returncode or 'Download verified successfully' not in q.stdout:raise RuntimeError('Write/readback not confirmed; no retry')
  r['readback_verified']=True;time.sleep(3)
  symbols=json.loads((io.PACKAGE/'verification/symbols.json').read_text(encoding='utf-8'))
  d=io.read_report(pr,symbols['mic_load_report']['address'],out,'boot2793')
  er=pr.read(symbols['mic_logic_edge_report']['address'],48,'boot_edges');(out/'edge_boot.bin').write_bytes(er)
  e=io.decode_edges(er)
  assert io.eligible(d) and e['flags']==0
  r.update(passed=True,boot=d,auxiliary=e)
 except Exception as ex:r['error']=str(ex) or type(ex).__name__
 finally:
  (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
  print(json.dumps({k:v for k,v in r.items() if k not in ('boot','auxiliary')}))
 return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

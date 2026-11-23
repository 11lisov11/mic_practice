"""Restore the original sealed2710 after an archived2805 diagnostic; never START/CLEAR."""
import argparse,json,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
import prepare_no_switch_diag as p
from prepare_full_edges_busy_wait import OUT,BUILD
import full_mcsdk_edges_host as host
from pin_pwm_diag_io import PROGRAMMER,SERIAL
host.PACKAGE=OUT;host.BUILD=BUILD
PRODUCTION=p.ROOT/'artifacts/live_bench_20261027/i2c_persistent_pe_r1'
STEM='ACIM-NUCLEOG431RB-IPM15B-VF_OL'

def eligible(d):
 return d['pin']['build']==BUILD and d['pin']['state']==2 and d['pin']['reason']==0 and d['pin']['attempted']==1 and not(d['pin']['BDTR']&0xc000) and not(d['full']['TIM8_BDTR']&0xc000) and d['full']['backend_flags']==0 and d['full']['active_fault']==d['full']['occurred_fault']==4 and 0<=d['full']['bus_v']<20 and d['pin']['GPIOA_IDR']&64 and d['full']['rx_bad']==d['full']['uart_guard']==0

def get_status():
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open('http://192.168.1.138:8080/api/status',timeout=5) as f:r=json.load(f)
 if r.get('ok') is not True:raise RuntimeError('HMI status unavailable')
 return r['data']

def verify_image():
 m=json.loads(p.read(PRODUCTION/'manifest.json'))
 assert m['built'] and m['selftest_pass'] and m['pair_compatibility_ids']==[2026102709,2026102710]
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for rel,h in m[table].items():assert p.sha(PRODUCTION/rel)==h,rel
 b=json.loads(p.read(PRODUCTION/'build/nucleo'/(STEM+'.build-manifest.json')))
 assert b['firmware_build_id']==2026102710 and b['build_errors']==b['build_warnings']==0
 for x in b['artifacts']:assert p.sha(PRODUCTION/'build/nucleo'/x['file'])==x['sha256'].lower()
 image=PRODUCTION/'build/nucleo'/(STEM+'.bin')
 assert 0<len(image.read_bytes())<0x1f800
 return image,b

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--j1-unplugged-usb-current-bus-below20',action='store_true');ap.add_argument('--completed-trial',type=Path,required=True);ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
 if not a.j1_unplugged_usb_current_bus_below20:ap.error('Confirmed existing discharged USB connection required')
 trial=a.completed_trial.resolve();q=json.loads(p.read(trial/'report.json'))
 assert q['passed'] and q['I2C_healthy_during_PWM'] and q['UART_healthy_during_trial']
 image,b=verify_image();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();pr=host.Probe(out/'logs')
 r=dict(passed=False,production_build=2026102710,original_image_sha256=p.sha(image),firmware_source_changes=0,flash_commands=0,motor_START_commands=0,CLEAR_commands=0,guards_relaxed=False,Uno_flashed=False)
 def save():p.write(out/'report.json',json.dumps(r,indent=2)+'\n')
 try:
  for name in (STEM+'.bin',STEM+'.elf',STEM+'.hex',STEM+'.build-manifest.json'):
   shutil.copy2(PRODUCTION/'build/nucleo'/name,out/name)
  sy=json.loads(p.read(OUT/'verification/symbols.json'));before=host.read(pr,sy,out,'before_restore');host.archive(pr,sy,out,'before_restore')
  assert eligible(before),'Current firmware/output/protection admission failed; no flash'
  s=get_status();p.write(out/'before_web_status.json',json.dumps(s,indent=2)+'\n')
  assert (s.get('fw_build'),s.get('mc_fw_build'))==(2026102709,BUILD) and s.get('state')=='SAFE' and s.get('pwm')==s.get('hmi_hv_armed')==0 and s.get('mc_age_ms',9999)<300
  q=subprocess.run([sys.executable,str(p.ROOT/'tools/read_edges_uart_context.py'),'--outdir',str(out/'before_uart_context')],capture_output=True,text=True,timeout=30)
  p.write(out/'logs/before_uart_archive.log',q.stdout+q.stderr);assert not q.returncode
  r['flash_commands']=1;save();print('ARCHIVED: restoring original2710 once; no motor commands',flush=True)
  q=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=UR','reset=HWrst','sn='+SERIAL,'-w',str(out/(STEM+'.bin')),'0x08000000','-v','-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
  p.write(out/'logs/flash_verify.log',q.stdout+q.stderr)
  assert q.returncode==0 and 'Download verified successfully' in q.stdout,'Programming verification failed; no retry'
  pr.call(['-u','0x08000000',str(image.stat().st_size),str(out/'flash_readback.bin')],'readback_original2710')
  r['readback_sha256']=p.sha(out/'flash_readback.bin');assert r['readback_sha256']==r['original_image_sha256'];r['readback_verified']=True;save()
  deadline=time.monotonic()+20;last=None
  while time.monotonic()<deadline:
   s=get_status();last=s
   with (out/'startup_status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
   if (s.get('fw_build'),s.get('mc_fw_build'))==(2026102709,2026102710) and s.get('enc_diag_category_counts_available')==1:break
   time.sleep(.3)
  else:raise RuntimeError('Production status not complete; outputs remain uncommanded, no retry')
  assert s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==0 and 0<=s['vdc']<20 and s['mc_age_ms']<300
  r.update(passed=True,web_pair=[s['fw_build'],s['mc_fw_build']],outputs_off_confirmed=True,encoder_bus_ok=s['enc_bus_ok'],encoder_angle_ok=s['enc_ok'],encoder_errors=s['enc_errors'],encoder_reads=s['enc_reads'],vdc=s['vdc'])
  p.write(out/'after_web_status.json',json.dumps(s,indent=2)+'\n')
  return 0
 except Exception as e:r['error']=str(e) or type(e).__name__;return 1
 finally:save();print(json.dumps(r),flush=True)

if __name__=='__main__':raise SystemExit(main())

"""Install/status/run of a physically isolated AS5600 + original six TIM1 pins."""
import argparse,json,hashlib,subprocess,time
from pathlib import Path
import pin_pwm_diag_io as io
import no_switch_diag_snapshot_io as old
DEVICE='A7D1BB81883C0092'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('install','status','run'))
 p.add_argument('--isolation-confirmed',action='store_true');p.add_argument('--scl-sda-ready',action='store_true');p.add_argument('--outdir',type=Path,required=True);a=p.parse_args()
 if not a.isolation_confirmed:p.error('34pin cable disconnected, J1/J4 OFF, bus independently confirmed discharged, NucleoUSB required')
 if a.action=='run' and not a.scl_sda_ready:p.error('CH0..4 original phases, CH5=SDA, CH6=SD, CH7=SCL required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();pr=io.Probe(out/'logs')
 m=json.loads((io.PACKAGE/'manifest.json').read_text());assert m['built'] and m['offline_verified']
 for rel,h in m['sealed_sha256'].items():assert hashlib.sha256((io.PACKAGE/rel).read_bytes()).hexdigest()==h,rel
 symbols=json.loads((io.PACKAGE/'verification/symbols.json').read_text())
 r=dict(passed=False,motor_commands=0,clear_commands=0,flash_commands=0,pin_requests=0,
  channel_map={'0':'UH','1':'UL','2':'VH','3':'VL','4':'WH','5':'SDA','6':'SD','7':'SCL'},all_six_outputs_generated=True,observed_PWM_outputs=5)
 def archive(sy,label):
  for name in ('fault_record','release_probe'):
   s=sy[name];(out/(label+'_'+name+'.bin')).write_bytes(pr.read(s['address'],s['bytes'],label+name))
 def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
 try:
  if a.action=='install':
   previous=io.PACKAGE.with_name('pin_pwm_diag_r1')
   sy=json.loads((previous/'verification/symbols.json').read_text())
   raw=pr.read(sy['mic_pin_report']['address'],256,'before2794');(out/'before2794.bin').write_bytes(raw)
   before=io.decode(raw);assert before['build']==2026102794 and before['state']==0 and before['attempted']==0 and not(before['BDTR']&0x8000)
   # A disconnected voltage-sense cable cannot qualify the floating ADC.
   # Isolation and discharged-bus confirmation are physical prerequisites.
   archive(sy,'before2794');r['flash_commands']=1;save()
   image=io.PACKAGE/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
   q=subprocess.run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','reset=HWrst','sn='+io.SERIAL,'-w',str(image),'-v','-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
   (out/'logs/flash_readback.log').write_text(q.stdout+q.stderr,encoding='utf-8')
   if q.returncode or 'Download verified successfully' not in q.stdout:raise RuntimeError('Readback not confirmed; no retry')
   r['readback_verified']=True;time.sleep(3)
   d=io.read_report(pr,out,'boot');r['boot']=d;assert io.eligible(d)
   r['AS5600_idle_ok']=d['encoder']['reads']>100 and d['encoder']['valid_flags']&3==3
   if 'bus_clear' in symbols:
    s=symbols['bus_clear'];(out/'bus_clear_after_boot.bin').write_bytes(pr.read(s['address'],s['bytes'],'bus_clear_after_boot'))
   r['passed']=r['AS5600_idle_ok'];return 0 if r['passed'] else 1
  before=io.read_report(pr,out,'before');r['before']=before
  if a.action=='status':r['passed']=io.eligible(before);return 0 if r['passed'] else 1
  assert io.eligible(before) and before['encoder']['valid_flags']&3==3
  from runtime_python import ensure_modules_or_reexec
  ensure_modules_or_reexec(['saleae'],'MIC_PIN_PWM_REEXEC')
  from saleae import automation
  with automation.Manager.connect(port=10430,connect_timeout_seconds=3) as manager:
   assert any(d.device_id==DEVICE and not d.is_simulation for d in manager.get_devices())
   with manager.start_capture(device_id=DEVICE,
     device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=8_000_000,glitch_filters=[]),
     capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=10))) as cap:
    try:
     r['pin_requests']=1;save();pr.request(symbols['mic_pin_request']['address']);time.sleep(6)
    finally:
     # Retain a waveform even if the write response was ambiguous. No retry.
     cap.wait();cap.save_capture(str(out/'pin_pwm_i2c.sal'));(out/'csv').mkdir()
     cap.export_raw_data_csv(directory=str(out/'csv'),digital_channels=list(range(8)))
  after=io.read_report(pr,out,'after');r['after']=after;archive(symbols,'after')
  keys=('reads','errors','NACK','deadline','BUSY','ARLO','BERR_clears','forced_resets','normal_parks')
  r['counter_delta']={k:after['encoder'][k]-before['encoder'][k] for k in keys}
  b=after['boundaries'];r['phases']=[dict(stage=stage,reads=b[i+2]-b[i],errors=b[i+3]-b[i+1]) for stage,i in [('quiet',0),('fixed_PWM',2),('modulated_PWM',4)]]
  r['passed']=after['state']==2 and after['reason']==0 and 5000<=after['elapsed_ms']<=5010 and not(after['BDTR']&0x8000)
  r['AS5600_no_new_errors']=all(r['counter_delta'][k]==0 for k in keys if k!='reads')
  r['physical_waveform_not_yet_analyzed']=True
  return 0 if r['passed'] else 1
 except Exception as ex:r['error']=str(ex) or type(ex).__name__;return 1
 finally:save();print(json.dumps({k:v for k,v in r.items() if k not in ('before','after','boot')}),flush=True)
if __name__=='__main__':raise SystemExit(main())

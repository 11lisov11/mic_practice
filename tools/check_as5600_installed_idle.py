"""Read-only2792 idle observation: no mailbox writes, reset, flash or motor commands."""
import argparse,json,time,hashlib
from pathlib import Path
from no_switch_diag_snapshot_io import PACKAGE,Probe,read_report

class ReadOnlyProbe(Probe):
 def call(self,args,label):
  if len(args)!=3 or args[0]!='-r32':raise RuntimeError('Only SRAM reads are allowed')
  return super().call(args,label)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--seconds',type=int,default=60,choices=range(30,121))
 p.add_argument('--outdir',type=Path,required=True);a=p.parse_args()
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir()
 symbols=json.loads((PACKAGE/'verification/symbols.json').read_text(encoding='utf-8'))
 pr=ReadOnlyProbe(out/'logs')
 result=dict(passed=False,mode='installed2792_idle_not_minimal_sensor_only_image',
  motor_commands=0,diagnostic_requests=0,reset_commands=0,flash_commands=0,clear_commands=0,
  rotating_sensor_qualified=False,PWM_cause_proven=False)
 def read(label):
  d=read_report(pr,symbols['mic_load_report']['address'],out,label)
  assert d['build']==2026102792 and d['state']==2 and d['reason']==0
  assert not(d['TIM1_BDTR']&0x8000) and d['phase_pins_gpio_low']==1 and d['actual_bus_v']<20
  assert d['guard_flags']==0 and d['local_stop']==0
  return d
 def frozen(label):
  r={}
  for name in ('fault_record','release_probe'):
   s=symbols[name];raw=pr.read(s['address'],s['bytes'],label+'_'+name)
   (out/(label+'_'+name+'.bin')).write_bytes(raw);r[name]=hashlib.sha256(raw).hexdigest()
  return r
 try:
  before=read('before');result['before']=before
  prior=frozen('before')
  print(json.dumps(dict(started=True,build=before['build'],state=before['state_name'],
   reads=before['encoder']['reads'],errors=before['encoder']['errors'],status=before['encoder']['magnet_status'],
   raw_angle=before['encoder']['raw_angle'],PWM=False,observation_seconds=a.seconds)),flush=True)
  start=time.monotonic()
  # No debug reads during this observation interval. The MCU and sensor keep
  # running on their existing firmware; no new diagnostic workload is requested.
  while time.monotonic()-start<a.seconds:
   time.sleep(min(1,max(0,a.seconds-(time.monotonic()-start))))
  after=read('after');duration=time.monotonic()-start
  result['after']=after;later=frozen('after')
  x,y=before['encoder'],after['encoder']
  fields=('reads','errors','NACK','deadline','BUSY','ARLO','BERR_clears','forced_resets','normal_parks')
  delta={key:y[key]-x[key] for key in fields}
  assert all(v>=0 for v in delta.values()),'Counter reset/wrap: observation not comparable'
  assert after['sequence']>before['sequence'] and y['sample_ms']>x['sample_ms'],'No fresh live report'
  healthy=(x['valid_flags']&3)==3 and (y['valid_flags']&3)==3
  magnet=(x['magnet_status']&0x38)==0x20 and (y['magnet_status']&0x38)==0x20
  fresh_delta=(y['sample_ms']-x['sample_ms'])/1000
  reads_ok=delta['reads']>=a.seconds*150 and .8*duration<=fresh_delta<=1.2*duration
  errors_ok=all(delta[key]==0 for key in fields if key!='reads')
  result.update(passed=healthy and magnet and reads_ok and errors_ok and prior==later,
   duration_s=duration,counter_deltas=delta,successful_reads_per_second=delta['reads']/duration,
   bus_and_angle_valid_at_endpoints=healthy,magnet_OK_at_endpoints=magnet,
   frozen_records_unchanged=prior==later,baseline_errors_total=x['errors'],final_errors_total=y['errors'],
   raw_angle_before=x['raw_angle'],raw_angle_after=y['raw_angle'],
   limitation='Installed diagnostic firmware in idle, with background ADC/communications; not a sensor-only minimal firmware and not a rotation/EMC qualification')
 except Exception as e:result['error']=str(e) or type(e).__name__
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k not in ('before','after')}),flush=True)
 return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

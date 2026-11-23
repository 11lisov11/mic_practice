"""One computation-only request. Requires separately confirmed discharged/off setup."""
import argparse,hashlib,json,time
from pathlib import Path
from no_switch_diag_io import PACKAGE,Probe,decode,eligible,read_report
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--confirm-j1-j4-off-meter-below20-nucleo-usb',action='store_true')
 p.add_argument('--request-once',action='store_true');p.add_argument('--outdir',type=Path,required=True)
 a=p.parse_args()
 if not a.confirm_j1_j4_off_meter_below20_nucleo_usb:p.error('Fresh physical OFF/independent meter/USB confirmation is required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);logs=out/'logs';logs.mkdir()
 m=json.loads((PACKAGE/'manifest.json').read_text(encoding='utf-8'));assert m['built'] and m['offline_verified']
 for rel,sha in m['sealed_sha256'].items():assert hashlib.sha256((PACKAGE/rel).read_bytes()).hexdigest()==sha,rel
 symbols=json.loads((PACKAGE/'verification/symbols.json').read_text(encoding='utf-8'))
 pr=Probe(logs);r=dict(hardware_tested=False,computation_requests=0,motor_start_commands=0,clear_commands=0,reset_commands=0,flash_commands=0)
 def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
 try:
  before=read_report(pr,symbols['mic_load_report']['address'],out,'before_initial');r['before_initial']=before;save()
  if not eligible(before):raise RuntimeError('Diagnostic admission failed; no request was sent')
  time.sleep(.3)
  fresh=read_report(pr,symbols['mic_load_report']['address'],out,'before_fresh')
  if not eligible(fresh) or fresh['sequence']==before['sequence'] or fresh['adc_seen']<=before['adc_seen']:
   raise RuntimeError('Fresh diagnostic/ADC progress not confirmed; no request was sent')
  before=fresh;r['before']=before;save()
  if not a.request_once:r['preflight_only']=True;return 0
  r['computation_requests']=1;save()
  pr.request(symbols['mic_load_request']['address'])
  # No debug memory polling during the five-second workload. The local DWT
  # guard and physical output inhibits are independent of this host wait.
  time.sleep(6)
  after=read_report(pr,symbols['mic_load_report']['address'],out,'after');r['after']=after
  if after['state']==1:
   r['cancel_requests']=1;save();pr.request(symbols['mic_load_request']['address'],cancel=True)
   raise RuntimeError('Local five-second bound not confirmed; canceled without retry')
  r['hardware_tested']=True
  r['timed_done']=after['state']==2 and after['reason']==0 and 5000<=after['elapsed_ms']<=5010
  r['outputs_disabled']=after['phase_pins_gpio_low']==1 and not(after['TIM1_BDTR']&0x8000)
  r['timing_coverage_ok']=79000<=after['tim_updates']<=80160 and 79000<=after['adc_calls']<=80160 and 2450<=after['medium_updates']<=2501
  r['full_current_processing_coverage']=after['adc_quality_flags']==1 and after['adc_accepted']>=79000
  r['i2c_error_delta']=after['encoder']['errors']-before['encoder']['errors']
  r['i2c_reads_delta']=after['encoder']['reads']-before['encoder']['reads']
  r['i2c_under_compute_load_ok']=r['i2c_error_delta']==0 and r['i2c_reads_delta']>500
  r['passed']=r['timed_done'] and r['outputs_disabled'] and r['timing_coverage_ok']
  r['full_ADC_processing_path_exercised']=r['passed'] and r['full_current_processing_coverage']
  r['motor_current_measurement_qualified']=False
  r['root_cause_proven']=False
  for name in ('fault_record','release_probe'):
   if name in symbols:
    d=symbols[name];(out/(name+'.bin')).write_bytes(pr.read(d['address'],d['bytes'],name))
  return 0 if r['passed'] else 1
 except Exception as e:r['error']=str(e);return 1
 finally:save();print(json.dumps({k:v for k,v in r.items() if k not in ('before','after')}))
if __name__=='__main__':raise SystemExit(main())

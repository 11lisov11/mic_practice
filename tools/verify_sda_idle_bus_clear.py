"""Passive post-install AS5600 verification; no motor, CLEAR or reset commands."""
import argparse,json,time,urllib.request
from pathlib import Path
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True);p.add_argument('--seconds',type=int,default=20,choices=range(10,31));a=p.parse_args()
 a.outdir.mkdir(parents=True,exist_ok=False);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));samples=[]
 r=dict(passed=False,motor_commands=0,clear_commands=0,reset_commands=0,flash_commands=0,pwm_validation=False)
 try:
  boot_deadline=time.monotonic()+25
  while True:
   try:
    with opener.open('http://127.0.0.1:18080/api/status',timeout=8) as f:s=json.load(f)['data']
    if (s.get('enc_bus_clear_record') is not None and s.get('enc_diag_category_counts_available')==1 and
        s.get('enc_fault_first_hex','-')!='-' and s.get('enc_release_first_hex','-')!='-'):break
   except Exception as exc:r['startup_last_error']=str(exc)
   if time.monotonic()>boot_deadline:raise RuntimeError('Read-only boot/record delivery did not complete')
   time.sleep(.5)
  end=time.monotonic()+a.seconds
  while time.monotonic()<end:
   with opener.open('http://127.0.0.1:18080/api/status',timeout=8) as f:response=json.load(f)
   assert response.get('ok') is True;s=response['data'];samples.append(s)
   with (a.outdir/'samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
   assert (s['fw_build'],s['mc_fw_build'])==(2026102707,2026102708)
   assert s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==0 and s['vdc']<20 and s['mc_age_ms']<300
   assert s['enc_bus_ok']==s['enc_ok']==1 and s['enc_age_ms']<100
   assert s['enc_fault_decode_valid']==s['enc_release_decode_valid']==s['enc_bus_clear_decode_valid']==1
   assert s['mc_sd_live']['available'] and s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['config_ok'] and s['mc_sd_live']['break_irq_enabled']
   time.sleep(.5)
  x,y=samples[0],samples[-1]
  keys=('enc_errors','enc_diag_controller_resets','enc_health_nack','enc_health_busy','enc_health_deadline','enc_health_arlo','enc_health_berr_clears','enc_peer_bad','enc_fault_bad','enc_release_bad','mc_bad_cnt','mc_uart_error_flags','rpc_response_timeouts','rpc_send_timeouts')
  delta={k:y[k]-x[k] for k in keys};assert all(v==0 for v in delta.values()),str(delta)
  assert y['enc_reads']-x['enc_reads']>1000
  for key in ('enc_fault_first_hex','enc_release_first_hex','enc_bus_clear_hex'):
   assert all(s[key]==x[key] for s in samples),'Frozen record changed: '+key
  r.update(passed=True,samples=len(samples),reads_delta=y['enc_reads']-x['enc_reads'],errors_total=y['enc_errors'],counter_deltas=delta,bus_clear=y['enc_bus_clear_record'],fault_current_mask=y['mc_fault_current_mask'],transport_latch=y['mc_transport_fault'],vdc=y['vdc'],duration_seconds=a.seconds)
 except Exception as exc:r['error']=str(exc)
 if samples:r['last']=samples[-1]
 (a.outdir/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in r.items() if k!='last'}));return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

"""Read-only USB/WiFi OFF-state check; sends no control or reset commands."""
import argparse,json,time,urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from current_zero_quality import ready
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--outdir',type=Path,required=True)
 p.add_argument('--url',default='http://127.0.0.1:18080')
 p.add_argument('--seconds',type=int,default=20,choices=range(5,46))
 p.add_argument('--confirm-j1-off-meter-below-20v',action='store_true')
 a=p.parse_args()
 if not a.confirm_j1_off_meter_below_20v:p.error('Operator-confirmed J1 OFF / DMM<20V required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 r=dict(passed=False,read_only=True,commands=0,flash_commands=0,clear_commands=0,reset_commands=0,physical_pwm_validated=False,requests=0)
 samples=[]
 def get():
  t=time.monotonic();opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with opener.open(a.url+'/api/status',timeout=10) as f:data=json.load(f)
  assert data.get('ok') is True and isinstance(data.get('data'),dict),'No current status'
  return data['data'],time.monotonic()-t
 try:
  deadline=time.monotonic()+15
  while True:
   s,dt=get()
   assert (s['fw_build'],s['mc_fw_build'])==(2026102703,2026102704)
   assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0 and not(s['bp_status']&0x22)
   assert 0<=s['vdc']<20 and 0<=s['mc_age_ms']<300
   if ready(s) and s.get('enc_diag_category_counts_available')==1:break
   if time.monotonic()>=deadline:raise RuntimeError('OFF autozero / category snapshot not ready')
   time.sleep(.25)
  start=time.monotonic()
  with ThreadPoolExecutor(max_workers=3) as pool:
   while time.monotonic()-start<a.seconds:
    futures=[pool.submit(get) for _ in range(3)]
    for f in futures:
     s,dt=f.result();r['requests']+=1;samples.append(s)
     with (out/'samples.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps(dict(status=s,http_seconds=dt))+'\n')
     assert (s['fw_build'],s['mc_fw_build'])==(2026102703,2026102704)
     assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0 and not(s['bp_status']&0x22)
     assert 0<=s['vdc']<20 and 0<=s['mc_age_ms']<300 and ready(s)
     assert s['enc_source']=='nucleo_g431_i2c1' and s['enc_bus_ok']==1 and s['enc_ok']==1 and s['enc_init_error']==0
     assert 0<=s['enc_age_ms']<200 and s['enc_diag_category_counts_available']==1
     assert s['enc_fault_decode_valid']==1
     sd=s['mc_sd_live'];assert sd['available'] and sd['config_ok'] and sd['level']=='HIGH' and 0<=sd['age_ms']<300
     r['max_http_seconds']=max(r.get('max_http_seconds',0),dt)
    time.sleep(.25)
  first,last=samples[0],samples[-1];r.update(first=first,last=last)
  counters=('enc_errors','enc_diag_controller_resets','enc_diag_timeout_count','enc_peer_bad','enc_fault_bad','mc_bad_cnt','mc_uart_error_flags','rpc_response_timeouts','rpc_send_timeouts','enc_health_nack','enc_health_busy','enc_health_arlo','enc_health_ovr','enc_health_short','enc_health_setup','enc_health_forced_resets','enc_health_stop_requests','enc_health_cleanup_expired')
  r['counter_deltas']={k:last[k]-first[k] for k in counters}
  assert all(v==0 for v in r['counter_deltas'].values()),'Counters changed at rest'
  r['reads_delta']=last['enc_reads']-first['enc_reads'];assert r['reads_delta']>100
  for k in ('enc_fault_first_hex','enc_fault_pwm_hex'):assert all(s[k]==first[k] for s in samples),'Saved capture changed'
  r['sd_irq_enabled']=last['mc_sd_live']['break_irq_enabled']
  r['passed']=True
 except Exception as exc:r['error']=str(exc)
 if samples:r['last_observed']=samples[-1]
 (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:r.get(k) for k in ('passed','requests','reads_delta','counter_deltas','max_http_seconds','sd_irq_enabled','error')}))
 return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

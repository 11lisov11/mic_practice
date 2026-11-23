"""Read-only concurrent web load after stack repair, no motor commands."""
import json,time
from concurrent.futures import ThreadPoolExecutor
import prepare_standstill_irq_timing as p
from current_only_lab import get_status
def main():
 out=p.OUT/'hardware_install_r1/rpc_idle_load';out.mkdir(exist_ok=False)
 rows=[];report=dict(passed=False,start_commands=0,clear_commands=0,read_only=True)
 try:
  first=get_status('http://127.0.0.1:18080');end=time.monotonic()+15
  def get():
   before=time.monotonic();s=get_status('http://127.0.0.1:18080');return dict(seconds=time.monotonic()-before,status=s)
  with ThreadPoolExecutor(max_workers=3) as pool:
   while time.monotonic()<end:
    for row in pool.map(lambda _:get(),range(3)):
     rows.append(row);s=row['status']
     assert (s['fw_build'],s['mc_fw_build'])==p.NEW and s['state']=='SAFE' and s['pwm']==0
     assert 0<=s['vdc']<=20 and 0<=s['mc_age_ms']<300
     assert 0<s.get('id_timing_cycles',0)<=4800 and s.get('rpc_stack_budget')==4096
     for key in ('rpc_response_timeouts','rpc_send_timeouts','rpc_late_responses','rpc_unknown_methods',
       'mc_transport_fault','mc_bad_cnt','research_native_bad','id_wire_bad'):
      assert s.get(key)==first.get(key)==0,key
  report.update(passed=True,requests=len(rows),maximum_http_s=max(r['seconds'] for r in rows),
    timing_cycles=rows[-1]['status']['id_timing_cycles'],stack_bytes=4096,stack_watermark_available=rows[-1]['status'].get('rpc_stack_free')!=4294967295)
 except Exception as exc:report['error']=str(exc)
 p.write(out/'samples.json',json.dumps(rows,ensure_ascii=False,indent=2));p.write(out/'report.json',json.dumps(report,indent=2))
 print(json.dumps(report));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

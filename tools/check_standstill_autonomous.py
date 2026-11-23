"""Observe autonomous boot only; never START/CLEAR/ARM/reset."""
import json,time
from pathlib import Path
from current_only_lab import get_status
import prepare_standstill_irq_timing as p
def main():
 out=p.OUT/'autonomous_before_first_point';out.mkdir(exist_ok=False)
 report=dict(passed=False,start_commands=0,clear_commands=0,reset_commands=0,errors=[]);rows=[];end=time.monotonic()+70;stable=0
 while time.monotonic()<end:
  try:
   s=get_status('http://192.168.1.138:8080');rows.append(s)
   assert (s['fw_build'],s['mc_fw_build'])==p.NEW,'wrong pair'
   assert s['state']=='SAFE' and s['pwm']==0 and not(s['bp_status']&0x22) and s['hmi_hv_armed']==0,'outputs/arm not OFF'
   assert 0<=s['vdc']<=20 and 0<=s['mc_age_ms']<300,'not fresh low bus'
   assert s.get('id_valid')==1 and 0<s.get('id_timing_cycles',0)<=4800,'timing not ready'
   assert s.get('mc_current_zero_ready')==1 and s.get('rpc_stack_budget')==4096,'zero/stack not ready'
   assert s.get('mc_sd_live',{}).get('level')=='HIGH','SD not HIGH'
   for k in ('rpc_response_timeouts','rpc_send_timeouts','rpc_late_responses','rpc_unknown_methods'):assert s.get(k)==0,k
   stable+=1
   if stable>=3:report.update(passed=True,after=s,samples=len(rows));break
  except Exception as exc:report['errors'].append(str(exc));stable=0
  time.sleep(.8)
 p.write(out/'status.json',json.dumps(rows,ensure_ascii=False,indent=2));p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2))
 last=rows[-1] if rows else {}
 print(json.dumps(dict(passed=report['passed'],errors=report['errors'][-3:],status={k:last.get(k) for k in
  ('fw_build','mc_fw_build','state','pwm','vdc','id_timing_cycles','mc_current_zero_ready','mc_fault_current_mask','mc_fault_occurred_mask','mc_transport_fault','estop')})))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

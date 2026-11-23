"""One ordinary ACK of saved startup UV/SD, for the authorized first ID point."""
import json,time,urllib.request
from pathlib import Path
from current_only_lab import get_status
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/live_bench_20261029/standstill_commissioning_r1/powered_preflight_r1'
URL='http://192.168.1.138:8080'
def eligible(s):
 sd=s.get('mc_sd_live') or {};snap=(s.get('mc_break_snapshots') or [{}])[0];event=snap.get('event') or {}
 return ((s.get('fw_build'),s.get('mc_fw_build'))==(2026102931,2026102932) and s.get('state')=='SAFE' and
  s.get('pwm')==0 and not(s.get('bp_status',0x22)&0x22) and s.get('hmi_hv_armed')==0 and s.get('estop')==0 and
  0<=s.get('mc_age_ms',9999)<300 and 250<=s.get('vdc',0)<=350 and s.get('mc_transport_fault')==0 and
  s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==1028 and s.get('mc_fault_reason')==8 and
  s.get('mc_current_zero_ready')==1 and s.get('bp_temp_valid')==1 and s.get('bp_temp_fault')==0 and
  s.get('id_flags')==0 and s.get('run_id')==0 and sd.get('level')=='HIGH' and sd.get('config_ok') is True and
  snap.get('captured') is True and event.get('moe_at_irq') is False and event.get('during_start_request_window') is False)
def main():
 log=OUT/'ack_report.json';assert not log.exists(),'No repeated CLEAR'
 report=dict(passed=False,clear_commands=0,start_commands=0,snapshots_erased=False)
 try:
  before=get_status(URL);assert eligible(before),'not solely saved startup UV/SD'
  raw=before['mc_break_wave_hex'];assert len(bytes.fromhex(raw))==320
  (OUT/'before_clear.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
  assert (OUT/'mc_break_wave_hex.bin').read_bytes()==bytes.fromhex(raw),'first snapshot changed'
  token=(ROOT/'.unoq_ssh/control_token').read_text(encoding='utf-8').strip()
  request=urllib.request.Request(URL+'/api/cmd',data=json.dumps({'cmd':'CLEAR'}).encode(),method='POST',
   headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token})
  report['clear_commands']=1
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as r:reply=json.load(r)
  assert reply.get('ok') is True,reply
  end=time.monotonic()+8
  while True:
   after=get_status(URL);assert after['pwm']==0 and after['state']=='SAFE','unexpected output state'
   sd=after.get('mc_sd_live') or {}
   if after['mc_fault_current_mask']==after['mc_fault_occurred_mask']==after['mc_transport_fault']==0 and sd.get('level')=='HIGH' and sd.get('break_irq_enabled') and sd.get('config_ok'):break
   assert time.monotonic()<end,'one CLEAR did not restore protection';time.sleep(.2)
  assert after['mc_break_wave_hex']==raw,'stored SD waveform changed'
  (OUT/'after_clear.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
  report.update(passed=True,break_irq_restored=True,snapshot_unchanged=True,after=after)
 except Exception as exc:report['error']=str(exc)
 log.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:report.get(k) for k in ('passed','clear_commands','start_commands','break_irq_restored','error')}))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

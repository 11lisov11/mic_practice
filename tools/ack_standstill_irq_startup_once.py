"""One normal CLEAR of a saved pre-START SD event on the authorized trial."""
import json,time,urllib.request
from pathlib import Path
import prepare_standstill_irq_timing as p
from current_only_lab import get_status
URL='http://192.168.1.138:8080'
def eligible(s):
 sd=s.get('mc_sd_live') or {};snap=(s.get('mc_break_snapshots') or [{}])[0];event=snap.get('event') or {}
 return ((s.get('fw_build'),s.get('mc_fw_build'))==p.NEW and s.get('state')=='SAFE' and s.get('pwm')==0 and
  not(s.get('bp_status',0x22)&0x22) and s.get('hmi_hv_armed')==0 and s.get('estop')==0 and
  0<=s.get('mc_age_ms',9999)<300 and 250<=s.get('vdc',0)<=350 and s.get('mc_transport_fault')==0 and
  s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==1024 and s.get('mc_fault_reason')==8 and
  s.get('run_id')==0 and s.get('id_flags') in (0,1) and 0<s.get('id_timing_cycles',0)<=4800 and
  s.get('mc_current_zero_ready')==1 and sd.get('level')=='HIGH' and sd.get('config_ok') is True and
  snap.get('captured') is True and event.get('moe_at_irq') is False and event.get('during_start_request_window') is False)
def main():
 out=p.OUT/'powered_preflight_r1';log=out/'ack_report.json';assert not log.exists(),'No repeated CLEAR'
 report=dict(passed=False,clear_commands=0,start_commands=0,snapshots_erased=False)
 try:
  end=time.monotonic()+20
  while True:
   before=get_status(URL);assert eligible(before),'not solely saved pre-START SD'
   raw=before.get('mc_break_wave_hex','-')
   if raw!='-':break
   assert time.monotonic()<end,'waiting for complete SD transport';time.sleep(.4)
  assert len(bytes.fromhex(raw))==320
  p.write(out/'before_clear.json',json.dumps(before,ensure_ascii=False,indent=2));(out/'sd_before_clear.bin').write_bytes(bytes.fromhex(raw))
  token=(p.ROOT/'.unoq_ssh/control_token').read_text(encoding='utf-8').strip()
  request=urllib.request.Request(URL+'/api/cmd',data=json.dumps({'cmd':'CLEAR'}).encode(),method='POST',
    headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token})
  report['clear_commands']=1
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=6) as r:reply=json.load(r)
  assert reply.get('ok') is True,reply
  end=time.monotonic()+8
  while True:
   s=get_status(URL);assert s['state']=='SAFE' and s['pwm']==0
   sd=s.get('mc_sd_live') or {}
   if s['mc_fault_current_mask']==s['mc_fault_occurred_mask']==s['mc_transport_fault']==0 and sd.get('level')=='HIGH' and sd.get('break_irq_enabled') and sd.get('config_ok'):break
   assert time.monotonic()<end,'one CLEAR did not restore guarded OFF';time.sleep(.25)
  assert s['mc_break_wave_hex']==raw,'SD waveform changed'
  p.write(out/'after_clear.json',json.dumps(s,ensure_ascii=False,indent=2));report.update(passed=True,break_irq_restored=True,snapshot_unchanged=True)
 except Exception as exc:report['error']=str(exc)
 p.write(log,json.dumps(report,indent=2));print(json.dumps(report));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

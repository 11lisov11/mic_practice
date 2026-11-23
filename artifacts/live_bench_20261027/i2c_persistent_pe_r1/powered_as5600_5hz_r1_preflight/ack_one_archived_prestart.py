"""Archive and acknowledge exactly one inactive pre-START SD event. No START."""
import json,hashlib,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tools'))
import run_persistent_pe_as5600_5hz as wrapper
run=wrapper.load_trial()
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token
c=Path.cwd()/'artifacts/live_bench_20261027/i2c_persistent_pe_r1/powered_as5600_5hz_r1_preflight'
run.configure(2026102709,'NUCLEO')
initial=json.loads((c/'pre_ack_fresh.json').read_text(encoding='utf-8'))
wave=initial['mc_break_wave_hex'];assert wave!='-'
event=next(x for x in initial['mc_break_snapshots'] if x['kind']=='first_since_boot')['raw']
assert event['current_faults']==event['occurred_faults']==0 and event['reference_speed_unit']==0 and event['motor_state']==0
def retained(s):
 try:return s['mc_break_wave_hex']==wave and next(x for x in s['mc_break_snapshots'] if x['kind']=='first_since_boot')['raw']==event
 except (KeyError,StopIteration):return False
def allowed(s):
 return (run.t.checks.off(s) and run.t.checks.transport_clean(s) and run.zero_ready(s) and run.setup_ok(s) and run.t.sd_high(s,False)
  and run.t.archive_before_start(s) and retained(s) and s.get('estop')==0
  and s.get('mc_fault')==s.get('bp_fault')==5 and s.get('mc_fault_reason')==8
  and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==1024
  and s.get('enc_errors')==0 and run.capture_ready(s))
r=dict(passed=False,clear_commands=0,start_commands=0,reset_commands=0,flash_commands=0,before=[],after=[],commands=[],wave_sha256=hashlib.sha256(bytes.fromhex(wave)).hexdigest(),authorization_scope='Necessary preparation of user-requested one5Hz/5s trial; no repeated CLEAR or running-fault acknowledgement')
h=WifiHmi('http://192.168.1.138:8080',read_token(str(Path.cwd()/'.unoq_ssh/control_token')),r['commands'],False)
def save():(c/'prestart_sd_ack.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
try:
 for _ in range(3):
  s=h.status();r['before'].append(s);assert allowed(s),'Pre-START SD acknowledgement not allowed';time.sleep(.2)
 for name,path in [('break_snapshot','/api/break-snapshot'),('bkin_trace','/api/bkin-trace')]:
  req=urllib.request.Request(h.base+path,headers={'X-UNOQ-Control-Token':h.token})
  with h.opener.open(req,timeout=8) as f:data=json.load(f)
  assert data.get('ok') is True
  (c/('prestart_'+name+'.json')).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
 save()
 # Offline negative controls ensure neither a running trip nor active input
 # or altered recorded event can pass this exact-event admission.
 import copy
 for key,value in [('pwm',1),('mc_fault_current_mask',1024),('mc_fault_occurred_mask',4),('mc_transport_fault',7),('vdc',0),('mc_age_ms',300)]:assert not allowed(dict(s,**{key:value}))
 q=copy.deepcopy(s);q['mc_sd_live']['level']='LOW';assert not allowed(q)
 s=h.status();assert allowed(s),'State changed before CLEAR'
 r['clear_commands']=1;save();h.command('CLEAR')
 deadline=time.monotonic()+8;stable=0
 while stable<3:
  s=h.status();r['after'].append(s)
  assert retained(s),'Saved SD event changed'
  okay=run.t.ready(s) and run.setup_ok(s) and run.capture_ready(s) and s['enc_bus_ok']==1 and s['enc_errors']==0
  stable=stable+1 if okay else 0
  if time.monotonic()>deadline:raise RuntimeError('One CLEAR failed to restore protected ready; no retry')
  time.sleep(.2)
 r['passed']=True;r['archive_preserved']=True
except Exception as exc:r['error']=str(exc)
finally:save();h.close()
print(json.dumps({k:r.get(k) for k in ('passed','clear_commands','start_commands','archive_preserved','error')}))
raise SystemExit(0 if r['passed'] else 1)

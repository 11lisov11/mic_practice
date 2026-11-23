"""One existing MCU-timed5s trial, qualified for2709/2710; no automatic CLEAR."""
import argparse,hashlib,json,sys,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026102709,2026102710)
def once(s,a,b):assert s.count(a)==1,a;return s.replace(a,b)
def trial_source():
 p=ROOT/'tools/run_as5600_bounded_5hz.py';s=p.read_text(encoding='utf-8')
 s=once(s,'2026102703:2026102704}','2026102703:2026102704,2026102709:2026102710}')
 s=s.replace('(2026102703,2026102704)','(2026102703,2026102704),(2026102709,2026102710)')
 s=once(s,'2026102701,2026102703)','2026102701,2026102703,2026102709)')
 return s
def load_trial():
 module=types.ModuleType('persistent_pe_existing_trial');module.__file__=str(ROOT/'tools/run_as5600_bounded_5hz.py')
 exec(compile(trial_source(),module.__file__,'exec'),module.__dict__)
 z=(ROOT/'tools/current_zero_quality.py').read_text(encoding='utf-8')
 z=once(z,'(2026102703,2026102704)','(2026102703,2026102704),(2026102709,2026102710)')
 ns={};exec(compile(z,'current_zero_quality_with2710','exec'),ns)
 module.zero_ready=ns['ready'];module.t.zero_ok=ns['ready']
 return module
def extension_complete(s):
 if s.get('enc_fault_decode_valid')!=1 or s.get('enc_release_decode_valid')!=1:return False
 for parent,child in (('enc_fault_first_hex','enc_release_first_hex'),('enc_fault_pwm_hex','enc_release_pwm_hex')):
  if s.get(parent,'-')!='-' and s.get(child,'-')=='-':return False
 return True
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-powered-ready',action='store_true');p.add_argument('--outdir',type=Path,required=True);a=p.parse_args()
 if not a.confirm_powered_ready:p.error('Fresh powerbank/PC-off/powered-ready operator confirmation is required')
 module=load_trial();old=sys.argv
 sys.argv=[old[0],'--confirm-powered-ready','--outdir',str(a.outdir),'--uno-build',str(PAIR[0]),'--sensor-mode','NUCLEO','--collect-first-i2c-fault']
 try:code=module.main()
 finally:sys.argv=old
 report_path=a.outdir/'report.json';r=json.loads(report_path.read_text(encoding='utf-8'))
 # Keep original timing/current pass/fail verbatim. Extension collection below
 # is read-only and occurs only after fresh OFF has already been confirmed.
 q=dict(passed=False,hardware_motor_commands=0,clear_commands=0,old_trial_exit=code,initial_nack_cause_proven=False)
 if r.get('outputs_off_confirmed'):
  h=module.WifiHmi('http://192.168.1.138:8080',module.read_token(str(ROOT/'.unoq_ssh/control_token')),[],False)
  try:
   deadline=time.monotonic()+8
   while True:
    s=h.status()
    with (a.outdir/'after_release_status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
    if not module.t.checks.off(s):raise RuntimeError('Fresh OFF changed during extension collection')
    if extension_complete(s):break
    if time.monotonic()>deadline:raise RuntimeError('PE0 extension not complete; old records remain saved')
    time.sleep(.25)
   q.update(passed=True,final=s,errors_delta=s.get('enc_errors',0)-r.get('before',{}).get('enc_errors',0),reads_delta=s.get('enc_reads',0)-r.get('before',{}).get('enc_reads',0))
  except Exception as exc:q['error']=str(exc)
  finally:h.close()
 else:q['error']='Original trial did not confirm OFF; no further diagnostic commands'
 (a.outdir/'release_capture_result.json').write_text(json.dumps(q,indent=2)+'\n',encoding='utf-8')
 return code if q['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

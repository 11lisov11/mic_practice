"""OFF-only checks, including the newly measured conservative CPU/IRQ split."""
import json,sys
from pathlib import Path
import verify_estimated_foc_idle as verify
import prepare_foc_runtime_fix as package
verify.p=package

def main():
 rc=verify.main()
 if rc:return rc
 out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
 r=json.loads(package.read(out/'report.json'));s=r['after'];d=s.get('foc_runtime') or {}
 try:
  assert d.get('available') and d.get('observer_measured')
  assert d['source']=='OFF_synthetic_CPU_probe'
  assert d['meter_errors']==0 and d['first_fault'] is None and d['observer_steps']==64
  assert 0<=d['irq_body_lower_us']<=d['observer_wall_us']
  assert abs(d['cpu_upper_us']+d['irq_body_lower_us']-d['observer_wall_us'])<.01
  assert s['algorithm_fault']==0 and s['run_id']==0
  assert s['mc_bad_integrity']==s['mc_uart_error_flags']==s['mc_transport_fault']==0
  r.update(OFF_CPU_IRQ_split_verified=True,runtime_timing=d)
 except Exception as e:r.update(passed=False,error='OFF runtime split: '+str(e))
 package.write(out/'report.json',json.dumps(r,ensure_ascii=False,indent=2))
 print(json.dumps({k:r.get(k) for k in ('passed','OFF_CPU_IRQ_split_verified','error')}))
 return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

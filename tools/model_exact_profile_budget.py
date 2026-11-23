"""Differential plant model, own old/new headers, unchanged 2ms refusal."""
import inspect,json
from types import SimpleNamespace
import model_observer_voltage_stop as prior
import test_foc_runtime_fix as common
import prepare_exact_profile_budget as p


def main():
 original=common.compile_run
 def variant(out,name,code):
  common.p=SimpleNamespace(OUT=p.BASE if name.endswith('_baseline') else p.OUT,write=p.write)
  # Both sides now contain the same independent per-vector diagnostics.
  code='#include "irq_breakdown.h"\n'+code
  try:return original(out,name,code)
  finally:common.p=p
 common.compile_run=variant
 try:
  source=inspect.getsource(prior.main);scope=dict(prior.__dict__,p=p)
  exec(compile(source,__file__,'exec'),scope);scope['main']()
 finally:common.compile_run=original
 f=p.OUT/'model_verification/model_report.json';r=json.loads(p.read(f))
 assert r['baseline_results']==r['results'],'Actuator trajectories changed'
 r.update(baseline_candidate_model_trajectories_identical=True,own_release_headers_used=True,
          target_CPU_timing_measured=False,hardware_commands=0,IRQ_deadlines_proven_by_model=False,
          original_hypot_core_output_equivalence_separately_proven=True)
 p.write(f,json.dumps(r,ensure_ascii=False,indent=2)+'\n')
 print('All independent plant scenarios identical; no target cycle claim')


if __name__=='__main__':main()

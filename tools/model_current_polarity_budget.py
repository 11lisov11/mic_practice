"""Differential independent-plant simulation using each release's own headers."""
import inspect,json
from types import SimpleNamespace
import model_observer_voltage_stop as prior
import test_foc_runtime_fix as common
import prepare_current_polarity_budget as p


def main():
 compile_original=common.compile_run
 def compile_variant(out,name,code):
  common.p=SimpleNamespace(OUT=p.BASE if name.endswith('_baseline') else p.OUT,write=p.write)
  try:return compile_original(out,name,code)
  finally:common.p=p
 common.compile_run=compile_variant
 try:
  source=inspect.getsource(prior.main)
  scope=dict(prior.__dict__,p=p)
  exec(compile(source,__file__,'exec'),scope);scope['main']()
 finally:common.compile_run=compile_original
 f=p.OUT/'model_verification/model_report.json';r=json.loads(p.read(f))
 assert r['baseline_results']==r['results'],'Optimization changed simulated trajectories'
 r.update(baseline_candidate_model_trajectories_identical=True,own_release_headers_used=True,
  target_CPU_timing_measured=False,hardware_commands=0)
 p.write(f,json.dumps(r,ensure_ascii=False,indent=2)+'\n')
 print('Own-header baseline/candidate model trajectories identical; target timing unmeasured')


if __name__=='__main__':main()

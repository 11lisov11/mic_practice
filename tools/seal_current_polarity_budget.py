"""Seal an offline numerically exact optimization; never access boards."""
import inspect,json
import seal_observer_input_epoch as old
import prepare_current_polarity_budget as p


def main():
 assert json.loads(p.read(p.OUT/'verification/ARM_optimization_scope.json'))['passed']
 r=json.loads(p.read(p.OUT/'verification/report.json'));assert r['passed']
 model=json.loads(p.read(p.OUT/'model_verification/model_report.json'))
 assert model['passed'] and model['baseline_candidate_model_trajectories_identical'] and model['own_release_headers_used']
 src=inspect.getsource(old.main)
 src=src.replace('_observer_input.hex','_current_polarity_budget.hex').replace('_observer_trace.elf-zsk.bin','_current_polarity_budget.elf-zsk.bin')
 scope=dict(old.__dict__,p=p);exec(compile(src,__file__,'exec'),scope);scope['main']()
 m=json.loads(p.read(p.OUT/'manifest.json'))
 m.update(numeric_bit_exact=True,numeric_tests=r['numeric'],unchanged_source_files=r['unchanged_source_files'],
  profiling_work_removed=False,target_timing_measured=False,OFF_CPU_qualified=False,
  FOC_start_ready=False,installed=False,
  verification_reports={rel:p.sha(p.OUT/rel) for rel in ('verification/report.json','verification/ARM_optimization_scope.json','model_verification/model_report.json')})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')


if __name__=='__main__':main()

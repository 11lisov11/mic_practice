"""Independent flux-plant adapter simulation; NOT replay of hardware currents."""
import inspect
import json
import model_observer_trace as old
import prepare_observer_input_epoch as p


def main():
    src=inspect.getsource(old.main)
    src=src.replace("    assert results['baseline']==results['candidate'],'Diagnostics changed simulated actuator trajectory'", "")
    src=src.replace('baseline_candidate_model_trajectories_identical=True',
                    'baseline_candidate_model_trajectories_identical=False,baseline_results=results[\'baseline\']')
    src=src.replace('trajectories_identical=True', 'trajectories_identical=False')
    src=src.replace("p.OUT/'verification'", "p.OUT/'model_verification'")
    src=src.replace('out.mkdir(exist_ok=True)', 'out.mkdir(exist_ok=True)')
    scope=dict(old.__dict__,p=p)
    exec(compile(src,__file__,'exec'),scope)
    scope['main']()
    f=p.OUT/'model_verification/model_report.json'
    report=json.loads(p.read(f))
    report['simulated_input_epoch_fix']=True
    report['hardware_record_replay']=False
    report['target_CPU_cycles_measured']=False
    p.write(f,json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()

"""Independent flux-plant simulation with active compare/current ADC context."""
import inspect,json
import model_observer_trace as old
import prepare_observer_voltage_stop as p


def main():
 src=inspect.getsource(old.main)
 src=src.replace("    assert results['baseline']==results['candidate'],'Diagnostics changed simulated actuator trajectory'",'')
 src=src.replace('baseline_candidate_model_trajectories_identical=True',
  "baseline_candidate_model_trajectories_identical=False,baseline_results=results['baseline']")
 src=src.replace('trajectories_identical=True','trajectories_identical=False')
 src=src.replace("p.OUT/'verification'","p.OUT/'model_verification'")
 src=src.replace("pre='#include \"observer_trace_core.h\"", "pre='#include \"observer_applied_voltage.h\"\\n#include \"observer_trace_core.h\"")
 # Each current measurement carries the compare set applied in the preceding
 # simulated plant step, independently of the newly calculated next command.
 anchor="    tail=tail.replace(' int rc=ma_native_fast(reference);',"
 extra='''    tail=tail.replace(' sample.counts[2]=(int16_t)(-sample.counts[0]-sample.counts[1]);',
        ' sample.counts[2]=(int16_t)(-sample.counts[0]-sample.counts[1]);sample.arr=timer.ARR;sample.bus_v=fake_bus;sample.ccr[0]=timer.CCR1;sample.ccr[1]=timer.CCR2;sample.ccr[2]=timer.CCR3;')
    tail=tail.replace('assert(ma_native_prepare());timer.BDTR=1;plant.m=model;',
        'assert(ma_native_prepare());timer.CCR1=timer.CCR2=timer.CCR3=timer.ARR/2;timer.BDTR=1;plant.m=model;')
'''
 assert anchor in src;src=src.replace(anchor,extra+anchor)
 scope=dict(old.__dict__,p=p);exec(compile(src,__file__,'exec'),scope);scope['main']()
 f=p.OUT/'model_verification/model_report.json';r=json.loads(p.read(f))
 r.update(measured_current_replay=False,hardware_root_cause_proven=False,
  voltage_source='ADC active CCR model with unchanged deadtime, not voltage measurement',
  target_CPU_timing_measured=False)
 p.write(f,json.dumps(r,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()

"""Offline-only evidence audit and independent inverter sensitivity experiment.

No network, serial, programmer, bench command or firmware writes. Existing
releases and captures are inputs. Results go to a new, exclusive directory.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess

from test_foc_estimate_publish_fix import native_source
from test_observer_current_window import compile_case

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'artifacts/live_bench_20261116/observer_current_window_r1'
CAP = RELEASE / 'FOC_5Hz_20261117_r1'
OUT = ROOT / 'artifacts/live_bench_20261117/remaining_nis_offline_r1'


def read(path):
    return path.read_text(encoding='utf8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def audit():
    protected = {}
    for manifest in ('saved_files_sha256.json', 'analysis_files_sha256.json',
                     'extended_saved_files_sha256.json'):
        for relative, expected in json.loads(read(CAP / manifest)).items():
            path = CAP / relative
            assert digest(path) == expected, str(path)
            protected[str(path.relative_to(ROOT))] = expected
    for relative, expected in json.loads(read(RELEASE / 'source_hashes.json')).items():
        path = RELEASE / relative
        assert digest(path) == expected, str(path)
        protected[str(path.relative_to(ROOT))] = expected
    write(OUT / 'protected_inputs_sha256.json', protected)
    trace = json.loads(read(CAP / 'observer_trace_decoded.json'))
    rows = []
    for r in [trace['first_loss']] + trace['samples']:
        e = r['innovation_A']; s = r['innovation_variance_A2']
        nis = sum(a*a/b for a, b in zip(e, s))
        assert math.isclose(nis, r['nis'], rel_tol=2e-6)
        assert r['control_adc_cycles'] == r['observer_adc_cycles'] == r['bin_cycles']
        # beta is CONDITIONAL after the alpha update: rotating these innovations
        # as if they were an unconditioned physical residual would be misleading.
        rows.append(dict(step=r['steps'], NIS=nis,
                         standardized_conditional_innovation=[a/math.sqrt(b) for a,b in zip(e,s)],
                         conditional_innovation_A=e, sigma_A=[math.sqrt(b) for b in s],
                         reference_hz=r['reference_hz'], rpm_est=r['rpm_est'],
                         modeled_voltage_magnitude_V=math.hypot(r['input_va_V'],r['input_vb_V']),
                         flux_Wb=r['flux_wb']))
    loss = trace['first_loss']
    adc = json.loads(read(CAP / 'ADC_decoded.json'))
    first = adc['samples'][0]['cycles']
    timing = {
        'ADC_after_mean_us': ((first-loss['observation_cycles']) & 0xffffffff)/170,
        'ADC_after_endpoint_us': ((first-loss['bin_cycles']) & 0xffffffff)/170,
        'mean_to_endpoint_us': loss['forecast_dt_s']*1e6,
    }
    ls=.528093860573909; lm=.4944775988161633; lr=ls
    leakage = ls-lm*lm/lr
    # Sensitivity scale only, NOT an identified voltage or physical root cause:
    # ignores Rs damping and flux/speed feedback over the interval.
    scales = [abs(e)*leakage/loss['dt_s'] for e in loss['innovation_A']]
    result = dict(hardware_commands=0, protected_files=len(protected), rows=rows,
                  timing=timing, leakage_H=leakage,
                  one_step_voltage_error_scale_V=scales,
                  physical_root_cause_proven=False, full_record_replay_possible=False,
                  missing='Prior EKF state/covariance and all effective input samples were not recorded',
                  conditional_innovations_not_rotated_as_physical_dq=True)
    write(OUT / 'recorded_audit.json', result)
    return protected


def inverter_experiment():
    template = read(ROOT / 'artifacts/live_bench_20261116/clear_recovery_r1/model_verification/plant_observer_candidate.cpp')
    pre = template.split('#define MIC_NATIVE_BUILD', 1)[0]
    tail = template[template.index('#undef ma_observe'):]
    tail = tail.replace('sample.valid=sample.zero=1;sample.cycles=cycle.CYCCNT-4000;',
                        'sample.zero=1;sample.valid=(frames>0);sample.cycles=cycle.CYCCNT-4000;')
    tail = tail.replace(' int rc=ma_native_fast(reference);', '''
 if(scenario==16){sample.counts[0]+=8;sample.counts[1]-=4;sample.counts[2]=-sample.counts[0]-sample.counts[1];}
 if(scenario==17&&frames==20000U){sample.counts[0]=150;sample.counts[1]=-75;sample.counts[2]=-75;}
 if(scenario==18||scenario==19){
  double gain=scenario==18?.9:1.1;
  sample.counts[0]=(int16_t)lround(a*gain/amp);
  sample.counts[1]=(int16_t)lround((-.5*a+.8660254037844386*b)*gain/amp);
  sample.counts[2]=-sample.counts[0]-sample.counts[1];
 }
 int rc=ma_native_fast(reference);''')
    # The plant no longer consumes controller.last_va/vb (which shares the
    # controller's inverter assumptions). Calculate terminal voltage in double
    # from the new PWM compares, true plant current and independently varied
    # deadtime, device drop and conduction resistance. Smooth sign near zero is
    # explicit; this synthetic model is not claimed to identify the real IPM.
    tail = tail.replace(' plant.step(controller.last_va,controller.last_vb,10624./170000000.);', '''
 double dticks=229.,drop=0.,ron=0.;
 if(scenario>=8&&scenario<=11)drop=(scenario-7)*.5;
 if(scenario==12)dticks+=42.5; // additional0.25us
 if(scenario==13)dticks+=85.;  // additional0.50us
 if(scenario==14)dticks-=42.5;
 if(scenario==15)ron=1.;
 const double iph[3]={a,-.5*a+.8660254037844386*b,-.5*a-.8660254037844386*b};
 const double cc[3]={(double)timer.CCR1,(double)timer.CCR2,(double)timer.CCR3};
 double legs[3];
 for(int i=0;i<3;++i){
  double polarity=std::max(-1.,std::min(1.,iph[i]/.05));
  legs[i]=fake_bus*cc[i]/timer.ARR-(fake_bus*dticks/(2.*timer.ARR)+drop)*polarity-ron*iph[i];
 }
 const double av=(legs[0]+legs[1]+legs[2])/3.;
 plant.step(legs[0]-av,(legs[1]-legs[2])/sqrt(3.),10624./170000000.);''')
    assert 'plant.step(controller.last_va' not in tail
    extra = '#include "observer_current_window.h"\n#include "observer_forecast.h"\n'
    exe = compile_case(OUT, 'independent_inverter', extra+pre+native_source(RELEASE)+'\n'+tail, RELEASE)
    cases = [
        (0,'independent_nominal'), (1,'Rs_plus20pct'),(2,'Rr_plus20pct'),(3,'Lm_minus5pct'),
        (4,'ADC_1count'),(5,'ADC_16counts'),(8,'device_drop_0_5V'),(9,'device_drop_1V'),
        (10,'device_drop_1_5V'),(11,'device_drop_2V'),(12,'deadtime_plus0_25us'),
        (13,'deadtime_plus0_50us'),(14,'deadtime_minus0_25us'),(15,'device_Ron_1ohm'),
        (16,'ADC_offset_alpha8counts'),(17,'raw_overcurrent'),(18,'current_gain_minus10pct'),
        (19,'current_gain_plus10pct')]
    results=[]
    for scenario, name in cases:
        run=subprocess.run([str(exe),'95737','17000',str(scenario),str(OUT/(name+'.bin'))],
                           capture_output=True,text=True,check=True)
        results.append(dict(case=name, **json.loads(run.stdout)))
    run=subprocess.run([str(exe),'357000','0','0',str(OUT/'observer_2_1ms.bin')],
                       capture_output=True,text=True,check=True)
    stale=dict(case='observer_2_1ms',**json.loads(run.stdout));results.append(stale)
    assert results[0]['completed_5s'] and results[0]['native_valid_fraction_after1s']>.99
    assert results[15]['fault']==2 and not results[15]['completed_5s']
    assert stale['fault']==3 and not stale['completed_5s']
    report=dict(results=results, hardware_commands=0, installed_firmware_changed=False,
                tested_source_directory=str(RELEASE),
                target_cycles_measured=False, assumed_wall_cycles=95737,
                assumed_queue_cycles=17000, full_hardware_replay=False,
                plant_voltage_independent_of_controller_last_voltage=True,
                thresholds_and_motor_profile_unchanged=True)
    write(OUT/'independent_inverter_report.json', report)
    return results


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    protected=audit()
    results=inverter_experiment()
    for relative, expected in protected.items():
        assert digest(ROOT/relative)==expected, relative
    write(OUT/'summary.json', dict(passed=True, hardware_commands=0,
          captures_and_firmware_unchanged=True, verified_files=len(protected),
          independent_cases=len(results), physical_root_cause_proven=False,
          safe_to_raise_FOC_speed_limit=False))
    for r in results:
        print(r['case'], 'complete',r['completed_5s'],'valid',round(r['native_valid_fraction_after1s'],3),
              'NIS',round(r['peak_NIS'],2),'speed_RMSE',round(r['speed_RMSE_after1s_rpm'],2))


if __name__=='__main__':
    main()

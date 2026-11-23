"""Audit the real step 536 and test reduction of I/f current-feedback ripple."""

import csv
import difflib
import json
import math
import struct
import subprocess

import numpy as np

import build_foc_handover_budget_release as release
import check_foc_rotating_start as rotating
from replay_start_history import ArmObserver, pair_counts, replay
from run_handover_budget_paged_trial import verify_release
from test_observer_current_window import compile_case


BASE = release.OUT
TRIAL = BASE / 'FOC_5Hz_if_handover_r1'
HISTORY = BASE / 'FOC_5Hz_if_handover_r1_history'
OUT = BASE / 'if_current_feedback_r2'
HEADER, NATIVE = rotating.HEADER, rotating.NATIVE
change = rotating.change
REST_SPEED_VARIANCE = 1.0
UNLOADED_TORQUE_VARIANCE = 0.000025


def prepare():
    original = release.read(BASE / HEADER)
    header = change(original, '  float start_cos,start_sin;', '''  float start_cos,start_sin;
  float if_last_ia,if_last_ib;''')
    header = change(header, '    c->start_cos=1.f;c->start_sin=0.f;c->preflux=1U;', '''    c->start_cos=1.f;c->start_sin=0.f;c->preflux=1U;
    c->if_last_ia=ia;c->if_last_ib=ib;''')
    header = change(header, '  const float id=c0*ia+s*ib,iq=-s*ia+c0*ib;', '''  /* During I/f only, attenuate alternating ADC-frame feedback before the
   * current PI. Raw ia/ib have already passed the original current trip.
   * Keep the dead-time polarity and the 16-frame observer input raw. */
  float feedback_ia=ia,feedback_ib=ib;
  if(c->preflux==1U){
    feedback_ia=.5f*(ia+c->if_last_ia);feedback_ib=.5f*(ib+c->if_last_ib);
    c->if_last_ia=ia;c->if_last_ib=ib;
  }
  const float id=c0*feedback_ia+s*feedback_ib,iq=-s*feedback_ia+c0*feedback_ib;''')
    before_native = release.read(BASE / NATIVE)
    native = change(before_native, '  fe_test_controller.preflux=(uint8_t)(fe_n%3U);', '''  fe_test_controller.preflux=(uint8_t)(fe_n%3U);
  if(!fe_n){fe_test_controller.if_last_ia=fe_test_ia;fe_test_controller.if_last_ib=fe_test_ib;}''')
    native = change(native, '  memset(&field_rate,0,sizeof(field_rate));', f'''  memset(&field_rate,0,sizeof(field_rate));
  if(qualification==FE_ESTIMATED&&selected==MA_FOC){{
    /* This bounded test starts the unloaded bench motor from rest. The old
     * generic prior allowed hundreds of rpm before a rotating field existed.
     * Use initial uncertainties of 1 rad/s and 5 mN m. The electrical part
     * of x/P, process/measurement noise and NIS tests remain unchanged.
     * nh_begin below records this initial P for exact future replay. */
    observer.p[4][4]={REST_SPEED_VARIANCE:.1f}f;
    observer.p[5][5]={UNLOADED_TORQUE_VARIANCE:.6f}f;
  }}''')
    candidate = OUT / 'candidate'
    patch = []
    for rel,old,new in ((HEADER,original,header),(NATIVE,before_native,native)):
        dest = candidate / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        release.write(dest,new)
        patch.extend(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),
                                          'a/'+rel,'b/'+rel))
    release.write(OUT/'if_current_feedback.patch',''.join(patch))
    return candidate


def replay_with_rest_prior(arm, journal):
    meta = (journal/'meta.bin').read_bytes()
    source = (journal/'rows.bin').read_bytes()
    prior = bytearray(meta[116:320])
    assert struct.unpack_from('<2f',prior,16)==(0.,0.)
    for index,variance in ((4,REST_SPEED_VARIANCE),(5,UNLOADED_TORQUE_VARIANCE)):
        struct.pack_into('<f',prior,4*(6+6*index+index),variance)
    result=[]
    for index in range(0,len(source),22):
        row=source[index:index+22]
        rc,prior,_=arm.step(prior,meta[64:116],row[:20],(row[21]>>3)<<22,pair_counts(row[20]))
        assert rc==0,(index,rc)
        state=struct.unpack_from('<6f',prior)
        score=struct.unpack_from('<f',prior,168)[0]
        result.append(dict(step=index//22+1,NIS=score,omega_rad_s=state[4],load_torque_Nm=state[5],
                           flux_Wb=math.hypot(state[2],state[3])))
    return result


def analyze(elf):
    analysis = TRIAL.with_name(TRIAL.name + '_analysis')
    trace = release.read_json(analysis/'observer_trace_decoded.json')
    adc = release.read_json(analysis/'ADC_decoded.json')
    rep = trace['first_nis_replay']
    assert rep['post_steps']==adc['source_observer_step']==536 and adc['source_window_exact']
    end = next(i for i,r in enumerate(adc['samples']) if r['cycles']==adc['requested_end_cycles'])+1
    windows = [adc['samples'][end+i-16:end+i] for i in (-32,-16,0)]
    current = [np.array([row['nominal_currents_a'] for row in window]) for window in windows]
    assert all(len(w)==16 and all(r['pair']==1 and r['accepted_by_monitor'] for r in w) for w in windows)
    u = current[2][:,0]
    prior = rep['prior_state'][0]
    pred = rep['predicted_current_A'][0]
    gap = float(u.mean()-pred)
    prev = float(current[1][:,0].mean())
    raw = bytes.fromhex(rep['raw_hex'])
    counts = struct.unpack_from('<I',raw,452)[0]>>8
    state = raw[:168]+bytes(28)+raw[168:176]
    rc, post, _ = ArmObserver(elf).step(state,raw[176:228],raw[228:248],rep['fpscr'],counts)
    assert rc==rep['result']==0 and post==raw[248:444]+struct.pack('<II',rep['post_steps'],rep['post_rejected'])
    history = replay(HISTORY,elf,release.NEW[1],OUT/'ARM_start_history.jsonl')
    rest_history=replay_with_rest_prior(ArmObserver(elf),HISTORY)
    release.save(OUT/'ARM_same_inputs_rest_prior.json',rest_history)
    original=[json.loads(line) for line in (OUT/'ARM_start_history.jsonl').read_text(encoding='utf8').splitlines()]
    # Disturbance fixture: remove each 1 ms mean phase current. The results
    # represent the captured deviation at the two direct ADC paths, including
    # any true ripple. They are neither a hardware noise measurement nor a fit.
    residuals = []
    for window in windows:
        samples = np.array([row['raw_adc'] for row in window],dtype=int)
        for sample in samples:
            residuals.append([int(x) for x in np.rint(samples.mean(axis=0)-sample)])
    result = {
        'step':536,'electrical_reference_Hz':trace['first_loss']['reference_hz'],'NIS':rep['nis'],
        'conditional_NIS_terms':trace['first_loss']['NIS_components'],
        'phase_U_mean_A_534_535_536':[float(c[:,0].mean()) for c in current],
        'previous_window_mean_minus_prior_U_A':prev-prior,
        'change_in_measured_U_since_previous_window_A':float(u.mean()-prev),
        'predictor_change_U_this_step_A':pred-prior,
        'total_U_innovation_A':gap,
        'previous_gap_fraction_of_final_U_innovation':(prev-prior)/gap,
        'phase_U_max_consecutive_change_A':float(max(abs(np.diff(u)))),
        'phase_U_peak_to_peak_A':float(np.ptp(u)), 'bit_exact_NIS_51_words':True,
        'first_crossing_during_warmup':history,'centered_ADC_residual_fixture_counts':residuals,
        'first_237_steps_same_inputs_rest_prior':{
            'score_at_237_before':original[-1]['NIS'],'score_at_237_candidate':rest_history[-1]['NIS'],
            'peak_NIS_before':max(row['NIS'] for row in original),
            'peak_NIS_candidate':max(row['NIS'] for row in rest_history),
            'rpm_at_100_before':original[99]['x'][4]*30/math.pi,
            'rpm_at_100_candidate':rest_history[99]['omega_rad_s']*30/math.pi,
            'crossings_candidate':sum(row['NIS']>=25. for row in rest_history),
            'not_a_replay_of_unavailable_steps_238_to_535':True,
        },
        'scope':'No measured terminal voltage or independent rotor speed. Centered real frame deviations exercise I/f feedback in a separate model, not a closed-loop replay of the physical bench.',
    }
    release.save(OUT/'saved_evidence.json',result)
    return result


def simulate(candidate, residuals):
    reports={}
    root=OUT/'PC';root.mkdir()
    raw_fixture = ','.join('{%d,%d}' % tuple(row) for row in residuals)
    scenarios=(('nominal',0),('captured_frame_deviations',24),('larger_frame_deviations',25),
               ('Rs_plus20pct',1),('Rr_plus20pct',2),('voltage_model_1V',9),('edge_model_minus250ns',14),
               ('current_trip',17),('estimate_age_2_1ms',0),('NIS_25',21),('NIS_just_below_25',22))
    for name,model in (('installed',BASE),('filtered_IF',candidate)):
        source=rotating.model_source(model,name if name!='installed' else 'baseline')
        source=change(source,'static double maximum_plant_rpm;',f'''static double maximum_plant_rpm;
static const int captured[48][2]={{{raw_fixture}}};
static double previous_alpha,previous_beta,delta_voltage_squared;
static unsigned voltage_samples;''')
        source=change(source,' if(scenario==16)n0+=8;', ''' if(scenario==16)n0+=8;
 if(scenario==24||scenario==25){
  const unsigned index=(frames-1U)%48U;
  const int gain=scenario==24?1:2;
  n0+=gain*captured[index][0];n1+=gain*captured[index][1];
 }''')
        source=change(source,' plant.step(legs[0]-av,(legs[1]-legs[2])/sqrt(3.),10624./170000000.);', ''' const double alpha=legs[0]-av,beta=(legs[1]-legs[2])/sqrt(3.);
 const double secs=(next_irq-origin)/170000000.;
 if(secs>=.45&&secs<.55){
  const double da=alpha-previous_alpha,db=beta-previous_beta;
  delta_voltage_squared+=da*da+db*db;
  ++voltage_samples;
 }
 previous_alpha=alpha;previous_beta=beta;
 plant.step(alpha,beta,10624./170000000.);''')
        source=change(source,r'\"maximum_plant_rpm\":%.9g}',r'\"maximum_plant_rpm\":%.9g,\"IF_delta_voltage_rms_V\":%.9g,\"IF_delta_voltage_samples\":%u}')
        source=change(source,'handover_step,maximum_plant_rpm);',
                      'handover_step,maximum_plant_rpm,voltage_samples?sqrt(delta_voltage_squared/voltage_samples):0.,voltage_samples);')
        exe=compile_case(root,name,source,BASE)
        for scenario,number in scenarios:
            timing=['357000','0'] if scenario=='estimate_age_2_1ms' else ['95737','17000']
            command=[str(exe),*timing,str(number),str(root/f'{name}_{scenario}.bin'),'.40']
            data=json.loads(subprocess.check_output(command,text=True,timeout=25))
            reports.setdefault(scenario,{})[name]=data
    release.save(root/'cases.json',reports)
    return reports


def main():
    _,protected=verify_release()
    for folder,files in ((TRIAL,release.read_json(TRIAL/'saved_files_sha256.json')),
                         (HISTORY,release.read_json(HISTORY/'download.json')['sha256'])):
        release.verify_inventory(files,folder)
        protected.update({(folder/key).relative_to(release.ROOT).as_posix(): h for key,h in files.items()})
    OUT.mkdir()
    candidate=prepare()
    previous=rotating.pc.previous
    old_base=previous.BASE
    try:
        previous.BASE=BASE
        arm=previous.arm_compile(output=OUT/'ARM_linkcheck',source=candidate)
    finally:
        previous.BASE=old_base
    evidence=analyze(OUT/'ARM_linkcheck/speed_admission_linkcheck_DO_NOT_FLASH.elf')
    result=simulate(candidate,evidence['centered_ADC_residual_fixture_counts'])
    def controlled(name):
        row=result[name]['filtered_IF']
        return (row['completed_5s'] and row['maximum_reference_Hz']==5 and row['handover_step']>0
                and abs(row['rpm_true_end']-300)<15)
    ripple=result['captured_frame_deviations']
    checks={
        'same_recorded_early_inputs_rest_prior_reduces_drift':
            evidence['first_237_steps_same_inputs_rest_prior']['peak_NIS_candidate']<25
            and abs(evidence['first_237_steps_same_inputs_rest_prior']['rpm_at_100_candidate'])<20,
        'nominal_reaches_5Hz': controlled('nominal'),
        'capture_disturbance_reaches_5Hz': controlled('captured_frame_deviations'),
        'capture_disturbance_reduces_PWM_voltage_variation':
            ripple['filtered_IF']['IF_delta_voltage_rms_V']<.8*ripple['installed']['IF_delta_voltage_rms_V'],
        'NIS_at_25_stops_at_injected_step':result['NIS_25']['filtered_IF']['fault']==5
                                         and result['NIS_25']['filtered_IF']['observer_calls']==571,
        'just_below_25_can_continue':controlled('NIS_just_below_25'),
        'raw_overcurrent_obeys_trip':result['current_trip']['filtered_IF']['fault']==2,
        'old_estimate_obeys_2ms_limit':result['estimate_age_2_1ms']['filtered_IF']['fault']==3,
        'field_rate_guard_still_stops':result['edge_model_minus250ns']['filtered_IF']['fault']==5,
    }
    release.verify_inventory(protected,release.ROOT)
    report={'passed':all(checks.values()),'checks':checks,'nominal':result['nominal'],
            'capture_disturbance':ripple,'protected_files_verified':len(protected),'ARM':arm,
            'NIS':25,'OFF_cycles_limit':4000,'estimate_age_ms':2,'new_powered_starts':0,'target_DWT_measured':False}
    release.save(OUT/'verification.json',report)
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())

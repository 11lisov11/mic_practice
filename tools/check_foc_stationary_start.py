"""Build and validate a stationary preflux FOC candidate without bench I/O."""

import argparse
import difflib
import json
import subprocess
import struct
from pathlib import Path

import analyze_nis571_startup as previous
import check_ipm_loss_model as archive
from test_foc_estimate_publish_fix import native_source
from test_observer_current_window import compile_case
from replay_start_history import ArmObserver, replay


BASE = previous.BASE
AUDIT = previous.OUT
DEFAULT_OUT = BASE / 'foc_stationary_start_r1'
release = previous.release
HEADER = 'nucleo/Inc/motor_control.h'
NATIVE = 'nucleo/Src/multi_native.c'


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f'Expected one occurrence of {old!r}')
    return source.replace(old, new)


def prepare(out):
    candidate = out / 'candidate'
    header = release.read(AUDIT / 'candidate' / HEADER)
    header = replace_once(header, '  uint32_t faults,adaptive_steps;', '''  uint32_t faults,adaptive_steps;
  uint8_t preflux; /* 0 unused, 1 stationary frame, 2 handed over */''')
    header = replace_once(header, '''  const float flux=ma_control_norm(x[2],x[3]);
  const float c0=flux>.0001f?x[2]/flux:1.f,s=flux>.0001f?x[3]/flux:0.f;''', '''  const float flux=ma_control_norm(x[2],x[3]);
  /* Establish rotor flux along a commanded stator axis. An unsettled EKF
   * angle must not rotate the magnetizing current during the initial start.
   * A later loss of speed admission must not switch the current frame back. */
  if(!speed_ready&&c->preflux==0U)c->preflux=1U;
  const int stationary=!speed_ready&&c->preflux==1U;
  const int rotate=!stationary&&flux>.0001f;
  const float c0=rotate?x[2]/flux:1.f,s=rotate?x[3]/flux:0.f;
  if(speed_ready&&c->preflux==1U){
    /* Transport the existing stator voltage integral into the admitted dq
     * frame so that switching coordinates does not step its voltage. */
    const float a=c->integral[0],b=c->integral[1];
    c->integral[0]=c0*a+s*b;
    c->integral[1]=-s*a+c0*b;
    c->preflux=2U;
  }''')
    header = replace_once(header, '  const float sync=ma_clip(m->poles*omega+ar*m->lm*iq/ma_max2(flux,.025f),-600,600);',
                          '  const float sync=stationary?0.f:ma_clip(m->poles*omega+ar*m->lm*iq/ma_max2(flux,.025f),-600,600);')

    native = release.read(AUDIT / 'candidate' / NATIVE)
    native = replace_once(native, '  __DMB();fe_pending=1;', '''  /* Cover entry, sustained preflux, and dq handover in the OFF budget. */
  fe_test_controller.preflux=(uint8_t)(fe_n%3U);
  __DMB();fe_pending=1;''')
    # The installed observer kernel and post-warmup trip must stay verbatim.
    installed = release.read(BASE / NATIVE)
    start = '  if(!fault&&observer.steps>=500U&&!(observer.nis<25.f)){'
    end = '  float endpoint_estimate[6];'
    assert native.split(start)[1].split(end)[0] == installed.split(start)[1].split(end)[0]
    assert 'SystemCoreClock/500U' in native and 'fe_elapsed>FE_FAST_BUDGET' in native
    assert 'millihz<=5000U' in native

    diffs = []
    for name, changed in ((HEADER, header), (NATIVE, native)):
        before = release.read(BASE / name)
        path = candidate / name
        path.parent.mkdir(parents=True, exist_ok=True)
        release.write(path, changed)
        diffs.extend(difflib.unified_diff(before.splitlines(keepends=True), changed.splitlines(keepends=True),
                                          'a/' + name, 'b/' + name))
    release.write(out / 'foc_stationary_start.patch', ''.join(diffs))
    return candidate


CASES = (
    ('nominal', 0, 0), ('recent_ramp_delay', 0, .443),
    ('Rs_plus20pct', 1, .443), ('Rr_plus20pct', 2, .443), ('Lm_minus5pct', 3, .443),
    ('ADC_1count', 4, .443), ('ADC_16counts', 5, .443),
    ('voltage_model_disturbance_1V', 9, .443), ('voltage_model_disturbance_2V', 11, .443),
    ('switching_model_disturbance_minus250ns', 14, .443),
    ('current_scale_minus10pct', 18, .443), ('current_scale_plus10pct', 19, .443),
    ('raw_overcurrent', 17, .443), ('observer_stale_2_1ms', 0, .443),
)


def simulation_source(folder, variant):
    template = release.read(AUDIT / 'PC_verification/candidate_plant.cpp')
    header = BASE / HEADER if variant == 'installed' else folder / HEADER
    prefix = '#include "' + header.as_posix() + '"\n' + template.split('\n', 1)[1].split('#define MIC_NATIVE_BUILD', 1)[0]
    tail = template[template.index('#undef ma_observe_noise'):]
    tail = replace_once(tail, 'static double error_sum,peak_nis,min_flux=100;', '''static double ramp_delay_s,reference_max,last_iq,peak_hold_speed_error;
static unsigned first_torque_step;
static double error_sum,peak_nis,min_flux=100;''')
    tail = replace_once(tail, ' float reference=(float)fmin(5.,5.*(next_irq-origin)/170000000.);', ''' float reference=(float)fmin(5.,5.*fmax(0.,(next_irq-origin)/170000000.-ramp_delay_s));
 reference_max=fmax(reference_max,reference);
 if(reference==5.f)peak_hold_speed_error=fmax(peak_hold_speed_error,
   fabs(plant.x[4]*9.5492965855-300.));''')
    tail = replace_once(tail, ' if(observer.steps<500U)max_prequalification_iq=fmaxf(max_prequalification_iq,fabsf(bin_iqref));', ''' if(observer.steps<500U)max_prequalification_iq=fmaxf(max_prequalification_iq,fabsf(bin_iqref));
 if(bin_iqref!=0.f&&last_iq==0.&&first_torque_step==0U)first_torque_step=observer.steps;
 last_iq=bin_iqref;''')
    tail = replace_once(tail, ' setup();', ' ramp_delay_s=argc>=6?atof(argv[5]):0.;\n setup();')
    tail = replace_once(tail, 'int rc=ma_observe_noise(o,m,a,b,va,vb,dt,n);++observer_calls;',
                        '''int rc=ma_observe_noise(o,m,a,b,va,vb,dt,n);++observer_calls;
 if(!rc&&scenario>=20&&scenario<=22&&o->steps==571U){
  o->nis=scenario==20?27.091480255126953f:scenario==21?25.f:nextafterf(25.f,0.f);
 }''')
    tail = replace_once(tail, r'\"prequalification_Iq_ref_max_A\":%.9g}',
                        r'\"prequalification_Iq_ref_max_A\":%.9g,\"first_torque_step\":%u,\"maximum_reference_Hz\":%.9g,\"peak_hold_speed_error_rpm\":%.9g}')
    tail = replace_once(tail, 'peak_nis,max_prequalification_iq);',
                        'peak_nis,max_prequalification_iq,first_torque_step,reference_max,peak_hold_speed_error);')
    return prefix + native_source(folder) + '\n' + tail


def simulate(out, candidate):
    folder = out / 'PC_plant'
    folder.mkdir()
    results = {name: {} for name, _, _ in CASES}
    variants = (('installed', BASE), ('speed_admission_only', AUDIT / 'candidate'), ('stationary_preflux', candidate))
    for name, source in variants:
        program = compile_case(folder, name, simulation_source(source, name), BASE)
        for case, scenario, delay in CASES:
            clocks = ('357000', '0') if case == 'observer_stale_2_1ms' else ('95737', '17000')
            run = subprocess.run([str(program), *clocks, str(scenario), str(folder / f'{name}_{case}.bin'), str(delay)],
                                 capture_output=True, text=True, check=True, timeout=30)
            results[case][name] = json.loads(run.stdout)

    release.save(folder / 'cases.json', results)
    for case in ('nominal', 'recent_ramp_delay'):
        result = results[case]['stationary_preflux']
        assert result['completed_5s'] and result['fault'] == 0
        assert result['maximum_reference_Hz'] == 5 and 5 <= result['PWM_duration_s'] < 5.001
        assert result['prequalification_Iq_ref_max_A'] == 0 and result['first_torque_step'] >= 500
        assert abs(result['rpm_true_end'] - 300) < 15 and result['native_valid_fraction_after1s'] > .99
    for item in ('installed', 'speed_admission_only', 'stationary_preflux'):
        assert results['raw_overcurrent'][item]['fault'] == 2
        assert results['observer_stale_2_1ms'][item]['fault'] == 3
    return results


def acceptance_cases(out, candidate):
    """Exercise the shipped C code with a trip boundary and test the dq handover."""
    folder = out / 'PC_plant'
    program = folder / 'stationary_preflux.exe'
    summary = {}
    for code, name in ((20, 'recorded_NIS_27_09'), (21, 'exactly_25'), (22, 'just_below_25')):
        run = subprocess.run([str(program), '95737', '17000', str(code), str(folder / f'{name}.bin'), '.443'],
                             check=True, capture_output=True, text=True, timeout=30)
        summary[name] = json.loads(run.stdout)
    for name in ('recorded_NIS_27_09', 'exactly_25'):
        assert summary[name]['fault'] == 5 and summary[name]['observer_calls'] == 571
    assert summary['just_below_25']['completed_5s']

    source = '#include "' + (candidate / HEADER).as_posix() + '"\n' + r'''
#include <cassert>
#include <cstdio>
#include "foc_experiment.h"
int main(){
  const ma_motor motor=FE_ESTIMATED_MOTOR;
  const ma_geometry geometry={5312,5184,771,112,240,229};
  const float x[6]={-.1684476f,-.6725104f,-.199377f,-.08908632f,-14.100735f,.13949648f};
  const float reversed[6]={x[0],x[1],-x[2],-x[3],90.f,x[5]};
  const float ia=-.2596263f,ib=-.7377065f,ref=.9f,bus=322.f,dt=1.f/16000.f;
  ma_controller feedback={},startup={},altered={};
  feedback.time_s=startup.time_s=altered.time_s=.4f;
  ma_output a,b,c;
  assert(ma_control_checked(&feedback,&motor,x,&geometry,MA_FOC,ia,ib,ref,bus,dt,1,&a,1)==MA_OK);
  assert(ma_control_with_speed_admission(&startup,&motor,x,&geometry,MA_FOC,ia,ib,ref,bus,dt,1,&b,1,0)==MA_OK);
  assert(ma_control_with_speed_admission(&altered,&motor,reversed,&geometry,MA_FOC,ia,ib,ref,bus,dt,1,&c,1,0)==MA_OK);
  assert(a.iq_ref>.25f && b.iq_ref==0.f && c.iq_ref==0.f);
  assert(startup.speed_integral==0.f && startup.preflux==1U && b.id_measured==ia && b.iq_measured==ib);
  assert(!memcmp(&startup,&altered,sizeof(startup)) && !memcmp(b.ccr,c.ccr,sizeof(b.ccr)));

  const float other_axis[6]={.3f,.1f,.12f,.16f,3.f,0.f};
  ma_controller handover=startup,equivalent=startup;
  handover.integral[0]=2.f;handover.integral[1]=-3.f;
  equivalent=handover;equivalent.preflux=2U;
  const float mag=ma_control_norm(other_axis[2],other_axis[3]);
  const float d=other_axis[2]/mag,q=other_axis[3]/mag;
  equivalent.integral[0]=2.f*d-3.f*q;equivalent.integral[1]=-2.f*q-3.f*d;
  assert(ma_control_with_speed_admission(&handover,&motor,other_axis,&geometry,MA_FOC,.3f,.1f,ref,bus,dt,1,&b,1,1)==MA_OK);
  assert(ma_control_with_speed_admission(&equivalent,&motor,other_axis,&geometry,MA_FOC,.3f,.1f,ref,bus,dt,1,&c,1,1)==MA_OK);
  assert(handover.preflux==2U && !memcmp(&handover,&equivalent,sizeof(handover)) && !memcmp(b.ccr,c.ccr,sizeof(b.ccr)));
  assert(ma_control_with_speed_admission(&handover,&motor,other_axis,&geometry,MA_FOC,.3f,.1f,ref,bus,dt,1,&b,1,0)==MA_OK);
  assert(handover.preflux==2U && b.iq_ref==0.f && handover.speed_integral==0.f);
  printf("{\"recorded_state_Iq_with_old_speed_feedback_A\":%.9g,\"recorded_state_Iq_before_admission_A\":0,\"coordinate_handover\":true}\n",a.iq_ref);
}
'''
    test = compile_case(folder, 'saved_controller_state', source, BASE)
    summary['recorded_controller_stimulus'] = json.loads(subprocess.check_output([str(test)], text=True, timeout=30))
    release.save(out / 'acceptance_cases.json', summary)
    return summary


def saved_trace_check(out, candidate_elf):
    record = release.read_json(AUDIT / 'ADC_and_model_evidence.json')['baseline']
    early = replay(archive.HISTORY, candidate_elf, 2026112102)
    trace = release.read_json(previous.DATA / 'observer_trace_decoded.json')
    sample, event = trace['first_loss'], trace['first_nis_replay']
    assert record['bit_exact_ARM_words'] == 51 and early['terminal_51_words_bit_exact']
    assert record['step'] == sample['steps'] == 571
    assert early['first_NIS_ge25'] == 83 and sample['nis'] >= 25.
    assert sample['observer_fault'] == 5 and not sample['published']
    raw = bytes.fromhex(event['raw_hex'])
    state = raw[:168] + bytes(28) + raw[168:176]
    counts = struct.unpack_from('<I', raw, 452)[0] >> 8
    code, post, _ = ArmObserver(candidate_elf).step(state, raw[176:228], raw[228:248], event['fpscr'], counts)
    assert code == event['result'] == 0
    assert post == raw[248:444] + struct.pack('<II', event['post_steps'], event['post_rejected'])
    result = {
        'status': 'saved observations, not a closed-loop replay of changed PWM',
        'first_crossing': {'step': 83, 'before_speed_loop': True, 'candidate_ARM_exact_rows': early['rows']},
        'stop': {'step': 571, 'reference_hz': sample['reference_hz'], 'NIS': sample['nis'],
                 'iq_reference_A': sample['iq_ref_A'], 'observer_rpm': sample['rpm_est'],
                 'phase_U_prediction_error_A': record['phase_residual_A'][0], 'candidate_ARM_exact_words': 51},
    }
    release.save(out / 'saved_run.json', result)
    return result


def verify_preserved():
    protected = archive.protected_inputs()
    assert protected == release.read_json(archive.OUT / 'preserved_inputs_sha256.json')
    prior = release.read_json(archive.OUT / 'sha256.json')
    release.verify_inventory(prior, archive.OUT)
    return len(set(protected) | {(archive.OUT / name).relative_to(previous.ROOT).as_posix() for name in prior})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, default=DEFAULT_OUT)
    out = parser.parse_args().outdir.resolve()
    files = verify_preserved()
    out.mkdir()
    candidate = prepare(out)
    results = simulate(out, candidate)
    acceptance = acceptance_cases(out, candidate)
    arm_dir = out / 'ARM_linkcheck'
    arm = previous.arm_compile(output=arm_dir, source=candidate)
    trace = saved_trace_check(out, arm_dir / 'speed_admission_linkcheck_DO_NOT_FLASH.elf')
    assert verify_preserved() == files
    result = {
        'archival_files_verified_sha256': files, 'saved_run': trace, 'simulated_profiles': len(results),
        'nominal': results['nominal']['stationary_preflux'],
        'recent_ramp_delay': results['recent_ramp_delay']['stationary_preflux'],
        'recorded_controller_stimulus': acceptance['recorded_controller_stimulus'],
        'ARM': arm, 'hardware_commands': 0, 'hardware_timing_measured': False,
        'NIS_threshold': 25, 'OFF_cycle_limit': 4000, 'estimate_age_limit_ms': 2,
    }
    release.save(out / 'verification.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

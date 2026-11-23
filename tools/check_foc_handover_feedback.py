"""Verify I/f to FOC voltage continuity and current feedback on the PC."""

import argparse
import difflib
import json
import math
import re
import struct
import subprocess
from pathlib import Path

import numpy as np
from elftools.elf.elffile import ELFFile

import build_foc_clear_ack_release as release
import check_foc_handover_budget as budget
import check_foc_rotating_start as rotating
from replay_start_history import ArmObserver
from test_observer_current_window import compile_case


BASE = release.OUT
TRIAL = BASE / 'replacement_ipm_FOC_5Hz_r1'
ANALYSIS = BASE / 'replacement_ipm_FOC_5Hz_r1_analysis'
OUT = BASE.parent.parent / 'live_bench_20261122/foc_handover_feedback_r1'
HEADER, NATIVE = rotating.HEADER, rotating.NATIVE
change = rotating.change


def protected_inputs():
    hashes = release.read_json(BASE / 'preserved_inputs_sha256.json')
    history = BASE / (TRIAL.name + '_history')
    for path in (TRIAL, ANALYSIS, history):
        for file in path.rglob('*'):
            if file.is_file():
                hashes[file.relative_to(release.ROOT).as_posix()] = release.sha(file)
    release.verify_inventory(release.read_json(TRIAL / 'saved_files_sha256.json'), TRIAL)
    release.verify_inventory(release.read_json(ANALYSIS / 'sha256.json'), ANALYSIS)
    release.verify_inventory(release.read_json(history / 'download.json')['sha256'], history)
    release.verify_inventory(release.read_json(BASE / 'source_hashes.json'), BASE)
    release.verify_inventory(hashes, release.ROOT)
    return hashes


def source_variant(out):
    original = release.read(BASE / HEADER)
    header = original.replace('if_last_ia','feedback_ia').replace('if_last_ib','feedback_ib')
    first = header.index('  /* During I/f only,')
    last = header.index('  const float id=', first)
    header = header[:first] + '''  /* At 16 kHz this pole (about 340 Hz) is above the 400 rad/s
   * current loop. Carry its state through handover. Use its polarity for
   * dead-time compensation; raw peaks and the observer current stay raw. */
  float feedback_ia=ia,feedback_ib=ib;
  if(c->preflux){
    feedback_ia=c->feedback_ia+.125f*(ia-c->feedback_ia);
    feedback_ib=c->feedback_ib+.125f*(ib-c->feedback_ib);
  }
  c->feedback_ia=feedback_ia;c->feedback_ib=feedback_ib;
''' + header[last:]
    header = change(header, '  float c0=1.f,s=0.f,start_omega=0.f;', '  float c0=1.f,s=0.f,start_omega=0.f;\n  int handover=0;')
    first = header.index('    /* At handover')
    last = header.index('    }else{', first)
    header = header[:first] + '''    const float projection=c0*x[2]+s*x[3];
    if(speed_ready&&start_hz>=1.f&&flux>.0001f&&projection>=.92f*flux&&
       fabsf(m->poles*x[4]-start_omega)<=6.2831853072f){
      const float inv_flux=1.f/flux;
      c0=x[2]*inv_flux;s=x[3]*inv_flux;
      c->preflux=2U;
      handover=1;
''' + header[last:]
    header = change(header, '''  float dq[2]={ff[0]+l*m->current_bw*err[0]+c->integral[0],
               ff[1]+l*m->current_bw*err[1]+c->integral[1]};''', '''  const float kp_current=l*m->current_bw;
  const float vd=ff[0]+kp_current*err[0],vq=ff[1]+kp_current*err[1];
  if(handover){
    /* Track the last realizable stator voltage in the new frame. Rotating
     * the integral alone leaves the feed-forward and proportional steps. */
    c->integral[0]=c0*c->last_va+s*c->last_vb-vd;
    c->integral[1]=-s*c->last_va+c0*c->last_vb-vq;
  }
  float dq[2]={vd+c->integral[0],vq+c->integral[1]};''')
    first = header.index('  const float loss_phase[3]')
    last = header.index('  const float loss_a=', first)
    header = header[:first] + re.sub(r'\b(i[ab])\b', r'feedback_\1', header[first:last]) + header[last:]
    header = change(header, '    if(p.valid)break;\n    shift=target;',
                    '    if(p.valid||shift==target)break; /* Same compares would fail again. */\n    shift=target;')
    raw = release.read(BASE / NATIVE)
    native = raw.replace('if_last_ia','feedback_ia').replace('if_last_ib','feedback_ib')
    native = change(native, '''  int voltage_fault=ma_applied_voltage(&g,sample.ccr,sample.arr,sample.bus_v,
    actual_ia,actual_ib,&applied_a,&applied_b);
''','')
    native = change(native, '  if(!fault && voltage_fault)fault=voltage_fault;', '''  /* Use the same filtered polarity for the active-epoch voltage model.
   * Keep the raw, paired current sample in the observer window below. */
  if(!fault)fault=ma_applied_voltage(&g,sample.ccr,sample.arr,sample.bus_v,
    controller.feedback_ia,controller.feedback_ib,&applied_a,&applied_b);''')
    native = change(native, ''' float av,bv;int avrc=ma_applied_voltage(&fe_test_geometry,cc,(uint16_t)fe_test_geometry.arr,
   (uint16_t)fe_test_bus,fe_test_ia,fe_test_ib,&av,&bv);
 fe_applied_a=av;fe_applied_b=bv;
''', '')
    native = change(native, ' fe_rc=avrc?avrc:ma_control_with_speed_admission(', ' fe_rc=ma_control_with_speed_admission(')
    native = change(native, ' ow_state window_probe=fe_window_seed;ow_bin window_result={0};', ''' float av=0.f,bv=0.f;
 if(!fe_rc)fe_rc=ma_applied_voltage(&fe_test_geometry,cc,(uint16_t)fe_test_geometry.arr,
   (uint16_t)fe_test_bus,fe_test_controller.feedback_ia,fe_test_controller.feedback_ib,&av,&bv);
 ow_state window_probe=fe_window_seed;ow_bin window_result={0};''')
    delta = []
    for rel, text in ((HEADER, header), (NATIVE, native)):
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        release.write(path, text)
        before = release.read(BASE / rel).splitlines(keepends=True)
        delta.extend(difflib.unified_diff(before, text.splitlines(keepends=True), 'a/'+rel, 'b/'+rel))
    release.write(out.parent / 'foc_handover_feedback.patch', ''.join(delta))
    return out


def capture(out):
    adc = release.read_json(ANALYSIS / 'ADC_decoded.json')
    trace = release.read_json(ANALYSIS / 'observer_trace_decoded.json')
    rep = trace['first_nis_replay']
    assert rep['post_steps'] == adc['source_observer_step'] == 756 and adc['source_window_exact']
    end = next(i for i, row in enumerate(adc['samples']) if row['cycles'] == adc['requested_end_cycles']) + 1
    deviations, means, ripple, deadtime = [], [], [], []
    for offset in (-32, -16, 0):
        rows = adc['samples'][end+offset-16:end+offset]
        assert len(rows) == 16 and all(row['accepted_by_monitor'] and row['pair'] == 1 for row in rows)
        currents = np.array([row['nominal_currents_a'] for row in rows])
        beta = (currents[:, 1] - currents[:, 2])/math.sqrt(3)
        means.append(float(beta.mean()))
        ripple.append(float(abs(np.diff(beta)).max()))
        loss = np.array([row['bus_v'] * 229 / (2*row['timer_arr']) for row in rows])
        polarity = np.clip(currents/.05, -1., 1.)
        beta_loss = loss*(polarity[:, 1]-polarity[:, 2])/math.sqrt(3)
        deadtime.append(float(np.ptp(beta_loss)))
        samples = np.array([row['raw_adc'] for row in rows], dtype=int)
        deviations.extend(np.rint(samples.mean(axis=0)-samples).astype(int).tolist())
    first_torque = min(row['steps'] for row in trace['samples'] if row['iq_ref_A'] != 0.)
    assert first_torque == 701
    beta_prior = rep['prior_state'][1]
    beta_pred = rep['predicted_current_A'][1]
    report = {
        'step':756, 'NIS':rep['nis'], 'first_trace_torque_step':first_torque,
        'beta_window_means_A':means, 'beta_max_adjacent_changes_A':ripple,
        'modeled_deadtime_beta_peak_to_peak_V':deadtime,
        'prior_beta_A':beta_prior, 'predicted_beta_A':beta_pred,
        'previous_window_minus_prior_A':means[1]-beta_prior,
        'measured_change_A':means[2]-means[1], 'predicted_change_A':beta_pred-beta_prior,
        'total_beta_innovation_A':means[2]-beta_pred,
        'conditional_NIS_terms':trace['first_loss']['NIS_components'],
        'captured_frame_deviations_adc_counts':deviations,
        'voltage_model_on_saved_PWM':voltage_model_on_saved_pwm(adc['samples'][:end], rep['inputs']),
    }
    release.save(out / 'capture_analysis.json', report)
    return rep, deviations


def voltage_model_on_saved_pwm(rows, observer_input):
    """Keep saved CCRs and acquired currents. Only recalculate the modeled voltage."""
    current = np.array([row['nominal_currents_a'] for row in rows])
    filtered = current.copy()
    for index in range(1, len(filtered)):
        filtered[index] = filtered[index-1] + .125*(current[index]-filtered[index-1])
    stamps = np.array([row['cycles'] for row in rows], dtype=np.int64)
    begin = (stamps[-25] + stamps[-24])//2
    end = (stamps[-9] + stamps[-8])//2
    overlap = np.maximum(0, np.minimum(stamps[1:],end)-np.maximum(stamps[:-1],begin))
    weights = np.concatenate(([0], overlap))/(end-begin)
    assert abs(weights.sum()-1) < 1e-9
    loss = np.array([row['bus_v']*229/(2*row['timer_arr']) for row in rows])
    scale = loss*(2/229)
    ccr = np.array([row['ccr_at_update'][:3] for row in rows])
    voltage = ccr*scale[:, None]

    def alpha_beta_average(phases):
        u, v, w = phases.T
        return weights @ np.column_stack(((2*u-v-w)/3, (v-w)/math.sqrt(3)))

    unfiltered_v = alpha_beta_average(voltage - loss[:, None]*np.clip(current/.05,-1.,1.))
    filtered_v = alpha_beta_average(voltage - loss[:, None]*np.clip(filtered/.05,-1.,1.))
    assert np.allclose(unfiltered_v, [observer_input['va_V'],observer_input['vb_V']], atol=.00001, rtol=0)
    return {'raw_polarity_alpha_beta_V':unfiltered_v.tolist(),
            'filtered_polarity_alpha_beta_V':filtered_v.tolist(),
            'same_saved_CCRs':True}


def plant_source(folder, label, deviations):
    source = rotating.model_source(folder, label)
    fixture = ','.join('{%d,%d}' % tuple(row) for row in deviations)
    source = change(source, 'static double maximum_plant_rpm;', f'''static double maximum_plant_rpm;
static const int captured[48][2]={{{fixture}}};
static double prior_va,prior_vb,handover_delta,voltage_delta_sum;
static unsigned voltage_samples;
static bool handover_measured;''')
    source = change(source, ' if(scenario==16)n0+=8;', ''' if(scenario==16)n0+=8;
 if((scenario==24||scenario==25||scenario==26)&&controller.preflux==2U){
  const unsigned index=(frames-1U)%48U;
  const int gain=scenario==25?2:1;
  n0+=gain*captured[index][0];n1+=gain*captured[index][1];
  if(scenario==26)n1+=2;
 }''')
    source = change(source, ' plant.step(legs[0]-av,(legs[1]-legs[2])/sqrt(3.),10624./170000000.);', ''' const double alpha=legs[0]-av,beta=(legs[1]-legs[2])/sqrt(3.);
 const double jump=hypot(alpha-prior_va,beta-prior_vb);
 if(handover_step&&!handover_measured){handover_delta=jump;handover_measured=true;}
 if(handover_step&&observer.steps<handover_step+120U){
  voltage_delta_sum+=jump*jump;++voltage_samples;
 }
 prior_va=alpha;prior_vb=beta;
 plant.step(alpha,beta,10624./170000000.);''')
    source = change(source, r'\"maximum_plant_rpm\":%.9g}', r'\"maximum_plant_rpm\":%.9g,\"handover_voltage_delta_V\":%.9g,\"post_handover_voltage_delta_rms_V\":%.9g}')
    return change(source,'handover_step,maximum_plant_rpm);',
                  'handover_step,maximum_plant_rpm,handover_delta,voltage_samples?sqrt(voltage_delta_sum/voltage_samples):0.);')


CASES = (('nominal', 0, '.523'), ('captured_deviations', 24, '.523'),
         ('captured_deviations_early', 24, '.483'), ('captured_deviations_late', 24, '.550'),
         ('double_deviations', 25, '.523'), ('deviations_plus_offset', 26, '.523'),
         ('Rs_plus20pct', 1, '.523'), ('Rr_plus20pct', 2, '.523'),
         ('voltage_mismatch_1V', 9, '.523'), ('voltage_mismatch_2V', 11, '.523'),
         ('edge_minus250ns', 14, '.523'), ('current_trip', 17, '.523'),
         ('age_2_1ms', 0, '.523'), ('NIS_exactly25', 21, '.523'), ('NIS_below25', 22, '.523'))


def simulate(out, folders, deviations):
    pc = out / 'PC'
    pc.mkdir()
    reports = {}
    for name, folder in folders.items():
        exe = compile_case(pc, name, plant_source(folder, name, deviations), BASE)
        for case, code, delay in CASES:
            timing = ('357000', '0') if case == 'age_2_1ms' else ('95737', '17000')
            bins = pc / f'{name}_{case}.bin'
            result = subprocess.check_output([str(exe), *timing, str(code), str(bins), delay],
                                             text=True, timeout=30)
            reports.setdefault(case, {})[name] = json.loads(result)
    release.save(pc / 'cases.json', reports)
    return reports


def replay_arm(elf, captured, voltage_comparison=None):
    raw = bytes.fromhex(captured['raw_hex'])
    state = raw[:168] + bytes(28) + raw[168:176]
    counts = struct.unpack_from('<I', raw, 452)[0] >> 8
    arm = ArmObserver(elf)
    code, post, _ = arm.step(state, raw[176:228], raw[228:248], captured['fpscr'], counts)
    assert code == captured['result'] == 0
    assert post == raw[248:444] + struct.pack('<II', captured['post_steps'], captured['post_rejected'])
    result = {'exact_words':51, 'original_NIS':captured['nis']}
    if voltage_comparison is not None:
        a,b = voltage_comparison['filtered_polarity_alpha_beta_V']
        inputs = raw[228:236] + struct.pack('<2f',a,b) + raw[244:248]
        code, post, _ = arm.step(state, raw[176:228], inputs, captured['fpscr'], counts)
        assert code == 0
        result['same_CCR_prior_and_current_NIS_with_filtered_polarity'] = struct.unpack_from('<f',post,168)[0]
    return result


def probe_arm(out, candidate_elf):
    ram = (BASE/'post_install_idle_r1/native_SRAM_0.bin').read_bytes()
    with (BASE/release.ELF).open('rb') as source:
        symbols = ELFFile(source).get_section_by_name('.symtab').iter_symbols()
        recorded = {sym.name: ram[int(sym['st_value'])-0x20000000:
                                 int(sym['st_value'])-0x20000000+sym['st_size']]
                    for sym in symbols if sym.name in ('model', 'fe_test_geometry')}
    # The firmware fixture retains the updated synthetic speed until the next
    # case. Also report the older stress probe that restores it on every IRQ.
    images = {'baseline':BASE/release.ELF, 'candidate':candidate_elf}
    actual = {name:budget.instruction_probe(elf, recorded, retain_handover_speed=True)
              for name,elf in images.items()}
    stress = {name:budget.instruction_probe(elf, recorded) for name,elf in images.items()}
    release.save(out/'ARM_OFF_instruction_counts.json', {'firmware_fixture':actual, 'speed_jump_stress':stress})
    return {'cases':64, 'iterations_per_case':8, 'DWT_on_target_measured':False,
            'max_ARM_instructions_before_after':{
                label:[max(row['instructions'] for row in rows) for rows in data.values()]
                for label,data in (('firmware_fixture',actual),('speed_jump_stress',stress))
            }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    out = args.output.resolve()
    protected = protected_inputs()
    out.mkdir()
    rep, deviations = capture(out)
    folders = {
        'baseline':BASE,
        'candidate':source_variant(out/'candidate'),
    }
    results = simulate(out, folders, deviations)
    rotating.pc.previous.BASE = BASE
    arm_dir = out / 'ARM'
    arm = rotating.pc.previous.arm_compile(output=arm_dir, source=folders['candidate'])
    elf = arm_dir / 'speed_admission_linkcheck_DO_NOT_FLASH.elf'
    capture_report = release.read_json(out/'capture_analysis.json')
    arm['step_756_replay'] = replay_arm(elf, rep, capture_report['voltage_model_on_saved_PWM'])
    arm['OFF'] = probe_arm(out, elf)
    before, after = arm['OFF']['max_ARM_instructions_before_after']['firmware_fixture']
    assert after <= before, (before,after)
    for case in ('nominal','captured_deviations','captured_deviations_early','captured_deviations_late','NIS_below25'):
        r = results[case]['candidate']
        assert r['completed_5s'] and r['fault']==0 and 5 <= r['PWM_duration_s'] < 5.001, (case,r)
        assert r['maximum_reference_Hz']==5 and r['handover_step']>0 and abs(r['rpm_true_end']-300)<15, (case,r)
    assert results['nominal']['candidate']['handover_voltage_delta_V'] < .1
    assert results['captured_deviations']['candidate']['post_handover_voltage_delta_rms_V'] < .5
    for variant in folders:
        assert results['NIS_exactly25'][variant]['fault']==5 and results['NIS_exactly25'][variant]['observer_calls']==571
        assert results['current_trip'][variant]['fault']==2 and results['age_2_1ms'][variant]['fault']==3
        assert results['double_deviations'][variant]['fault']==5
    release.verify_inventory(protected, release.ROOT)
    release.save(out/'verification.json', {
        'passed':True, 'ARM':arm, 'hardware_commands':0, 'limits':[25,4000,2],
        'preserved_files':len(protected),
        'quick_results':{case: {v:[r['fault'],r['maximum_reference_Hz'],r['handover_step']]
                                for v,r in group.items()} for case,group in results.items()},
    })
    print(out)


if __name__ == '__main__':
    main()

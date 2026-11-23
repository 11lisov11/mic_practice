"""Reproduce recorded NIS and validate an offline Nucleo source overlay."""
import difflib
import ctypes
import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
from elftools.elf.elffile import ELFFile

from observer_exact_peak_decode import decode_exact_adc_peak_hex
from replay_start_history import ArmObserver
from test_foc_estimate_publish_fix import native_source
from test_observer_current_window import compile_case


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/live_bench_20261118/boot_stack_integrity_r1'
ELF = BASE / 'release/nucleo_2026111810_stack_guard.elf'
CURRENT = ROOT / 'artifacts/live_bench_20261120/rpc_capture_pages_r1/FOC_5Hz_paged_20261121_r2'
PREVIOUS = BASE / 'FOC_5Hz_20261120_r1'
OUT = ROOT / 'artifacts/live_bench_20261121/observer_nis_admission_r1'
OVERLAY = OUT / 'candidate'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, data):
    if path.exists() and read_json(path)==data:
        return
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def verified_files():
    paths = {}
    for folder, names in ((CURRENT, ('saved_files_sha256.json',)),
                          (PREVIOUS, ('saved_files_sha256.json', 'NIS_replay_files_sha256.json')),
                          (BASE, ('source_hashes.json',))):
        for name in names:
            for relative, checksum in read_json(folder / name).items():
                path = (folder / relative).resolve()
                assert digest(path) == checksum, str(path)
                paths[path] = checksum
    return paths


def alpha_beta_cov(replay, measurement_noise):
    x = np.array(replay['prior_state'])
    p0 = np.array(replay['prior_covariance'])
    m = replay['motor']
    ar, kr = m['rr'] / m['lr'], m['lm'] / m['lr']
    leakage = m['ls'] - kr * m['lm']
    poles = m['poles']
    torque = 1.5 * poles * kr
    dt = replay['inputs']['dt_s']
    a = np.zeros((6, 6))
    a[2] = [ar * m['lm'], 0, -ar, -poles * x[4], -poles * x[3], 0]
    a[3] = [0, ar * m['lm'], poles * x[4], -ar, poles * x[2], 0]
    a[:2] = -kr * a[2:4] / leakage
    a[0, 0] -= m['rs'] / leakage
    a[1, 1] -= m['rs'] / leakage
    a[4] = [-torque*x[3], torque*x[2], torque*x[1], -torque*x[0], -m['b'], -1]
    a[4] /= m['j']
    f = np.eye(6) + dt*a + 0.5*dt*dt*(a@a)
    q = np.diag([.02, .02, .00001, .00001, 4., .0001])
    pp = f@p0@f.T + q*dt
    aa, ab, bb = measurement_noise
    s = pp[:2, :2] + [[aa, ab], [ab, bb]]
    assert np.linalg.eigvalsh(p0).min() > 0 and np.linalg.eigvalsh(s).min() > 0
    return s


def audit_trace(trace, arm):
    replay = trace['first_nis_replay']
    sample = trace['first_loss']
    raw = bytes.fromhex(replay['raw_hex'])
    counts = struct.unpack_from('<I', raw, 452)[0] >> 8
    before = raw[:168] + bytes(28) + raw[168:176]
    result, after, noise = arm.step(before, raw[176:228], raw[228:248], replay['fpscr'], counts)
    expected = raw[248:444] + struct.pack('<II', replay['post_steps'], replay['post_rejected'])
    assert result == replay['result'] == 0 and after == expected
    assert replay['post_steps'] == sample['steps'] and replay['nis'] == sample['nis']
    assert sample['observer_adc_cycles'] == sample['bin_cycles'] == sample['control_adc_cycles']
    values = struct.unpack_from('<5f', raw, 228)
    s = alpha_beta_cov(replay, struct.unpack('<3f', noise))
    y = np.array(values[:2])
    pred = np.array(replay['predicted_current_A'])
    delta = y - pred
    nis = float(delta @ np.linalg.solve(s, delta))
    assert math.isclose(nis, replay['nis'], rel_tol=2e-6)
    phases = np.array([[1., 0.], [-.5, math.sqrt(3)/2], [-.5, -math.sqrt(3)/2]])
    phase_sigma = np.sqrt(np.diag(phases @ s @ phases.T))
    effects = {}
    for name, change in {'beta_voltage_minus_1V': (3, -1.), 'beta_voltage_plus_1V': (3, 1.),
                         'beta_current_minus_10mA': (1, -.01), 'beta_current_plus_10mA': (1, .01)}.items():
        shifted = list(values)
        axis, amount = change
        shifted[axis] += amount
        _, p, _ = arm.step(before, raw[176:228], struct.pack('<5f', *shifted), replay['fpscr'], counts)
        effects[name] = struct.unpack_from('<f', p, 168)[0]
    return dict(step=sample['steps'], reference_Hz=sample['reference_hz'], NIS=replay['nis'],
                bit_exact_ARM_words=51, observer_speed_before_rpm=replay['prior_state'][4]*60/(2*math.pi),
                observer_speed_after_rpm=sample['rpm_est'], innovation_covariance_A2=s.tolist(),
                current_predicted_A=pred.tolist(), current_measured_A=y.tolist(),
                conditional_NIS_terms=[e*e/v for e,v in zip(replay['innovation_A'], replay['innovation_variance_A2'])],
                phase_residual_A=(phases@delta).tolist(), phase_standard_deviations=phase_sigma.tolist(),
                phase_standardized_residual=(phases@delta/phase_sigma).tolist(),
                pair_counts=replay['pair_counts'], measurement_epoch_cycles=sample['observation_cycles'],
                counterfactual_ARM_NIS=effects, terminal_voltage_independently_measured=False)


def audit_adc(trace):
    original = (CURRENT / 'paged_capture/ADC_peak.bin').read_bytes()
    header = struct.unpack_from('<IHHII4H6I6HI', original)
    first, last, step, _, center = header[10:15]
    # Only remove the legacy warmup assertion in this offline decoder. The
    # CRC, pair, geometry, timestamps and quality checks still all execute.
    import inspect
    from observer_exact_peak_decode import exact_pc_crc
    namespace = {'struct': struct, 'exact_pc_crc': exact_pc_crc}
    decoder = inspect.getsource(decode_exact_adc_peak_hex)
    assert decoder.count('step<500') == 1 and 0 < step < 500
    exec(decoder.replace('step<500', 'step<1'), namespace)
    record = namespace['decode_exact_adc_peak_hex'](original.hex(), 2026111810)
    assert record['source_window_exact'] and len(record['source_samples']) == 16
    late = trace['first_loss']
    assert center != late['observation_cycles'] and step != late['steps']
    current = np.array([row['nominal_currents_a'] for row in record['source_samples']])
    phases = np.column_stack([current[:,0], (current[:,0]+2*current[:,1])/math.sqrt(3)])
    history = OUT/'start_history_get'
    witness = read_json(history/'ARM_exact_replay.json')
    assert witness['terminal_51_words_bit_exact'] and witness['first_NIS_ge25'] == step
    meta = struct.unpack_from('<16I', (history/'meta.bin').read_bytes())
    assert (meta[6], meta[7], meta[10], meta[11]) == (step, step, center, last)
    row = (history/'rows.bin').read_bytes()[-22:]
    inputs = struct.unpack_from('<5f', row)
    dll = OUT/'rebuild_1810_adc.dll'
    command = [shutil.which('g++'), '-std=c++17', '-O2', '-ffp-contract=off', '-shared',
               '-I', str(BASE/'nucleo/Inc'), str(ROOT/'tools/rebuild_exact_adc_source.cpp'), '-o', str(dll)]
    subprocess.run(command, check=True, capture_output=True)
    rebuild = ctypes.CDLL(str(dll)).rebuild_exact
    rebuild.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float]
    bin_data, points = ctypes.create_string_buffer(48), ctypes.create_string_buffer(400)
    assert rebuild(original, bin_data, points, -1) == 0
    volts_and_amps = struct.unpack_from('<4f', bin_data.raw)
    errors = [a-b for a,b in zip(volts_and_amps, inputs)]
    assert max(map(abs, errors)) < 2e-6
    agg = struct.unpack('<6f6I', bin_data.raw)
    assert (agg[6], agg[7], agg[8], agg[9]) == (center, last, first, 16)
    return dict(source_step=step, source_first_cycles=first, source_end_cycles=last,
                source_center_cycles=center, raw_windows=16, voltage_rows=25,
                clean_quality_all_25=True, pairs=record['source_pair_counts'],
                alpha_beta_mean_A=phases.mean(axis=0).tolist(),
                alpha_beta_sample_std_A=phases.std(axis=0, ddof=1).tolist(),
                time_before_late_event_ms=((late['observation_cycles']-center)&0xffffffff)/170000,
                matches_late_event=False, nominal_current_scale=True,
                early_NIS=witness['peak_NIS'], early_journal_replay_words=51,
                early_inputs_from_raw=list(volts_and_amps), early_journal_inputs=list(inputs[:4]),
                raw_reconstruction_error=errors)


def make_overlay():
    changes = {}
    def replace(source, old, new):
        assert source.count(old) == 1, old
        return source.replace(old, new)

    relative = 'nucleo/Src/multi_native.c'
    original = (BASE/relative).read_text(encoding='utf-8')
    source = replace(original,
        '  int history_event=nh_step(&observer_history,&observer,input,window.pair_counts,history_fpscr,fault,window.center,stamp);',
        '  nh_step(&observer_history,&observer,input,window.pair_counts,history_fpscr,fault,window.center,stamp);')
    source = replace(source, '  if(history_event||(!replay_was_latched&&observer_trace.replay_latched))',
        '  /* The startup journal retains early crossings. Reserve the raw NIS\n'
        '   * request for the same post-warmup event as the full x/P replay. */\n'
        '  if(!replay_was_latched&&observer_trace.replay_latched)')
    source = replace(source,
        '  float endpoint_estimate[6];\n  if(!fault)fault=ow_forecast',
        '  /* A numerically successful EKF step can still fail the existing NIS\n'
        '   * criterion. Latch the usual observer fault before TIM can consume\n'
        '   * this state. Preserve x/P and the rejected sample for replay. */\n'
        '  if(!fault&&observer.steps>=500U&&!(observer.nis<25.f)){\n'
        '    fault=MA_OBSERVER;\n'
        '    ma_fail(MA_OBSERVER);\n'
        '    ma_observer_record(&sample,stamp,trace_seq,trace_adc,trace_id,trace_iq,\n'
        '      trace_idref,trace_iqref,trace_ref,va,vb,dt,fault,0,&window);\n'
        '  }\n'
        '  float endpoint_estimate[6];\n  if(!fault)fault=ow_forecast')
    source = replace(source, ' if(observer_trace.frozen||!running||!LL_TIM_IsEnabledAllOutputs(TIM1))return;',
        ' if(observer_trace.frozen||(!fault&&(!running||!LL_TIM_IsEnabledAllOutputs(TIM1))))return;')
    changes[relative] = original, source

    relative = 'nucleo/Inc/observer_trace_core.h'
    original = (BASE/relative).read_text(encoding='utf-8')
    source = replace(original, '  if(c->seen_valid&&!c->blob.header.first_loss_present){',
        '  const int nis_stop=r->observer_fault==MA_OBSERVER&&\n'
        '    (r->reasons&(OD_WARMUP|OD_NIS))==OD_NIS;\n'
        '  if((c->seen_valid||nis_stop)&&!c->blob.header.first_loss_present){')
    changes[relative] = original, source

    diffs = []
    for relative, (old, new) in changes.items():
        path = OVERLAY/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as stream:
            stream.write(new)
        diffs.extend(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                         'a/'+relative, 'b/'+relative))
    (OUT/'source_changes.patch').write_text(''.join(diffs), encoding='utf-8')


def test_native(trace):
    out = OUT/'native_verification'
    out.mkdir()
    recorded = trace['first_nis_replay']
    sample = trace['first_loss']
    fixture = (BASE.parent/'exact_nis_input_release_r1/verification/adapter/exact_native_adapter.cpp').read_text(encoding='utf-8')
    prefix = fixture.split('#define MIC_NATIVE_BUILD', 1)[0]
    prefix = prefix.replace('static bool inject_torn;', '')
    prefix = '#include "observer_start_history.h"\n' + prefix
    def values(items):
        return ','.join(repr(float(v))+'f' for v in items)
    raw = bytes.fromhex(recorded['raw_hex'])
    pair_counts = struct.unpack_from('<I', raw, 452)[0] >> 8
    previous_center = sample['observation_cycles'] - round(recorded['inputs']['dt_s']*170000000)
    seed = f'''
void seed(unsigned steps,bool seen_valid) {{
 timer.BDTR=1;fake_bus=324;selected=MA_FOC;qualification=FE_ESTIMATED;
 profile_ready=1;running=1;run_fault=first_fault=0;fe_complete=1;fe_started=1;
 fe_case=64;fe_fault=0;fe_trial_done=0;id_profile_attempted=1;id_profile_running=0;
 cycle.CYCCNT={sample['observer_adc_cycles']+10000}U;telemetry_seq=0;
 start_cycles=fe_trial_begin=cycle.CYCCNT-1700000U;
 ma_estimate_reset({previous_center}U);observer_center_cycles={previous_center}U;
 observer={{}};observer.steps=steps;
 const float x[6]={{{values(recorded['prior_state'])}}};
 const float p[36]={{{values(v for row in recorded['prior_covariance'] for v in row)}}};
 memcpy(observer.x,x,sizeof(x));memcpy(observer.p,p,sizeof(p));
 bin_current={{}};bin_current.valid=bin_current.zero=1;
 bin_current.cycles={sample['observer_adc_cycles']}U;bin_current.sequence=42;
 bin_current.pair=2;bin_current.arr=5312;bin_current.bus_v=324;
 bin_cycles=bin_current.cycles;bin_control_sequence=42;bin_control_adc_cycles=bin_cycles;
 bin_window={{}};bin_window.first={sample['window_first_cycles']}U;
 bin_window.center={sample['observation_cycles']}U;bin_window.end=bin_cycles;
 bin_window.previous_center={previous_center}U;bin_window.count=16;bin_window.pair_counts={pair_counts}U;
 bin_window.ia={recorded['inputs']['ia_A']}f;bin_window.ib={recorded['inputs']['ib_A']}f;
 bin_va=bin_window.va=bin_window.tail_va={recorded['inputs']['va_V']}f;
 bin_vb=bin_window.vb=bin_window.tail_vb={recorded['inputs']['vb_V']}f;
 observer_trace={{}};observer_trace.seen_valid=seen_valid;
 observer_history={{}};nh_begin(&observer_history,&observer,&model,MIC_NATIVE_BUILD,cycle.CYCCNT,0);
 ma_perf={{}};ma_first_runtime={{}};mic_foc_irq_meter={{}};
 ma_perf_off=0;sample=bin_current;sample_coherent=1;request_calls=0;force_nis=false;
}}
'''
    body = r'''
static void NVIC_SetPendingIRQ(int irq){ assert(irq==25);++kicks;ma_native_profile_tick(); }
static int fixture_observe(ma_observer*o,const ma_motor*m,const float*v,const ma_noise*n){
 int rc=mic_observer_step(o,m,v,n);if(force_nis)o->nis=forced_nis;return rc;
}
SEED
int main(){
 unsigned checks=0;
 sample.valid=sample.zero=1;fake_bus=0;selected=MA_FOC;
 for(unsigned i=0;i<2000U&&!fe_complete&&!fe_fault;++i)ma_native_service();
 assert(fe_complete&&fe_case==64U&&!fe_fault);++checks;
 assert(FE_FAST_BUDGET==4000U);++checks;
 seed(PRIOR,true);unsigned old=estimate_cycles;ma_native_service();
 const float physical_nis=observer.nis;
 assert(fabsf(physical_nis-RECORDED)<.00015f);++checks;
 assert(observer_trace.replay_latched&&observer_trace.blob.replay.result>>8==PAIRS);++checks;
 assert(observer_trace.blob.header.first_loss_step==PRIOR+1&&request_calls==1);++checks;
 assert(request_first==bin_window.first&&request_end==bin_window.end&&request_step==PRIOR+1);++checks;
 #ifdef CANDIDATE
 assert(estimate_cycles==old&&observer_trace.blob.first_loss.published==0);++checks;
 assert(run_fault==MA_OBSERVER&&ma_first_runtime.word[0]==FT_OBSERVER);++checks;
 assert(ma_native_fast(1.f)==MC_SW_ERROR);++checks;
 #else
 assert(estimate_cycles==bin_cycles&&observer_trace.blob.first_loss.published==1);++checks;
 assert(!run_fault);++checks;
 #endif
 auto original=observer_trace.blob.replay;
 timer.BDTR=0;ma_native_service();assert(ma_native_prepare());
 assert(!memcmp(&original,&observer_trace.blob.replay,sizeof(original)));++checks;
 for(float nis:{24.999f,25.f,25.001f,50.f,51.f,NAN}){
  seed(499,false);force_nis=true;forced_nis=nis;old=estimate_cycles;ma_native_service();
  #ifdef CANDIDATE
  if(!(nis<25.f)){
   assert(run_fault==MA_OBSERVER&&estimate_cycles==old);
   assert(observer_trace.blob.header.first_loss_step==500&&observer_trace.blob.first_loss.published==0);
  }else assert(!run_fault&&estimate_cycles==bin_cycles);
  #else
  assert(!run_fault&&estimate_cycles==bin_cycles);
  #endif
  ++checks;
 }
 seed(78,false);force_nis=true;forced_nis=27.925209f;ma_native_service();
 assert(observer_history.meta.event_count==1&&!observer_trace.replay_latched&&!run_fault);++checks;
 #ifdef CANDIDATE
 assert(request_calls==0);
 #else
 assert(request_calls==1&&request_step==79);
 #endif
 ++checks;
 seed(PRIOR,true);observer.rejected=19;bin_window.ib+=.31f;ma_native_service();
 assert(observer.nis>50&&run_fault==MA_OBSERVER);++checks;
 seed(PRIOR,true);sample.counts[0]=150;sample.counts[1]=-75;sample.counts[2]=-75;
 assert(ma_native_fast(1.f)!=MC_NO_ERROR&&run_fault==MA_CURRENT);++checks;
 seed(PRIOR,true);ma_estimate_reset(cycle.CYCCNT-340001U);
 assert(ma_native_fast(1.f)!=MC_NO_ERROR&&run_fault==MA_STALE);++checks;
 (void)old;
 printf("{\"passed\":true,\"checks\":%u,\"OFF_cases\":64,\"physical_NIS\":%.9g}\n",checks,physical_nis);
}
'''.replace('SEED', seed).replace('PRIOR', str(recorded['prior_steps'])+'U').replace(
    'RECORDED', str(recorded['nis'])+'f').replace('PAIRS', str(pair_counts)+'U')
    result = {}
    for label, directory in (('baseline', BASE), ('candidate', OVERLAY)):
        native = native_source(directory, hook=False)
        marker = 'int fault=mic_observer_step(&observer,&model,input,&noise);'
        assert native.count(marker) == 1
        native = native.replace(marker, 'int fault=fixture_observe(&observer,&model,input,&noise);')
        patch_header = OVERLAY/'nucleo/Inc/observer_trace_core.h'
        pre = '#define CANDIDATE\n#include "'+patch_header.as_posix()+'"\n' if label=='candidate' else ''
        pre += prefix + '\nstatic int fixture_observe(ma_observer*,const ma_motor*,const float*,const ma_noise*);\n'
        pre += 'static bool force_nis=false;static float forced_nis;\n'
        exe = compile_case(out, label, pre+native+'\n'+body, BASE)
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        (out/(label+'_run.log')).write_text(run.stdout+run.stderr, encoding='utf-8')
        run.check_returncode()
        result[label] = json.loads(run.stdout)
    return result


def build_arm():
    out = OUT/'ARM_linkcheck'
    out.mkdir()
    debug = BASE/'nucleo/STM32CubeIDE/Debug'
    gcc = next(Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins').glob(
        '**/arm-none-eabi-gcc.exe'))
    mk = (debug/'Application/User/subdir.mk').read_text(encoding='utf-8')
    line = next(line for line in mk.split('Application/User/multi_native.o:', 1)[1].splitlines()
                if 'arm-none-eabi-gcc' in line)
    flags = line.split('"$<" ', 1)[1].split(' -o "$@"', 1)[0].split()
    flags = [flag for flag in flags if not flag.startswith(('-MMD', '-MP', '-MF', '-MT'))]
    objects = {}
    for name, directory in (('baseline', BASE), ('candidate', OVERLAY)):
        obj = out/(name+'.o')
        command = [str(gcc), str(directory/'nucleo/Src/multi_native.c'), '-I'+str(directory/'nucleo/Inc'),
                   *flags, '-o', str(obj)]
        run = subprocess.run(command, cwd=debug, capture_output=True)
        (out/(name+'_compile.log')).write_bytes(run.stdout+run.stderr)
        run.check_returncode()
        assert b'warning:' not in run.stderr
        objects[name] = obj
    with objects['baseline'].open('rb') as baseline, objects['candidate'].open('rb') as candidate:
        a,b = ELFFile(baseline),ELFFile(candidate)
        same = {name: a.get_section_by_name('.text.'+name).data()==b.get_section_by_name('.text.'+name).data()
                for name in ('ma_native_fast','mic_observer_step','mic_observer_noise')}
    assert all(same.values()), same
    lines = (debug/'objects.list').read_text(encoding='utf-8').splitlines()
    changed = [f'"{objects["candidate"].as_posix()}"' if 'multi_native.o' in line else line for line in lines]
    assert sum(a!=b for a,b in zip(lines,changed))==1
    rsp = out/'objects.list'
    rsp.write_text('\n'.join(changed)+'\n',encoding='ascii')
    linker = (debug/'makefile').read_text(encoding='utf-8')
    linker = next(line for line in linker.splitlines() if 'arm-none-eabi-gcc -o' in line)
    flags = linker.split('$(LIBS) ',1)[1]
    flags = [item.strip('"') for item in re.findall(r'(?:[^\s"]|"[^"]*")+', flags)
             if not item.startswith(('-T','-Wl,-Map='))]
    elf = out/'observer_admission_linkcheck_DO_NOT_FLASH.elf'
    ld = debug.parent/'STM32G431RBTX_FLASH.ld'
    command = [str(gcc), '-o', str(elf), '@'+str(rsp), '-T'+str(ld), *flags]
    run = subprocess.run(command, cwd=debug, capture_output=True)
    (out/'link.log').write_bytes(run.stdout+run.stderr)
    run.check_returncode()
    return dict(byte_identical_ARM_sections=same, full_link_passed=True, target_cycles_measured=False)


def main():
    protected = verified_files()
    save(OUT/'protected_input_sha256.json', {path.relative_to(ROOT).as_posix():sha for path,sha in protected.items()})
    trace = read_json(CURRENT/'observer_trace_decoded.json')
    arm = ArmObserver(ELF)
    evidence = dict(current_trace=audit_trace(trace, arm),
                    previous_trace=audit_trace(read_json(PREVIOUS/'observer_trace_decoded.json'), arm),
                    ADC=audit_adc(trace), observed_physical_rotation=True,
                    speed_independently_measured=False, physical_root_cause_uniquely_identified=False)
    save(OUT/'NIS_and_ADC_analysis.json', evidence)
    make_overlay()
    native = test_native(trace)
    target = build_arm()
    assert all(digest(path)==sha for path,sha in protected.items())
    save(OUT/'verification.json', dict(passed=True, native=native, ARM=target,
        no_START_CLEAR_RESET_or_flash=True, protection_limits_unchanged=True,
        protected_files_verified=len(protected), installed=False, physical_NIS_corrected=False))
    print(json.dumps({'analysis': evidence, 'verification': native, 'target': target}))


if __name__ == '__main__':
    main()

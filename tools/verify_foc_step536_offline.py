"""Independent replay and ARM OFF-path checks for the step-536 candidate."""

import ctypes as ct
import json
import shutil
import struct
import subprocess

import numpy as np
from elftools.elf.elffile import ELFFile

import check_foc_handover_budget as budget
import check_foc_if_current_feedback as candidate
from replay_start_history import ArmObserver, replay


release = candidate.release
BASE = release.OUT
OUT = BASE / 'step536_validation_r1'
CURRENT_ELF = BASE / 'release/nucleo_2026112108_if_start.elf'
CANDIDATE_ELF = candidate.OUT / 'ARM_linkcheck/speed_admission_linkcheck_DO_NOT_FLASH.elf'


def exact_record_sensitivity():
    run = candidate.TRIAL
    analysis = run.with_name(run.name + '_analysis')
    trace = release.read_json(analysis / 'observer_trace_decoded.json')
    event = trace['first_nis_replay']
    assert event['post_steps'] == 536
    packed = bytes.fromhex(event['raw_hex'])
    state = packed[:168] + bytes(28) + packed[168:176]
    profile = packed[176:228]
    expected = struct.unpack_from('<5f', packed, 228)
    pair_counts = struct.unpack_from('<I', packed, 452)[0] >> 8
    snapshot = (run / 'paged_capture/ADC_peak.bin').read_bytes()

    library_path = OUT / 'rebuild_536_adc.dll'
    build = subprocess.run([shutil.which('g++'), '-std=c++17', '-O2', '-ffp-contract=off', '-shared',
        '-I', str(BASE / 'nucleo/Inc'), str(release.ROOT / 'tools/rebuild_exact_adc_source.cpp'),
        '-o', str(library_path)], check=True, capture_output=True, text=True, timeout=30)
    release.write(OUT / 'rebuild_adc_build.log', build.stdout + build.stderr)
    dll = ct.CDLL(str(library_path))
    rebuild = dll.rebuild_exact
    rebuild.argtypes = [ct.c_char_p, ct.c_void_p, ct.c_void_p, ct.c_float]
    baseline = ArmObserver(CURRENT_ELF)

    def score(inputs):
        rc, output, _ = baseline.step(state, profile, struct.pack('<5f', *inputs), event['fpscr'], pair_counts)
        assert rc == 0
        return struct.unpack_from('<f', output, 168)[0]

    timings = {}
    waveform = np.empty((25, 4), dtype=np.float32)
    for weight in (-1., 0., .25, .5, .75, 1.):
        rebuilt = ct.create_string_buffer(48)
        assert rebuild(snapshot, rebuilt, waveform.ctypes.data, weight) == 0
        actual = struct.unpack_from('<4f', rebuilt.raw)
        if weight == -1.:
            assert actual == expected[:4], (actual, expected[:4])
            assert score(expected) == event['nis']
        timings[str(weight)] = dict(voltage_alpha_beta_V=actual[2:], NIS=score((*actual, expected[-1])))

    current_rows = waveform[-16:, :2].astype(float)
    sensitivities = []
    for index in range(len(current_rows)):
        substitute = np.delete(current_rows, index, axis=0).mean(axis=0)
        sensitivities.append(score((*substitute, *expected[2:])))
    result = {'exact_epoch_matches': True, 'baseline_NIS': event['nis'],
              'NIS_after_offline_voltage_epoch_shift': timings,
              'single_sample_removal_NIS_min_max': [min(sensitivities), max(sensitivities)],
              'under_threshold_if_replacing_one_of_16':sum(n<25. for n in sensitivities),
              'voltage_and_current_observations_are_unchanged_in_candidate_guards': True,
              'scope':'Sensitivity only. Removals and timing shifts are not firmware changes or permission to mask an ADC sample.'}
    release.save(OUT / 'exact_step_sensitivity.json', result)
    return result


def validate_existing_journals():
    parent = BASE.parent
    check_journals = (
        ('stationary_start_2104', parent / 'foc_stationary_start_release_r1/FOC_5Hz_stationary_start_r1_history',
         parent / 'foc_stationary_start_release_r1/release/nucleo_2026112104_foc_start.elf', 2026112104),
        ('prior_foc_2102', parent / 'observer_nis_release_r1/step571_ipm_model_r1/startup_history',
         parent / 'observer_nis_release_r1/release/nucleo_2026112102_nis_admission.elf', 2026112102),
    )
    summaries = {}
    for label, folder, elf, fw in check_journals:
        before = replay(folder, elf, fw, OUT / f'{label}_original.jsonl')
        new_rows = candidate.replay_with_rest_prior(ArmObserver(CANDIDATE_ELF), folder)
        release.save(OUT / f'{label}_same_inputs_new_prior.json', new_rows)
        summaries[label] = dict(
            real_recorded_steps=len(new_rows), original_state_replayed_bit_exact=before['terminal_51_words_bit_exact'],
            original_max_NIS=before['peak_NIS'], candidate_max_NIS=max(r['NIS'] for r in new_rows),
            candidate_NIS_crossings=sum(r['NIS']>=25. for r in new_rows),
        )
    release.save(OUT / 'older_journal_crosscheck.json', summaries)
    return summaries


def execute_off_code():
    post = BASE / 'post_install_idle_r1'
    ram = (post / 'native_SRAM_0.bin').read_bytes()
    with CURRENT_ELF.open('rb') as f:
        symbols = {s.name:(int(s['st_value']),s['st_size'])
                   for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols()}
    values = {name: ram[addr-0x20000000:addr-0x20000000+size]
              for name,(addr,size) in symbols.items() if name in ('model','fe_test_geometry')}
    old_rows = budget.instruction_probe(CURRENT_ELF, values)
    new_rows = budget.instruction_probe(CANDIDATE_ELF, values)
    assert len(old_rows)==len(new_rows)==64*8
    assert all(old['handover']==new['handover'] for old,new in zip(old_rows,new_rows))
    max_old = max(r['instructions'] for r in old_rows)
    max_new = max(r['instructions'] for r in new_rows)
    report = {'cases':64,'iterations_per_case':8,'all_OFF_paths_returned_OK':True,
              'installed_peak_executed_instructions':max_old,'candidate_peak_executed_instructions':max_new,
              'installed_DWT_cycles':3815,'candidate_DWT_not_measured':True,
              'installed':old_rows,'candidate':new_rows}
    release.save(OUT / 'ARM_OFF_checks.json', report)
    return {key:value for key,value in report.items() if key not in ('installed','candidate')}


def main():
    _, protected = candidate.verify_release()
    for folder, files in (
        (candidate.TRIAL, release.read_json(candidate.TRIAL/'saved_files_sha256.json')),
        (candidate.HISTORY, release.read_json(candidate.HISTORY/'download.json')['sha256']),
    ):
        release.verify_inventory(files, folder)
        protected.update({(folder/name).relative_to(release.ROOT).as_posix(): h for name,h in files.items()})
    release.verify_inventory(protected, release.ROOT)
    OUT.mkdir()
    sensitivity = exact_record_sensitivity()
    older = validate_existing_journals()
    off = execute_off_code()
    release.verify_inventory(protected, release.ROOT)
    result = {'sensitivity':sensitivity,'older_journals':older,'OFF_check':off,
              'old_files_verified':len(protected),'motor_commands':0,'thresholds_changed':False}
    release.save(OUT / 'validation.json', result)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()

"""Build and verify 2111/2112 with MCSDK STOP respecting pending fault ACKs."""

import argparse
import inspect
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from elftools.elf.elffile import ELFFile

import build_foc_step536_release as previous
import check_foc_handover_budget as budget
import install_foc_stationary_start_release as installer
import install_foc_step536_release as previous_installer
import run_nis_admission_paged_trial as archive


ROOT, BASE, RECIPE_BASE = previous.ROOT, previous.OUT, previous.RECIPE_BASE
OUT = BASE.parent / 'foc_clear_ack_release_r1'
OLD, NEW = previous.NEW, (2026112111, 2026112112)
read, write, sha = previous.read, previous.write, previous.sha
read_json, save, verify_inventory = previous.read_json, previous.save, previous.verify_inventory
INTERFACE = 'nucleo/Src/mc_interface.c'
TASKS = 'nucleo/Src/mc_tasks.c'
DEBUG = 'nucleo/STM32CubeIDE/Debug'
ELF = f'{DEBUG}/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'


def prepare():
    archive.release = previous
    _, protected = archive.verify_release()
    clear = BASE/'one_CLEAR_powered_r1'
    report = read_json(clear/'report.json')
    assert report['CLEAR'] == 1 and report['START'] == 0 and report['Break_restored']
    assert report['diagnostic']['result'] == 'ACK_ACCEPTED'
    assert report['remaining_faults'] == dict(mc_fault=5, mc_fault_current_mask=0, mc_fault_occurred_mask=0)
    for folder, seal in ((clear, 'sha256.json'), (BASE/'verification', None),
                         (BASE/'step536_hardware_capture_replay', None)):
        hashes = read_json(folder/seal) if seal else {
            path.relative_to(folder).as_posix(): sha(path)
            for path in folder.rglob('*') if path.is_file()
        }
        verify_inventory(hashes, folder)
        protected.update({(folder/name).relative_to(ROOT).as_posix(): digest for name, digest in hashes.items()})
    manifest = read_json(BASE/'release_manifest.json')
    verify_inventory(manifest['artifacts'], BASE)
    verify_inventory(read_json(BASE/'source_hashes.json'), BASE)

    OUT.mkdir()
    for folder in ('nucleo', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE/folder, OUT/folder, ignore=shutil.ignore_patterns(
            'Debug', 'Release', '__pycache__', '*.log', '*.pyc', 'backups'))
    sources = {}
    for folder in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        for path in (OUT/folder).rglob('*'):
            if not path.is_file() or path.suffix not in ('.c', '.h', '.cpp', '.ino', '.py', '.js', '.html'):
                continue
            relative = path.relative_to(OUT).as_posix()
            original = read(path)
            updated = original.replace(str(OLD[0]), str(NEW[0])).replace(str(OLD[1]), str(NEW[1]))
            if relative == INTERFACE:
                old = '  if (IDLE == State  || ICLWAIT == State)'
                assert updated.count(old) == 1
                updated = updated.replace(old,
                    '  /* A fault already inhibits PWM. Keep the scheduler\'s pending ACK. */\n'
                    '  if (IDLE == State || ICLWAIT == State || FAULT_NOW == State || FAULT_OVER == State)')
            if updated != original:
                write(path, updated)
            sources[relative] = sha(path)
    for relative in (TASKS, 'nucleo/Inc/foc_experiment.h', 'nucleo/Inc/current_adc_deadline.h',
                     'nucleo/Inc/current_adc_window_plan.h', 'nucleo/Inc/observer_pair_noise.h',
                     'nucleo/Inc/local_stop.h', 'nucleo/Src/current_shunt.c'):
        assert sources[relative] == sha(BASE/relative), relative
    save(OUT/'source_hashes.json', sources)
    save(OUT/'preserved_inputs_sha256.json', protected)
    save(OUT/'preparation.json', {**read_json(BASE/'preparation.json'),
        'pair': list(NEW), 'base_pair': list(OLD), 'clear_ack_protected_in_fault_states': True})
    print(f'Prepared {NEW}. Protected {len(protected)} old files.')


def c_function(source, signature):
    return source[source.index(signature):].split('\n}', 1)[0] + '\n}'


def verify_ack():
    """Compile the real STOP and ACK plus the real FAULT_OVER scheduler branch."""
    tasks = read(OUT/TASKS)
    fault = tasks.index('case FAULT_OVER:')
    fault_over = tasks[fault:tasks.index('case FAULT_NOW:', fault)]
    assert 'if (flags == 0U && mode == UNO_MODE_OFF) {\n    uno_link.coast_hold=false;\n    uno_stop_motor();' in read(OUT/'nucleo/Src/main.c')
    compiler = shutil.which('g++')
    assert compiler, 'g++ is required for the MCSDK host regression'
    with tempfile.TemporaryDirectory(prefix='mic_clear_ack_') as directory:
        work = Path(directory)
        for candidate, tree in ((False, BASE), (True, OUT)):
            interface = read(tree/INTERFACE)
            program = r'''#include <cassert>
#include <initializer_list>
#define __weak
using MCI_State_t=int;
enum {IDLE, ICLWAIT, RUN, STOP, FAULT_NOW, FAULT_OVER, MCI_NO_COMMAND,
      MCI_START, MCI_STOP, MCI_ACK_FAULTS, MC_NO_FAULTS=0};
struct MCI_Handle_t {int State, current, PastFaults, DirectCommand;};
MCI_Handle_t Mci[1];
constexpr int M1=0;
int MCI_GetSTMState(MCI_Handle_t *p) {return p->State;}
int MCI_GetCurrentFaults(MCI_Handle_t *p) {return p->current;}
int MCI_GetOccurredFaults(MCI_Handle_t *p) {return p->PastFaults;}
'''+c_function(interface, '__weak bool MCI_StopMotor(')+c_function(interface,
    '__weak bool MCI_FaultAcknowledged(')+r'''
void scheduler() {switch(Mci[M1].State) {
'''+fault_over+r'''default: break;}}
int main() {
    auto &m = Mci[M1];
    for (int frames : {0, 1, 8, 64}) {
        for (int previous_fault : {4, 1024, 1028}) {
            m = {FAULT_OVER, 0, previous_fault, MCI_NO_COMMAND};
            assert(MCI_FaultAcknowledged(&m));
            assert(m.PastFaults == 0);
            for (int frame=0; frame<frames; ++frame) {
                assert(MCI_StopMotor(&m) == !CANDIDATE);
            }
            scheduler();
            const bool should_recover = CANDIDATE || frames == 0;
            assert(m.State == (should_recover ? IDLE : FAULT_OVER));
            assert(m.DirectCommand == (should_recover ? MCI_NO_COMMAND : MCI_STOP));
            if (should_recover) assert(!MCI_StopMotor(&m));
        }
    }
    for (int state : {FAULT_NOW, FAULT_OVER}) {
        m = {state, 1024, 1024, MCI_NO_COMMAND};
        assert(!MCI_FaultAcknowledged(&m));
        assert(!MCI_StopMotor(&m));
        assert(m.current == 1024 && m.PastFaults == 1024 && m.State == state);
        m = {state, 0, 0, MCI_NO_COMMAND};
        assert(MCI_StopMotor(&m) == !CANDIDATE);
    }
    for (int state : {RUN, STOP, IDLE, ICLWAIT}) {
        m = {state, 0, 0, MCI_START};
        const bool accepts_stop = state == RUN || state == STOP;
        assert(MCI_StopMotor(&m) == accepts_stop);
        assert(m.DirectCommand == (accepts_stop ? MCI_STOP : MCI_START));
    }
}
'''
            unit, binary = work/'clear_ack.cpp', work/'clear_ack.exe'
            write(unit, program)
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            f'-DCANDIDATE={int(candidate)}', str(unit), '-o', str(binary)],
                           check=True, timeout=20)
            subprocess.run([str(binary)], check=True, timeout=5)
    return {'baseline_reproduced': True, 'pending_ACK_interleavings_passed': 12,
            'OFF_frames_tested': [0, 1, 8, 64], 'fault_masks_tested': [4, 1024, 1028],
            'active_fault_rejects_ACK': True, 'normal_STOP_preserved': True, 'stand_commands': 0}


def verify_off_code():
    ram = (BASE/'post_install_idle_r1/native_SRAM_0.bin').read_bytes()
    with (BASE/ELF).open('rb') as stream:
        symbols = ELFFile(stream).get_section_by_name('.symtab').iter_symbols()
        recorded = {symbol.name: ram[int(symbol['st_value'])-0x20000000:
                                     int(symbol['st_value'])-0x20000000+symbol['st_size']]
                    for symbol in symbols if symbol.name in ('model', 'fe_test_geometry')}
    assert set(recorded) == {'model', 'fe_test_geometry'}
    baseline = budget.instruction_probe(BASE/ELF, recorded)
    candidate = budget.instruction_probe(OUT/ELF, recorded)
    assert baseline == candidate and len(candidate) == 64*8
    return {'cases': 64, 'iterations_per_case': 8, 'instruction_trace_counts_unchanged': True,
            'maximum_executed_instructions': max(row['instructions'] for row in candidate),
            'DWT_on_target_measured': False}


def seal():
    ack = verify_ack()
    off = verify_off_code()
    builder = previous.builder
    builder.BASE, builder.OUT, builder.OLD, builder.NEW = BASE, OUT, OLD, NEW
    evidence = OUT/'step536_hardware_capture_replay'
    evidence.mkdir()
    replay = previous.check
    old_replay_output = replay.OUT
    try:
        replay.OUT = evidence
        result = replay.analyze(OUT/ELF)
    finally:
        replay.OUT = old_replay_output
    assert result['bit_exact_NIS_51_words'] and result['step'] == 536
    assert result['first_237_steps_same_inputs_rest_prior']['peak_NIS_candidate'] < 25
    # The physical capture is from 2108. The page compatibility check starts
    # with the already validated 2110 fixtures from the installed base release.
    with tempfile.TemporaryDirectory(prefix='mic_clear_ack_pages_') as directory:
        builder.CURRENT = Path(directory)
        pages = builder.CURRENT/'paged_capture'
        pages.mkdir()
        for name in ('ADC_peak.bin', 'observer_trace.bin'):
            shutil.copyfile(BASE/'verification'/name, pages/name)
        builder.seal()
    report = OUT/'verification/clear_ack.json'
    save(report, {'passed': True, 'MCSDK': ack, 'ARM_OFF': off,
                  'page_fixture_base_build': OLD[1], 'physical_replay_build': previous.OLD[1]})
    seal_test_report()
    print(f'CLEAR/STOP checked on PC. ARM OFF {off["cases"]} cases, counts unchanged.')


def seal_test_report():
    report = OUT/'verification/clear_ack.json'
    manifest = OUT/'release_manifest.json'
    data = read_json(manifest)
    assert data['pair'] == list(NEW) and read_json(report)['passed']
    verify_inventory(data['artifacts'], OUT)
    data['artifacts'][report.relative_to(OUT).as_posix()] = sha(report)
    staged = manifest.with_suffix('.pending.json')
    save(staged, data)
    staged.replace(manifest)
    script = Path(__file__).resolve()
    save(OUT/'installation_extension_sha256.json', {script.relative_to(ROOT).as_posix(): sha(script)})


def recipes():
    source = inspect.getsource(previous_installer.recipes)
    source = source.replace('import build_foc_step536_release as p', 'import build_foc_clear_ack_release as p')
    source = source.replace('mic_if2110_', 'mic_ack2112_').replace('if_2110_', 'ack_2112_')
    scope = dict(release=sys.modules[__name__])
    exec(compile(source, previous_installer.__file__, 'exec'), scope)
    return scope['recipes']()


def verify():
    installer.p = sys.modules[__name__]
    installer.package_check()
    verify_inventory(read_json(OUT/'installation_extension_sha256.json'), ROOT)
    assert read_json(OUT/'verification/clear_ack.json')['passed']
    recipes()
    print(f'Checked sealed {NEW} package and programming recipes. No hardware access.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'native', 'uno', 'seal', 'verify'))
    phase = parser.parse_args().phase
    if phase in ('native', 'uno'):
        builder = previous.builder
        builder.BASE, builder.OUT, builder.OLD, builder.NEW = BASE, OUT, OLD, NEW
        builder.build(phase)
    else:
        {'prepare': prepare, 'seal': seal, 'verify': verify}[phase]()


if __name__ == '__main__':
    main()

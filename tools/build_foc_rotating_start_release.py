"""Build and seal the 2105/2106 stationary-to-I/f-to-FOC bench release."""

import argparse
import shutil
import sys

from elftools.elf.elffile import ELFFile

import build_foc_stationary_start_release as previous
import check_foc_rotating_start as check
import run_nis_admission_paged_trial as archive
import seal_observer_nis_admission_release as capture_test
from probe_native_programming_state import programmed_hex_image


ROOT = previous.ROOT
BASE = previous.OUT
OUT = BASE.parent / 'foc_rotating_start_release_r1'
OLD = previous.NEW
NEW = (2026112105, 2026112106)
CURRENT = check.TRIAL
ANALYSIS = check.DEFAULT_OUT
RECIPE_BASE = previous.RECIPE_BASE
read, write, sha = previous.read, previous.write, previous.sha
read_json, save, verify_inventory = previous.read_json, previous.save, previous.verify_inventory


def prepare():
    analysis = read_json(ANALYSIS / 'verification.json')
    assert analysis['passed'] and analysis['hardware_commands'] == 0
    assert all(analysis['checks'].values())
    assert (analysis['NIS_trip'], analysis['OFF_cycles_limit'], analysis['estimate_age_ms']) == (25, 4000, 2)
    archive.release = previous
    _, preserved = archive.verify_release()
    for directory, name, field in (
        (CURRENT, 'saved_files_sha256.json', None),
        (BASE / 'one_CLEAR_powered_r1', 'sha256.json', None),
        (check.HISTORY, 'download.json', 'sha256'),
    ):
        identity = read_json(directory / name)
        seal = identity if field is None else identity[field]
        verify_inventory(seal, directory)
        preserved.update({(directory / file).relative_to(ROOT).as_posix(): h for file, h in seal.items()})
    for directory in (CURRENT.with_name(CURRENT.name + '_analysis'), ANALYSIS):
        for path in directory.rglob('*'):
            if path.is_file():
                preserved[path.relative_to(ROOT).as_posix()] = sha(path)
    previous_manifest = read_json(BASE / 'release_manifest.json')
    assert previous_manifest['pair'] == list(OLD)
    verify_inventory(previous_manifest['artifacts'], BASE)
    verify_inventory(read_json(BASE / 'source_hashes.json'), BASE)

    OUT.mkdir()
    for name in ('nucleo', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns(
            'Debug', 'Release', '__pycache__', '*.log', '*.pyc', 'backups'))
    for name in (check.HEADER, check.NATIVE):
        shutil.copyfile(ANALYSIS / 'candidate' / name, OUT / name)
    sources = {}
    for folder in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        for path in (OUT / folder).rglob('*'):
            if path.is_file():
                if path.suffix in ('.c', '.h', '.cpp', '.ino', '.py', '.js', '.html'):
                    original = read(path)
                    updated = original.replace(str(OLD[0]), str(NEW[0])).replace(str(OLD[1]), str(NEW[1]))
                    if updated != original:
                        write(path, updated)
                sources[path.relative_to(OUT).as_posix()] = sha(path)
    for name in ('foc_experiment.h', 'observer_pair_noise.h', 'observer_applied_voltage.h',
                 'current_adc_window_plan.h', 'current_adc_deadline.h', 'local_stop.h', 'stack_guard.h'):
        item = f'nucleo/Inc/{name}'
        assert sources[item] == sha(BASE / item), item
    save(OUT / 'source_hashes.json', sources)
    save(OUT / 'preserved_inputs_sha256.json', preserved)
    save(OUT / 'preparation.json', {
        'pair': list(NEW), 'base_pair': list(OLD), 'NIS': 25, 'OFF_fast_limit_cycles': 4000,
        'estimate_age_ms': 2, 'raw_current_trip_A': 1.35, 'ADC_UPDATE_ticks': 2048,
        'existing_RUN_deadline_cycles': 5312, 'FOC_estimated_profile_limit_Hz': 5,
        'startup': 'I/f followed by qualified FOC with field-rate supervision',
        'same_motor_Q_R_and_capture_ABI': True, 'hardware_commands': 0, 'installed': False,
    })
    print(f'Prepared {NEW}. Protected {len(preserved)} files.')


def build(target):
    previous.BASE, previous.OUT, previous.NEW = BASE, OUT, NEW
    previous.build(target)


def seal():
    protected = read_json(OUT / 'preserved_inputs_sha256.json')
    verify_inventory(protected, ROOT)
    verify_inventory(read_json(OUT / 'source_hashes.json'), OUT)
    native = read_json(OUT / 'nucleo_build_report.json')
    assert native['passed'] and native['build_id'] == NEW[1] and native['errors'] == native['warnings'] == 0
    uno_dir = OUT / 'build/uno'
    uno = read_json(uno_dir / 'unoq_mcsdk_scalar.build-manifest.json')
    assert uno['firmware_build_id'] == NEW[0] and '921600 8N1' in uno['transport']
    assert read_json(uno_dir / 'llext-check.json')['pass']
    verify_inventory({item['file']: item['sha256'].lower() for item in uno['artifacts']}, uno_dir)

    debug = 'nucleo/STM32CubeIDE/Debug'
    source_obj = debug + '/Application/User/multi_native.o'
    with (BASE / source_obj).open('rb') as before, (OUT / source_obj).open('rb') as after:
        old, new = ELFFile(before), ELFFile(after)
        for name in ('mic_observer_step', 'mic_observer_noise'):
            section = '.text.' + name
            assert old.get_section_by_name(section).data() == new.get_section_by_name(section).data()
    image = OUT / debug / 'ACIM-NUCLEOG431RB-IPM15B-VF_OL'
    elf = image.with_suffix('.elf')
    with elf.open('rb') as stream:
        names = {sym.name: int(sym['st_value']) for sym in ELFFile(stream).get_section_by_name('.symtab').iter_symbols()}
        assert names['_estack'] - names['__StackLimit'] == 4096
        assert names['_end'] + 512 <= names['__StackLimit']

    verification = OUT / 'verification'
    verification.mkdir()
    replay = check.saved_evidence(verification, elf)['full_history_before_first_crossing']
    capture_test.release = sys.modules[__name__]
    pages = capture_test.verify_page_contract(verification)
    images = OUT / 'release'
    images.mkdir()
    for ext in ('hex', 'elf', 'bin'):
        shutil.copyfile(image.with_suffix('.' + ext), images / f'nucleo_{NEW[1]}_if_start.{ext}')
    expected, holes = programmed_hex_image(image.with_suffix('.hex'), image.with_suffix('.bin').read_bytes())
    (images / f'nucleo_{NEW[1]}_expected_readback.bin').write_bytes(expected)
    shutil.copyfile(uno_dir / 'UNOQ_MOTOR.ino.elf-zsk.bin', images / f'uno_{NEW[0]}_if_start.elf-zsk.bin')
    save(verification / 'report.json', {
        'passed': True, 'actual_release_ARM_replay': replay, 'observer_kernel_bit_identical': True,
        'native_readback_bytes': len(expected), 'hex_erased_padding_offsets': holes, 'page_contract': pages,
        'physical_timing_measured': False, 'protected_files_verified': len(protected), 'hardware_commands': 0,
    })
    recipe_assets = [RECIPE_BASE / 'installation_recipe_r1/reviewable_installer.py',
                     RECIPE_BASE / 'verification/OFF_qualification_recipe.py',
                     *(ROOT / 'tools' / name for name in ('install_foc_rotating_start_release.py',
                         'install_foc_stationary_start_release.py', 'install_bkin_boot_armed_pair.py',
                         'install_sd_break_filter_usb_pair.py', 'finish_rollback_3014_hmi.py',
                         'flash_verify_unoq_history_hold.cfg', 'verify_restart_unoq_sketch.cfg'))]
    save(OUT / 'installation_assets_sha256.json', {p.relative_to(ROOT).as_posix(): sha(p) for p in recipe_assets})
    files = [*images.iterdir(), *(OUT / 'web_hmi' / name for name in ('server.py', 'static/app.js', 'static/index.html'))]
    verify_inventory(protected, ROOT)
    save(OUT / 'release_manifest.json', {**read_json(OUT / 'preparation.json'), 'built': True,
        'offline_acceptance_passed': True, 'motor_run_tested': False,
        'artifacts': {path.relative_to(OUT).as_posix(): sha(path) for path in files}})
    print(f'Sealed {NEW}. Readback image {len(expected)} bytes. Capture pages verified: {pages["roundtrip_pages"]}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'native', 'uno', 'seal'))
    phase = parser.parse_args().phase
    if phase in ('native', 'uno'):
        build(phase)
    else:
        {'prepare': prepare, 'seal': seal}[phase]()

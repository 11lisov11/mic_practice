"""Build and seal 2103/2104 for the stationary-preflux FOC startup."""

import argparse
import shutil
import sys

from elftools.elf.elffile import ELFFile

import build_observer_nis_admission_release as builder
import check_foc_stationary_start as check
import seal_observer_nis_admission_release as seal_previous
from probe_native_programming_state import programmed_hex_image


ROOT = builder.ROOT
BASE = builder.OUT
ANALYSIS = check.DEFAULT_OUT
CURRENT = check.previous.TRIAL
OUT = BASE.parent / 'foc_stationary_start_release_r1'
OLD = (2026112101, 2026112102)
NEW = (2026112103, 2026112104)
RECIPE_BASE = builder.BASE
read, write, sha = builder.read, builder.write, builder.sha
read_json, save, verify_inventory = builder.read_json, builder.save, builder.verify_inventory


def prepare():
    verified = read_json(ANALYSIS / 'verification.json')
    assert verified['recent_ramp_delay']['completed_5s'] and verified['hardware_commands'] == 0
    acceptance = read_json(ANALYSIS / 'acceptance_cases.json')
    assert acceptance['exactly_25']['fault'] == acceptance['recorded_NIS_27_09']['fault'] == 5
    assert acceptance['just_below_25']['completed_5s']
    check.verify_preserved()
    previous = read_json(BASE / 'release_manifest.json')
    assert previous['pair'] == list(OLD)
    verify_inventory(previous['artifacts'], BASE)
    verify_inventory(read_json(BASE / 'source_hashes.json'), BASE)
    protected = check.archive.protected_inputs()
    for folder in (BASE / 'hardware_install_r1', BASE / 'post_install_idle_r1', CURRENT,
                   ANALYSIS, BASE / 'ipm_calibration_preparation_r1'):
        for path in folder.rglob('*'):
            if path.is_file():
                protected[path.relative_to(ROOT).as_posix()] = sha(path)
    for path in read_json(check.archive.OUT / 'sha256.json'):
        file = check.archive.OUT / path
        protected[file.relative_to(ROOT).as_posix()] = sha(file)

    OUT.mkdir()
    for name in ('nucleo', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns(
            'Debug', 'Release', '__pycache__', '*.log', '*.pyc', 'backups'))
    for name in (check.HEADER, check.NATIVE):
        shutil.copyfile(ANALYSIS / 'candidate' / name, OUT / name)

    sources = {}
    for name in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        for file in (OUT / name).rglob('*'):
            if file.is_file():
                if file.suffix in ('.c', '.h', '.cpp', '.ino', '.py', '.js', '.html'):
                    old = read(file)
                    new = old.replace(str(OLD[0]), str(NEW[0])).replace(str(OLD[1]), str(NEW[1]))
                    if new != old:
                        write(file, new)
                sources[file.relative_to(OUT).as_posix()] = sha(file)
    for name in ('foc_experiment.h', 'observer_pair_noise.h', 'observer_applied_voltage.h',
                 'current_adc_window_plan.h', 'current_adc_deadline.h', 'local_stop.h', 'stack_guard.h'):
        relative = f'nucleo/Inc/{name}'
        assert sources[relative] == sha(BASE / relative), name
    save(OUT / 'source_hashes.json', sources)
    save(OUT / 'preserved_inputs_sha256.json', protected)
    save(OUT / 'preparation.json', {
        'pair': list(NEW), 'base_pair': list(OLD), 'NIS': 25,
        'OFF_fast_limit_cycles': 4000, 'estimate_age_ms': 2, 'raw_current_trip_A': 1.35,
        'ADC_UPDATE_ticks': 2048, 'existing_RUN_deadline_cycles': 5312,
        'FOC_estimated_profile_limit_Hz': 5, 'same_motor_Q_R_and_capture_ABI': True,
        'hardware_commands': 0, 'installed': False,
    })
    print(f'Prepared {NEW}. Protected {len(protected)} files.')


def build(target):
    builder.OUT, builder.BASE, builder.NEW = OUT, BASE, NEW
    getattr(builder, target)()


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
    obj = debug + '/Application/User/multi_native.o'
    with (BASE / obj).open('rb') as before, (OUT / obj).open('rb') as after:
        previous, candidate = ELFFile(before), ELFFile(after)
        for name in ('mic_observer_step', 'mic_observer_noise'):
            section = '.text.' + name
            assert previous.get_section_by_name(section).data() == candidate.get_section_by_name(section).data()
    native_image = OUT / debug / 'ACIM-NUCLEOG431RB-IPM15B-VF_OL'
    elf = native_image.with_suffix('.elf')
    with elf.open('rb') as stream:
        names = {s.name: int(s['st_value']) for s in ELFFile(stream).get_section_by_name('.symtab').iter_symbols()}
        assert names['_estack'] - names['__StackLimit'] == 4096
        assert names['_end'] + 512 <= names['__StackLimit']

    verification = OUT / 'verification'
    verification.mkdir()
    replay = check.saved_trace_check(verification, elf)
    seal_previous.release = sys.modules[__name__]
    pages = seal_previous.verify_page_contract(verification)
    assets = OUT / 'release'
    assets.mkdir()
    for ext in ('hex', 'elf', 'bin'):
        shutil.copyfile(native_image.with_suffix('.' + ext), assets / f'nucleo_{NEW[1]}_foc_start.{ext}')
    readback, holes = programmed_hex_image(native_image.with_suffix('.hex'), native_image.with_suffix('.bin').read_bytes())
    (assets / f'nucleo_{NEW[1]}_expected_readback.bin').write_bytes(readback)
    shutil.copyfile(uno_dir / 'UNOQ_MOTOR.ino.elf-zsk.bin', assets / f'uno_{NEW[0]}_foc_start.elf-zsk.bin')
    save(verification / 'report.json', {
        'passed': True, 'actual_release_ARM_replay': replay, 'observer_kernel_bit_identical': True,
        'native_readback_bytes': len(readback), 'hex_erased_padding_offsets': holes,
        'page_contract': pages, 'physical_timing_measured': False, 'hardware_commands': 0,
        'protected_files_verified': len(protected),
    })

    recipe_assets = [RECIPE_BASE / 'installation_recipe_r1/reviewable_installer.py',
                     RECIPE_BASE / 'verification/OFF_qualification_recipe.py',
                     *(ROOT / 'tools' / name for name in ('install_foc_stationary_start_release.py',
                        'install_bkin_boot_armed_pair.py', 'install_sd_break_filter_usb_pair.py',
                        'finish_rollback_3014_hmi.py', 'flash_verify_unoq_history_hold.cfg',
                        'verify_restart_unoq_sketch.cfg'))]
    save(OUT / 'installation_assets_sha256.json', {p.relative_to(ROOT).as_posix(): sha(p) for p in recipe_assets})
    files = [*assets.iterdir(), *(OUT / 'web_hmi' / name for name in ('server.py', 'static/app.js', 'static/index.html'))]
    verify_inventory(protected, ROOT)
    save(OUT / 'release_manifest.json', {**read_json(OUT / 'preparation.json'),
         'built': True, 'offline_acceptance_passed': True, 'motor_run_tested': False,
         'artifacts': {p.relative_to(OUT).as_posix(): sha(p) for p in files}})
    print(f'Sealed {NEW}. Readback image {len(readback)} bytes. Capture pages verified: {pages["roundtrip_pages"]}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'native', 'uno', 'seal'))
    phase = parser.parse_args().phase
    if phase in ('native', 'uno'):
        build(phase)
    else:
        {'prepare': prepare, 'seal': seal}[phase]()

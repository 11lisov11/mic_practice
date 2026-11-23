"""Build 2107/2108 with the PC-verified handover optimization."""

import argparse
import shutil
import tempfile
from pathlib import Path

import build_foc_rotating_start_release as builder
import check_foc_handover_budget as check


ROOT = builder.ROOT
BASE = builder.OUT
OUT = BASE.parent / 'foc_handover_budget_release_r1'
OLD = builder.NEW
NEW = (2026112107, 2026112108)
RECIPE_BASE = builder.RECIPE_BASE
read, write, sha = builder.read, builder.write, builder.sha
read_json, save, verify_inventory = builder.read_json, builder.save, builder.verify_inventory


def prepare():
    evidence = read_json(check.OUT / 'verification.json')
    assert evidence['passed'] and evidence['hardware_commands'] == 0
    assert evidence['recorded_DWT_cycles_before'] == 4076
    old_ops, new_ops = evidence['instruction_count_replay_before_after']
    assert new_ops < old_ops
    old_div, new_div = evidence['floating_divisions_replay_before_after']
    assert new_div < old_div
    old_manifest = read_json(BASE / 'release_manifest.json')
    assert old_manifest['pair'] == list(OLD)
    verify_inventory(old_manifest['artifacts'], BASE)
    verify_inventory(read_json(BASE / 'source_hashes.json'), BASE)

    protected = read_json(BASE / 'preserved_inputs_sha256.json')
    verify_inventory(protected, ROOT)
    idle = BASE / 'post_install_idle_r1'
    verify_inventory(read_json(idle / 'saved_files_sha256.json'), idle)
    for directory in (BASE / 'hardware_install_r1', idle, check.OUT):
        for file in directory.rglob('*'):
            if file.is_file():
                protected[file.relative_to(ROOT).as_posix()] = sha(file)
    previous_measurement = BASE / 'OFF_budget_audit.json'
    protected[previous_measurement.relative_to(ROOT).as_posix()] = sha(previous_measurement)

    OUT.mkdir()
    for folder in ('nucleo', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE / folder, OUT / folder, ignore=shutil.ignore_patterns('Debug', 'Release',
            '__pycache__', '*.log', '*.pyc', 'backups'))
    shutil.copyfile(check.OUT / 'candidate' / check.HEADER, OUT / check.HEADER)
    sources = {}
    for folder in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        for path in (OUT / folder).rglob('*'):
            if not path.is_file():
                continue
            if path.suffix in ('.c', '.h', '.cpp', '.ino', '.py', '.js', '.html'):
                original = read(path)
                updated = original.replace(str(OLD[0]), str(NEW[0])).replace(str(OLD[1]), str(NEW[1]))
                if updated != original:
                    write(path, updated)
            sources[path.relative_to(OUT).as_posix()] = sha(path)
    for filename in ('foc_experiment.h', 'observer_pair_noise.h', 'observer_applied_voltage.h',
                     'current_adc_window_plan.h', 'current_adc_deadline.h', 'local_stop.h'):
        rel = f'nucleo/Inc/{filename}'
        assert sources[rel] == sha(BASE / rel), rel
    save(OUT / 'source_hashes.json', sources)
    save(OUT / 'preserved_inputs_sha256.json', protected)
    save(OUT / 'preparation.json', {
        'pair': list(NEW), 'base_pair': list(OLD), 'NIS': 25, 'OFF_fast_limit_cycles': 4000,
        'estimate_age_ms': 2, 'raw_current_trip_A': 1.35, 'ADC_UPDATE_ticks': 2048,
        'existing_RUN_deadline_cycles': 5312, 'FOC_estimated_profile_limit_Hz': 5,
        'startup': 'I/f and qualified FOC with optimized fast IRQ',
        'same_motor_Q_R_and_capture_ABI': True, 'hardware_commands': 0, 'installed': False,
    })
    setup = ROOT / 'tools/install_foc_handover_budget_release.py'
    save(OUT / 'installation_extension_sha256.json', {setup.relative_to(ROOT).as_posix(): sha(setup)})
    print(f'Prepared {NEW}. Protected {len(protected)} files.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'native', 'uno', 'seal'))
    phase = parser.parse_args().phase
    if phase == 'prepare':
        prepare()
    else:
        builder.BASE, builder.OUT, builder.OLD, builder.NEW = BASE, OUT, OLD, NEW
        if phase == 'seal':
            # The preceding build produced ABI/CRC-verified 2106 fixtures
            # offline. The last powered capture remains untouched at 2104.
            with tempfile.TemporaryDirectory(prefix='mic_if_2106_pages_') as temp:
                builder.CURRENT = Path(temp)
                pages = builder.CURRENT / 'paged_capture'
                pages.mkdir()
                for name in ('ADC_peak.bin', 'observer_trace.bin'):
                    shutil.copyfile(BASE / 'verification' / name, pages / name)
                builder.seal()
        else:
            builder.build(phase)

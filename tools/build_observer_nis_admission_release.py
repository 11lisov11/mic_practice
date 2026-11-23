"""Prepare and build 2101/2102 without accessing devices or changing captures."""
import argparse
import json
import os
import shutil
import subprocess

from check_recorded_nis_admission import BASE, CURRENT, OUT as ANALYSIS, ROOT, digest, read_json, save


OLD = (2026112013, 2026111810)
NEW = (2026112101, 2026112102)
UNO = CURRENT.parent
OUT = ANALYSIS.parent / 'observer_nis_release_r1'
CHANGES = ('nucleo/Src/multi_native.c', 'nucleo/Inc/observer_trace_core.h')


def read(path):
    return path.read_text(encoding='utf-8')


def write(path, content):
    path.write_text(content, encoding='utf-8')


sha = digest


def verify_inventory(inventory, base):
    for relative, expected in inventory.items():
        assert digest(base/relative) == expected, relative


def prepare(resume=False):
    evidence = read_json(ANALYSIS/'verification.json')
    assert evidence['passed'] and not evidence['installed'] and not evidence['physical_NIS_corrected']
    protected = read_json(ANALYSIS/'protected_input_sha256.json')
    verify_inventory(protected, ROOT)
    verify_inventory(read_json(BASE/'release_manifest.json')['artifacts'], BASE)
    uno = read_json(UNO/'release_manifest.json')
    assert uno['pair']==list(OLD) and uno['readback_verified']
    assert digest(UNO/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')==uno['image_sha256']
    assert digest(UNO/'web_hmi/server.py')==uno['server_sha256']
    captures = (CURRENT, ANALYSIS/'start_history_get', BASE/'FOC_5Hz_20261120_r1',
                UNO/'powered_before_FOC_r1', UNO/'one_CLEAR_powered_r1')
    for folder in captures:
        for path in folder.rglob('*'):
            if path.is_file():
                protected[path.relative_to(ROOT).as_posix()] = digest(path)

    sources = {'nucleo': BASE, 'UNOQ_MOTOR': UNO, 'libraries': UNO, 'web_hmi': UNO}
    if resume:
        assert set(path.name for path in OUT.iterdir()) == sources.keys()
    else:
        OUT.mkdir()
        for name, source in sources.items():
            shutil.copytree(source/name, OUT/name, ignore=shutil.ignore_patterns(
                'Debug', 'Release', '__pycache__', '*.log', 'backups'))
        for name in CHANGES:
            shutil.copyfile(ANALYSIS/'candidate'/name, OUT/name)

    files = {}
    for folder in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        for path in (OUT/folder).rglob('*'):
            if not path.is_file():
                continue
            relative = path.relative_to(OUT).as_posix()
            source = ANALYSIS/'candidate' if relative in CHANGES else sources[relative.split('/')[0]]
            original = (source/relative).read_bytes()
            updated = original
            if path.suffix in ('.c', '.cpp', '.h', '.ino', '.py'):
                for before, after in zip(OLD, NEW):
                    updated = updated.replace(str(before).encode(), str(after).encode())
            saved = path.read_bytes()
            assert saved in (original, updated), relative
            if saved != updated:
                path.write_bytes(updated)
            files[relative] = digest(path)
    for name in ('motor_control.h', 'foc_experiment.h', 'observer_pair_noise.h',
                 'current_adc_window_plan.h', 'current_adc_deadline.h', 'local_stop.h',
                 'observer_start_history.h', 'peak_core.h', 'stack_guard.h'):
        relative = 'nucleo/Inc/'+name
        assert files[relative] == digest(BASE/relative), relative
    save(OUT/'source_hashes.json', files)
    save(OUT/'preserved_inputs_sha256.json', protected)
    save(OUT/'preparation.json', {'pair': list(NEW), 'base_pair': list(OLD),
        'NIS': 25, 'OFF_fast_limit_cycles': 4000, 'estimate_age_ms': 2,
        'raw_current_trip_A': 1.35, 'ADC_UPDATE_ticks': 2048, 'existing_RUN_deadline_cycles': 5312,
        'same_motor_Q_R_and_capture_ABI': True, 'hardware_commands': 0,
        'installed': False, 'protected_files': len(protected)})
    print(f'Sources prepared. Verified and inventoried {len(protected)} old files.')


def native():
    import build_standstill_timing as builder

    builder.p = type('Release', (), {'BASE': BASE, 'OUT': OUT, 'NEW': NEW,
        'read': staticmethod(lambda path: path.read_text(encoding='utf-8')),
        'write': staticmethod(lambda path, text: path.write_text(text, encoding='utf-8'))})
    builder.main()


def uno():
    powershell = shutil.which('pwsh') or shutil.which('powershell')
    build = OUT/'build/uno'
    result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(ROOT/'tools/build_unoq_mcsdk_scalar.ps1'), '-Sketch', str(OUT/'UNOQ_MOTOR'),
        '-OutputDirectory', str(build), '-LibrariesDirectory', str(OUT/'libraries')],
        env={**os.environ, 'PATH': str(ROOT/'.venv/Scripts')+os.pathsep+os.environ['PATH']},
        capture_output=True, text=True, encoding='utf-8', errors='replace')
    (OUT/'uno_build.log').write_text(result.stdout+result.stderr, encoding='utf-8')
    result.check_returncode()
    path = build/'unoq_mcsdk_scalar.build-manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    assert manifest['firmware_build_id'] == NEW[0]
    manifest['transport'] = 'Serial1 / D0-D1, 921600 8N1, protocol v0x03'
    path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print('Uno built and dynamic-loader checks passed.')


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'resume-preparation', 'native', 'uno'))
    {'prepare': prepare, 'resume-preparation': lambda: prepare(resume=True),
     'native': native, 'uno': uno}[parser.parse_args().phase]()

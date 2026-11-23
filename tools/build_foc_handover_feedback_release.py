"""Build the PC-verified FOC handover firmware pair without board I/O."""

import argparse
import shutil

from elftools.elf.elffile import ELFFile

import build_observer_nis_admission_release as builder
import check_foc_handover_feedback as check
from probe_native_programming_state import programmed_hex_image


base = check.release
BASE = check.BASE
CHECK = check.OUT.with_name('foc_handover_feedback_r3')
OUT = check.OUT.with_name('foc_handover_feedback_release_r1')
NEW = (2026112201, 2026112202)


def prepare():
    check.protected_inputs()
    manifest = base.read_json(BASE/'release_manifest.json')
    base.verify_inventory(manifest['artifacts'], BASE)
    OUT.mkdir()
    for name in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        shutil.copytree(BASE/name, OUT/name, ignore=shutil.ignore_patterns(
            'Debug','Release','__pycache__','*.log','*.pyc','backups'))
    for rel in (check.HEADER,check.NATIVE):
        shutil.copyfile(CHECK/'candidate'/rel, OUT/rel)
    hashes = {}
    for name in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
        for file in (OUT/name).rglob('*'):
            if not file.is_file() or file.suffix not in ('.c','.h','.cpp','.ino','.py','.js','.html'):
                continue
            before = base.read(file)
            after = before
            for old,new in zip(manifest['pair'],NEW):
                after = after.replace(str(old),str(new))
            if after != before:
                base.write(file,after)
            hashes[file.relative_to(OUT).as_posix()] = base.sha(file)
    for rel in ('nucleo/Inc/foc_experiment.h','nucleo/Inc/current_adc_deadline.h',
                'nucleo/Inc/current_adc_window_plan.h','nucleo/Inc/observer_pair_noise.h',
                'nucleo/Inc/observer_current_window.h','nucleo/Inc/local_stop.h',
                'nucleo/Src/current_shunt.c','nucleo/Src/mc_interface.c','nucleo/Src/mc_tasks.c'):
        assert hashes[rel] == base.sha(BASE/rel), rel
    base.save(OUT/'source_hashes.json',hashes)


def seal():
    pc = base.read_json(CHECK/'verification.json')
    assert pc['passed'] and pc['limits'] == [25,4000,2] and pc['hardware_commands'] == 0
    base.verify_inventory(base.read_json(OUT/'source_hashes.json'), OUT)
    readback = base.read_json(OUT/'nucleo_build_report.json')
    assert readback['passed'] and readback['build_id'] == NEW[1]
    uno_dir = OUT/'build/uno'
    uno = base.read_json(uno_dir/'unoq_mcsdk_scalar.build-manifest.json')
    assert uno['firmware_build_id'] == NEW[0] and '921600 8N1' in uno['transport']
    assert base.read_json(uno_dir/'llext-check.json')['pass']
    base.verify_inventory({item['file']:item['sha256'].lower() for item in uno['artifacts']}, uno_dir)

    artifacts = OUT/'release'
    artifacts.mkdir()
    image = (OUT/base.ELF).with_suffix('')
    raw = base.read_json(check.ANALYSIS/'observer_trace_decoded.json')['first_nis_replay']
    adc = base.read_json(CHECK/'capture_analysis.json')['voltage_model_on_saved_PWM']
    arm = check.replay_arm(image.with_suffix('.elf'), raw, adc)
    assert arm == pc['ARM']['step_756_replay']
    with image.with_suffix('.elf').open('rb') as stream:
        symbols = {s.name:int(s['st_value']) for s in ELFFile(stream).get_section_by_name('.symtab').iter_symbols()}
        assert symbols['_estack']-symbols['__StackLimit']==4096
        assert symbols['_end']+512<=symbols['__StackLimit']
    timing = check.probe_arm(OUT,image.with_suffix('.elf'))
    assert timing == pc['ARM']['OFF']
    for ext in ('bin','hex','elf'):
        shutil.copyfile(image.with_suffix('.'+ext), artifacts/f'nucleo_{NEW[1]}_if_foc.{ext}')
    expected, _ = programmed_hex_image(image.with_suffix('.hex'), image.with_suffix('.bin').read_bytes())
    (artifacts/f'nucleo_{NEW[1]}_expected_readback.bin').write_bytes(expected)
    shutil.copyfile(uno_dir/'UNOQ_MOTOR.ino.elf-zsk.bin',artifacts/f'uno_{NEW[0]}_if_foc.elf-zsk.bin')
    protected = check.protected_inputs()
    base.save(OUT/'preserved_inputs_sha256.json',protected)
    base.save(OUT/'release_manifest.json', {
        'pair':list(NEW), 'base_pair':list(base.NEW), 'installed':False, 'hardware_commands':0,
        'NIS':25, 'OFF_fast_limit_cycles':4000, 'estimate_age_ms':2, 'raw_current_trip_A':1.35,
        'ADC_UPDATE_ticks':2048, 'ARM_OFF':timing, 'step_756_replay':arm, 'preserved_files':len(protected),
        'artifacts':{file.relative_to(OUT).as_posix():base.sha(file) for file in artifacts.iterdir()},
    })
    base.verify_inventory(base.read_json(OUT/'release_manifest.json')['artifacts'], OUT)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('prepare','native','uno','seal'))
    builder.BASE,builder.OUT,builder.NEW = BASE,OUT,NEW
    phase = parser.parse_args().phase
    {'prepare':prepare,'native':builder.native,'uno':builder.uno,'seal':seal}[phase]()

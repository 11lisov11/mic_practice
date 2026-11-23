"""Build and seal 2109/2110 with the verified I/f startup correction."""

import argparse
import shutil

import build_foc_rotating_start_release as builder
import check_foc_if_current_feedback as check


ROOT = builder.ROOT
BASE = check.BASE
OUT = BASE.parent / 'foc_step536_release_r1'
OLD = check.release.NEW
NEW = (2026112109, 2026112110)
RECIPE_BASE = builder.RECIPE_BASE
read, write, sha = builder.read, builder.write, builder.sha
read_json, save, verify_inventory = builder.read_json, builder.save, builder.verify_inventory


def prepare():
    evidence = read_json(check.OUT / 'verification.json')
    assert evidence['passed'] and evidence['new_powered_starts'] == 0
    assert (evidence['NIS'], evidence['OFF_cycles_limit'], evidence['estimate_age_ms']) == (25, 4000, 2)
    extra = BASE / 'step536_validation_r1'
    crosscheck = read_json(extra / 'validation.json')
    assert crosscheck['OFF_check']['cases'] == 64 and crosscheck['OFF_check']['all_OFF_paths_returned_OK']
    _, protected = check.verify_release()
    for directory, manifest, field in (
            (check.TRIAL, 'saved_files_sha256.json', None), (check.HISTORY, 'download.json', 'sha256')):
        inventory = read_json(directory / manifest)
        if field:
            inventory = inventory[field]
        verify_inventory(inventory, directory)
        protected.update({(directory/name).relative_to(ROOT).as_posix(): digest for name,digest in inventory.items()})
    for directory in (check.TRIAL.with_name(check.TRIAL.name + '_analysis'), check.OUT, extra):
        for path in directory.rglob('*'):
            if path.is_file():
                protected[path.relative_to(ROOT).as_posix()] = sha(path)
    verify_inventory(read_json(BASE / 'release_manifest.json')['artifacts'], BASE)
    verify_inventory(read_json(BASE / 'source_hashes.json'), BASE)

    OUT.mkdir()
    for folder in ('nucleo', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE/folder,OUT/folder,ignore=shutil.ignore_patterns(
            'Debug','Release','__pycache__','*.log','*.pyc','backups'))
    for path in (check.HEADER,check.NATIVE):
        shutil.copyfile(check.OUT/'candidate'/path,OUT/path)
    sources={}
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
        for path in (OUT/folder).rglob('*'):
            if not path.is_file():
                continue
            if path.suffix in ('.c','.cpp','.h','.ino','.py','.html','.js'):
                old=read(path)
                new=old.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if new!=old:
                    write(path,new)
            sources[path.relative_to(OUT).as_posix()]=sha(path)
    for name in ('foc_experiment.h','observer_pair_noise.h','observer_applied_voltage.h',
                 'current_adc_window_plan.h','current_adc_deadline.h','local_stop.h'):
        item=f'nucleo/Inc/{name}'
        assert sources[item]==sha(BASE/item),item
    save(OUT/'source_hashes.json',sources)
    save(OUT/'preserved_inputs_sha256.json',protected)
    save(OUT/'preparation.json',{
        'pair':list(NEW),'base_pair':list(OLD),'NIS':25,'OFF_fast_limit_cycles':4000,
        'estimate_age_ms':2,'raw_current_trip_A':1.35,'ADC_UPDATE_ticks':2048,
        'existing_RUN_deadline_cycles':5312,'FOC_estimated_profile_limit_Hz':5,
        'startup':'I/f current feedback filter and standstill no-load observer prior',
        'same_motor_Q_R_and_capture_ABI':True,'hardware_commands':0,'installed':False,
    })
    relative='tools/install_foc_step536_release.py'
    save(OUT/'installation_extension_sha256.json',{relative:sha(ROOT/relative)})
    print(f'Prepared {NEW}. Protected {len(protected)} files.')


def seal():
    # These raw pages belong to 2108, unlike a prior release made without a live test.
    builder.CURRENT = check.TRIAL
    native = OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    # Validate the exact step 536 and the real early journal against the final
    # linked image before sealing the firmware and transport verification.
    evidence = OUT/'step536_hardware_capture_replay'
    evidence.mkdir()
    original = check.OUT
    try:
        check.OUT=evidence
        result=check.analyze(native)
    finally:
        check.OUT=original
    assert result['bit_exact_NIS_51_words'] and result['step']==536
    assert result['first_237_steps_same_inputs_rest_prior']['peak_NIS_candidate']<25
    builder.seal()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('prepare','native','uno','seal'))
    phase=parser.parse_args().phase
    if phase=='prepare':
        prepare()
    else:
        builder.BASE,builder.OUT,builder.OLD,builder.NEW=BASE,OUT,OLD,NEW
        if phase=='seal':
            seal()
        else:
            builder.build(phase)

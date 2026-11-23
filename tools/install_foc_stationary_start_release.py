"""Check or install the 2103/2104 pair and verify OFF timing over USB."""

import argparse
import sys
import types

import build_foc_stationary_start_release as p


INSTALL = p.OUT / 'hardware_install_r1'
RECEIPT = p.OUT / 'installation_acceptance.json'


def package_check():
    manifest = p.read_json(p.OUT / 'release_manifest.json')
    assert manifest['pair'] == list(p.NEW) and manifest['offline_acceptance_passed']
    assert (manifest['NIS'], manifest['OFF_fast_limit_cycles'], manifest['estimate_age_ms'],
            manifest['raw_current_trip_A'], manifest['ADC_UPDATE_ticks']) == (25, 4000, 2, 1.35, 2048)
    verification = p.read_json(p.OUT / 'verification/report.json')
    assert verification['passed'] and verification['observer_kernel_bit_identical']
    p.verify_inventory(manifest['artifacts'], p.OUT)
    p.verify_inventory(p.read_json(p.OUT / 'source_hashes.json'), p.OUT)
    for name in ('preserved_inputs_sha256.json', 'installation_assets_sha256.json'):
        p.verify_inventory(p.read_json(p.OUT / name), p.ROOT)
    return manifest


def held_programming_and_off_recipes():
    program_path = p.RECIPE_BASE / 'installation_recipe_r1/reviewable_installer.py'
    off_path = p.RECIPE_BASE / 'verification/OFF_qualification_recipe.py'
    source_import = 'import prepare_boot_stack_integrity as p'
    target_import = 'import build_foc_stationary_start_release as p'
    program = p.read(program_path)
    off = p.read(off_path)
    assert program.count(source_import) == off.count(source_import) == 1
    assert program.count('OLD=(2026111807,2026111806)') == 1
    low_bus = " assert 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20,'bus not discharged'"
    assert program.count(low_bus) == 1
    program = (program.replace(source_import, target_import)
               .replace('OLD=(2026111807,2026111806)', 'OLD=p.OLD')
               .replace('_stack_epoch.elf-zsk.bin', '_foc_start.elf-zsk.bin')
               .replace('_stack_guard.hex', '_foc_start.hex')
               .replace('mic_stack1810_', 'mic_foc2104_').replace('stack_1810_', 'foc_2104_')
               .replace(low_bus, " assert s['bp_vbus_valid']==1 and 0<=s['vdc']<20 and 0<=s['bp_vdc']<20,'bus not discharged'"))
    off = off.replace(source_import, target_import).replace('_stack_guard.elf', '_foc_start.elf')
    assert 'BKE/MOE not safe' in program and 'VERIFIED AND HELD' in program
    assert 'row[\'fast_cycles\']<=4000' in off and 'row[\'fe_case\']==64' in off
    assert "'/api/control'" not in program and "'/api/control'" not in off
    return compile(program, str(program_path), 'exec'), compile(off, str(off_path), 'exec')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--j1-off-below20-both-pc-usb', action='store_true')
    args = parser.parse_args()
    package_check()
    program, off = held_programming_and_off_recipes()
    if not args.j1_off_below20_both_pc_usb:
        print('2103/2104 package, readback and OFF recipes verified on PC. No hardware access.')
        return 0

    assert not INSTALL.exists() and not RECEIPT.exists(), 'Review existing programming results before retrying'
    programmer = types.ModuleType('stationary_start_programmer')
    exec(program, programmer.__dict__)
    programmer.package_check = package_check
    previous_argv = sys.argv
    try:
        sys.argv = [previous_argv[0], '--confirmed-j1-off-current-usb-low-bus', '--outdir', str(INSTALL)]
        result = programmer.main()
    finally:
        sys.argv = previous_argv
    report = p.read_json(INSTALL / 'report.json')
    if not (report.get('native_readback_verified') and report.get('uno_readback_verified')
            and report.get('calibration_unchanged')):
        return result or 1
    p.save(RECEIPT, {**report, 'installed': True, 'target_OFF_calculation_report': 'post_install_idle_r1/report.json'})
    verifier = types.ModuleType('stationary_start_off_verifier')
    exec(off, verifier.__dict__)
    return verifier.main()


if __name__ == '__main__':
    raise SystemExit(main())

"""Install 2201/2202 with verified readback and automatic DWT tests at PWM OFF."""

import argparse
import sys
import types

import build_foc_clear_ack_release as previous
import build_foc_handover_feedback_release as release
import install_bkin_boot_armed_pair as io
import install_foc_stationary_start_release as installer
from probe_low_bus_usb import probe


ROOT = release.base.ROOT
BASE, OUT, NEW = release.BASE, release.OUT, release.NEW
OLD = previous.NEW
read, write, sha = release.base.read, release.base.write, release.base.sha
read_json, save = release.base.read_json, release.base.save


def package_check():
    manifest = release.base.read_json(OUT/'release_manifest.json')
    assert manifest['pair'] == list(NEW) and manifest['base_pair'] == list(OLD)
    assert not manifest['installed'] and manifest['hardware_commands'] == 0
    assert (manifest['NIS'],manifest['OFF_fast_limit_cycles'],manifest['estimate_age_ms'],
            manifest['raw_current_trip_A'],manifest['ADC_UPDATE_ticks']) == (25,4000,2,1.35,2048)
    offline = release.base.read_json(release.CHECK/'verification.json')
    assert offline['passed'] and offline['limits'] == [25,4000,2]
    assert offline['ARM']['OFF'] == manifest['ARM_OFF']
    release.base.verify_inventory(manifest['artifacts'], OUT)
    release.base.verify_inventory(release.base.read_json(OUT/'source_hashes.json'), OUT)
    release.base.verify_inventory(release.base.read_json(OUT/'preserved_inputs_sha256.json'), ROOT)
    release.base.verify_inventory(release.base.read_json(BASE/'installation_assets_sha256.json'), ROOT)
    return manifest


def recipes():
    program_path = previous.RECIPE_BASE/'installation_recipe_r1/reviewable_installer.py'
    off_path = previous.RECIPE_BASE/'verification/OFF_qualification_recipe.py'
    old_import = 'import prepare_boot_stack_integrity as p'
    new_import = 'import install_foc_handover_feedback_release as p'
    program, off = read(program_path), read(off_path)
    assert program.count(old_import) == off.count(old_import) == 1
    program = (program.replace(old_import,new_import).replace('OLD=(2026111807,2026111806)','OLD=p.OLD')
               .replace('_stack_epoch.elf-zsk.bin','_if_foc.elf-zsk.bin')
               .replace('_stack_guard.hex','_if_foc.hex')
               .replace('mic_stack1810_','mic_if_foc2202_').replace('stack_1810_','if_foc_2202_')
               .replace(" assert 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20,'bus not discharged'",
                        " assert s['bp_vbus_valid']==1 and 0<=s['bp_vbus_age_ms']<300"
                        " and 0<=s['vdc']<20 and 0<=s['bp_vdc']<20,'bus not discharged'"))
    off = off.replace(old_import,new_import).replace('_stack_guard.elf','_if_foc.elf')
    assert "row['fast_cycles']<=4000" in off and "row['fe_case']==64" in off
    assert 'BKE/MOE not safe' in program and 'VERIFIED AND HELD' in program
    assert "'/api/control'" not in program and "'/api/control'" not in off
    return compile(program,str(program_path),'exec'),compile(off,str(off_path),'exec')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument('--confirmed-j1-off-below20-both-usb',action='store_true')
    operation.add_argument('--read-installed-dwt',action='store_true')
    args = parser.parse_args()
    package_check()
    _, off = recipes()
    if args.read_installed_dwt:
        report = read_json(OUT/'hardware_install_r1/report.json')
        assert report['native_readback_verified'] and report['uno_readback_verified']
        assert report['calibration_unchanged'] and report['native_BKE'] and not report['native_MOE']
        assert not (OUT/'post_install_idle_r1').exists()
        receipt = OUT/'installation_acceptance.json'
        if not receipt.exists():
            save(receipt,{**report,'installed':True,
                          'target_OFF_calculation_report':'post_install_idle_r1/report.json'})
        verifier = types.ModuleType('foc_handover_feedback_off_verifier')
        exec(off,verifier.__dict__)
        return verifier.main()
    if not args.confirmed_j1_off_below20_both_usb:
        print('2201/2202 images, archived captures and OFF64 recipes verified.')
        return 0

    installer.p = sys.modules[__name__]
    installer.INSTALL = OUT/'hardware_install_r1'
    installer.RECEIPT = OUT/'installation_acceptance.json'
    assert not installer.INSTALL.exists() and not installer.RECEIPT.exists()
    io.URL = 'http://127.0.0.1:18080'
    probe(BASE,OUT/'USB_OFF_preflight_r1',OLD)
    installer.package_check = package_check
    installer.held_programming_and_off_recipes = recipes
    original = sys.argv
    try:
        sys.argv = [original[0],'--j1-off-below20-both-pc-usb']
        return installer.main()
    finally:
        sys.argv = original


if __name__ == '__main__':
    raise SystemExit(main())

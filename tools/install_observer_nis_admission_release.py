"""Record 2101/2102 once on USB and verify the stopped calculation.

The default is an offline integrity check. Programming requires the actual
operator-confirmed J1 OFF, DC bus below 20 V, both boards on PC USB state.
"""
import argparse
import sys
import types

import build_observer_nis_admission_release as p


INSTALL = p.OUT/'hardware_install_r1'
RECEIPT = p.OUT/'installation_acceptance.json'


def package_check():
    manifest = p.read_json(p.OUT/'release_manifest.json')
    assert manifest['pair']==list(p.NEW) and manifest['offline_acceptance_passed']
    assert (manifest['NIS'],manifest['OFF_fast_limit_cycles'],manifest['estimate_age_ms'],
            manifest['raw_current_trip_A'],manifest['ADC_UPDATE_ticks'])==(25,4000,2,1.35,2048)
    assert p.read_json(p.OUT/'verification/report.json')['passed']
    p.verify_inventory(manifest['artifacts'], p.OUT)
    p.verify_inventory(p.read_json(p.OUT/'source_hashes.json'), p.OUT)
    p.verify_inventory(p.read_json(p.OUT/'preserved_inputs_sha256.json'), p.ROOT)
    p.verify_inventory(p.read_json(p.OUT/'installation_assets_sha256.json'), p.ROOT)
    return manifest


def recipes():
    base = p.BASE/'installation_recipe_r1/reviewable_installer.py'
    install = p.read(base).replace('import prepare_boot_stack_integrity as p',
                                  'import build_observer_nis_admission_release as p')
    assert 'OLD=(2026111807,2026111806)' in install
    install = install.replace('OLD=(2026111807,2026111806)', 'OLD=p.OLD')
    install = install.replace('_stack_epoch.elf-zsk.bin', '_nis_admission.elf-zsk.bin')
    install = install.replace('_stack_guard.hex', '_nis_admission.hex')
    install = install.replace('mic_stack1810_', 'mic_nis2102_').replace('stack_1810_', 'nis_2102_')
    original = " assert 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20,'bus not discharged'"
    assert install.count(original)==1
    install = install.replace(original,
        " assert s['bp_vbus_valid']==1 and 0<=s['vdc']<20 and 0<=s['bp_vdc']<20,'bus not discharged'")
    idle = p.read(p.BASE/'verification/OFF_qualification_recipe.py')
    idle = idle.replace('import prepare_boot_stack_integrity as p',
                        'import build_observer_nis_admission_release as p').replace('_stack_guard.elf','_nis_admission.elf')
    assert all(name not in install for name in ("'/api/control'", "'cmd'"))
    return compile(install, str(base), 'exec'), compile(idle, 'NIS2102_OFF_readback', 'exec')


def run(args):
    package_check()
    install, idle = recipes()
    if not args.j1_off_below20_both_pc_usb:
        print('2101/2102 integrity, independent readback assets and OFF recipe verified. No hardware access.')
        return 0
    assert not RECEIPT.exists() and not INSTALL.exists(), 'A previous programming attempt requires reviewed resume'
    # This checks the exact USB devices, low-bus report and native MOE=0 again
    # before either write. The reused recipe also archives old flash and SRAM.
    module = types.ModuleType('nis_admission_installer')
    exec(install, module.__dict__)
    module.package_check = package_check
    old_argv = sys.argv
    try:
        sys.argv = [old_argv[0], '--confirmed-j1-off-current-usb-low-bus', '--outdir', str(INSTALL)]
        result = module.main()
    finally:
        sys.argv = old_argv
    receipt = p.read_json(INSTALL/'report.json')
    verified_images = receipt.get('native_readback_verified') and receipt.get('uno_readback_verified')
    if verified_images:
        p.save(RECEIPT, {**receipt, 'installed':True, 'target_OFF_calculation_report':'post_install_idle_r1/report.json'})
    if not verified_images or not receipt.get('calibration_unchanged'):
        return result or 1
    verify = types.ModuleType('nis_admission_OFF_verifier')
    exec(idle, verify.__dict__)
    # Read DWT and MAX timings even if the initial HMI readiness wait timed out.
    return verify.main()


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--j1-off-below20-both-pc-usb', action='store_true')
    raise SystemExit(run(parser.parse_args()))

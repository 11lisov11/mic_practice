"""Verify or install 2107/2108 and run the USB readback/OFF DWT checks."""

import argparse
import sys

import build_foc_handover_budget_release as release
import install_foc_stationary_start_release as installer


def recipes():
    program_path = release.RECIPE_BASE / 'installation_recipe_r1/reviewable_installer.py'
    off_path = release.RECIPE_BASE / 'verification/OFF_qualification_recipe.py'
    source_import = 'import prepare_boot_stack_integrity as p'
    target_import = 'import build_foc_handover_budget_release as p'
    program = release.read(program_path)
    off = release.read(off_path)
    assert program.count(source_import) == off.count(source_import) == 1
    assert program.count('OLD=(2026111807,2026111806)') == 1
    low_bus = " assert 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20,'bus not discharged'"
    assert program.count(low_bus) == 1
    program = (program.replace(source_import, target_import)
               .replace('OLD=(2026111807,2026111806)', 'OLD=p.OLD')
               .replace('_stack_epoch.elf-zsk.bin', '_if_start.elf-zsk.bin')
               .replace('_stack_guard.hex', '_if_start.hex')
               .replace('mic_stack1810_', 'mic_if2108_').replace('stack_1810_', 'if_2108_')
               .replace(low_bus, " assert s['bp_vbus_valid']==1 and 0<=s['vdc']<20 and 0<=s['bp_vdc']<20,'bus not discharged'"))
    off = off.replace(source_import, target_import).replace('_stack_guard.elf', '_if_start.elf')
    assert 'BKE/MOE not safe' in program and 'VERIFIED AND HELD' in program
    assert "row['fast_cycles']<=4000" in off and "row['fe_case']==64" in off
    assert "'/api/control'" not in program and "'/api/control'" not in off
    return compile(program, str(program_path), 'exec'), compile(off, str(off_path), 'exec')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--j1-off-below20-both-pc-usb', action='store_true')
    args = parser.parse_args()
    release.verify_inventory(release.read_json(release.OUT / 'installation_extension_sha256.json'), release.ROOT)
    installer.p = release
    installer.INSTALL = release.OUT / 'hardware_install_r1'
    installer.RECEIPT = release.OUT / 'installation_acceptance.json'
    installer.held_programming_and_off_recipes = recipes
    if not args.j1_off_below20_both_pc_usb:
        installer.package_check()
        recipes()
        print('2107/2108 package, readback and OFF recipes verified on PC. No hardware access.')
        return 0
    return installer.main()


if __name__ == '__main__':
    raise SystemExit(main())

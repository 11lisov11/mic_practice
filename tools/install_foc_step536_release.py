"""Verify or install 2109/2110 and measure the OFF timing after readback."""

import argparse
import sys

import build_foc_step536_release as release
import install_foc_stationary_start_release as installer
from probe_low_bus_usb import off as require_off
from probe_native_programming_state import probe
from install_bkin_boot_armed_pair import live_status


def recipes(observed_off=False):
    program_path=release.RECIPE_BASE/'installation_recipe_r1/reviewable_installer.py'
    off_path=release.RECIPE_BASE/'verification/OFF_qualification_recipe.py'
    program=release.read(program_path)
    off=release.read(off_path)
    old_import='import prepare_boot_stack_integrity as p'
    new_import='import build_foc_step536_release as p'
    assert program.count(old_import)==off.count(old_import)==1
    assert program.count('OLD=(2026111807,2026111806)')==1
    low_bus=" assert 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20,'bus not discharged'"
    assert program.count(low_bus)==1
    program=(program.replace(old_import,new_import)
        .replace('OLD=(2026111807,2026111806)','OLD=p.OLD')
        .replace('_stack_epoch.elf-zsk.bin','_if_start.elf-zsk.bin')
        .replace('_stack_guard.hex','_if_start.hex')
        .replace('mic_stack1810_','mic_if2110_').replace('stack_1810_','if_2110_')
        .replace(low_bus," assert s['bp_vbus_valid']==1 and 0<=s['vdc']<20 and 0<=s['bp_vdc']<20,'bus not discharged'"))
    off=off.replace(old_import,new_import).replace('_stack_guard.elf','_if_start.elf')
    if observed_off:
        description = ('J1 OFF explicitly confirmed; exact PCUSB identities and fresh valid low-bus ADC/SWD '
                       'observed; 15V and wiring unchanged; no START/CLEAR')
        assert program.count(description)==1
        program=program.replace(description,'User explicitly authorized the present USB write. Fresh telemetry and direct '
                                'SWD agree on the low bus, BKE enabled and MOE off. No START/CLEAR.')
    assert 'BKE/MOE not safe' in program and 'VERIFIED AND HELD' in program
    assert "row['fast_cycles']<=4000" in off and "row['fe_case']==64" in off
    assert "'/api/control'" not in program and "'/api/control'" not in off
    return compile(program,str(program_path),'exec'),compile(off,str(off_path),'exec')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--j1-off-below20-both-pc-usb',action='store_true')
    action.add_argument('--observed-off-both-pc-usb',action='store_true',
                        help='Use only for an explicitly authorized write with both boards already on USB')
    args=parser.parse_args()
    release.verify_inventory(release.read_json(release.OUT/'installation_extension_sha256.json'),release.ROOT)
    replay=release.read_json(release.OUT/'step536_hardware_capture_replay/saved_evidence.json')
    assert replay['bit_exact_NIS_51_words'] and replay['step']==536
    installer.p=release
    installer.INSTALL=release.OUT/'hardware_install_r1'
    installer.RECEIPT=release.OUT/'installation_acceptance.json'
    installer.held_programming_and_off_recipes=lambda: recipes(args.observed_off_both_pc_usb)
    if not args.j1_off_below20_both_pc_usb and not args.observed_off_both_pc_usb:
        installer.package_check()
        recipes()
        print('2109/2110 package, readback and OFF recipes verified on PC. No hardware access.')
        return 0
    if not args.observed_off_both_pc_usb:
        return installer.main()

    installer.package_check()
    assert not installer.INSTALL.exists() and not installer.RECEIPT.exists()
    before=live_status()
    require_off(before,release.OLD)
    observed=probe(release.BASE,release.OUT/'observed_OFF_preflight_r1',
                   'User authorized immediate programming with both boards on USB and reported a 10 V bus.')
    after=live_status()
    require_off(after,release.OLD)
    assert before['linux_boot_id']==after['linux_boot_id']
    assert all(row['bdtr']&4096 and not row['moe'] and abs(row['bus_volts']-after['bp_vdc'])<=2
               for row in observed['rows'])
    argv=sys.argv
    try:
        sys.argv=[argv[0],'--j1-off-below20-both-pc-usb']
        return installer.main()
    finally:
        sys.argv=argv


if __name__=='__main__':
    raise SystemExit(main())

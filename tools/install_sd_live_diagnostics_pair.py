"""Install reviewed additive SD telemetry. No START/CLEAR/ARM or calibration writes.

Uses the existing atomic HMI and verified MCU installation procedure.
Physical USB programming still requires J1/J4 off and independent meter <=20 V.
"""
import hashlib
import json
import math
from pathlib import Path
import install_uart_resync_fix_pair as base

ROOT = Path(__file__).resolve().parents[1]
C = ROOT/'artifacts/live_bench_20261018/sd_live_diagnostics_r1'
OLD = (2026101807,2026101806)
NEW = (2026101809,2026101808)
io = base.io

GUARD = (ROOT/'tools/uart_resync_fix/update_guard.py').read_text(encoding='utf-8').replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026101807,2026101806),(2026101809,2026101808))')
exec(GUARD)


def verify_package(candidate=C):
    manifest=json.loads((candidate/'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('schema')!='mic_ai.sd_live_diagnostics.v1' or
        manifest.get('pair_compatibility_ids')!=list(NEW) or not manifest.get('built') or
        not manifest.get('selftest_pass') or manifest.get('physical_sd_cause_proven') is not False or
        manifest.get('hv_release_approved') is not False):
        raise RuntimeError('unverified SD diagnostic candidate')
    for key in ('calibration_changed','control_protocol_changed','pwm_or_motor_control_changed',
                'recovery_budget_changed','watchdog_changed'):
        if manifest.get(key) is not False:
            raise RuntimeError('unexpected change: '+key)
    test=json.loads((candidate/'selftest/report.json').read_text(encoding='utf-8'))
    if not test.get('pass') or test['bkin']['host_cases']!=450 or not test['uart']['pass']:
        raise RuntimeError('missing SD/recorder/transport acceptance')
    for table in ('source_sha256','build_sha256'):
        if not manifest.get(table):raise RuntimeError('missing package hashes')
        for relative,expected in manifest[table].items():
            if base.io.sha(candidate/relative)!=expected:
                raise RuntimeError('package changed: '+relative)
    for folder,name,build in [('uno','unoq_mcsdk_scalar',NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',NEW[1])]:
        m=json.loads((candidate/'build'/folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        if m['firmware_build_id']!=build:raise RuntimeError('wrong build identity')
    return candidate/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',candidate/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'


original_make_remote = base.make_remote_installer


def make_remote_installer():
    source=original_make_remote()
    old_guard=(ROOT/'tools/uart_resync_fix/update_guard.py').read_text(encoding='utf-8')
    if source.count(old_guard)!=1:raise RuntimeError('remote guard layout changed')
    return source.replace(old_guard,GUARD)


def main():
    base.C=C
    base.OLD=OLD
    base.NEW=NEW
    base.precheck=precheck
    base.verify_package=verify_package
    base.make_remote_installer=make_remote_installer
    base.__doc__=__doc__
    return base.main()


if __name__=='__main__':
    raise SystemExit(main())

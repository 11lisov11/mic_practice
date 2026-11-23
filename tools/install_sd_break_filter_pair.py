"""Install BKIN filter candidate on J1-off USB bench, measured bus <=20 V.

J4 auxiliary may remain on under the user's existing authorization. No START,
CLEAR, ARM, calibration write, or live protection override is issued here.
"""
import json
import math
import install_uart_tx_dma_pair as base
import prepare_sd_break_filter_fix as package

ROOT, C, OLD, NEW = package.ROOT, package.OUT, package.OLD, package.NEW
io = base.io
GUARD = (ROOT / 'tools/uart_resync_fix/update_guard.py').read_text(encoding='utf-8').replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026101813,2026101812),(2026102001,2026102002))')
exec(GUARD)


def verify_package(candidate=C):
    m = json.loads((candidate / 'manifest.json').read_text(encoding='utf-8'))
    if (m.get('schema') != 'mic_ai.sd_break_filter_fix.v1' or
            m.get('pair_compatibility_ids') != list(NEW) or not m.get('built') or
            not m.get('selftest_pass') or m.get('break_filter_before') != 3 or
            m.get('break_filter_after') != 9 or not m.get('break_filter_changed')):
        raise RuntimeError('unverified BKIN filter package')
    for k in ('calibration_changed', 'control_protocol_changed', 'vf_or_pwm_timing_changed',
              'internal_ipm_protection_changed', 'automatic_restart_added',
              'recovery_budget_changed', 'watchdog_changed', 'tx_backend_changed'):
        if m.get(k) is not False:
            raise RuntimeError('unexpected change: ' + k)
    tests = json.loads((candidate / 'selftest/report.json').read_text(encoding='utf-8'))
    filt = json.loads((candidate / 'filter_selftest/report.json').read_text(encoding='utf-8'))
    if (not tests['pass'] or tests['tx']['dma_stress_frames'] != 2048 or
            tests['bkin']['host_cases'] != 450 or tests['mutation_controls'] != 6 or
            not tests['uart']['pass'] or not filt['passed'] or filt['mutations_detected'] != 3 or
            filt['phase_cases'] != 22528):
        raise RuntimeError('missing driver, recorder or filter checks')
    for table in ('source_sha256', 'build_sha256', 'verification_sha256'):
        if not m.get(table):
            raise RuntimeError('missing package hashes')
        for relative, expected in m[table].items():
            if io.sha(candidate / relative) != expected:
                raise RuntimeError('package changed: ' + relative)
    for folder, name, build in [('uno', 'unoq_mcsdk_scalar', NEW[0]),
                               ('nucleo', 'ACIM-NUCLEOG431RB-IPM15B-VF_OL', NEW[1])]:
        b = json.loads((candidate / 'build' / folder / (name + '.build-manifest.json')).read_text(encoding='utf-8-sig'))
        if b['firmware_build_id'] != build:
            raise RuntimeError('image identity mismatch')
        for artifact in b['artifacts']:
            if io.sha(candidate / 'build' / folder / artifact['file']) != artifact['sha256'].lower():
                raise RuntimeError('image manifest hash mismatch')
    return candidate / 'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin', candidate / 'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'


base.C = C
base.OLD = OLD
base.NEW = NEW
base.GUARD = GUARD
base.precheck = precheck
base.verify_package = verify_package
make_remote_installer = base.make_remote_installer

if __name__ == '__main__':
    raise SystemExit(base.main())

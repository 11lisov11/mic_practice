"""Install the sealed smooth V/f profile on the confirmed J1-off USB bench."""
import json
import math
import install_uart_clean_confirm_pair as parent
import prepare_vf_smooth_start as package

ROOT,C,OLD,NEW=package.ROOT,package.OUT,package.OLD,package.NEW
base=parent.base;io=parent.io
GUARD=parent.GUARD.replace('((2026102101,2026102102),(2026102103,2026102104))',
                          '((2026102103,2026102104),(2026102401,2026102402))')
exec(GUARD)

def verify_package(candidate=C):
    m=json.loads((candidate/'manifest.json').read_text(encoding='utf-8'))
    if (m.get('schema')!='mic_ai.vf_smooth_start.v1' or m.get('pair_compatibility_ids')!=list(NEW)
        or not m.get('built') or not m.get('selftest_pass') or m.get('record_schema')!=5
        or m.get('record_bytes')!=320 or m.get('join_frequency_hz')!=10
        or m.get('half_join_frequency_phase_peak_anchor_v')!=20
        or m.get('zero_frequency_phase_peak_v')!=0
        or m.get('pwm_or_motor_control_changed') is not True or m.get('vf_envelope_changed') is not True):
        raise RuntimeError('unverified smooth V/f package')
    for key in ('calibration_changed','break_filter_changed','control_protocol_changed','uart_changed',
                'uart_tx_backend_changed','watchdogs_changed','recovery_budget_changed','automatic_restart_added'):
        if m.get(key) is not False:raise RuntimeError('unexpected change: '+key)
    t=json.loads((candidate/'selftest/report.json').read_text(encoding='utf-8'))
    if not t['passed'] or not t['vf']['passed'] or t['vf']['ramp_cases']!=3 or t['negative_controls']<1:
        raise RuntimeError('missing continuity/ramp evidence')
    if not t['uart']['pass'] or t['uart']['two_NE_position_pairs']!=903:
        raise RuntimeError('missing retained UART checks')
    for table in ('source_sha256','build_sha256','verification_sha256'):
        if not m.get(table):raise RuntimeError('missing hashes')
        for rel,expected in m[table].items():
            if io.sha(candidate/rel)!=expected:raise RuntimeError('package changed: '+rel)
    for folder,name,build in [('uno','unoq_mcsdk_scalar',NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',NEW[1])]:
        b=json.loads((candidate/'build'/folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        if b['firmware_build_id']!=build:raise RuntimeError('image identity mismatch')
        for artifact in b['artifacts']:
            if io.sha(candidate/'build'/folder/artifact['file'])!=artifact['sha256'].lower():
                raise RuntimeError('image manifest hash mismatch')
    return candidate/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',candidate/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'

def configure():
    base.C=C;base.OLD=OLD;base.NEW=NEW;base.GUARD=GUARD
    base.precheck=precheck;base.verify_package=verify_package
configure()
make_remote_installer=base.make_remote_installer
if __name__=='__main__':raise SystemExit(base.main())

"""Install the sealed UART confirmation pair on the confirmed deenergized USB bench."""
import json
import math
import install_uart_tx_dma_pair as base
import prepare_uart_clean_confirm as package

ROOT,C,OLD,NEW=package.ROOT,package.OUT,package.OLD,package.NEW
io=base.io
GUARD=(ROOT/'tools/uart_resync_fix/update_guard.py').read_text(encoding='utf-8').replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026102101,2026102102),(2026102103,2026102104))')
# Retain the diagnosed NE-only latch for programming; never send CLEAR to make
# a programming gate pass. All physical J1-off / USB / meter checks still apply.
anchor="        for key in ('mc_uart_error_flags','bp_uart_error_flags'):\n"
assert GUARD.count(anchor)==1
GUARD=GUARD.replace(anchor,"""        known_ne=(s.get('mc_transport_fault')==5 and s.get('bp_transport_fault')==5
            and s.get('mc_fault') in (1,5) and s.get('bp_fault')==s.get('mc_fault')
            and s.get('mc_fault_reason')==12 and s.get('bp_fault_reason')==12
            and s.get('mc_last_bad_reason')==12 and s.get('bp_last_bad_reason')==12
            and s.get('mc_last_uart_error_flags')==4 and s.get('bp_last_uart_error_flags')==4
            and s.get('mc_uart_error_flags')==4 and s.get('bp_uart_error_flags')==4
            and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0
            and s.get('bp_fault_current_mask')==0 and s.get('bp_fault_occurred_mask')==0)
"""+anchor)
GUARD=GUARD.replace("if s[key]!=0: return False,'active UART hardware error: '+key",
                    "if s[key]!=0 and not known_ne: return False,'active UART hardware error: '+key")
GUARD=GUARD.replace('not (reset_timeout or known_crc)','not (reset_timeout or known_crc or known_ne)')
exec(GUARD)

def verify_package(candidate=C):
    m=json.loads((candidate/'manifest.json').read_text(encoding='utf-8'))
    if (m.get('schema')!='mic_ai.uart_clean_confirm.v1' or m.get('pair_compatibility_ids')!=list(NEW)
        or not m.get('built') or not m.get('selftest_pass') or m.get('record_schema')!=5
        or m.get('record_bytes')!=320 or m.get('clean_confirmation_deadline_ms')!=100
        or m.get('maximum_outstanding_noisy_frames')!=1 or m.get('damaged_frame_budget')!=2
        or m.get('damaged_frame_window_ms')!=1000 or m.get('watchdog_ms')!=300
        or m.get('frame_deadline_ms')!=15):raise RuntimeError('unverified UART confirmation package')
    for key in ('calibration_changed','break_filter_changed','control_protocol_changed',
                'pwm_or_motor_control_changed','uart_tx_backend_changed','watchdogs_changed',
                'recovery_budget_changed','automatic_restart_added'):
        if m.get(key) is not False:raise RuntimeError('unexpected change: '+key)
    t=json.loads((candidate/'selftest/report.json').read_text(encoding='utf-8'))
    if not t['passed'] or not t['replay']['old']['old_fatal_reproduced'] or t['replay']['fixed']['two_NE_position_pairs']!=903:
        raise RuntimeError('missing captured-frame regression')
    if not t['contract']['pass'] or t['host']['host_cases']<1149 or t['negative_controls']<7:
        raise RuntimeError('missing transport/SD/negative checks')
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

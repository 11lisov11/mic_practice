"""Install the sealed dual SD package only on the confirmed J1-off USB bench."""
import json
import math
import install_uart_tx_dma_pair as base
import prepare_sd_dual_capture as package

ROOT,C,OLD,NEW=package.ROOT,package.OUT,package.OLD,package.NEW
io=base.io
GUARD=(ROOT/'tools/uart_resync_fix/update_guard.py').read_text(encoding='utf-8').replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026102001,2026102002),(2026102101,2026102102))')
exec(GUARD)

def verify_package(candidate=C):
    m=json.loads((candidate/'manifest.json').read_text(encoding='utf-8'))
    if (m.get('schema')!='mic_ai.sd_dual_capture.v1' or m.get('pair_compatibility_ids')!=list(NEW)
        or not m.get('built') or not m.get('selftest_pass') or m.get('record_schema')!=5
        or m.get('record_bytes')!=320):raise RuntimeError('unverified dual SD package')
    for key in ('calibration_changed','break_filter_changed','control_protocol_changed',
                'pwm_or_motor_control_changed','uart_tx_backend_changed','watchdogs_changed','automatic_restart_added'):
        if m.get(key) is not False:raise RuntimeError('unexpected change: '+key)
    t=json.loads((candidate/'selftest/report.json').read_text(encoding='utf-8'))
    if not t['passed'] or t['host']['host_cases']<1149 or t.get('mutation_controls')!=2:
        raise RuntimeError('missing recorder/receiver/HMI tests')
    for table in ('source_sha256','build_sha256','verification_sha256'):
        if not m.get(table):raise RuntimeError('missing hashes')
        for relative,expected in m[table].items():
            if io.sha(candidate/relative)!=expected:raise RuntimeError('package changed: '+relative)
    for folder,name,build in [('uno','unoq_mcsdk_scalar',NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',NEW[1])]:
        b=json.loads((candidate/'build'/folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        if b['firmware_build_id']!=build:raise RuntimeError('image identity mismatch')
        for artifact in b['artifacts']:
            if io.sha(candidate/'build'/folder/artifact['file'])!=artifact['sha256'].lower():
                raise RuntimeError('image manifest hash mismatch')
    return candidate/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',candidate/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'

def configure():
    # Legacy adapters share this module; explicitly rebind after imports too.
    base.C=C;base.OLD=OLD;base.NEW=NEW;base.GUARD=GUARD
    base.precheck=precheck;base.verify_package=verify_package
configure()
make_remote_installer=base.make_remote_installer
if __name__=='__main__':raise SystemExit(base.main())

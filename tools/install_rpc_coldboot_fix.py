"""Uno-only programming in confirmed J1OFF/DMM<20V/UnoUSB state; no motor commands."""
import json
import install_unoq_bus_display as install
import prepare_rpc_coldboot_fix as p
install.ROOT,install.C,install.OLD,install.NEW=p.ROOT,p.OUT,p.OLD,p.NEW
install.GUARD=install.GUARD.replace('((2026102401,2026102402),(2026102403,2026102402))','((2026102605,2026102604),(2026102607,2026102604))')
assert '2026102607' in install.GUARD
exec(install.GUARD,install.__dict__)
def verify_package():
    c=p.OUT;m=json.loads(p.util.read(c/'manifest.json'))
    assert m['schema']=='mic_ai.rpc_coldboot_fix.v1' and m['pair_compatibility_ids']==list(p.NEW)
    assert m['built'] and m['selftest_pass'] and m['uno_only'] and m['nucleo_firmware_unchanged']
    for k in ('motor_control_changed','thresholds_changed','watchdogs_changed','calibration_changed','uart_command_protocol_changed','i2c_capture_changed'):assert m[k] is False,k
    for table in ('source_sha256','build_sha256','verification_sha256'):
        assert m[table]
        for rel,digest in m[table].items():assert install.io.sha(c/rel)==digest,rel
    b=json.loads(p.util.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    assert b['firmware_build_id']==p.NEW[0]
    for rel,digest in b['library_override_sha256'].items():assert install.io.sha(c/'libraries'/rel)==digest.lower()
    for item in b['artifacts']:assert install.io.sha(c/'build/uno'/item['file'])==item['sha256'].lower()
    assert json.loads(p.util.read(c/'verification/report.json'))['passed']
    assert json.loads(p.util.read(c/'build/uno/llext-check.json'))['pass']
    return c/'build/uno'/b['flash_artifact']
install.verify_package=verify_package
if __name__=='__main__':raise SystemExit(install.main())

"""Install Uno2518 only after explicit physical J1OFF/DMM<20V/USB state."""
import json
import install_unoq_bus_display as install
import prepare_as5600_recovery as package
install.ROOT,install.C=package.ROOT,package.OUT
install.OLD,install.NEW=(2026102517,2026102510),(2026102518,2026102510)
install.GUARD=install.GUARD.replace('((2026102401,2026102402),(2026102403,2026102402))','((2026102517,2026102510),(2026102518,2026102510))')
assert '2026102518' in install.GUARD;exec(install.GUARD,install.__dict__)
def verify_package():
    out=package.OUT;m=json.loads((out/'manifest.json').read_text())
    assert m['schema']=='mic_ai.as5600_recovery.v1' and m['pair_compatibility_ids']==list(install.NEW)
    assert m['built'] and m['selftest_pass'] and m['uno_only'] and m['nucleo_firmware_unchanged']
    for key in ('calibration_changed','thresholds_changed','motor_control_changed','uart_protocol_changed','sd_capture_changed','sensor_feedback_control'):assert m[key] is False,key
    for table in ('source_sha256','build_sha256','verification_sha256'):
        assert m[table]
        for rel,digest in m[table].items():assert install.io.sha(out/rel)==digest,rel
    b=json.loads((out/'build/uno/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'));assert b['firmware_build_id']==2026102518
    for item in b['artifacts']:assert install.io.sha(out/'build/uno'/item['file'])==item['sha256'].lower()
    assert json.loads((out/'offline-checks.json').read_text())['passed']
    assert json.loads((out/'build/uno/llext-check.json').read_text())['pass']
    return out/'build/uno'/b['flash_artifact']
install.verify_package=verify_package
if __name__=='__main__':raise SystemExit(install.main())

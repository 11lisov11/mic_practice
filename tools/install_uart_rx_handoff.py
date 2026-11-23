"""Install Uno RX handoff fix only on the already confirmed discharged USB bench."""
import json
import install_unoq_bus_display as install
import prepare_uart_rx_handoff as package

install.ROOT,install.C=package.ROOT,package.OUT
install.OLD,install.NEW=package.OLD,package.NEW
install.GUARD=install.GUARD.replace(
    '((2026102401,2026102402),(2026102403,2026102402))',
    '((2026102601,2026102602),(2026102603,2026102602))')
assert '2026102603' in install.GUARD
exec(install.GUARD,install.__dict__)


def verify_package():
    out=package.OUT;m=json.loads((out/'manifest.json').read_text())
    assert m['schema']=='mic_ai.uart_rx_handoff.v1' and m['pair_compatibility_ids']==list(package.NEW)
    assert m['built'] and m['selftest_pass'] and m['uno_only'] and m['nucleo_firmware_unchanged']
    for key in ('sensor_feedback_control','motor_control_changed','calibration_changed',
                'thresholds_changed','sd_capture_changed','uart_protocol_changed','watchdogs_changed'):
        assert m[key] is False,key
    for table in ('source_sha256','build_sha256','verification_sha256'):
        assert m[table]
        for rel,digest in m[table].items():assert install.io.sha(out/rel)==digest,rel
    b=json.loads((out/'build/uno/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    assert b['firmware_build_id']==package.NEW[0]
    for item in b['artifacts']:assert install.io.sha(out/'build/uno'/item['file'])==item['sha256'].lower()
    assert json.loads((out/'verification/report.json').read_text())['passed']
    assert json.loads((out/'build/uno/llext-check.json').read_text())['pass']
    return out/'build/uno'/b['flash_artifact']


install.verify_package=verify_package
if __name__=='__main__':raise SystemExit(install.main())

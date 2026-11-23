"""Install verified UNO-only AS5600 diagnostics with the existing USB installer."""
import json
from pathlib import Path
import install_unoq_bus_display as install
import prepare_as5600_i2c_diag as package

install.ROOT = package.ROOT
install.C = package.OUT
install.OLD = (2026102509, 2026102510)
install.NEW = (2026102513, 2026102510)
install.GUARD = install.GUARD.replace(
    '((2026102401,2026102402),(2026102403,2026102402))',
    '((2026102509,2026102510),(2026102513,2026102510))')
assert '2026102513' in install.GUARD
exec(install.GUARD, install.__dict__)


def verify_package():
    out = package.OUT
    m = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    assert m['schema'] == 'mic_ai.as5600_i2c_diag.v1'
    assert m['pair_compatibility_ids'] == list(install.NEW)
    assert m['built'] and m['selftest_pass'] and m['uno_only']
    assert m['nucleo_firmware_unchanged'] and m['source_sha256']
    for name in ('calibration_changed', 'uart_protocol_changed', 'thresholds_changed',
                 'motor_control_changed', 'sd_capture_changed', 'sensor_feedback_control'):
        assert m[name] is False, name
    for rel, digest in m['source_sha256'].items():
        assert install.io.sha(out / rel) == digest, rel
    b = json.loads((out / m['build_manifest']).read_text(encoding='utf-8-sig'))
    assert b['firmware_build_id'] == install.NEW[0]
    for item in b['artifacts']:
        assert install.io.sha(out / 'build/uno' / item['file']) == item['sha256'].lower()
    assert json.loads((out / 'offline-checks.json').read_text())['passed'] is True
    assert json.loads((out / 'build/uno/llext-check.json').read_text())['pass'] is True
    return out / m['flash_artifact']


install.verify_package = verify_package

if __name__ == '__main__':
    raise SystemExit(install.main())

"""Finish the verified filter installation with passive observations only.

The original installer timeout is preserved. This writes a separate completion
report after the operator's cold restart; no MCU reset, flash, CLEAR or START.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import time
import install_sd_break_filter_pair as install
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    a = p.parse_args()
    out = a.outdir.resolve()
    install.verify_package()
    installed = json.loads((out / 'report.json').read_text(encoding='utf-8'))
    assert installed['mcu_flash_commands'] == 2 and installed['hmi_installed']
    assert installed['nucleo_readback_verified'] and installed['uno_readback_verified']
    assert installed['calibration_unchanged'] and installed['calibration_before'] == installed['calibration_after']
    archive = json.loads((out / 'boot_read_after_cold_start/read_only_report.json').read_text(encoding='utf-8'))
    assert archive['pass'] and archive['fresh_uart'] and archive['reply_progress']
    registers = json.loads((out / 'filter_register_verification.json').read_text(encoding='utf-8'))
    assert registers['bkin_filter'] == 9 and registers['break_enabled']
    assert not registers['automatic_output'] and not registers['main_output']
    r = dict(passed=False, read_only=True, motor_commands=0, clear_commands=0,
             flash_commands=0, reset_commands=0, original_installer_timed_out=not installed['pass'],
             samples=[])
    destination = out / 'completion_verification.json'
    if destination.exists():
        raise RuntimeError('preserve existing completion evidence')
    try:
        for local, remote in ((18080, 8080), (12222, 2222)):
            subprocess.run(['adb', '-s', install.io.UNO_SERIAL, 'forward',
                'tcp:' + str(local), 'tcp:' + str(remote)], check=True, capture_output=True)
        install.io.URL = 'http://127.0.0.1:18080'
        for _ in range(16):
            s = install.io.live_status()
            r['samples'].append(s)
            okay, reason = install.precheck(s)
            assert okay, reason
            assert (s['fw_build'], s['mc_fw_build']) == install.NEW
            assert s['mc_fault_current_mask'] in (0, 4) and s['mc_fault_occurred_mask'] in (0, 4)
            assert s['mc_fault'] in (0, 5) and s['mc_fault_reason'] in (0, 8)
            for k in ('mc_transport_fault', 'bp_transport_fault', 'mc_bad', 'mc_bad_integrity',
                      'mc_bad_sequence', 'mc_uart_error_flags', 'uno_rx_dropped', 'uno_tx_short_writes'):
                assert s.get(k) == 0, k
            sd = s['mc_sd_live']
            assert sd['available'] and sd['level'] == 'HIGH' and sd['config_ok']
            assert sd['break_irq_enabled'] and sd['capture_running'] and not sd['first_record_ready']
            assert s['hmi_manual_scalar_supported'] == 1 and s['manual_scalar_capable'] == 1
            assert s['hmi_vbus_hv_calibrated'] == 1
            assert s['mc_break_wave_hex'] == '-' and s['mc_uart_reject_hex'] == '-'
            slots = s['mc_break_snapshots']
            assert len(slots) == 2 and all(x.get('available') and not x.get('captured') for x in slots)
            time.sleep(.8)
        assert r['samples'][-1]['mc_good'] > r['samples'][0]['mc_good']
        remote = '/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi'
        paths = [remote + '/server.py', remote + '/static/app.js', '/home/arduino/.config/mic-ai/vbus_calibration.json']
        ssh = tunneled(ssh_base)('192.168.1.138', 2222, 'arduino', install.ROOT / '.unoq_ssh/id_ed25519',
                                install.ROOT / '.unoq_ssh/known_hosts')
        result = subprocess.run(ssh + [shlex.join(['sha256sum'] + paths)],
            capture_output=True, text=True, timeout=20, check=True)
        actual = [line.split()[0] for line in result.stdout.splitlines()]
        expected = [install.io.sha(install.C / 'web_hmi/server.py'),
                    install.io.sha(install.C / 'web_hmi/static/app.js'), installed['calibration_before']]
        assert actual == expected, 'HMI or calibration hash mismatch'
        r.update(passed=True, hmi_source_sha256=actual[0], hmi_app_js_sha256=actual[1],
                 calibration_sha256=actual[2], calibration_unchanged=True, live_pair=list(install.NEW),
                 sd_filter_readback_verified=True, powered_motor_test_performed=False)
    except Exception as exc:
        r['error'] = str(exc)
    destination.write_text(json.dumps(r, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('passed', 'live_pair', 'calibration_unchanged', 'motor_commands', 'reset_commands', 'error')}))
    return 0 if r['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

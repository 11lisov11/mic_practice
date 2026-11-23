"""Read-only recheck of the installed filter pair; no reset or flash writes."""
import json
import re
import shlex
import subprocess
from pathlib import Path
import install_sd_break_filter_pair as install
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base


def main():
    out = install.ROOT / 'artifacts/live_bench_20261020/sd_break_filter_recheck_r1'
    target = out / 'verification.json'
    if target.exists():
        raise RuntimeError('preserve existing recheck')
    install.verify_package()
    archive = json.loads((out / 'read_only_report.json').read_text(encoding='utf-8'))
    assert archive['pass']
    r = dict(passed=False, flash_writes=0, reset_commands=0, motor_commands=0, clear_commands=0,
             uno_flash_readback_repeated=False)
    try:
        install.io.URL = 'http://127.0.0.1:18080'
        before = install.io.live_status()
        okay, reason = install.precheck(before)
        assert okay, reason
        assert (before['fw_build'], before['mc_fw_build']) == install.NEW
        r['before'] = before
        binary = install.C / 'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin'
        readback = out / 'nucleo_flash_readback.bin'
        connect = [str(install.io.PROGRAMMER), '-c', 'port=SWD', 'mode=HOTPLUG', 'sn=' + install.io.STLINK_SERIAL]
        install.io.run(connect + ['-u', '0x08000000', str(binary.stat().st_size), str(readback)],
                       'nucleo_flash_read_only', out, r, 30)
        assert readback.read_bytes() == binary.read_bytes(), 'Nucleo flash mismatch'
        r.update(nucleo_byte_for_byte_match=True, nucleo_verified_bytes=binary.stat().st_size,
                 nucleo_bin_sha256=install.io.sha(readback))
        log = install.io.run(connect + ['-r32', '0x40012C00', '0x68'], 'tim1_read_only', out, r, 20)
        words = {}
        for m in re.finditer(r'(?m)^(0x[0-9a-fA-F]+) : ([0-9a-fA-F ]+)$', log):
            words.update({int(m[1], 16) + 4*i: int(w, 16) for i, w in enumerate(m[2].split())})
        bdtr, cr1 = words[0x40012c44], words[0x40012c00]
        assert (bdtr >> 16) & 15 == 9 and bdtr & 0x1000 and not bdtr & 0xc000
        assert cr1 & 0x300 == 0x100 and words[0x40012c60] == 0x201
        r.update(bdtr_hex=hex(bdtr), cr1_hex=hex(cr1), bkin_filter=9,
                 break_enabled=True, auto_restart=False, pwm_output_enabled=False)
        subprocess.run(['adb', '-s', install.io.UNO_SERIAL, 'forward', 'tcp:12222', 'tcp:2222'],
                       capture_output=True, check=True)
        ssh = tunneled(ssh_base)('192.168.1.138', 2222, 'arduino', install.ROOT / '.unoq_ssh/id_ed25519',
                                install.ROOT / '.unoq_ssh/known_hosts')
        remote = '/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/'
        paths = [remote + 'server.py', remote + 'static/app.js', '/home/arduino/.config/mic-ai/vbus_calibration.json']
        response = install.io.run(ssh + [shlex.join(['sha256sum'] + paths)], 'live_hmi_calibration_hashes', out, r, 20)
        actual = [x.split()[0] for x in response.splitlines()]
        original = json.loads((install.ROOT / 'artifacts/live_bench_20261020/sd_break_filter_install_usb_r1/report.json').read_text())
        expected = [install.io.sha(install.C / 'web_hmi/server.py'), install.io.sha(install.C / 'web_hmi/static/app.js'), original['calibration_before']]
        assert actual == expected
        uno_log = (install.ROOT / 'artifacts/live_bench_20261020/sd_break_filter_install_usb_r1/verify_uno.log').read_text()
        assert original['uno_readback_verified'] and 'UNO Q loader and sketch verification PASSED' in uno_log
        after = install.io.live_status()
        assert install.precheck(after)[0] and after['mc_good'] > before['mc_good']
        assert (after['fw_build'], after['mc_fw_build']) == install.NEW
        assert all(after.get(k) == 0 for k in ('mc_bad_integrity', 'mc_bad_sequence', 'mc_uart_error_flags', 'mc_transport_fault'))
        assert after['mc_sd_live']['config_ok'] and after['mc_sd_live']['level'] == 'HIGH'
        assert after['hmi_manual_scalar_supported'] == 1 and after['hmi_vbus_hv_calibrated'] == 1
        r.update(passed=True, after=after, live_pair=list(install.NEW), hmi_files_match=True,
                 calibration_unchanged=True, calibration_sha256=actual[2],
                 uno_at_install_flash_readback_passed=True, uno_runtime_identity_matches=True,
                 powered_motor_test_performed=False)
    except Exception as exc:
        r['error'] = str(exc)
    target.write_text(json.dumps(r, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('passed', 'nucleo_byte_for_byte_match', 'nucleo_verified_bytes', 'bkin_filter',
        'uno_at_install_flash_readback_passed', 'uno_runtime_identity_matches', 'hmi_files_match', 'calibration_unchanged', 'error')}))
    return 0 if r['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

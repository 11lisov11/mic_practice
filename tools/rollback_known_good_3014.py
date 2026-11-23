"""Restore the verified 3013/3014 pair on the operator-isolated USB bench.

No START, CLEAR, ARM, or edits to either firmware image. Programming-only guard
uses the explicit disconnected-ribbon/J1/J4-OFF setup: the ADC bus sensor is
unwired and its floating value cannot qualify the physical bus.
"""
import argparse
import hashlib
import json
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import install_current_shunt_monitor as install
import install_research_suite as hmi
import prepare_boot_reset_capture as old
from probe_native_programming_state import programmed_hex_image
from unoq_wifi_hmi_deploy import ssh_base, scp_base
from wifi_stop_tail_probe import parse_registers

ROOT = old.ROOT
OUT = ROOT / 'artifacts/live_bench_20261031/rollback_3013_3014_r1'
CURRENT = ROOT / 'artifacts/live_bench_20261030/observer_trace_r1'
PREVIOUS = (2026103015, 2026103016)
TARGET = (2026103013, 2026103014)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def precheck(s, max_vdc=20):
    """Installation only; applies solely to the confirmed isolated setup."""
    try:
        if max_vdc != 20:
            return False, 'unsupported installer argument'
        if (s['fw_build'], s['mc_fw_build']) not in ((2026103015, 2026103016), (2026103013, 2026103014)):
            return False, 'unexpected pair'
        if s['state'] != 'SAFE' or s['pwm'] != 0 or s.get('hmi_hv_armed') != 0 or int(s['bp_status']) & 0x22:
            return False, 'outputs or RUN request active'
        if s['rpc_schema_version'] != 3 or s['mc_capabilities'] != 1 or s['bp_mcsdk_telemetry'] != 1:
            return False, 'unexpected telemetry contract'
        if not 0 <= s['mc_age_ms'] < 300:
            return False, 'stale controller reply'
        if s.get('mc_last_uart_error_flags', 0) != 0:
            return False, 'recent UART hardware error'
        if any(s.get(k, 0) != 0 for k in ('precharge', 'pfc', 'brake', 'bp_ext')):
            return False, 'service output active'
        return True, 'isolated programming only: operator J1/J4 OFF and ribbon absent; ADC bus input disconnected'
    except (KeyError, TypeError, ValueError, OverflowError):
        return False, 'missing or invalid controller state'


def verify_old_images():
    manifest = json.loads(old.read(old.OUT / 'manifest.json'))
    assert manifest['built'] and manifest['readback_verified']
    successful = json.loads(old.read(old.OUT / 'powered_FOC_boot_capture_20261030_r1/report.json'))
    assert successful['passed'] and successful['physical_rotation_verified']
    assert successful['pair'] == list(TARGET)
    for name, expected in json.loads(old.read(old.OUT / 'source_hashes.json')).items():
        assert digest(old.OUT / name) == expected, name
    for name, expected in manifest['artifacts'].items():
        assert digest(old.OUT / name) == expected, name
    image = old.OUT / 'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'
    assert image.read_bytes() == (old.OUT / 'release/unoq_2026103013_boot_capture.elf-zsk.bin').read_bytes()
    native = old.OUT / 'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
    expected, holes = programmed_hex_image(native, native.with_suffix('.bin').read_bytes())
    evidence = json.loads(old.read(old.OUT / 'installation_verified_r1/report.json'))
    assert hashlib.sha256(expected).hexdigest() == evidence['native_flash_sha256']
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'expected_native_3014.bin').write_bytes(expected)
    (OUT / 'plan.json').write_text(json.dumps(dict(
        target_pair=TARGET, previous_pair=PREVIOUS,
        native_hex_sha256=digest(native), uno_image_sha256=digest(image),
        known_success='FOC5Hz5s, physical rotation confirmed',
        native_expected_sha256=hashlib.sha256(expected).hexdigest(), hex_holes=holes,
        firmware_images_modified=False, motor_commands=0,
        thresholds=dict(current_A=1.35, ADC_ticks=2048, estimate_age_ms=2),
        physical_authorization='User confirmed J1/J4OFF, ribbon absent, USB boards for preceding isolated PWM test; no subsequent physical changes requested',
        ADC_bus_voltage_is_not_available=True,
    ), indent=2), encoding='utf-8')
    return image, native


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--confirm-existing-isolated-usb-bench', action='store_true')
    parser.add_argument('--ssh-openocd', action='store_true', help='Pinned SSH and installed board OpenOCD; no ADB dependency')
    args = parser.parse_args()
    if args.ssh_openocd:
        OUT = OUT.parent / 'rollback_3013_3014_ssh_r2'
    image, native = verify_old_images()
    if args.validate_only:
        print(json.dumps(dict(validated=True, target_pair=TARGET, hardware_commands=0)))
        return 0
    if not args.confirm_existing_isolated_usb_bench:
        parser.error('Existing physical isolation confirmation required')
    assert not (OUT / 'install').exists(), 'Never overwrite an installation attempt'
    install.io.board_ports()
    before = install.io.live_status()
    okay, why = precheck(before)
    assert okay and (before['fw_build'], before['mc_fw_build']) == PREVIOUS, why
    (OUT / 'before.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
    command = [str(install.io.PROGRAMMER), '-c', 'port=SWD', 'mode=HOTPLUG',
               'sn='+install.io.STLINK_SERIAL]
    result = subprocess.run(command + ['-r32', '0x48000000', '40', '-r32', '0x40012c00', '104'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', check=True, timeout=20)
    (OUT / 'gpio_before.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    words = parse_registers(result.stdout)
    # Programming an OFF controller does not require clearing an active SD.
    # Preserve its real level; BKE must stay enabled and MOE must be OFF.
    assert words[0x40012c44] & 4096 and not words[0x40012c44] & 32768
    (OUT / 'programming_pin_state.json').write_text(json.dumps(dict(
        PA6_HIGH=bool(words[0x48000010] & 64), BKE=True, MOE=False,
        active_SD_is_not_motor_START_permission=True, CLEAR_commands=0,
    ), indent=2), encoding='utf-8')
    result = subprocess.run(command + ['-u', '0x20000000', '32768', str(OUT / 'native_RAM_before.bin')],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', check=True, timeout=20)
    (OUT / 'RAM_preservation.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    install.ROOT, install.C, install.OLD, install.NEW = ROOT, old.OUT, PREVIOUS, TARGET
    install.verify_package = lambda: (image, native)
    install.precheck = precheck
    import inspect
    install.GUARD = inspect.getsource(precheck)
    hmi.p = SimpleNamespace(ROOT=ROOT, OUT=old.OUT, NEW=TARGET, OLD=PREVIOUS,
                            read=old.read, write=old.write, once=old.once, sha=digest)
    install.remote_installer = hmi.remote_installer
    original_run = install.io.run
    serial_closed = False

    def serial_route(action, folder, report):
        nonlocal serial_closed
        code = '''import socket,msgpack,json
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(5);s.connect('/var/run/arduino-router.sock');u=msgpack.Unpacker(raw=False)
s.sendall(msgpack.packb([0,1,'$/serial/ACTION',['/dev/ttyHS1']],use_bin_type=True))
while True:
 b=s.recv(65536);assert b;u.feed(b)
 for r in u:
  if r[0]==1 and r[1]==1:
   assert r[2] is None and r[3] is True,r
   print(json.dumps(dict(action='ACTION',ok=True)));raise SystemExit(0)
'''.replace('ACTION', action)
        ssh = install.io.ssh_base('192.168.1.138', 2222, 'arduino', ROOT/'.unoq_ssh/id_ed25519', ROOT/'.unoq_ssh/known_hosts')
        original_run(ssh + ['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(code)],
                     'router_serial_'+action, folder, report, 15)
        serial_closed = action == 'close'

    def run(command, label, folder, report, timeout=240):
        if label == 'flash_uno':
            serial_route('close', folder, report)
        try:
            value = original_run(command, label, folder, report, min(timeout, 90))
        finally:
            if label == 'verify_uno' and serial_closed:
                serial_route('open', folder, report)
        if label == 'flash_verify_nucleo':
            path = folder / 'native_flash_readback.bin'
            original_run([str(install.io.PROGRAMMER), '-c', 'port=SWD', 'mode=HOTPLUG',
                          'sn='+install.io.STLINK_SERIAL, '-u', '0x08000000',
                          str((OUT/'expected_native_3014.bin').stat().st_size), str(path)],
                         'native_independent_readback', folder, report, 20)
            assert path.read_bytes() == (OUT/'expected_native_3014.bin').read_bytes()
        return value

    install.io.run = run
    if args.ssh_openocd:
        return install_ssh(image, native, run, serial_route)
    sys.argv = [sys.argv[0], '--confirm-j1-off-meter-below-20v-both-usb', '--outdir', str(OUT/'install')]
    try:
        code = install.main()
    finally:
        if serial_closed:
            serial_route('open', OUT, {})
    print(json.dumps(dict(installation_exit=code, target_pair=TARGET, START=0, CLEAR=0)))
    return code


def install_ssh(image, native, run, serial_route):
    """Same checked images and Arduino upload scripts, using board GPIO SWD over SSH.

    Do not use /opt/openocd/bin/arduino-flash.sh: that obsolete board script uses
    0x080F0000; this package requires the installed Arduino recipe at 0x08100000.
    """
    folder = OUT / 'install'
    folder.mkdir(exist_ok=False)
    r = dict(passed=False, target_pair=TARGET, transport='pinned SSH + board OpenOCD linuxgpiod',
             uno_flash_commands=0, nucleo_flash_commands=0, motor_commands=0, clear_commands=0,
             thresholds_unchanged=True, old_captures_preserved=True)
    ssh = ssh_base('192.168.1.138', 2222, 'arduino', ROOT/'.unoq_ssh/id_ed25519', ROOT/'.unoq_ssh/known_hosts')
    scp = scp_base('192.168.1.138', 2222, 'arduino', ROOT/'.unoq_ssh/id_ed25519', ROOT/'.unoq_ssh/known_hosts')
    def execute(command, label, timeout=60):
        return run(command, label, folder, r, timeout)
    def safe(pair):
        s = install.io.live_status()
        okay, why = precheck(s)
        assert okay and (s['fw_build'], s['mc_fw_build']) == pair, why
        return s
    def stage(local, suffix):
        remote = prefix + suffix
        execute(scp + [str(local), 'arduino@192.168.1.138:'+remote], 'stage_'+suffix)
        output = execute(ssh+['sha256sum '+shlex.quote(remote)], 'sha256_'+suffix)
        assert output.split()[0] == digest(local), suffix
        return remote
    try:
        install.io.URL = 'http://192.168.1.138:8080'
        install.io.ssh_base = ssh_base
        r['before'] = safe(PREVIOUS)
        r['calibration_before'] = install.io.calibration_hash(folder, r)
        install.io.board_ports()
        prefix = '/tmp/mic_rollback_' + uuid.uuid4().hex + '_'
        installer = folder/'remote_hmi_installer.py'
        helper_source = install.remote_installer()
        # Only the check-only staging probe evaluates the prospective exact pair.
        # The actual deployment below checks the real post-flash pair and leaves
        # the saved record and installed server's calibration checks untouched.
        assert helper_source.count('if not store.is_valid(current):') == 1
        helper_source = helper_source.replace('if not store.is_valid(current):',
            'candidate_status = dict(current)\n'
            '    if args.check_only:\n'
            '        candidate_status.update(fw_build=2026103013, mc_fw_build=2026103014)\n'
            '    if not store.is_valid(candidate_status):')
        installer.write_text(helper_source, encoding='utf-8')
        server = stage(old.OUT/'web_hmi/server.py', 'server.py')
        app = stage(old.OUT/'web_hmi/static/app.js', 'app.js')
        helper = stage(installer, 'installer.py')
        core = Path('C:/Users/USER/AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0')
        loader = stage(core/'firmwares/zephyr-arduino_uno_q_stm32u585xx.elf', 'loader.elf')
        sketch = stage(image, 'sketch.bin')
        flash_cfg = stage(core/'variants/arduino_uno_q_stm32u585xx/flash_sketch.cfg', 'flash.cfg')
        verify_cfg = stage(ROOT/'tools/verify_restart_unoq_sketch.cfg', 'verify.cfg')
        r['loader_sha256'] = digest(core/'firmwares/zephyr-arduino_uno_q_stm32u585xx.elf')
        command = ['python3', helper, '--candidate', server, '--sha256', digest(old.OUT/'web_hmi/server.py'),
                   '--app-js', app, '--app-js-sha256', digest(old.OUT/'web_hmi/static/app.js'),
                   '--max-vdc', '20', '--confirm-mains-off']
        execute(ssh+[shlex.join(command+['--check-only'])], 'hmi_precheck')
        safe(PREVIOUS)
        r['before_flash'] = safe(PREVIOUS)
        r['nucleo_flash_commands'] = 1
        execute([str(install.io.PROGRAMMER), '-c', 'port=SWD', 'mode=UR',
                 'sn='+install.io.STLINK_SERIAL, '-w', str(native), '-v', '-rst'], 'flash_verify_nucleo')
        r['nucleo_readback_verified'] = True
        def ocmd(cfg):
            return ssh+[shlex.join(['/opt/openocd/bin/openocd', '-s', '/opt/openocd',
                        '-s', '/opt/openocd/share/openocd/scripts', '-f', '/opt/openocd/openocd_gpiod.cfg',
                        '-c', 'set filename0 '+loader, '-c', 'set filename1 '+sketch, '-f', cfg])]
        r['uno_flash_commands'] = 1
        execute(ocmd(flash_cfg), 'flash_uno', 90)
        execute(ocmd(verify_cfg), 'verify_uno', 90)
        assert 'UNO Q verification PASSED; restarting unchanged images' in (folder/'verify_uno.log').read_text()
        r['uno_readback_verified'] = True
        # Both MCUs now contain the candidate pair. Its matching server evaluates
        # the live identity, rather than asking an old server to accept new MCUs.
        time.sleep(2)
        execute(ssh+[shlex.join(command)], 'install_hmi')
        r['hmi_installed'] = True
        r['calibration_after'] = install.io.calibration_hash(folder, r)
        assert r['calibration_before'] == r['calibration_after']
        r['calibration_unchanged'] = True
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            try:
                r['after'] = safe(TARGET)
                r['passed'] = True
                break
            except Exception as exc:
                r['last_runtime_error'] = str(exc)
                time.sleep(1)
        if not r['passed']:
            raise RuntimeError('Verified images installed; runtime verification pending: '+r.get('last_runtime_error', ''))
    except Exception as exc:
        r['error'] = str(exc)
    finally:
        # Idempotent route-open also covers an upload error before verification.
        try:
            serial_route('open', folder, r)
        except Exception as exc:
            r['route_restore_error'] = str(exc)
    (folder/'report.json').write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('passed', 'uno_flash_commands', 'nucleo_flash_commands',
                      'uno_readback_verified', 'nucleo_readback_verified', 'calibration_unchanged', 'error')}))
    return 0 if r['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

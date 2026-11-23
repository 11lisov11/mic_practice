"""Install only the HMI server; preserve calibration and MCU firmware."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import py_compile
import signal
import subprocess
import time
import urllib.request


def precheck(s, max_vdc=2, *, lso_verified_idle=False):
    try:
        if type(max_vdc) is not int or max_vdc not in (2, 10):
            return False, 'unreviewed update voltage limit'
        if (s['state'] != 'SAFE' or s['pwm'] != 0 or s['hmi_hv_armed'] != 0
                or s['estop'] != 0 or int(s['bp_status']) & 0x22):
            return False, 'outputs are not disarmed SAFE'
        pair = s['fw_build'], s['mc_fw_build']
        if lso_verified_idle and (
                max_vdc != 10 or pair != (2026112305, 2026112306)
                or s['bp_softstart_ready'] != 0 or s['research_native_valid'] != 1
                or s['research_native_caps'] != 2):
            return False, 'LSO idle and discharged power stage not verified'
        if ((not lso_verified_idle and pair not in (
                (2026100612, 2026100601), (2026100701, 2026100601), (2026100701, 2026100701),
                (2026100702, 2026100601), (2026100702, 2026100701), (2026100702, 2026100702),
                (2026100703, 2026100601), (2026100703, 2026100701),
                (2026100703, 2026100702), (2026100703, 2026100703),
                (2026100704, 2026100601), (2026100704, 2026100701),
                (2026100704, 2026100702), (2026100704, 2026100703), (2026100704, 2026100704),
                (2026100705, 2026100704), (2026100705, 2026100705), (2026100706, 2026100705),
                (2026100707, 2026100707), (2026100708, 2026100707), (2026100708, 2026100708),
                (2026100709, 2026100708), (2026100709, 2026100710), (2026100709, 2026100801),
                (2026100802, 2026100801), (2026100803, 2026100801), (2026100804, 2026100801),
                (2026101001, 2026100801), (2026101002, 2026100801),
                (2026101004, 2026101003), (2026101005, 2026101003), (2026101007, 2026101006),
                (2026101008, 2026101006), (2026101108, 2026101102),
                (2026101507, 2026101506), (2026101703, 2026101702)))
                or s['rpc_schema_version'] != 3 or s['mc_capabilities'] != 1
                or s['bp_mcsdk_telemetry'] != 1 or s['bp_vbus_valid'] != 1):
            return False, 'unsupported measurement contract'
        for key in ('mc_age_ms', 'bp_vbus_age_ms', 'bp_temp_age_ms'):
            age = float(s[key])
            if not math.isfinite(age) or not 0 <= age < 300:
                return False, 'stale telemetry: ' + key
        for key in ('vdc', 'bp_vdc'):
            v = float(s[key])
            if not math.isfinite(v) or not 0 <= v <= max_vdc:
                return False, 'bus not discharged: ' + key
        if not 0 <= int(s['bp_vbus_raw']) <= max_vdc * 10:
            return False, 'bus word is not in the zero-voltage range'
        if (s['bp_temp_valid'] != 1 or s['bp_temp_fault'] != 0
                or not math.isfinite(float(s['bp_temp_c']))
                or s['bp_fault'] not in (0, 5)):
            return False, 'unhealthy controller or temperature protection'
        if any(s[k] != 0 for k in ('precharge', 'pfc', 'brake', 'bp_ext')):
            return False, 'service output active'
        return True, 'discharged, disarmed; no actuation needed'
    except (KeyError, ValueError, TypeError, OverflowError):
        return False, 'missing or invalid telemetry'


def status():
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        'http://127.0.0.1:8080/api/status', timeout=8
    ) as response:
        payload = json.load(response)
    if payload.get('ok') is not True or not isinstance(payload.get('data'), dict):
        raise RuntimeError('HMI status unavailable')
    return payload['data']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--wait-sec', type=int, default=0)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--max-vdc', type=int, choices=(2, 10), default=2)
    parser.add_argument('--confirm-mains-off', action='store_true',
                        help='Required for HMI-only update with auxiliary supply on; never MCU programming')
    parser.add_argument('--lso-verified-idle', action='store_true',
                        help='Require live discharged telemetry from the exact 2305/2306 LSO pair')
    parser.add_argument('--app-js', type=Path)
    parser.add_argument('--app-js-sha256')
    args = parser.parse_args()
    if args.lso_verified_idle and (args.max_vdc != 10 or args.app_js):
        parser.error('LSO idle mode requires the 10-V server-only update path')
    if args.max_vdc == 10 and not (args.confirm_mains_off or args.lso_verified_idle):
        parser.error('auxiliary-only HMI update requires mains-off confirmation')
    if not 0 <= args.wait_sec <= 3600:
        parser.error('wait-sec outside 0..3600')
    root = Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
    calibration = Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
    candidate = args.candidate.resolve(strict=True)
    data = candidate.read_bytes()
    if hashlib.sha256(data).hexdigest() != args.sha256.lower():
        raise RuntimeError('candidate hash mismatch')
    py_compile.compile(str(candidate), doraise=True)
    app_data = None
    if args.app_js:
        app_data = args.app_js.resolve(strict=True).read_bytes()
        if not args.app_js_sha256 or hashlib.sha256(app_data).hexdigest() != args.app_js_sha256.lower():
            raise RuntimeError('app.js hash mismatch')
    spec = importlib.util.spec_from_file_location('candidate_hmi', candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_calibration = calibration.read_bytes()
    store = module.VbusCalibrationStore(str(calibration))
    deadline = time.monotonic() + args.wait_sec
    while True:
        current = status()
        safe, reason = precheck(current, args.max_vdc, lso_verified_idle=args.lso_verified_idle)
        print(json.dumps({'precheck': safe, 'reason': reason,
                          'vdc': current.get('vdc')}), flush=True)
        if safe or time.monotonic() >= deadline:
            break
        time.sleep(10)
    if not safe:
        return 2
    if not store.is_valid(current):
        raise RuntimeError('saved calibration does not match candidate')
    if args.check_only:
        print(json.dumps({'check_only': True, 'calibration_valid': True}))
        return 0
    pid = int(subprocess.check_output(
        ['systemctl', 'show', '-p', 'MainPID', '--value', 'unoq-hmi.service'], text=True
    ).strip())
    restart = subprocess.check_output(
        ['systemctl', 'show', '-p', 'Restart', '--value', 'unoq-hmi.service'], text=True
    ).strip()
    proc = Path('/proc') / str(pid)
    if (pid <= 1 or restart != 'always' or proc.stat().st_uid != os.geteuid()
            or (proc / 'cwd').resolve() != root
            or 'server.py' not in (proc / 'cmdline').read_bytes().decode().split('\0')):
        raise RuntimeError('owned, automatically restarted HMI process not identified')
    target = root / 'server.py'
    previous = target.read_bytes()
    backup = root / 'backups' / ('vbus_reuse_' + time.strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True, exist_ok=False)
    (backup / 'server.py').write_bytes(previous)
    if app_data is not None:
        (backup / 'app.js').write_bytes((root / 'static/app.js').read_bytes())
    # Copy atomically only after the last live safety check. Never change tokens,
    # calibration, startup arguments, or either MCU image.
    safe, reason = precheck(status(), args.max_vdc, lso_verified_idle=args.lso_verified_idle)
    if not safe:
        raise RuntimeError(reason)
    pending = root / 'server.py.vbus-pending'
    pending.write_bytes(data)
    pending.chmod(target.stat().st_mode & 0o777)
    os.replace(pending, target)
    if app_data is not None:
        pending_js = root / 'static/app.js.diag-pending'
        pending_js.write_bytes(app_data)
        pending_js.chmod(0o644)
        os.replace(pending_js, root / 'static/app.js')
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 35
    final = None
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            s = status()
            if (precheck(s, args.max_vdc, lso_verified_idle=args.lso_verified_idle)[0]
                    and s.get('hmi_vbus_hv_calibrated') == 1
                    and int(subprocess.check_output(
                        ['systemctl', 'show', '-p', 'MainPID', '--value', 'unoq-hmi.service'],
                        text=True).strip()) != pid):
                final = s
                break
        except Exception:
            continue
    if final is None:
        raise RuntimeError('HMI installed but final verification failed; backup: ' + str(backup))
    if calibration.read_bytes() != original_calibration:
        raise RuntimeError('calibration record unexpectedly changed')
    if target.read_bytes() != data or (app_data is not None and (root/'static/app.js').read_bytes() != app_data):
        raise RuntimeError('installed HMI files do not match candidate')
    print(json.dumps({'installed': True, 'sha256': args.sha256.lower(),
                      'calibration_unchanged': True, 'calibration_valid': True,
                      'state': final['state'], 'pwm': final['pwm'], 'backup': str(backup),
                      'mc_fw_build': final['mc_fw_build'], 'fw_build': final['fw_build'],
                      'actuation_commands': 0}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

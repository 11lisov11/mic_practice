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


def precheck(s, max_vdc=20):
    """Programming gate only; latched ESTOP/protection need not be cleared.

    Physical mains-off and independent meter confirmation are required by the
    caller. This does not authorize START or overriding any motor protection.
    """
    try:
        if max_vdc != 20: return False, 'unsupported programming threshold'
        if (s['fw_build'],s['mc_fw_build']) not in ((2026102513,2026102510),(2026102515,2026102510)):
            return False,'unexpected firmware pair'
        if s['state']!='SAFE' or s['pwm']!=0 or s['hmi_hv_armed']!=0 or int(s['bp_status'])&0x22:
            return False,'outputs or run request active'
        if s['estop'] not in (0,1): return False,'invalid ESTOP metadata'
        if s['rpc_schema_version']!=3 or s['mc_capabilities']!=1 or s['bp_mcsdk_telemetry']!=1:
            return False,'unexpected measurement contract'
        for key in ('vdc','bp_vdc'):
            if type(s[key]) not in (int,float) or not math.isfinite(s[key]) or not 0<=s[key]<=max_vdc:
                return False,'bus above programming limit: '+key
        for key in ('mc_age_ms','bp_vbus_age_ms','bp_temp_age_ms'):
            if type(s[key]) not in (int,float) or not math.isfinite(s[key]) or not 0<=s[key]<300:
                return False,'stale measurement: '+key
        if s['bp_vbus_valid']!=1 or s['bp_temp_valid']!=1 or s['bp_temp_fault']!=0:
            return False,'invalid measurement or active temperature fault'
        if type(s['bp_vbus_raw']) is not int or not 0<=s['bp_vbus_raw']<=max_vdc*10:
            return False,'raw bus word above programming limit'
        for key in ('mc_uart_error_flags','bp_uart_error_flags'):
            if s[key]!=0: return False,'active UART hardware error: '+key
        # Resetting the Uno while Nucleo stays powered latches its command
        # watchdog. Fresh OFF replies remain usable for programming. Preserve
        # this evidence instead of sending CLEAR just to satisfy an installer.
        reset_timeout=(s.get('mc_transport_fault')==7 and s.get('bp_transport_fault')==7
            and s.get('mc_fault')==2 and s.get('bp_fault')==2
            and s.get('mc_last_bad_reason')==13
            and s.get('mc_last_uart_error_flags')==0)
        # A saved CRC latch need not be CLEARed for reprogramming on the
        # physically deenergized bench. This does not authorize motor START.
        known_crc=(s.get('mc_transport_fault')==2 and s.get('bp_transport_fault')==2
            and s.get('mc_fault') in (1,3) and s.get('bp_fault') in (1,3)
            and s.get('mc_fault_reason')==1 and s.get('mc_last_bad_reason')==1
            and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0
            and s.get('mc_last_uart_error_flags')==0)
        for key in ('mc_transport_fault','bp_transport_fault'):
            if s[key]!=0 and not (reset_timeout or known_crc): return False,'unrecognized transport latch: '+key
        for key in ('precharge','pfc','brake','bp_ext'):
            if s[key]!=0:return False,'service output active: '+key
        return True,'disarmed, fresh low bus; latched protection retained'
    except (KeyError,ValueError,TypeError,OverflowError):
        return False,'invalid or missing programming telemetry'


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
    parser.add_argument('--max-vdc', type=int, choices=(20,), default=20)
    parser.add_argument('--confirm-mains-off', action='store_true',
                        help='Required for HMI-only update with auxiliary supply on; never MCU programming')
    parser.add_argument('--app-js', type=Path)
    parser.add_argument('--app-js-sha256')
    args = parser.parse_args()
    if args.max_vdc == 20 and not args.confirm_mains_off:
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
        safe, reason = precheck(current, args.max_vdc)
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
    safe, reason = precheck(status(), args.max_vdc)
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
            if (precheck(s, args.max_vdc)[0] and s.get('hmi_vbus_hv_calibrated') == 1
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

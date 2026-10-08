"""One operator-authorized production V/f trial over Wi-Fi; always stop."""
import argparse
import getpass
import json
import math
from pathlib import Path
import time

from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import operator_keepalive


def ready(s, faults_allowed=False):
    try:
        return (
            s['state'] == 'SAFE' and s['pwm'] == 0 and s['estop'] == 0
            and s['hmi_hv_armed'] == 0 and s['hmi_arm_profile'] == 'hv'
            and s['hmi_vbus_hv_calibrated'] == 1
            and (s['fw_build'], s['mc_fw_build']) in (
                (2026100707, 2026100707), (2026100708, 2026100708), (2026100709, 2026100708))
            and s.get('mc_diag_valid') == 1
            and s.get('mc_last_bad_valid') == 1
            and s['mode'] == 'VF' and s['mc_capabilities'] == 1
            and s['bp_vbus_valid'] == 1 and s['bp_softstart_ready'] == 1
            and all(math.isfinite(float(s[k])) and 250 <= float(s[k]) <= 360
                    for k in ('vdc', 'bp_vdc'))
            and abs(float(s['bp_vbus_raw']) * .1 - float(s['vdc'])) <= 1
            and all(0 <= float(s[k]) < 300 for k in ('bp_age_ms', 'bp_vbus_age_ms', 'bp_temp_age_ms'))
            and s['bp_temp_valid'] == 1 and s['bp_temp_fault'] == 0
            and math.isfinite(float(s['bp_temp_c'])) and s['bp_temp_c'] < 80
            and not (int(s['bp_status']) & 0x22)
            and all(s[k] == 0 for k in ('precharge', 'pfc', 'brake', 'bp_ext'))
            and (faults_allowed or (s['bp_fault'] == 0 and s['bp_bad'] == 0 and s['bp_bad_cnt'] == 0))
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def outputs_off(s):
    return (s.get('state') == 'SAFE' and s.get('pwm') == 0
            and not (int(s.get('bp_status', 0x22)) & 0x22)
            and 0 <= float(s.get('bp_age_ms', 999999)) < 300)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-operator-ready', action='store_true')
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_operator_ready:
        parser.error('operator readiness and external wired interfaces removed are required')
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    token = getpass.getpass('Control credential (not echoed): ').strip()
    if len(token) < 16:
        raise RuntimeError('missing credential')
    report = {'scope': 'one production HV V/f trial; no analyzer or firmware change',
              'commands': [], 'samples': [], 'pass': False,
              'commanded_frequency_hz': 10, 'requested_observation_s': 3,
              'physical_rotation_verified': False, 'sensor_speed_verified': False,
              'current_telemetry_qualified': False,
              'current_telemetry_note': 'UNO Q local ADC telemetry is not validated Nucleo phase-current telemetry'}
    h = WifiHmi('http://192.168.1.138:8080', token, report['commands'], via_wsl=True)
    try:
        report['before'] = h.status()
        if not ready(report['before'], faults_allowed=True):
            raise RuntimeError('production bus/identity/temperature/idle precheck failed')
        with operator_keepalive(h) as heartbeat:
            h.post('/api/stop-sequence', {'emergency': False}, 'prepare STOP')
            h.command('CLEAR')
            report['after_clear'] = wait_status(h, ready, 5, 'fault-free production SAFE')
            h.command('MODE VF')
            h.command('SET FREQ 10')
            before_arm = h.status()
            if not ready(before_arm) or heartbeat['errors']:
                raise RuntimeError('pre-arm readiness or heartbeat lost')
            runlimit = float(before_arm['hmi_start_runlimit_s'])
            if not math.isfinite(runlimit) or not 0 < runlimit <= 15:
                raise RuntimeError('finite MCU-backed start run limit unavailable')
            report['hmi_start_runlimit_s'] = runlimit
            confirm = before_arm.get('hmi_arm_confirm')
            if confirm != 'ARM 310V':
                raise RuntimeError('unexpected HV confirmation contract')
            h.post('/api/hv-arm', {'action': 'arm', 'confirm': confirm}, 'HV ARM')
            began = time.monotonic()
            report['start_response'] = h.post('/api/start-sequence', {}, 'one-shot START')
            # The endpoint applies its finite run limit before START. Once it
            # confirms RUN, shorten that limit; never increase an existing one.
            h.command('SET RUNLIMIT 3')
            while time.monotonic() - began < 3:
                s = h.status()
                report['samples'].append({'since_start_s': time.monotonic() - began, 'status': s})
                if (s.get('bp_fault') != 0 or s.get('estop') != 0
                        or s.get('pwm') != 1 or not (int(s.get('bp_status', 0)) & 0x20)
                        or s.get('hmi_hv_armed') != 1 or s.get('hmi_vbus_hv_calibrated') != 1
                        or not 250 <= float(s.get('vdc', 0)) <= 360
                        or not 0 <= float(s.get('bp_age_ms', 999999)) < 300
                        or heartbeat['errors']):
                    report['abort_status'] = s
                    report['abort_observations'] = {
                        'controller_fault': s.get('bp_fault'),
                        'controller_bad_count': s.get('bp_bad_cnt'),
                        'pwm': s.get('pwm'), 'state': s.get('state'),
                        'estop': s.get('estop'), 'vdc': s.get('vdc'),
                        'heartbeat_errors': list(heartbeat['errors']),
                        'first_fault_detail': s.get('mc_fault_detail'),
                        'current_note': report['current_telemetry_note'],
                    }
                    raise RuntimeError('trial aborted by live controller/bus/link checks')
                time.sleep(.1)
            report['stop_response'] = h.post('/api/stop-sequence', {'emergency': False}, 'trial STOP')
            report['after_stop'] = wait_status(h, outputs_off, 5, 'confirmed outputs off')
            report['heartbeat'] = heartbeat
            report['pass'] = bool(report['samples']) and report['after_stop']['pwm'] == 0
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        code, response = h.fail_safe_stop()
        report['final_stop'] = {'http': code, 'ok': response.get('ok'), 'error': response.get('error')}
        try:
            report['final_status'] = h.status()
            report['pass'] = report['pass'] and code == 200 and response.get('ok') is True and outputs_off(report['final_status'])
            if not outputs_off(report['final_status']):
                print('OUTPUT OFF NOT CONFIRMED: operator must cut power', flush=True)
        except Exception as exc:
            report['pass'] = False
            report['final_status_error'] = str(exc)
            print('STATUS LOST: operator must cut power', flush=True)
        try:
            (out / 'wifi_logs.txt').write_text(get_wifi_logs(h, token), encoding='utf-8')
        except Exception as exc:
            report['log_error'] = str(exc)
        h.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report.get(k) for k in ('pass', 'error', 'final_stop', 'final_status')}, indent=2), flush=True)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

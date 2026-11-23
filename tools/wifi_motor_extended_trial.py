"""One operator-authorized 15-second V/f trial; retain all samples and always STOP."""
import argparse
import json
import math
from pathlib import Path
import time

from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import operator_keepalive
from wifi_motor_first_start import ready, outputs_off, trial_transport_clean


def owned_previous_stop(s, previous):
    old = previous.get('final_status', {})
    keys = ('fw_build', 'mc_fw_build', 'mc_fault_reason', 'mc_fault_sequence',
            'mc_fault_motor_state', 'mc_fault_current_mask', 'mc_fault_occurred_mask',
            'mc_last_bad_reason', 'mc_uart_error_flags', 'mc_last_uart_error_flags')
    if (previous.get('pass') is not True or previous.get('final_stop', {}).get('ok') is not True
            or not trial_transport_clean(s) or s.get('estop') != 1
            or s.get('bp_fault') != 1 or s.get('mc_fault_reason') != 4
            or s.get('mc_fault_current_mask') != 0 or s.get('mc_fault_occurred_mask') != 0
            or any(s.get(k) != old.get(k) for k in keys)):
        return False
    # Validate the remaining READY conditions without changing the real snapshot.
    return ready(dict(s, estop=0, bp_fault=0, mc_fault_reason=0))


def running_healthy(s):
    try:
        return ((s.get('fw_build'), s.get('mc_fw_build')) == (2026101002, 2026100801)
                and s.get('state') == 'VF_RUN' and s.get('mode') == 'VF'
                and s.get('pwm') == 1 and bool(s['bp_status'] & 0x20)
                and math.isfinite(s['freq']) and 0 <= s['freq'] <= 10.5
                and s.get('freq_cmd') == 10
                and s.get('bp_fault') == 0 and s.get('estop') == 0
                and s.get('hmi_hv_armed') == 1 and s.get('hmi_vbus_hv_calibrated') == 1
                and trial_transport_clean(s)
                and all(math.isfinite(s[k]) and 250 <= s[k] <= 360 for k in ('vdc', 'bp_vdc'))
                and all(0 <= s[k] < 300 for k in ('bp_age_ms', 'bp_vbus_age_ms', 'bp_temp_age_ms'))
                and s.get('bp_temp_valid') == 1 and s.get('bp_temp_fault') == 0
                and math.isfinite(s['bp_temp_c']) and s['bp_temp_c'] < 80
                and all(s.get(k) == 0 for k in ('precharge', 'pfc', 'brake', 'bp_ext')))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-operator-ready', action='store_true')
    parser.add_argument('--previous-trial', type=Path, required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    a = parser.parse_args()
    if not a.confirm_operator_ready:
        parser.error('attended, secured, autonomous stand with no PC/analyzer connections required')
    previous = json.loads(a.previous_trial.read_text())
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    r = {'pass': False, 'commands': [], 'samples': [], 'runlimit_s': 15.0,
         'commanded_frequency_hz': 10.0, 'target_reached': False,
         'sensor_speed_verified': False, 'current_telemetry_qualified': False,
         'scope': 'one attended extended production V/f trial, not full commissioning'}
    h = WifiHmi('http://192.168.1.138:8080', read_token(a.token_file), r['commands'], via_wsl=True)
    try:
        r['before'] = h.status()
        if not (ready(r['before']) or owned_previous_stop(r['before'], previous)):
            raise RuntimeError('not clean SAFE or the exact stop from the authorized previous trial')
        with operator_keepalive(h) as heartbeat:
            h.command('CLEAR')
            r['after_clear'] = wait_status(h, ready, 5, 'clean disarmed production SAFE')
            if r['after_clear'].get('hmi_start_runlimit_s', 0) < 15:
                raise RuntimeError('existing profile cannot permit 15 seconds')
            h.command('MODE VF')
            h.command('SET FREQ 10')
            if not ready(h.status()) or heartbeat['errors']:
                raise RuntimeError('pre-arm readiness changed')
            h.post('/api/hv-arm', {'action': 'arm', 'confirm': 'ARM 310V'}, 'extended HV ARM')
            began = time.monotonic()
            r['start_response'] = h.post('/api/start-sequence', {'runlimit_s': 15.0}, 'bounded 15 s START')
            while time.monotonic() - began < 15:
                s = h.status()
                elapsed = time.monotonic() - began
                r['samples'].append({'since_start_s': elapsed, 'status': s})
                if not running_healthy(s) or heartbeat['errors']:
                    expected_end = (elapsed >= 14.5 and outputs_off(s) and trial_transport_clean(s)
                                    and s.get('mc_fault_reason') in (0, 4)
                                    and s.get('mc_fault_current_mask') == 0
                                    and s.get('mc_fault_occurred_mask') == 0 and not heartbeat['errors'])
                    if expected_end:
                        r['bounded_limit_stop_observed'] = s
                        break
                    r['abort_status'] = s
                    raise RuntimeError('active health/transport/heartbeat gate failed')
                time.sleep(.15)
            r['stop_response'] = h.post('/api/stop-sequence', {'emergency': False}, 'extended trial STOP')
            r['after_stop'] = wait_status(h, outputs_off, 5, 'extended trial outputs off')
            r['post_stop_samples'] = []
            for _ in range(5):
                s = h.status()
                r['post_stop_samples'].append(s)
                if not outputs_off(s) or not trial_transport_clean(s):
                    raise RuntimeError('post-stop outputs or transport unhealthy')
                time.sleep(.2)
            r['heartbeat'] = heartbeat
            active = [x for x in r['samples'] if running_healthy(x['status'])]
            r['target_reached'] = any(x['status']['freq'] >= 9.8 for x in active)
            r['reported_frequency_max_hz'] = max((x['status']['freq'] for x in active), default=0)
            r['target_band_samples'] = sum(x['status']['freq'] >= 9.8 for x in active)
            r['pass'] = bool(active) and not heartbeat['errors']
    except Exception as exc:
        r['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        code, data = h.fail_safe_stop()
        r['final_stop'] = {'http': code, 'ok': data.get('ok') is True}
        try:
            r['final_status'] = h.status()
            r['pass'] = r['pass'] and code == 200 and data.get('ok') is True and outputs_off(r['final_status'])
            if not outputs_off(r['final_status']):
                print('OUTPUTS OFF NOT CONFIRMED: operator cut power', flush=True)
        except Exception as exc:
            r['pass'] = False
            r['final_status_error'] = str(exc)
            print('STATUS LOST: operator cut power', flush=True)
        try:
            (out/'wifi_logs.txt').write_text(get_wifi_logs(h, h.token), encoding='utf-8')
        except Exception as exc:
            r['log_error'] = str(exc)
        h.close()
        (out/'report.json').write_text(json.dumps(r, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: r.get(k) for k in ('pass', 'error', 'target_reached',
          'reported_frequency_max_hz', 'target_band_samples', 'final_stop')}, indent=2))
    return 0 if r['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

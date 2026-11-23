"""One authorized staged current trial; no CLEAR, flash or retry.

Existing online manual mode retains its 3s operator watchdog. An independent
host timer requests STOP within the profile deadline, including startup.
"""
import argparse
import json
from pathlib import Path
import threading
import time

from run_current_shunt_5hz import ROOT, checks, ready, zero_ok, sd_high
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token, get_logs
from wifi_bench_scenarios import operator_keepalive

PROFILES = {'5-10-5': ((5, 8), (10, 8), (5, 12)),
            '10-15-10': ((10, 9), (15, 8), (10, 12)),
            '15-20-15': ((15, 10), (20, 8), (15, 12)),
            '20-25-20': ((20, 11), (25, 8), (20, 12)),
            '25-30-25': ((25, 12), (30, 8), (25, 12)),
            '30-to-50': ((30, 13), (35, 8), (40, 8), (45, 8), (50, 8))}

MEASUREMENT_POLICY = 'full_valid_rms_required'


def measurement_healthy(s):
    return s.get('mc_current_telemetry_valid') == 1


def active(s, target):
    return (checks.physical_ok(s) and checks.transport_clean(s)
        and s.get('state') == 'VF_RUN' and s.get('pwm') == 1
        and s.get('bp_status', 0) & 0x22 == 0x22
        and s.get('mc_fault') == s.get('bp_fault') == 0
        and s.get('mc_fault_current_mask') == s.get('mc_fault_occurred_mask') == 0
        and s.get('estop') == 0 and s.get('hmi_hv_armed') == 1
        and s.get('manual_run_mode') == 1 and s.get('downmode_coast') == 0
        and abs(s.get('freq_cmd', -1) - target) < .01
        and s.get('mc_frequency_reference_valid') == 1
        and zero_ok(s) and sd_high(s, True))


def current_at_target(s, target):
    return (s.get('pwm') == 1 and s.get('mc_current_telemetry_valid') == 1
        and s.get('mc_frequency_reference_valid') == 1
        and abs(s.get('mc_frequency_reference_hz', -1) - target) <= .11
        and s.get('mc_current_window_ms', 0) >= 199
        and not (s.get('mc_current_flags', 0) & 4))


def power_outputs_off(s):
    """STOP returns raw MCU status without HMI annotations; verify power bits."""
    return (s.get('state') == 'SAFE' and s.get('pwm') == 0
        and not (s.get('bp_status', 0x22) & 0x22)
        and 0 <= s.get('mc_age_ms', 999999) < 300)


def outputs_off(s):
    # Final GET /api/status must additionally confirm the HMI arm is revoked.
    return power_outputs_off(s) and s.get('hmi_hv_armed') == 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-powered-ready', action='store_true')
    p.add_argument('--outdir', type=Path, required=True)
    p.add_argument('--profile', choices=tuple(PROFILES), default='5-10-5')
    a = p.parse_args()
    if not a.confirm_powered_ready:
        p.error('Fresh operator authorization and powered autonomous bench required')
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    plan = PROFILES[a.profile]
    targets = [target for target, _ in plan]
    description = ' -> '.join(map(str, targets))+' Hz'
    # Higher initial frequency needs more ramp time before the first plateau.
    host_deadline_s = 60 if a.profile == '30-to-50' else (40 if targets[0] >= 20 else 35)
    r = dict(passed=False, start_commands=0, clear_commands=0, flash_commands=0,
        calibration_writes=0, profile=a.profile, requested_targets_hz=targets, commands=[], samples=[],
        settled_steps=[], collection_errors=[], host_deadline_s=host_deadline_s,
        manual_mode=True, operator_watchdog_s=3, current_scale_qualified=False,
        start_http_timeout_s=12,
        physical_rotation_verified=False,
        measurement_policy=MEASUREMENT_POLICY,
        sd_waveform_limit='Retained pre-START waveform cannot record a second full wave; hardware Break remains enabled.')
    h = WifiHmi('http://192.168.1.138:8080', read_token(str(ROOT/'.unoq_ssh/control_token')), r['commands'], False)
    done = threading.Event()
    expired = threading.Event()
    lock = threading.Lock()
    timer = collector = None
    phase = 0

    def save(name, data):
        (out/name).write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')

    def record(s, source):
        row = dict(source=source, step=phase, host_monotonic_s=time.monotonic(), status=s)
        with lock:
            r['samples'].append(row)
            with (out/'status.jsonl').open('a', encoding='utf-8') as f:
                f.write(json.dumps(row)+'\n')
        return s

    def sample():
        return record(h.status(), 'monitor')

    def collect():
        client = WifiHmi(h.base, h.token, [], False)
        try:
            while not done.is_set():
                try:
                    record(client.status(), 'collector')
                except Exception as exc:
                    r['collection_errors'].append(str(exc))
                done.wait(.15)
        finally:
            client.close()

    def deadline_stop():
        expired.set()
        dispatched = time.monotonic()
        client = WifiHmi(h.base, h.token, [], False)
        try:
            code, body = client.fail_safe_stop()
            r['deadline_stop'] = dict(http=code, ok=body.get('ok'), dispatched_monotonic_s=dispatched)
        finally:
            client.close()

    try:
        s = sample()
        r['before'] = s
        save('before.json', s)
        if not ready(s):
            raise RuntimeError('Preflight failed; no CLEAR or START')
        if (s.get('accel_hz_per_s'), s.get('decel_hz_per_s'), s.get('downmode_coast')) != (5, 1, 0):
            raise RuntimeError('Unexpected ramp settings; no parameter changes')
        with operator_keepalive(h) as heartbeat:
            r['heartbeat'] = heartbeat
            for cmd in ('MODE VF', 'SET FREQ '+str(targets[0])):
                h.command(cmd)
            s = sample()
            if not ready(s) or s.get('freq_cmd') != targets[0] or heartbeat['errors']:
                raise RuntimeError('Preparation failed')
            if s.get('hmi_arm_confirm') != 'ARM 310V':
                raise RuntimeError('Unexpected arm contract')
            h.post('/api/hv-arm', {'action':'arm', 'confirm':'ARM 310V'}, 'ARM single staged current trial')
            collector = threading.Thread(target=collect, daemon=True)
            collector.start()
            began = time.monotonic()
            r['start_monotonic_s'] = began
            timer = threading.Timer(host_deadline_s, deadline_stop)
            timer.daemon = True
            timer.start()
            r['start_commands'] = 1
            # START includes the soft-start wait plus serial confirmation; it
            # can legitimately take longer than the ordinary 8s HTTP deadline.
            # Watchdog and independent host STOP remain active during the wait.
            r['start_response'] = h.post('/api/start-sequence', {'manual':True},
                'single START '+description, timeout_s=12)
            r['start_confirmed_monotonic_s'] = time.monotonic()
            print('START confirmed; recording '+description, flush=True)
            for phase, (target, limit) in enumerate(plan, 1):
                if expired.is_set():
                    raise RuntimeError('Host deadline reached')
                baseline = s.get('mc_current_window_tick_ms')
                if phase > 1:
                    h.command('SET FREQ '+str(target))
                step_began = time.monotonic()
                stable_since = None
                windows = set()
                while True:
                    s = sample()
                    now = time.monotonic()
                    if expired.is_set() or not active(s, target) or heartbeat['errors'] or r['collection_errors']:
                        r['abort_status'] = s
                        raise RuntimeError('Active health changed; STOP without retry')
                    if now-r['start_confirmed_monotonic_s'] > 1.5 and not measurement_healthy(s):
                        r['abort_status'] = s
                        raise RuntimeError('Invalid current telemetry; STOP without retry')
                    if current_at_target(s, target):
                        if stable_since is None:
                            stable_since = now
                        tick = s['mc_current_window_tick_ms']
                        if tick != baseline:
                            windows.add(tick)
                    else:
                        stable_since = None
                        windows.clear()
                    if stable_since is not None and now-stable_since >= 1 and len(windows) >= 2:
                        break
                    if now-step_began > limit:
                        raise RuntimeError('Target/current windows did not settle within step limit')
                    time.sleep(.12)
                r['settled_steps'].append(dict(step=phase, target_hz=target,
                    elapsed_s=now-step_began, distinct_monitor_windows=len(windows),
                    latest_rms_a=s['mc_current_rms_a'], latest_peak_a=s['mc_current_peak_a']))
                r['settled_steps'][-1].update(current_valid=s.get('mc_current_telemetry_valid'),
                    coverage_pct=s.get('mc_current_coverage_pct'),
                    rejected_samples=s.get('mc_current_rejected_samples'),current_flags=s.get('mc_current_flags'))
                save('progress.json', r['settled_steps'])
                print('Settled '+str(target)+' Hz; measurement windows recorded', flush=True)
            r['stop_response'] = h.post('/api/stop-sequence', {'emergency':False}, 'scheduled STOP after '+description)
            r['scheduled_stop_power_outputs_off_confirmed'] = power_outputs_off(r['stop_response'].get('status', {}))
            if r['scheduled_stop_power_outputs_off_confirmed']:
                r['scheduled_stop_confirmed_monotonic_s'] = time.monotonic()
                timer.cancel()
                timer.join(timeout=9)
            r['passed'] = not expired.is_set()
            if not r['passed']:
                r['error'] = 'Host deadline reached before scheduled STOP confirmation'
    except Exception as exc:
        r['error'] = str(exc)
    finally:
        code, body = h.fail_safe_stop()
        r['final_stop'] = dict(http=code, ok=body.get('ok'))
        if timer:
            timer.cancel()
            timer.join(timeout=9)
        done.set()
        if collector:
            collector.join(timeout=9)
        try:
            s = sample()
            if not outputs_off(s):
                r['emergency_stop'] = h.post('/api/stop-sequence', {'emergency':True}, 'emergency STOP after missing OFF confirmation')
                s = sample()
            r['final_status'] = s
            r['outputs_off_confirmed'] = outputs_off(s)
            r['passed'] = (r['passed'] and r['outputs_off_confirmed']
                and code == 200 and body.get('ok') is True and not r.get('deadline_stop'))
        except Exception as exc:
            r['passed'] = False
            r['final_status_error'] = str(exc)
        try:
            time.sleep(2)
            save('after_diagnostics.json', h.status())
            (out/'logs.txt').write_text(get_logs(h.opener, h.base, h.token, .25), encoding='utf-8')
        except Exception as exc:
            r['diagnostic_error'] = str(exc)
        save('report.json', r)
        h.close()
        print(json.dumps({k:r.get(k) for k in ('passed', 'error', 'settled_steps', 'outputs_off_confirmed')}), flush=True)
        if not r.get('outputs_off_confirmed'):
            print('OUTPUT OFF NOT CONFIRMED: operator must switch off power', flush=True)
    return 0 if r['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

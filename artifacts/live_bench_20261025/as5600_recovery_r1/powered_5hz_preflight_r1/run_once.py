"""One authorized CLEAR and five-second trial; retain exact pre-START evidence.

This run's first IRQ predates context publication (context_valid=0). Do not
invent a cached motor context. Qualify only this saved event using direct
MOE-off/START-window bits and the independently observed zero run counter.
All firmware protections and live health predicates remain unchanged.
"""
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
import run_as5600_bounded_5hz as trial
import run_current_shunt_5hz as t
from current_zero_quality import ready as zero_ready
from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi

P = Path(__file__).resolve().parent
OUT = P.parent / 'powered_5hz_r1'
baseline = json.loads((P / 'before_qualification.json').read_text())
first = next(x for x in baseline['mc_break_snapshots'] if x['kind'] == 'first_since_boot')
wave_hash = hashlib.sha256(baseline['mc_break_wave_hex'].encode()).hexdigest()
assert baseline['run_id'] == 0 and first['raw']['context_valid'] == 0
assert first['event']['moe_at_irq'] is False
assert first['event']['during_start_request_window'] is False

def exact_archived_event(s):
    records = {x.get('kind'): x for x in s.get('mc_break_snapshots', [])}
    f = records.get('first_since_boot', {})
    return (hashlib.sha256(s.get('mc_break_wave_hex', '').encode()).hexdigest() == wave_hash
            and f.get('captured') is True and f.get('raw') == first['raw']
            and f.get('event') == first['event']
            and records.get('first_start_window', {}).get('captured') is False)

t.archive_before_start = exact_archived_event
t.zero_ok = zero_ready
t.checks.PAIR = (2026102518, 2026102510)
trial.EXPECTED_SENSOR_MODE = 5
report = {'clear_commands': 0, 'commands': [], 'samples': [],
          'qualified_event_tick_ms': first['raw']['tick_ms'], 'wave_sha256': wave_hash,
          'cached_context_missing': True, 'protection_threshold_changes': 0,
          'capture_preserved': True, 'run_invoked': False}
resume = '--resume-after-clear' in sys.argv
previous_path = P / 'single_clear_report.json'
if previous_path.exists():
    previous = json.loads(previous_path.read_text())
    assert resume and previous['clear_commands'] == 1 and previous['run_invoked'] is False
    report = previous
    report['first_post_clear_observation_error'] = report.pop('error', None)
else:
    assert not resume

def save():
    (P / 'single_clear_report.json').write_text(json.dumps(report, indent=2) + '\n')

assert not OUT.exists(), 'Trial already exists: never repeat automatically'
h = WifiHmi('http://192.168.1.138:8080', read_token(str(ROOT / '.unoq_ssh/control_token')), report['commands'], False)
try:
    for _ in range(0 if resume else 8):
        s = h.status()
        report['samples'].append(s)
        save()
        assert (t.checks.off(s) and t.checks.transport_clean(s) and zero_ready(s)
                and t.sd_high(s, False) and exact_archived_event(s) and trial.setup_ok(s)
                and s['run_id'] == 0 and s['estop'] == 0
                and s['mc_fault'] == s['bp_fault'] == 5 and s['mc_fault_reason'] == 8
                and s['mc_fault_current_mask'] == 0 and s['mc_fault_occurred_mask'] == 1024
                and s['mc_last_bad_reason'] == 0
                and s['enc_bus_ok'] == 1 and s['enc_io_error'] == 0), 'Pre-CLEAR health changed'
        time.sleep(.15)
    if not resume:
        report['clear_commands'] = 1
        save()  # Persist intent before issuing the only CLEAR; never retry.
        report['clear_response'] = h.command('CLEAR')
        save()
    for _ in range(8):
        s = h.status()
        report['samples'].append(s)
        save()
        assert t.ready(s) and trial.setup_ok(s) and s['run_id'] == 0, 'CLEAR did not restore healthy OFF'
        time.sleep(.15)
    report['run_invoked'] = True
    save()
    h.close()
    sys.argv = ['run_as5600_bounded_5hz.py', '--uno-build', '2026102518',
                '--sensor-mode', 'FILTER100', '--confirm-powered-ready', '--outdir', str(OUT)]
    report['trial_exit_code'] = trial.main()
except Exception as exc:
    report['error'] = str(exc)
    print(json.dumps({'error': str(exc), 'clear_commands': report['clear_commands'], 'run_invoked': report['run_invoked']}))
finally:
    save()
    h.close()

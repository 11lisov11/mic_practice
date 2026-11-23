"""Authorized single CLEAR and single MCU-bounded POLL100 trial.

The known pre-START partial UART record is archived before normal CLEAR.
No START unless all existing drive/transport/zero/SD predicates recover.
No predicate overrides, repeated CLEAR, reset, flash, or automatic retry.
"""
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import run_as5600_bounded_5hz as trial
import run_current_shunt_5hz as t
from current_zero_quality import ready as zero_ready
from collect_wifi_telemetry import read_token, get_logs
from run_wifi_nucleo_pwm_bench import WifiHmi

P = Path(__file__).resolve().parent
OUT = P / 'poll100_powered_5hz_r1'
REPORT = P / 'single_clear_poll100_report.json'
assert not REPORT.exists() and not OUT.exists(), 'Never repeat this trial automatically'
t.checks.PAIR = (2026102518, 2026102510)
t.zero_ok = zero_ready
trial.EXPECTED_SENSOR_MODE = 4
r = dict(clear_commands=0, start_commands=0, firmware_writes=0,
         commands=[], samples=[], mode_change_commands=0)

def save():
    REPORT.write_text(json.dumps(r, indent=2) + '\n')

h = WifiHmi('http://192.168.1.138:8080', read_token(str(ROOT / '.unoq_ssh/control_token')), r['commands'], False)

def status():
    s = h.status()
    r['samples'].append(s)
    save()
    return s

def diag(ep, name):
    req = urllib.request.Request(h.base + ep, headers={'X-UNOQ-Control-Token': h.token})
    with h.opener.open(req, timeout=8) as response:
        result = json.load(response)
    assert result.get('ok') is True
    (P / name).write_text(json.dumps(result, indent=2) + '\n')
    return result

try:
    save()
    sd = diag('/api/bkin-trace', 'before_clear_sd_trace.json')
    diag('/api/break-snapshot', 'before_clear_break_snapshot.json')
    uart = diag('/api/uart-reject', 'before_clear_uart_reject.json')['data']
    record = uart['records'][1]
    assert record['tick_ms'] == 116387 and record['reason_code'] == 4
    assert record['length'] == 5 and record['raw_hex'] == 'aa55030000'
    assert uart['records'][0] is None
    assert sd['data']['event_tick_ms'] == 116386 and sd['data']['post_complete'] is True
    assert not any(sd['data'][k] for k in ['dma_error','timeout','sampling_overrun'])
    for _ in range(8):
        s = status()
        assert t.checks.off(s) and zero_ready(s) and t.sd_high(s, False) and t.archive_before_start(s)
        assert s['run_id'] == 0 and s['estop'] == 0
        assert s['mc_transport_fault'] == s['bp_transport_fault'] == 4
        assert s['mc_bad_cnt'] == 31 and s['mc_last_bad_reason'] == 1
        assert s['mc_fault'] == s['bp_fault'] == 3 and s['mc_fault_reason'] == 8
        assert s['mc_fault_current_mask'] == s['mc_fault_occurred_mask'] == 4
        assert all(s.get(k) == 0 for k in t.checks.ERROR_KEYS if k != 'mc_bad_cnt')
        time.sleep(.15)
    r['clear_commands'] = 1
    save()  # Persist before the only CLEAR, so exceptions cannot cause a retry.
    r['clear_response'] = h.command('CLEAR')
    save()
    deadline = time.monotonic() + 6
    while True:
        s = status()
        assert t.checks.off(s) and t.sd_high(s, False) and zero_ready(s)
        if t.ready(s):
            break
        if time.monotonic() > deadline:
            raise RuntimeError('Single CLEAR did not restore every live protection/transport check')
        time.sleep(.2)
    for _ in range(8):
        assert t.ready(status()), 'Health changed after CLEAR; no retry'
        time.sleep(.15)
    r['mode_change_commands'] = 1
    save()
    r['mode_response'] = h.command('ENC BUS POLL100')
    save()
    deadline = time.monotonic() + 6
    while True:
        s = status()
        assert t.ready(s), 'Drive health changed during sensor handover'
        if trial.setup_ok(s) and s['enc_bus_ok'] == 1 and s['enc_io_error'] == 0 and s['enc_age_ms'] < 100:
            break
        if time.monotonic() > deadline:
            raise RuntimeError('POLL100 handover failed')
        time.sleep(.15)
    baseline = s
    for _ in range(8):
        s = status()
        assert t.ready(s) and trial.setup_ok(s)
        assert s['enc_errors'] == baseline['enc_errors'] and s['enc_io_error'] == 0 and s['enc_bus_ok'] == 1
        time.sleep(.15)
    assert s['enc_reads'] > baseline['enc_reads']
    r['run_invoked'] = True
    save()
    h.close()
    sys.argv = ['run_as5600_bounded_5hz.py', '--uno-build', '2026102518',
                '--sensor-mode', 'POLL100', '--confirm-powered-ready', '--outdir', str(OUT)]
    r['trial_exit_code'] = trial.main()
    if (OUT / 'report.json').exists():
        run = json.loads((OUT / 'report.json').read_text())
        r['start_commands'] = run['start_commands']
except Exception as exc:
    r['error'] = str(exc) or type(exc).__name__
    print(json.dumps({'error': r['error'], 'clear_commands': r['clear_commands'], 'start_commands': r['start_commands']}), flush=True)
finally:
    save()
    h.close()

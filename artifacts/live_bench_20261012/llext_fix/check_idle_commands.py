"""One off-only Wi-Fi setpoint check for the installed 1108/1102 pair."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi
from verify_wifi_command_path import safe_off, get_wifi_logs

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--outdir', type=Path, default=Path(__file__).with_name('idle_commands_r1'))
out = p.parse_args().outdir.resolve()
out.mkdir(exist_ok=False)
report = dict(pass_=False, arm_commands=0, start_commands=0, clear_commands=0,
              commands=[], samples=[], hv_release_approved=False)
hmi = WifiHmi('http://192.168.1.138:8080', read_token(str(ROOT / '.unoq_ssh/control_token')),
              report['commands'], False)


def checked():
    s = hmi.status()
    report['samples'].append(s)
    assert safe_off(s), 'Fresh discharged/off state required'
    assert (s['fw_build'], s['mc_fw_build']) == (2026101108, 2026101102)
    assert s['bp_bad'] == s['bp_bad_cnt'] == 0
    return s


began = False
try:
    checked()
    began = True
    for value in (5, 20, 0):
        checked()
        hmi.command(f'SET FREQ {value}')
        assert abs(checked()['freq_cmd'] - value) <= 0.1
    report['pass_'] = True
except Exception as exc:
    report['error'] = f'{type(exc).__name__}: {exc}'
finally:
    if began:
        try:
            code, response = hmi.fail_safe_stop()
            report['stop'] = dict(http=code, ok=response.get('ok'))
            assert code == 200 and response.get('ok') is True
            assert abs(checked()['freq_cmd']) <= 0.1
            (out / 'logs.txt').write_text(get_wifi_logs(hmi, hmi.token), encoding='utf-8')
        except Exception as exc:
            report['pass_'] = False
            report['final_error'] = str(exc)
    hmi.close()
    report['pass'] = report.pop('pass_')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: report.get(k) for k in ('pass', 'stop', 'error', 'final_error')}))
raise SystemExit(0 if report['pass'] else 1)

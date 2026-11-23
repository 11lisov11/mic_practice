"""Install exactly the off-only reviewed Linux logging delta, without MCU writes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_unoq_fault_context_fix import BASE, patched, sha
from verify_wifi_command_path import safe_off
from unoq_wifi_hmi_deploy import fetch_status, ssh_base, scp_base
from uart_update_regression import source_hashes

root = Path(__file__).parent
candidate = root / 'candidate_r2/web_hmi/server.py'
regression = json.loads((root / 'regression_r1/report.json').read_text())
assert regression['pass'] and regression['sources_unchanged_during_tests']
assert regression['source_sha256'] == source_hashes(ROOT), 'Source changed since regression'
assert json.loads((root / 'hmi_guards_r1/report.json').read_text())['pass']
assert candidate.read_text() == patched(BASE.read_text()), 'Unexpected logging delta'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--outdir', type=Path, default=root / 'install_r1')
out = p.parse_args().outdir.resolve()
out.mkdir(exist_ok=False)
rep = dict(pass_=False, start_commands=0, arm_commands=0, clear_commands=0,
           mcu_flash_commands=0, hv_release_approved=False)
ssh = ssh_base('192.168.1.138', 2222, 'arduino', ROOT / '.unoq_ssh/id_ed25519', ROOT / '.unoq_ssh/known_hosts')
scp = scp_base('192.168.1.138', 2222, 'arduino', ROOT / '.unoq_ssh/id_ed25519', ROOT / '.unoq_ssh/known_hosts')
url = 'http://192.168.1.138:8080'
cal = '/home/arduino/.config/mic-ai/vbus_calibration.json'


def check(s):
    assert safe_off(s), 'Fresh discharged, disarmed status required'
    assert (s['fw_build'], s['mc_fw_build']) == (2026101108, 2026101102)
    assert s['rpc_schema_version'] == 3 and s['mc_capabilities'] == 1
    assert s['bp_vbus_valid'] == 1 and s['bp_mcsdk_telemetry'] == 1
    assert all(s[k] == 0 for k in ('bp_bad', 'bp_bad_cnt', 'mc_bad_integrity', 'mc_bad_sequence',
                                  'uno_rx_dropped', 'uno_rx_hw_errors', 'mc_transport_fault'))


def run(command, label):
    result = subprocess.run([str(x) for x in command], capture_output=True, timeout=60)
    (out / (label + '.log')).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(label + ' failed')
    return result.stdout.decode(errors='replace')


try:
    rep['before'] = s = fetch_status(url)
    check(s)
    before_cal = run(ssh + ['sha256sum ' + cal], 'cal_before').split()[0]
    remote = '/home/arduino/mic_fault_history_server.py'
    helper = '/home/arduino/mic_fault_history_install.py'
    run(scp + [candidate, 'arduino@192.168.1.138:' + remote], 'copy_server')
    run(scp + [ROOT / 'tools/recover_unoq_hmi_router_remote.py', 'arduino@192.168.1.138:' + helper], 'copy_helper')
    command = (f'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python {helper}'
               f' --candidate {remote} --sha256 {sha(candidate)} --expected-live-sha256 {sha(BASE)}'
               ' --confirm-mains-j4-off')
    run(ssh + [command + ' --check-only'], 'precheck')
    check(fetch_status(url))
    rep['install'] = json.loads(run(ssh + [command], 'install'))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            rep['after'] = s = fetch_status(url)
            check(s)
            break
        except Exception as exc:
            rep['last_poll_error'] = str(exc)
            time.sleep(1)
    else:
        raise RuntimeError('Post-update live state not verified')
    rep['calibration_unchanged'] = run(ssh + ['sha256sum ' + cal], 'cal_after').split()[0] == before_cal
    rep['server_hash_verified'] = run(ssh + ['sha256sum /home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py'],
                                      'server_after').split()[0] == sha(candidate)
    rep['pass_'] = rep['calibration_unchanged'] and rep['server_hash_verified']
except Exception as exc:
    rep['error'] = f'{type(exc).__name__}: {exc}'
finally:
    rep['pass'] = rep.pop('pass_')
    (out / 'report.json').write_text(json.dumps(rep, indent=2) + '\n')
print(json.dumps({k: rep.get(k) for k in ('pass', 'calibration_unchanged', 'server_hash_verified', 'error')}))
raise SystemExit(0 if rep['pass'] else 1)

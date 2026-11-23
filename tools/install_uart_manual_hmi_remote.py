"""Install ONLY the tested current-pair HMI compatibility fix while drive is stopped.

Runs on Uno Linux over SSH; sends GET requests only. No MCU access or control.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

ROOT = Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
CAL = Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
PAIR = (2026101813, 2026101812)


def digest(b): return hashlib.sha256(b).hexdigest()


def status():
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open('http://127.0.0.1:8080/api/status', timeout=5) as f:
        p = json.load(f)
    assert p.get('ok') is True
    return p['data']


def stopped(s):
    sd = s.get('mc_sd_live', {})
    return ((s.get('fw_build'),s.get('mc_fw_build')) == PAIR
        and s.get('state') == 'SAFE' and s.get('pwm') == 0
        and s.get('hmi_hv_armed') == 0 and s.get('hmi_hv_started') == 0
        and s.get('manual_run_mode') == 0 and s.get('manual_scalar_capable') == 1
        and s.get('hmi_arm_profile') == 'hv' and s.get('hmi_vbus_hv_calibrated') == 1
        and 250 <= s.get('vdc',0) <= 350 and 250 <= s.get('bp_vdc',0) <= 350
        and s.get('bp_softstart_ready') == 1
        and 0 <= s.get('mc_age_ms',99999) < 300
        and 0 <= s.get('bp_temp_age_ms',99999) < 300 and s.get('bp_temp_valid') == 1
        and 0 <= s.get('bp_temp_c',999) < 80
        and all(s.get(k) == 0 for k in ('bp_fault','mc_fault','estop','mc_fault_current_mask',
            'mc_fault_occurred_mask','mc_transport_fault','bp_transport_fault','mc_bad',
            'mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','uno_rx_dropped',
            'precharge','pfc','brake','bp_ext'))
        and not (s.get('bp_status',0x22) & 0x22)
        and sd.get('available') is True and sd.get('level') == 'HIGH'
        and sd.get('config_ok') is True and sd.get('break_irq_enabled') is True
        and sd.get('capture_running') is True and sd.get('first_record_ready') is False
        and s.get('mc_break_wave_hex') == '-' and s.get('mc_uart_reject_hex') == '-'
        and len(s.get('mc_break_snapshots',[])) == 2
        and all(x.get('available') and not x.get('captured') for x in s['mc_break_snapshots']))


def service(key):
    return subprocess.check_output(['systemctl','show','-p',key,'--value','unoq-hmi.service'],text=True).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--expected-old',required=True)
    p.add_argument('--expected-new',required=True)
    a = p.parse_args()
    target = ROOT/'server.py'
    old, new = target.read_bytes(), a.candidate.read_bytes()
    assert digest(old) == a.expected_old and digest(new) == a.expected_new
    oldtree,newtree = ast.parse(old),ast.parse(new)
    oldfn = next(x for x in oldtree.body if isinstance(x,ast.FunctionDef) and x.name=='manual_scalar_supported')
    newfn = next(x for x in newtree.body if isinstance(x,ast.FunctionDef) and x.name=='manual_scalar_supported')
    oldtext = ast.get_source_segment(old.decode(),oldfn)
    newtext = ast.get_source_segment(new.decode(),newfn)
    assert newtext == oldtext.replace('(2026101807,2026101806))','(2026101807,2026101806),(2026101813,2026101812))')
    assert newtext != oldtext
    oldtree.body.remove(oldfn);newtree.body.remove(newfn)
    assert ast.dump(oldtree) == ast.dump(newtree)
    compile(new,str(target),'exec')
    original_cal = CAL.read_bytes()
    assert digest(original_cal) == 'a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17'
    pid = int(service('MainPID'));proc = Path('/proc')/str(pid)
    assert pid > 1 and service('Restart') == 'always'
    assert proc.stat().st_uid == os.geteuid() and (proc/'cwd').resolve() == ROOT
    assert 'server.py' in (proc/'cmdline').read_bytes().decode().split('\0')
    samples = [status() for _ in range(3)]
    assert all(stopped(s) and s.get('hmi_manual_scalar_supported') == 0 for s in samples)
    backup = ROOT/'backups'/('manual_pair_'+time.strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False)
    (backup/'server.py').write_bytes(old)
    (backup/'before.json').write_text(json.dumps(samples[-1],indent=2)+'\n')
    assert stopped(status()) and target.read_bytes() == old
    pending = ROOT/'server.py.manual-pair-pending'
    pending.write_bytes(new);pending.chmod(target.stat().st_mode & 0o777)
    os.replace(pending,target)
    os.kill(pid,signal.SIGTERM)
    deadline = time.monotonic()+40;verified=[]
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            s = status()
            if stopped(s) and s.get('hmi_manual_scalar_supported') == 1 and int(service('MainPID')) != pid:
                verified.append(s)
                if len(verified) >= 3:break
            else:verified=[]
        except (OSError,AssertionError):verified=[]
    assert len(verified) >= 3, 'HMI verification incomplete; keep drive stopped, no auto rollback or start'
    assert CAL.read_bytes() == original_cal and target.read_bytes() == new
    print(json.dumps({'pass':True,'candidate_sha256':digest(new),'calibration_sha256':digest(original_cal),
        'calibration_unchanged':True,'only_compatibility_function_changed':True,'backup':str(backup),
        'old_pid':pid,'new_pid':int(service('MainPID')),'manual_scalar_supported':1,
        'state':verified[-1]['state'],'pwm':verified[-1]['pwm'],'vdc':verified[-1]['vdc'],
        'mcu_flash_commands':0,'mcu_reset_commands':0,'motor_commands':0}))


if __name__ == '__main__':main()

"""Exercise adapted stop classification offline; no network or hardware access."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
from unoq_boot_trial_selftest import status

spec=importlib.util.spec_from_file_location('runner',Path(__file__).with_name('run_trial.py'))
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
ns=runner.load_runner()
s=status();s['hmi_vbus_hv_calibrated']=1
assert ns['active_clean'](s)
assert not ns['active_clean'](dict(s,freq_cmd=6))
assert not ns['active_clean'](dict(s,fw_build=2026101109))
stop=dict(s,estop=1,bp_fault=1,bp_status=13,mc_fault_reason=4,mc_diag_valid=1,
    mc_fault_current_mask=0,mc_fault_occurred_mask=0,mc_last_bad_reason=0,
    hmi_powered_trial_used=1,precharge=0,pfc=0,brake=0,bp_ext=0,freq_cmd=0,
    state='SAFE',pwm=0)
assert ns['expected_runlimit_estop'](3.1,True,stop)
assert not ns['expected_runlimit_estop'](.5,True,stop)
assert not ns['expected_runlimit_estop'](3.1,False,stop)
assert not ns['expected_runlimit_estop'](3.1,True,dict(stop,mc_fault_occurred_mask=0x400))
assert not ns['expected_runlimit_estop'](3.1,True,dict(stop,bp_transport_fault=7))
out=Path(__file__).with_name('runner_selftest.json')
report=dict(pass_=True,cases=8,hardware_commands=0,physical_rotation_verified=False)
report['pass']=report.pop('pass_');out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))

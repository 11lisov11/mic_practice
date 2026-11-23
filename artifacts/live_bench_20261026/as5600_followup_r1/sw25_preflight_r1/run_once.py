"""One SW25 selection with outputs off, idle verification, one bounded START."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools'))
import run_as5600_bounded_5hz as trial
import run_current_shunt_5hz as t
from current_zero_quality import ready as zero_ready
from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi

P=Path(__file__).resolve().parent
OUT=P.parent/'sw25_powered_5hz_r1'
REPORT=P/'report.json'
assert not REPORT.exists() and not OUT.exists(),'Do not repeat automatically'
t.checks.PAIR=(2026102518,2026102510);t.zero_ok=zero_ready
trial.EXPECTED_SENSOR_MODE=2
r=dict(mode_commands=0,start_commands=0,clear_commands=0,firmware_writes=0,commands=[],samples=[],run_invoked=False)
def save():REPORT.write_text(json.dumps(r,indent=2)+'\n')
h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),r['commands'],False)
def sample():
    s=h.status();r['samples'].append(s);save();return s
try:
    s=sample();r['before']=s
    assert t.ready(s) and s['enc_diag_mode']==4 and s['run_id']==5
    assert s['enc_ok']==1 and s['enc_bus_ok']==1 and s['enc_io_error']==0
    r['mode_commands']=1;save()
    r['mode_response']=h.command('ENC BUS SW25');save()
    deadline=time.monotonic()+6
    while True:
        s=sample();assert t.ready(s),'Drive health changed during handover'
        if trial.setup_ok(s) and s['enc_bus_ok']==1 and s['enc_io_error']==0 and s['enc_age_ms']<100:break
        if time.monotonic()>deadline:raise RuntimeError('SW25 did not establish a healthy idle transaction')
        time.sleep(.15)
    baseline=s;r['idle_before']=s;save()
    for _ in range(8):
        s=sample()
        assert t.ready(s) and trial.setup_ok(s) and s['run_id']==5
        assert s['enc_errors']==baseline['enc_errors'] and s['enc_io_error']==0 and s['enc_bus_ok']==1
        assert s['enc_diag_tx_byte']==s['enc_diag_tx_echo']==0x6d and s['enc_diag_tx_bits']==8
        assert s['enc_ok']==1 and (s['enc_status']&0x38)==0x20
        time.sleep(.15)
    assert s['enc_reads']>baseline['enc_reads']
    r['idle_read_delta']=s['enc_reads']-baseline['enc_reads'];r['idle_error_delta']=0
    r['run_invoked']=True;save();h.close()
    sys.argv=['run_as5600_bounded_5hz.py','--uno-build','2026102518',
              '--sensor-mode','SW25','--confirm-powered-ready','--outdir',str(OUT)]
    r['trial_exit_code']=trial.main()
    if (OUT/'report.json').exists():r['start_commands']=json.loads((OUT/'report.json').read_text())['start_commands']
except Exception as exc:
    r['error']=str(exc) or type(exc).__name__;print(json.dumps({k:r.get(k) for k in ['error','mode_commands','start_commands','run_invoked']}),flush=True)
finally:save();h.close()

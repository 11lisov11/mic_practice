"""One normal power-up SD acknowledgement and one authorized 5s trial."""
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools'))
import run_current_shunt_5hz as t
import run_as5600_bounded_5hz as trial
from current_zero_quality import ready as zero_ready
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token

P=Path(__file__).resolve().parent
OUT=P.parent/'poll100_powered_with_j4_r1'
REPORT=P/'single_clear_report.json'
assert not REPORT.exists() and not OUT.exists(),'No automatic repeat'
t.checks.PAIR=(2026102518,2026102510);t.zero_ok=zero_ready
trial.EXPECTED_SENSOR_MODE=4
r=dict(clear_commands=0,start_commands=0,firmware_writes=0,commands=[],samples=[],run_invoked=False)
def save():REPORT.write_text(json.dumps(r,indent=2)+'\n')
h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),r['commands'],False)
def sample():
    s=h.status();r['samples'].append(s);save();return s
try:
    save()
    for ep,name in [('/api/bkin-trace','before_sd_trace.json'),('/api/break-snapshot','before_break_snapshot.json'),('/api/uart-reject','before_uart_reject.json')]:
        req=urllib.request.Request(h.base+ep,headers={'X-UNOQ-Control-Token':h.token})
        with h.opener.open(req,timeout=8) as response:data=json.load(response)
        assert data.get('ok') is True
        (P/name).write_text(json.dumps(data,indent=2)+'\n')
    for _ in range(8):
        s=sample()
        assert (t.checks.off(s) and t.checks.transport_clean(s) and zero_ready(s)
                and t.sd_high(s,False) and t.archive_before_start(s) and trial.setup_ok(s))
        assert s['run_id']==2 and s['estop']==0 and s['run_reason']==2
        assert s['mc_fault']==s['bp_fault']==5 and s['mc_fault_reason']==8
        assert s['mc_fault_current_mask']==0 and s['mc_fault_occurred_mask']==1024
        assert s['enc_errors']==0 and s['enc_bus_ok']==1 and s['enc_io_error']==0
        time.sleep(.15)
    r['clear_commands']=1;save()
    r['clear_response']=h.command('CLEAR');save()
    deadline=time.monotonic()+6
    while True:
        s=sample()
        assert t.checks.off(s) and t.checks.transport_clean(s) and zero_ready(s) and t.sd_high(s,False)
        if t.ready(s):break
        if time.monotonic()>deadline:raise RuntimeError('Single CLEAR did not restore ready; no START')
        time.sleep(.15)
    for _ in range(8):
        s=sample();assert t.ready(s) and trial.setup_ok(s) and s['run_id']==2
        time.sleep(.15)
    r['run_invoked']=True;save();h.close()
    sys.argv=['run_as5600_bounded_5hz.py','--uno-build','2026102518',
              '--sensor-mode','POLL100','--confirm-powered-ready','--outdir',str(OUT)]
    r['trial_exit_code']=trial.main()
    if (OUT/'report.json').exists():r['start_commands']=json.loads((OUT/'report.json').read_text())['start_commands']
except Exception as exc:
    r['error']=str(exc) or type(exc).__name__;print(json.dumps({k:r.get(k) for k in ['error','clear_commands','start_commands','run_invoked']}),flush=True)
finally:save();h.close()

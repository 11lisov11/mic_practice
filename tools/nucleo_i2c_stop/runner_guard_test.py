"""Offline guard checks for the added exact2703/2704 identity. No IO."""
import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_as5600_bounded_5hz as r
c=Path(__file__).resolve().parents[2]/'artifacts/live_bench_20261027/nucleo_i2c_stop_recovery_r1'
s=json.loads((c/'powered_first_fault_5hz_r1/before_preflight.json').read_text())
r.configure(2026102703,'NUCLEO')
assert r.setup_ok(s) and r.capture_ready(s) and not r.t.ready(s)
base=copy.deepcopy(s);base.update(mc_fault=0,bp_fault=0,mc_fault_reason=0,mc_fault_current_mask=0,mc_fault_occurred_mask=0)
base['mc_sd_live']['break_irq_enabled']=True
assert r.t.ready(base) and r.setup_ok(base)
checks=3
for k,v in [('vdc',0),('bp_vdc',351),('mc_age_ms',300),('bp_temp_c',80),('pwm',1),('hmi_hv_armed',1),('estop',1),('mc_transport_fault',7),('mc_fault_current_mask',1024),('mc_fault_occurred_mask',1024),('mc_bad_integrity',1),('mc_bad_sequence',1),('mc_uart_error_flags',4),('uno_rx_dropped',1),('mc_current_zero_ready',0),('mc_fw_build',2026102702)]:
 q=copy.deepcopy(base);q[k]=v;assert not r.t.ready(q),k;checks+=1
for k,v in [('level','LOW'),('break_irq_enabled',False),('config_ok',False),('age_ms',300)]:
 q=copy.deepcopy(base);q['mc_sd_live'][k]=v;assert not r.t.ready(q),k;checks+=1
for k,v in [('enc_source','uno_q_i2c2'),('enc_init_error',7),('enc_diag_cfg_match',0),('mc_fw_build',2026102702)]:
 assert not r.setup_ok(dict(base,**{k:v})),k;checks+=1
for k,v in [('enc_fault_pwm_hex','00'*160),('enc_fault_bad',1),('enc_fault_decode_valid',0)]:assert not r.capture_ready(dict(base,**{k:v}));checks+=1
result=dict(passed=True,checks=checks,hardware_commands=0,synthetic_ready_status=True,change='Host pair admission only; unchanged MCU5000ms/host watchdog and physical/fault gates')
(c/'powered_first_fault_5hz_r1/runner_guards.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))

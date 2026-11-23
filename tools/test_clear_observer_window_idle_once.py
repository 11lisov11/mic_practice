"""Offline negative guards for the one CLEAR; no network or hardware."""
import copy,json,socket
from unittest.mock import patch
import clear_observer_window_idle_once as cmd
def main():
    p=cmd.p;s=json.loads(p.read(p.OUT/'installation_verified_r1/report.json'))['after']
    with patch.object(socket.socket,'connect',side_effect=AssertionError('offline only')):
        cmd.preflight(s);n=0
        cases={'pwm':1,'run_id':1,'hmi_hv_armed':1,'vdc':21,'bp_vdc':21,
            'fw_build':2026111609,'mc_fw_build':2026111606,'uno_rx_hw_errors':3,
            'uno_rx_dropped':1,'mc_transport_fault':4,'mc_bad_cnt':2,'mc_last_bad_reason':12,
            'mc_uart_error_flags':1,'mc_bad_integrity':1,'mc_fault_current_mask':1024,'algorithm_fault':1,
            'precharge':1,'pfc':1,'brake':1,'bp_ext':1}
        for key,value in cases.items():
            b=copy.deepcopy(s);b[key]=value
            try:cmd.preflight(b)
            except AssertionError:n+=1
            else:raise AssertionError('Unsafe CLEAR accepted: '+key)
        for key,value in [('level','LOW'),('config_ok',False),('break_irq_enabled',False)]:
            b=copy.deepcopy(s);b['mc_sd_live'][key]=value
            try:cmd.preflight(b)
            except AssertionError:n+=1
            else:raise AssertionError('SD guard bypassed')
        b=copy.deepcopy(s);b['clear_recovery']={'available':True}
        try:cmd.preflight(b)
        except AssertionError:n+=1
        else:raise AssertionError('Repeated CLEAR accepted')
    print(json.dumps(dict(passed=True,negative_gates=n,hardware_commands=0)))
if __name__=='__main__':main()

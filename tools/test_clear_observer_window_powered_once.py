"""Negative admission cases for powered CLEAR only; no device access."""
import copy,json,socket
from unittest.mock import patch
import clear_observer_window_powered_once as cmd
def main():
    p=cmd.p;s=json.loads(p.read(p.OUT/'powered_before_FOC_20261117_r1/final_status.json'))['data']
    cases={'fw_build':0,'mc_fw_build':0,'state':'RUN','pwm':1,'run_id':1,'hmi_hv_armed':1,
        'vdc':249,'bp_vdc':351,'mc_age_ms':300,'bp_temp_valid':0,'bp_temp_fault':1,'bp_temp_c':80,
        'mc_current_zero_ready':0,'mc_current_zero_stable':2,'algorithm_fault':1,
        'mc_transport_fault':7,'mc_bad_cnt':1,'mc_bad_integrity':1,'mc_bad_sequence':1,
        'uno_rx_hw_errors':1,'uno_rx_dropped':1,'mc_fault_current_mask':1024,
        'mc_fault_occurred_mask':8,'algorithm_fast_cycles':4001,'foc_timing_cases':63,'foc_timing_fault':1}
    n=0
    with patch.object(socket.socket,'connect',side_effect=AssertionError('offline')):
        cmd.off(s)
        for key,value in cases.items():
            b=copy.deepcopy(s);b[key]=value
            try:cmd.off(b)
            except AssertionError:n+=1
            else:raise AssertionError('Unsafe powered CLEAR admitted: '+key)
        for key,value in [('level','LOW'),('config_ok',False)]:
            b=copy.deepcopy(s);b['mc_sd_live'][key]=value
            try:cmd.off(b)
            except AssertionError:n+=1
            else:raise AssertionError('SD guard bypassed')
    print(json.dumps(dict(passed=True,negative_gates=n,hardware_commands=0)))
if __name__=='__main__':main()

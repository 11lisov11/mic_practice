"""Exactly one authorized CLEAR1611/1612. No START/ARM/reset or threshold writes."""
import inspect
import prepare_observer_current_window as p
import clear_recovery_idle_once as prior
from run_foc_boot_capture_trial import decode_boot

def preflight(s,expected_uno_hw_errors=2):
    assert (s.get('fw_build'),s.get('mc_fw_build'))==p.NEW
    assert prior.disarmed(s) and 0<=s.get('vdc',999)<=20 and 0<=s.get('bp_vdc',999)<=20
    assert all(s.get(k)==0 for k in ('precharge','pfc','brake','bp_ext','algorithm_fault',
        'mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence','uno_rx_dropped'))
    # Exact archived installation state, not a wildcard exception for new faults.
    assert expected_uno_hw_errors in (0,2)
    assert s.get('uno_rx_hw_errors')==expected_uno_hw_errors,'UART hardware-error counter changed'
    assert (s.get('mc_transport_fault'),s.get('mc_bad_cnt'),s.get('mc_last_bad_reason'))==(7,1,13)
    assert s.get('mc_fault_current_mask') in (0,4) and s.get('mc_fault_occurred_mask') in (0,4)
    sd=s.get('mc_sd_live') or {}
    assert sd.get('level')=='HIGH' and sd.get('config_ok') is True and sd.get('break_irq_enabled') is True
    assert s.get('clear_recovery',{}).get('available') is False,'First CLEAR already attempted; no repeat'
    decode_boot(s,p.NEW)

def main():
    source=inspect.getsource(prior.main)
    source=source.replace('    a=parser.parse_args();',
        "    parser.add_argument('--expected-uno-hw-errors',type=int,choices=(0,2),default=2)\n    a=parser.parse_args();")
    source=source.replace("before=status('before_CLEAR');preflight(before)",
        "before=status('before_CLEAR');preflight(before,a.expected_uno_hw_errors)")
    source=source.replace("p.OUT/'preserved_capture_hashes.json'","p.OUT/'preserved_all_hashes.json'")
    source=source.replace("('hardware_install_r1','post_install_idle_r1')",
        "('hardware_install_r1','post_install_idle_r1','installation_verified_r1')")
    scope=dict(prior.__dict__,p=p,preflight=preflight)
    exec(compile(source,__file__,'exec'),scope)
    return scope['main']()
if __name__=='__main__':raise SystemExit(main())

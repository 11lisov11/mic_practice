"""Exactly one authorized CLEAR1801/1802 at low bus; never START/ARM/reset."""
import inspect,json
import clear_recovery_idle_once as prior
import prepare_exact_nis_input_release as p
from run_foc_boot_capture_trial import decode_boot


def preflight(s):
    assert (s.get('fw_build'),s.get('mc_fw_build'))==p.NEW
    assert prior.disarmed(s) and 0<=s.get('vdc',999)<20 and 0<=s.get('bp_vdc',999)<20
    assert s.get('bp_vbus_valid')==1 and 0<=s.get('bp_vbus_age_ms',999)<300 and 0<=s.get('mc_age_ms',999)<300
    for k in ('precharge','pfc','brake','bp_ext','algorithm_fault','mc_uart_error_flags',
              'mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence','uno_rx_hw_errors','uno_rx_dropped'):
        assert s.get(k)==0,(k,s.get(k))
    # Exact preserved programming-time latch, not admission for arbitrary faults.
    assert (s.get('mc_transport_fault'),s.get('mc_bad_cnt'),s.get('mc_last_bad_reason'))==(7,1,13)
    assert s.get('mc_fault_current_mask') in (0,4) and s.get('mc_fault_occurred_mask') in (0,4)
    sd=s.get('mc_sd_live') or {}
    assert sd.get('level')=='HIGH' and sd.get('config_ok') is True and sd.get('break_irq_enabled') is True
    assert s.get('clear_recovery',{}).get('available') is False,'CLEAR already exists; never repeat'
    assert s.get('foc_timing_ready') is True and s.get('foc_timing_cases')==64 and s.get('foc_timing_fault')==0
    assert 0<s.get('algorithm_fast_cycles',99999)<=4000
    assert s.get('mc_current_zero_ready')==1 and s.get('mc_current_zero_stable')==3
    assert s.get('observer_trace')==dict(available=False,reason='not_received')
    assert s.get('mc_observer_trace_hex')=='-' and s.get('mc_adc_peak_hex')=='-'
    decode_boot(s,p.NEW)


def main():
    accepted=json.loads(p.read(p.OUT/'installation_acceptance.json'))
    qualified=json.loads(p.read(p.OUT/'OFF_qualification.json'))
    assert accepted['installed'] and accepted['pair']==list(p.NEW)
    assert qualified['OFF_CPU_qualified'] and qualified['OFF_fast_limit_cycles']==4000 and qualified['estimate_age_limit_ms']==2
    # Check complete immutable installation evidence before the one command.
    for rel,h in json.loads(p.read(p.OUT/'installation_files_sha256.json')).items():
        path=p.ROOT/rel[5:] if rel.startswith('ROOT:') else p.OUT/rel
        assert p.sha(path)==h,rel
    source=inspect.getsource(prior.main)
    replacements={
        "p.OUT/'preserved_capture_hashes.json'":"p.OUT/'preserved_inputs_sha256.json'",
        "('hardware_install_r1','post_install_idle_r1')":"('hardware_install_r1','post_install_idle_r1','USB_readiness_r1')",
    }
    for a,b in replacements.items():assert a in source;source=source.replace(a,b)
    scope=dict(prior.__dict__,p=p,preflight=preflight)
    exec(compile(source,__file__,'exec'),scope)
    return scope['main']()


if __name__=='__main__':raise SystemExit(main())

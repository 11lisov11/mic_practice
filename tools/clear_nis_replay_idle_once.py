"""One explicitly authorized CLEAR1713/1714, without START/ARM/reset/flash."""
import inspect
import json
import importlib.util

import clear_recovery_idle_once as prior
import prepare_observer_nis_replay as p
from run_foc_boot_capture_trial import decode_boot

spec=importlib.util.spec_from_file_location('nis_clear_saved_decoder',p.OUT/'web_hmi/server.py')
decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)


def preflight(s):
    assert (s.get('fw_build'),s.get('mc_fw_build'))==p.NEW
    assert prior.disarmed(s) and 0<=s.get('vdc',999)<=20 and 0<=s.get('bp_vdc',999)<=20
    assert s.get('bp_vbus_valid')==1 and s.get('bp_vbus_age_ms',999)<300 and s.get('mc_age_ms',999)<300
    assert all(s.get(k)==0 for k in ('precharge','pfc','brake','bp_ext','algorithm_fault',
        'mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence',
        'uno_rx_hw_errors','uno_rx_dropped'))
    # Exact archived boot-link latch from installation, not arbitrary errors.
    assert (s.get('mc_transport_fault'),s.get('mc_bad_cnt'),s.get('mc_last_bad_reason'))==(7,1,13)
    assert s.get('mc_fault_current_mask') in (0,4) and s.get('mc_fault_occurred_mask') in (0,4)
    sd=s.get('mc_sd_live') or {}
    assert sd.get('level')=='HIGH' and sd.get('config_ok') is True
    if sd.get('break_irq_enabled') is not True:
        # This is CLEAR admission, never START admission. The normal firmware
        # CLEAR restores a latched Break only with SD HIGH; do not demand that
        # restoration has already happened. Preserve/validate the frozen event.
        assert sd.get('first_record_ready') is True
        wave=decoder.dual_sd_wave_status(s)
        assert wave.get('available') is True and wave.get('input_configuration_verified') is True
        assert not any(wave.get(k) for k in ('dma_error','sampling_overrun','run_overflow'))
    assert s.get('clear_recovery',{}).get('available') is False,'A CLEAR already exists; never repeat'
    assert s.get('foc_timing_ready') is True and s.get('foc_timing_cases')==64 and s.get('foc_timing_fault')==0
    assert s.get('mc_current_zero_ready')==1
    assert s.get('observer_trace')==dict(available=False,reason='not_received')
    decode_boot(s,p.NEW)


def main():
    accepted=json.loads(p.read(p.OUT/'installation_acceptance.json'))
    assert accepted['installed'] and accepted['pair']==list(p.NEW)
    source=inspect.getsource(prior.main)
    source=source.replace("p.OUT/'preserved_capture_hashes.json'","p.BASE/'preserved_all_hashes.json'")
    source=source.replace("('hardware_install_r1','post_install_idle_r1')",
        "('hardware_install_r1','post_install_idle_r1','USB_readiness_r1')")
    source=source.replace("operator_state='J1 OFF, both boards PCUSB, J4 ON; wiring unchanged'",
        "operator_state='User requests one CLEAR, no START; unchanged power/wiring; fresh observed low bus and USB, no inferred J1 switch position'")
    scope=dict(prior.__dict__,p=p,preflight=preflight)
    exec(compile(source,__file__,'exec'),scope)
    return scope['main']()


if __name__=='__main__':raise SystemExit(main())

"""One expressly authorized powered CLEAR1611/1612; no START/ARM/reset/flash."""
import inspect,json
import prepare_observer_current_window as p
import clear_observer_window_after_recovery_once as prior
from run_foc_boot_capture_trial import decode_boot
OUT=p.OUT/'one_CLEAR_powered_20261117_r1'

def off(s):
    assert (s['fw_build'],s['mc_fw_build'])==p.NEW
    assert s['state']=='SAFE' and all(s[k]==0 for k in ('pwm','run_id','hmi_hv_armed','precharge','pfc','brake','bp_ext'))
    assert not s['bp_status']&0x22
    assert 250<=s['vdc']<=350 and 250<=s['bp_vdc']<=350
    assert 0<=s['mc_age_ms']<300
    sd=s['mc_sd_live'];assert sd['level']=='HIGH' and sd['config_ok']
    assert s['bp_temp_valid']==1 and s['bp_temp_fault']==0 and s['bp_temp_c']<80
    assert s['mc_current_zero_ready']==1 and s['mc_current_zero_stable']==3
    assert s['algorithm_fault']==0
    assert all(s[k]==0 for k in ('mc_transport_fault','mc_bad_cnt','mc_bad_integrity','mc_bad_sequence',
        'mc_uart_error_flags','mc_last_uart_error_flags','uno_rx_hw_errors','uno_rx_dropped'))
    assert s['mc_fault_current_mask'] in (0,4)
    assert s['mc_fault_occurred_mask'] in (0,4,1024,1028)
    assert s['algorithm_fast_cycles']<=4000 and s['foc_timing_cases']==64 and s['foc_timing_fault']==0
    assert s['foc_runtime']['source']=='OFF_synthetic_CPU_probe' and s['foc_runtime']['first_fault'] is None

def main():
    last=json.loads(p.read(p.OUT/'powered_before_FOC_20261117_r1/final_status.json'))['data']
    expected=decode_boot(last,p.NEW,require_fresh=False)
    def same_session_off(s):
        off(s);b=decode_boot(s,p.NEW)
        assert b['identity']==expected['identity'] and b['Linux_boot_id']==expected['Linux_boot_id']
        assert b['native_tick_ms']>=expected['native_tick_ms']
        assert s['mc_break_wave_hex']==last['mc_break_wave_hex'],'SD evidence changed since powered check'
    source=inspect.getsource(prior.main)
    source=source.replace("prior=p.OUT/'one_CLEAR_idle_r1'","prior=p.OUT/'powered_before_FOC_20261117_r1'")
    source=source.replace("Uno_only_power_cycle_confirmed=True", "operator_state='Both powerbanks, PC/Saleae detached,15V and J1ON; no motor start'")
    source=source.replace('http://127.0.0.1:18080','http://192.168.1.138:8080')
    source=source.replace("('hardware_install_r1','post_install_idle_r1','installation_verified_r1','one_CLEAR_idle_r1')",
        "('hardware_install_r1','post_install_idle_r1','installation_verified_r1','one_CLEAR_idle_r1','one_CLEAR_after_RPC_recovery_r1','autonomous_before_FOC_20261117_r1','powered_before_FOC_20261117_r1')")
    source=source.replace('operator_must_keep_J1_OFF=True', 'operator_must_keep_connections_unchanged=True')
    scope=dict(prior.__dict__,p=p,OUT=OUT,off=same_session_off)
    exec(compile(source,__file__,'exec'),scope);return scope['main']()
if __name__=='__main__':raise SystemExit(main())

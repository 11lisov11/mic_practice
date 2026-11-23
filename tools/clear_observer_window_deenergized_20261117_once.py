"""One authorized CLEAR after Uno powerbank reboot, J1 OFF; never START/ARM."""
import inspect
import prepare_observer_current_window as p
import clear_observer_window_after_recovery_once as prior
OUT=p.OUT/'one_CLEAR_deenergized_after_Uno_boot_20261117_r1'
def off(s):
    assert (s['fw_build'],s['mc_fw_build'])==p.NEW
    assert s['state']=='SAFE' and all(s[k]==0 for k in ('pwm','run_id','hmi_hv_armed','precharge','pfc','brake','bp_ext'))
    assert not s['bp_status']&0x22 and 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20
    assert 0<=s['mc_age_ms']<300
    sd=s['mc_sd_live'];assert sd['level']=='HIGH' and sd['config_ok']
    assert s['algorithm_fault']==0 and s['mc_current_zero_ready']==1
    assert s['mc_current_zero_stable']==3
    assert all(s[k]==0 for k in ('mc_uart_error_flags','mc_last_uart_error_flags','uno_rx_hw_errors','uno_rx_dropped'))
    assert s['mc_transport_fault'] in (0,7)
    assert s['mc_fault_current_mask'] in (0,4)
    assert s['mc_fault_occurred_mask'] in (0,4,1024,1028)
    assert 0<s['algorithm_fast_cycles']<=4000 and s['foc_timing_cases']==64 and s['foc_timing_fault']==0
    cpu=s['foc_runtime'];assert cpu['source']=='OFF_synthetic_CPU_probe' and cpu['first_fault'] is None and cpu['meter_errors']==0

def main():
    src=inspect.getsource(prior.main)
    src=src.replace("prior=p.OUT/'one_CLEAR_idle_r1'", "prior=p.OUT/'one_CLEAR_powered_20261117_r1'")
    src=src.replace('    OUT.mkdir(exist_ok=False)',"    assert not (OUT/'report.json').exists(),'Do not repeat an attempted command'\n    OUT.mkdir(exist_ok=True)")
    src=src.replace('http://127.0.0.1:18080','http://192.168.1.138:8080')
    src=src.replace("('hardware_install_r1','post_install_idle_r1','installation_verified_r1','one_CLEAR_idle_r1')",
        "('hardware_install_r1','post_install_idle_r1','installation_verified_r1','one_CLEAR_idle_r1','one_CLEAR_after_RPC_recovery_r1','autonomous_before_FOC_20261117_r1','powered_before_FOC_20261117_r1','one_CLEAR_powered_20261117_r1')")
    anchor='        baseline=None\n        for i in range(10):'
    wait='''        attempts=[];deadline=time.monotonic()+45
        while True:
            try:
                initial=request('/api/status');assert initial.get('ok')
                break
            except Exception as error:
                attempts.append(dict(error=repr(error),at=time.monotonic()))
                save('startup_attempts.json',attempts)
                if time.monotonic()>=deadline:raise
                time.sleep(1)
        baseline=None
        for i in range(10):'''
    assert anchor in src;src=src.replace(anchor,wait)
    scope=dict(prior.__dict__,p=p,OUT=OUT,off=off)
    exec(compile(src,__file__,'exec'),scope);return scope['main']()
if __name__=='__main__':raise SystemExit(main())

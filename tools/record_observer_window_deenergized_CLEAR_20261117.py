"""Seal the completed single CLEAR and preserve all earlier failed attempts."""
import json
import prepare_observer_current_window as p
from run_foc_boot_capture_trial import decode_boot
def main():
    out=p.OUT/'one_CLEAR_deenergized_after_Uno_boot_20261117_r2'
    r=json.loads(p.read(out/'report.json'));s=json.loads(p.read(out/'final_status.json'))
    before=json.loads(p.read(out/'before_CLEAR.json'))
    assert r['passed'] and r['CLEAR']==1 and r['START']==r['ARM']==r['RESET']==r['flash']==0
    assert r['diagnostic']['result_code']==1 and r['diagnostic']['MOE_at_attempt'] is False
    assert s['state']=='SAFE' and s['pwm']==s['run_id']==s['hmi_hv_armed']==0
    assert not s['bp_status']&0x22
    assert all(s[k]==0 for k in ('mc_fault','bp_fault','mc_fault_current_mask','mc_fault_occurred_mask',
        'mc_transport_fault','mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags',
        'mc_last_uart_error_flags','uno_rx_hw_errors','uno_rx_dropped','algorithm_fault'))
    sd=s['mc_sd_live'];assert sd['level']=='HIGH' and sd['break_irq_enabled'] and sd['config_ok']
    assert s['mc_current_zero_ready']==1 and s['mc_current_zero_stable']==3
    assert s['algorithm_fast_cycles']==3811 and s['foc_timing_cases']==64 and s['foc_timing_fault']==0
    cpu=s['foc_runtime'];assert cpu['source']=='OFF_synthetic_CPU_probe' and cpu['observer_steps']==64
    assert cpu['first_fault'] is None and cpu['meter_errors']==0
    previous_attempts={}
    for name in ('one_CLEAR_powered_20261117_r1','one_CLEAR_deenergized_after_Uno_boot_20261117_r1'):
        old=json.loads(p.read(p.OUT/name/'report.json'));assert old['CLEAR']==0
        previous_attempts[name]=0
    history=json.loads(p.read(out/'preserved_before_sha256.json'))
    for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
    # The old17.7144ms capture remains on disk, independently of the new MCU boot.
    oldwave=p.OUT/'autonomous_before_FOC_20261117_r1/SD_first_boot.bin'
    assert p.sha(oldwave)=='980e1f0676f232a4e867362b7fb346b18b4d6bb21b8fc92a37d2fa1b9bdc7ff4'
    result=dict(passed=True,CLEAR=1,START=0,ARM=0,software_MCU_RESET=0,flash=0,
        prior_unsent_attempts=previous_attempts,one_CLEAR_authorization_consumed=True,
        CLEAR_result='ACK_ACCEPTED',UART_errors_after=0,transport_latch_after=0,
        active_mask_after=0,occurred_mask_after=0,SD='HIGH',Break_IRQ_enabled=True,
        SD_configuration_ok=True,PWM=False,zero_ready=True,zero_stable_blocks=3,
        OFF_fast_cycles=3811,OFF_budget_cycles=4000,estimate_age_limit_ms=2,
        raw_trip_A=1.35,ADC_UPDATE_limit_ticks=2048,source_and_protections_unchanged=True,
        old_files_verified=len(history),old_first_SD_disk_SHA256=p.sha(oldwave),
        pre_CLEAR_fault_masks=[before['mc_fault_current_mask'],before['mc_fault_occurred_mask']],
        fault_masks_already_zero_before_command=True,
        previous_boot_first_SD_in_RAM=before.get('mc_break_wave_hex','-')!='-',
        no_claim_previous_native_RAM_survived_power_change=True,
        current_boot=decode_boot(s,p.NEW,require_fresh=False),
        J1_OFF=True,boards_on_powerbanks=True,current_bus_V=s['vdc'],
        full_powered_FOC_readiness_evaluated=False)
    assert result['pre_CLEAR_fault_masks']==[0,0]
    target=out/'acceptance.json';assert not target.exists();p.write(target,json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    manifest=p.OUT/'manifest.json';(out/'manifest_before_result.json').write_bytes(manifest.read_bytes())
    m=json.loads(p.read(manifest));m.update(remaining_transport_latch=0,idle_UART_recovered=True,
        latest_no_power_CLEAR_recovery_passed=True,latest_CLEAR_result_code=1,FOC_start_ready=False,
        latest_CLEAR_report={target.relative_to(p.OUT).as_posix():p.sha(target)})
    p.write(manifest,json.dumps(m,indent=2)+'\n')
    p.write(out/'acceptance_files_sha256.json',json.dumps({f.name:p.sha(f) for f in out.iterdir() if f.is_file() and f.name!='acceptance_files_sha256.json'},indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('passed','CLEAR','START','active_mask_after','SD','Break_IRQ_enabled','OFF_fast_cycles','old_files_verified')}))
if __name__=='__main__':main()

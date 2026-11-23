"""Record verified install + OFF timing; preserve the strict idle-gate failure."""
import json
import prepare_observer_current_window as p
def main():
    out=p.OUT/'installation_verified_r1';assert not (out/'report.json').exists();out.mkdir(exist_ok=True)
    install=json.loads(p.read(p.OUT/'hardware_install_r1/report.json'))
    idle=json.loads(p.read(p.OUT/'post_install_idle_r1/report.json'))
    assert install['passed'] and install['native_readback_verified'] and install['uno_readback_verified']
    assert install['nucleo_flash_commands']==install['uno_flash_commands']==1
    assert install['calibration_unchanged'] and install['native_BKE'] and not install['native_MOE']
    assert idle['CPU_qualified'] and idle['fast_cycles']==3811 and idle['budget_cycles']==4000
    assert idle['samples']==20 and idle['RPC_stable'] and idle['ordinary_telemetry_fresh']
    assert idle['fresh_link'] and not idle['new_rejected_frames']
    statuses=[json.loads(x)['data'] for x in p.read(p.OUT/'post_install_idle_r1/status_samples.jsonl').splitlines()]
    for s in statuses:
        assert (s['fw_build'],s['mc_fw_build'])==p.NEW
        assert s['state']=='SAFE' and s['pwm']==s['run_id']==s['hmi_hv_armed']==0
        assert not s['bp_status']&0x22 and 0<=s['mc_age_ms']<300 and 0<=s['vdc']<=20
        assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled']
        assert s['mc_sd_live']['config_ok'] and s['mc_current_zero_ready']==1
        assert all(s[k]==0 for k in ('mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity',
            'mc_bad_sequence','uno_rx_dropped','rpc_response_timeouts','rpc_send_timeouts'))
        assert s['uno_rx_hw_errors']==2 # retained count, not new errors
        assert s['mc_transport_fault']==7 and s['mc_bad_cnt']==1 and s['mc_last_bad_reason']==13
    # The original strict report remains failed; no latches are cleared or
    # reinterpreted as START authorization. Installation/OFF are separate facts.
    assert not idle['passed'] and not idle['UART_clean']
    preserved=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
    for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
    m=json.loads(p.read(p.OUT/'manifest.json'))
    for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
    for rel,h in json.loads(p.read(p.OUT/'installation_assets.json')).items():assert p.sha(p.OUT/rel)==h,rel
    report=dict(installed_verified=True,pair=p.NEW,native_readback_verified=True,uno_readback_verified=True,
        native_flash_commands=1,uno_flash_commands=1,additional_native_flash_commands=0,
        START=0,CLEAR=0,ARM=0,manual_RESET=0,programming_recipe_resets=True,
        OFF_CPU_passed=True,OFF_fast_cycles=3811,OFF_fast_budget_cycles=4000,
        OFF_observer_cycles=21512,OFF_cases=64,observer_limit_ms=2,raw_trip_A=1.35,ADC_UPDATE_ticks=2048,
        protections_unchanged=True,current_link_stable=True,new_RPC_UART_errors=0,
        strict_idle_gate_passed=False,motor_start_ready=False,
        remaining_latch=dict(transport_code=7,meaning='UV3_LINK_TIMEOUT',last_bad_reason=13,
            mc_bad_cnt=1,uno_rx_hw_errors=2,stable_in20samples=True,cleared=False,
            initial_UART_error_source_not_independently_proven=True),
        SD='HIGH',BKE=True,BIE=True,MOE=False,zero_ready=True,
        calibration_unchanged=True,preserved_files_verified=len(preserved),
        powered_NIS_fix_not_tested=True,RUN_CPU_under_PWM_not_measured=True,
        programming_reference='IntelHEX-derived image withFF in4 explicitly unprogrammed alignment bytes',
        after=statuses[-1])
    p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    evidence={}
    for folder in ('hardware_install_r1','post_install_idle_r1','installation_preparation_r1','installation_verified_r1'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file() and f.name!='saved_files_sha256.json':evidence[f.relative_to(p.OUT).as_posix()]=p.sha(f)
    p.write(out/'saved_files_sha256.json',json.dumps(evidence,indent=2)+'\n')
    m.update(installed=True,installed_reports={'installation_verified_r1/report.json':p.sha(out/'report.json')},
        OFF_CPU_qualified=True,target_timing_measured_OFF=True,measured_OFF_fast_cycles=3811,
        measured_OFF_observer_cycles=21512,FOC_start_ready=False,strict_idle_gate_passed=False,
        remaining_transport_latch=7,installation_no_motor_commands=True,powered_NIS_root_cause_verified=False)
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('installed_verified','pair','OFF_fast_cycles','OFF_fast_budget_cycles','strict_idle_gate_passed','motor_start_ready','preserved_files_verified')}))
if __name__=='__main__':main()

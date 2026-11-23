"""Record completed readback/OFF qualification evidence; no device access."""
import json
import prepare_exact_profile_budget as p


def main():
    install=json.loads(p.read(p.OUT/'hardware_install_r1/report.json'))
    idle=json.loads(p.read(p.OUT/'post_install_idle_r1/report.json'))
    assert install['passed'] and install['native_readback_verified'] and install['uno_readback_verified']
    assert install['calibration_unchanged'] and idle['native_readback_verified']
    assert idle['passed'] and idle['CPU_qualified'] and idle['fast_cycles']<=4000
    assert idle['START']==idle['CLEAR']==idle['ARM']==idle['RESET']==0
    assert install['uno_flash_commands']==install['nucleo_flash_commands']==1
    for rel,digest in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==digest,rel
    preserved=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
    for rel,digest in preserved.items():assert p.sha(p.ROOT/rel)==digest,rel
    acceptance=dict(programming_passed=True,OFF_CPU_qualification_passed=True,
        pair=list(p.NEW),native_readback_SHA256=idle['native_SHA256'],
        fast_cycles=idle['fast_cycles'],budget_cycles=4000,margin_cycles=4000-idle['fast_cycles'],
        previous_failed_cycles=4229,cases=64,repetitions_per_case=8,
        observer_cycles=idle['native_rows'][-1]['observer_cycles'],
        MOE=False,BKE=True,SD=idle['SD']['level'],calibration_unchanged=True,
        motor_START=0,CLEAR=0,ARM=0,manual_RESET=0,programming_resets_per_recipe=True,
        fresh_link=True,new_rejected_frames=False,UART_flags=idle['uart_flags'][-1],
        saved_transport_latch=idle['transport_latches'][-1],
        saved_fault_mask=idle['saved_fault_mask'],active_fault_mask=idle['active_fault_mask'],
        motor_start_readiness_evaluated=False,powered_FOC_verified=False,
        preserved_files_verified=len(preserved),thresholds_changed=False)
    p.write(p.OUT/'installation_acceptance.json',json.dumps(acceptance,ensure_ascii=False,indent=2)+'\n')
    manifest=p.OUT/'manifest.json';previous=manifest.read_bytes()
    backup=p.OUT/'preinstallation_manifest.json';assert not backup.exists();backup.write_bytes(previous)
    m=json.loads(previous)
    m.update(installed=True,OFF_CPU_qualified=True,target_timing_measured=True,
        target_timing_measured_OFF=True,target_timing_requalification_required=False,
        measured_OFF_fast_cycles=idle['fast_cycles'],measured_CPU_profile_cases=64,
        measured_OFF_observer_cycles=acceptance['observer_cycles'],
        FOC_start_ready=False,full_adapter_under_PWM_measured=False,
        hardware_validated=False,hardware_validation_scope='Image readback and OFF-DWT CPU only',
        hardware_commands=len(install['commands'])+len(list((p.OUT/'post_install_idle_r1').glob('*.log'))),
        hardware_commands_scope='Logged installation subprocesses and passive SWD reads; includes transport/HMI deployment; excludes GET requests',
        START=0,CLEAR=0,ARM=0,RESET=0,manual_RESET=0,programming_resets_per_recipe=True,
        nucleo_flash_commands=1,uno_flash_commands=1,
        calibration_SHA256=install['calibration_after'],preserved_files_verified=len(preserved),
        installation_acceptance_SHA256=p.sha(p.OUT/'installation_acceptance.json'),
        installed_reports={rel:p.sha(p.OUT/rel) for rel in (
            'hardware_install_r1/report.json','post_install_idle_r1/report.json')})
    p.write(manifest,json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(acceptance))


if __name__=='__main__':main()

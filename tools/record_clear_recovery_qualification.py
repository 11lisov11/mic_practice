"""Record independent installation/OFF CPU axes without rewriting a failed idle check."""
import json
import prepare_clear_recovery as p


def main():
    install=json.loads(p.read(p.OUT/'hardware_install_r1/report.json'))
    idle=json.loads(p.read(p.OUT/'post_install_idle_r1/report.json'))
    raw_idle_hash=p.sha(p.OUT/'post_install_idle_r1/report.json')
    assert install['passed'] and install['native_readback_verified'] and install['uno_readback_verified']
    assert install['uno_flash_commands']==install['nucleo_flash_commands']==1
    assert install['calibration_unchanged'] and idle['native_readback_verified']
    assert idle['CPU_qualified'] and 0<idle['fast_cycles']<=4000
    assert idle['START']==idle['CLEAR']==idle['ARM']==idle['RESET']==idle['flash']==0
    assert all(r['BKE'] and not r['MOE'] and not r['running'] and not r['fe_trial_done']
        and r['recorder_empty'] and r['clear_record_empty'] for r in idle['native_rows'])
    assert idle['samples']==20 and idle['fresh_link'] and not idle['new_rejected_frames']
    assert idle['ordinary_telemetry_fresh'] and idle['RPC_stable']
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
    preserved=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
    for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
    ages=idle['current_age_rows']
    acceptance=dict(pair=list(p.NEW),programming_passed=True,OFF_CPU_qualification_passed=True,
        complete_idle_check_passed=idle['passed'],UART_clean=idle['UART_clean'],RPC_stable=idle['RPC_stable'],
        full_protection_readiness_confirmed=False,motor_start_readiness_evaluated=False,
        native_readback_SHA256=idle['native_SHA256'],uno_readback_verified=True,
        fast_cycles=idle['fast_cycles'],budget_cycles=4000,margin_cycles=4000-idle['fast_cycles'],
        observer_cycles=idle['native_rows'][-1]['observer_cycles'],cases=64,repetitions_per_case=8,
        ordinary_telemetry_fresh=True,telemetry_samples=20,
        telemetry_max_age_ms={k:max(row[k] for row in ages) for k in (
            'mc_current_age_ms','mc_current_detail_age_ms','mc_current_quality_age_ms')},
        saved_transport_latch=idle['transport_latches'][-1],bad_frame_count=idle['bad_counts'][-1],
        bad_frame_count_unchanged=True,RPC_guard=idle['rpc_guard'],
        BKE=True,MOE=False,CLEAR_record_empty=True,observer_record_empty=True,
        calibration_unchanged=True,calibration_SHA256=install['calibration_after'],
        motor_START=0,CLEAR=0,ARM=0,manual_RESET=0,programming_resets_per_recipe=True,
        thresholds_changed=False,powered_FOC_verified=False,physical_CLEAR_recovery_verified=False,
        preserved_files_verified=len(preserved),strict_idle_report_SHA256=raw_idle_hash,
        limitation='Programming and OFF timing passed. Saved transport fault remains; no CLEAR or motor readiness approval.')
    target=p.OUT/'installation_acceptance.json';assert not target.exists()
    p.write(target,json.dumps(acceptance,ensure_ascii=False,indent=2)+'\n')
    manifest=p.OUT/'manifest.json';backup=p.OUT/'preinstallation_manifest.json'
    assert not backup.exists();backup.write_bytes(manifest.read_bytes())
    m=json.loads(backup.read_bytes());assert not m['installed']
    m.update(installed=True,OFF_CPU_qualified=True,target_timing_measured=True,target_timing_measured_OFF=True,
        measured_OFF_fast_cycles=idle['fast_cycles'],measured_OFF_observer_cycles=acceptance['observer_cycles'],
        target_timing_requalification_required=False,full_adapter_under_PWM_measured=False,
        FOC_start_ready=False,qualified=False,hardware_validated=False,
        hardware_validation_scope='Readback plus OFF-DWT64x8 only; strict idle check failed on retained transport latch',
        complete_idle_check_passed=idle['passed'],UART_clean=idle['UART_clean'],
        START=0,CLEAR=0,ARM=0,RESET=0,manual_RESET=0,programming_resets_per_recipe=True,
        hardware_commands=len(install['commands'])+len(list((p.OUT/'post_install_idle_r1').glob('*.log'))),
        hardware_commands_scope='Installation subprocesses and passive SWD reads; excludes GET requests',
        nucleo_flash_commands=1,uno_flash_commands=1,calibration_SHA256=install['calibration_after'],
        installation_acceptance_SHA256=p.sha(target),
        installed_reports={rel:p.sha(p.OUT/rel) for rel in ('hardware_install_r1/report.json','post_install_idle_r1/report.json')})
    p.write(manifest,json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    assert p.sha(p.OUT/'post_install_idle_r1/report.json')==raw_idle_hash
    print(json.dumps(acceptance,ensure_ascii=True))


if __name__=='__main__':main()

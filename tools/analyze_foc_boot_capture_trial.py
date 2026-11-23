"""Analyze the completed 3013/3014 run offline; never control hardware."""
import hashlib
import json
import math
import shutil
import prepare_boot_reset_capture as p


def sha(f):
    with f.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    out=p.OUT/'powered_FOC_boot_capture_20261030_r1'
    for rel,digest in json.loads(p.read(out/'saved_files_sha256.json')).items():assert sha(out/rel)==digest,rel
    report=json.loads(p.read(out/'report.json'));s=report['after']
    assert report['passed'] and report['completed_5s'] and report['Uno_limit_done']
    assert report['start_commands']==report['clear_commands']==report['arm_commands']==1
    assert s['state']=='SAFE' and s['pwm']==0 and s['run_elapsed_ms']==5000 and s['run_reason']==1
    assert s['algorithm_fault']==s['mc_fault_current_mask']==s['mc_fault_occurred_mask']==0
    b=report['boot_evidence_audit'];assert b['passed'] and b['native_identity_unchanged'] and b['Linux_identity_unchanged']
    assert b['ADC_firmware_and_CRC_verified'] and report['prior_SD_record_retained']
    adc=s['mc_adc_peak'];samples=adc['samples'];active=[r for r in samples if r['flags']&1]
    assert len(active)==11 and len(samples)==12
    assert all(r['accepted_by_monitor'] and r['epoch_consistent'] and not r['three_leg_window_rejected']
        and not r['publish_deadline_missed'] and not r['pending_epoch_mismatch']
        and r['timer_cnt_at_update']<2048 for r in active)
    assert not samples[-1]['flags']&1 and not samples[-1]['accepted_by_monitor']
    assert s['algorithm_fast_cycles']<5312
    cpu=s['foc_runtime'];assert cpu['first_fault'] is None and cpu['meter_errors']==0
    preserved=json.loads(p.read(p.OUT/'verification/preserved_captures_sha256.json'))
    for rel,digest in preserved.items():assert sha(p.ROOT/rel)==digest,rel
    for rel,digest in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==digest,rel
    analysis=dict(passed=True,trial_pair=list(p.NEW),commanded_electrical_frequency_hz=5,
        supervisor_autostop_ms=5000,supervisor_run_reason=1,
        native_observer_steps=cpu['observer_steps'],ADC_total_frames=adc['total_samples'],
        nominal_PWM_interval_us=2*5312/170,
        estimated_PWM_active_s=(adc['total_samples']-1)*2*5312/170000000,
        duration_note='Uno 5000ms includes START acknowledgement latency; ADC count indicates about4.954s PWM, not exactly5.000s electrical excitation.',
        physical_rotation_reported_by_user=True,user_observation='Да, вращался ровно',
        rotation_is_independently_measured=False,
        boot_unchanged_during_trial=True,boot_before=b['before'],boot_after=b['after'],
        new_boot_between_autonomous_and_powered_preflight=True,
        powered_boot_CSR='0x0C000000',powered_boot_flags=['NRST','BOR'],
        powered_boot_software_flag=False,
        prior_boot_physical_cause_identified=False,
        RMS_last_window_A=s['mc_current_rms_a'],phase_peak_last_window_A=s['mc_current_peak_a'],
        current_scale='nominal shunt0.04ohm/gain2.1/VREF3.3, not independently calibrated',
        current_window_ms=s['mc_current_window_ms'],electrical_period_ms=200,
        current_coverage_percent=s['mc_current_coverage_pct'],
        current_window_covers_full_5Hz_period=s['mc_current_window_ms']>=200,
        current_rejected_samples=s['mc_current_rejected_samples'],
        raw_ADC_1024B_CRC_verified=True,raw_ADC_SHA256=sha(out/'ADC_peak.bin'),
        raw_ADC_ring_active_accepted=len(active),raw_ADC_ring_total=len(samples),
        raw_ADC_last_frame_is_after_outputs_off=True,
        raw_ADC_ring_max_abs_phase_nominal_A=max(abs(v) for r in active for v in r['nominal_currents_a']),
        raw_ADC_ring_max_UPDATE_CNT=max(r['timer_cnt_at_update'] for r in active),
        raw_ADC_trigger_threshold_nominal_A=adc['threshold_nominal_a'],
        raw_ADC_trigger_is_not_control_trip_threshold=True,
        CPU_IRQ=cpu,fast_max_cycles=s['algorithm_fast_cycles'],fast_limit_cycles=5312,
        max_result_age_us=cpu['max_result_age_us'],estimate_limit_us=2000,
        UPDATE_limit=2048,raw_vector_trip_A=1.35,
        UART_RPC_errors_zero=all(s[k]==0 for k in ('mc_bad_integrity','mc_bad_sequence',
            'mc_uart_error_flags','mc_transport_fault','rpc_response_timeouts','rpc_send_timeouts')),
        heartbeat_sent=report['operator_heartbeat']['sent'],heartbeat_error=report['operator_heartbeat']['error'],
        SD_before_preserved=True,old_files_verified=len(preserved),
        actual_commands=dict(START=1,CLEAR=1,ARM=1,RESET=0,flash=0,retries=0),
        protection_thresholds_unchanged=True,one_successful_run_is_not_long_term_qualification=True)
    # Preserve the original tool report before appending the later user observation.
    shutil.copy2(out/'report.json',out/'report_before_operator_observation.json')
    report.update(physical_rotation_verified=True,physical_rotation_evidence='user visual confirmation',
        physical_rotation_response='Да, вращался ровно',analysis_file='analysis.json')
    p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    p.write(out/'analysis.json',json.dumps(analysis,ensure_ascii=False,indent=2)+'\n')
    # Freeze the powered preflight including the stored startup SD before CLEAR.
    pre=p.OUT/'powered_before_FOC_boot_r1'
    p.write(pre/'saved_files_sha256.json',json.dumps({f.name:sha(f) for f in pre.iterdir()
        if f.is_file() and f.name!='saved_files_sha256.json'},indent=2)+'\n')
    p.write(out/'saved_files_sha256.json',json.dumps({f.name:sha(f) for f in out.iterdir()
        if f.is_file() and f.name!='saved_files_sha256.json'},indent=2)+'\n')
    print(json.dumps(dict(passed=True,auto_stop_ms=5000,estimated_PWM_active_s=analysis['estimated_PWM_active_s'],
        RMS_last_window_A=analysis['RMS_last_window_A'],old_files_verified=len(preserved),boot_unchanged=True)))


if __name__=='__main__':main()

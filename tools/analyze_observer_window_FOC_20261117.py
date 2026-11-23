"""Saved hardware records only: CRC, timings, nominal currents and NIS comparison."""
import ast,json,math
import prepare_observer_current_window as p
from configure_multi_algorithm import crc32c
OUT=p.OUT/'FOC_5Hz_20261117_r1'
OLD=p.ROOT/'artifacts/live_bench_20261116/rpc_hmi_admission_r1/FOC_trial_r1'
def load(folder,name):return json.loads(p.read(folder/name))
def write(name,obj):p.write(OUT/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def main():
    for folder,manifest in ((OUT,'saved_files_sha256.json'),(OLD,'analysis_files_sha256.json')):
        for rel,h in load(folder,manifest).items():assert p.sha(folder/rel)==h,rel
    for rel,h in load(p.OUT,'preserved_all_hashes.json').items():assert p.sha(p.ROOT/rel)==h,rel
    r=load(OUT,'report.json');s=load(OUT,'final_status.json');t=load(OUT,'observer_trace_decoded.json')
    old=load(OLD,'observer_trace_decoded.json');old_s=load(OLD,'final_status.json')
    assert r['passed'] and r['start_commands']==r['clear_commands']==r['arm_commands']==1
    assert r['completed_5s'] and r['Uno_limit_done'] and s['run_elapsed_ms']==5000 and s['run_reason']==1
    assert s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==0 and not s['bp_status']&0x22
    assert all(s[k]==0 for k in ('mc_fault_current_mask','mc_fault_occurred_mask','algorithm_fault','mc_transport_fault',
        'mc_bad_integrity','mc_bad_sequence','rpc_response_timeouts','rpc_send_timeouts'))
    assert r['boot_evidence_audit']['passed'] and r['boot_evidence_audit']['native_identity_unchanged']
    assert (OUT/'SD_before.bin').read_bytes()==(OUT/'SD_after.bin').read_bytes()
    assert (OUT/'SD_before.bin').read_bytes()==(p.OUT/'powered_before_FOC_20261117_r2/SD_before_CLEAR.bin').read_bytes()
    decoder=next(n for n in ast.parse(p.read(p.OUT/'web_hmi/server.py')).body if isinstance(n,ast.FunctionDef) and n.name=='decode_adc_peak_hex')
    scope={'current_crc32c':crc32c};exec(compile(ast.Module(body=[decoder],type_ignores=[]),'installed_ADC_decoder','exec'),scope)
    adc=scope['decode_adc_peak_hex']((OUT/'ADC_peak.bin').read_bytes().hex(),p.NEW[1]);write('ADC_decoded.json',adc)
    assert all(x['accepted_by_monitor'] and x['epoch_consistent'] and not x['publish_deadline_missed'] for x in adc['samples'])
    assert adc['observer_validity_trigger']
    for x in t['samples']+[t['first_loss']]:
        assert x['window_count']==16 and 0<x['forecast_dt_s']<.001
        assert math.isclose(sum(e*e/v for e,v in zip(x['innovation_A'],x['innovation_variance_A2'])),x['nis'],rel_tol=2e-6)
    runtime=load(OUT,'CPU_IRQ_and_first_fault.json');assert runtime['first_fault'] is None and runtime['max_result_age_us']<2000
    assert runtime['meter_errors']==0 and s['algorithm_fast_cycles']<5312
    before=load(OUT,'before_START.json');assert before['algorithm_fast_cycles']==3811
    assert before['foc_runtime']['source']=='OFF_synthetic_CPU_probe' and before['foc_timing_cases']==64
    observation=dict(physical_rotation_verified=True,operator_report='Да, вращался ровно',
        applies_only_to='FOC_5Hz_20261117_r1/run_id1',independent_speed_sensor=False,
        original_runner_report_not_rewritten=True)
    assert not (OUT/'operator_observation.json').exists();write('operator_observation.json',observation)
    def stats(v):
        return dict(total=v['total_observer_samples'],valid=v['valid_samples'],invalid=v['invalid_samples'],
            valid_percent_all_steps=100*v['valid_samples']/v['total_observer_samples'],
            warmup_invalid_steps=499,eligible_steps=v['total_observer_samples']-499,
            valid_percent_after_warmup=100*v['valid_samples']/(v['total_observer_samples']-499),
            first_loss_step=v['first_loss']['steps'],first_loss_NIS=v['first_loss']['nis'],
            final_NIS=v['samples'][-1]['nis'],final_estimated_rpm=v['samples'][-1]['rpm_est'])
    effective=t['first_loss']['observation_cycles'];end=t['first_loss']['observer_adc_cycles']
    result=dict(passed=True,hardware_commands_added_by_analysis=0,physical_rotation=observation,
        auto_stop_ms=5000,Uno_auto_stop_confirmed=True,native_auto_stop_flag_set=r['native_done'],
        native_auto_stop_not_reached_before_Uno_stop=not r['native_done'],PWM=False,final_fault_masks=[0,0],
        raw_ADC_bytes=1024,raw_observer_bytes=1888,raw_ADC_CRC_peer_verified=True,observer_CRC_peer_verified=True,
        SD_before_after_identical=True,SD_SHA256=p.sha(OUT/'SD_before.bin'),
        nominal_RMS_last_window_A=s['mc_current_rms_a'],nominal_peak_last_window_A=s['mc_current_peak_a'],
        last_current_window_ms=s['mc_current_window_ms'],coverage_pct=s['mc_current_coverage_pct'],
        last_window_covers_full_electrical_period=s['mc_current_window_ms']>=200,
        physical_current_scale_independently_qualified=False,whole_run_current_peak_not_recorded_by_last_window=True,
        NIS_before=stats(old),NIS_after=stats(t),
        NIS_threshold=25,NIS_problem_fully_solved=False,NIS_max_whole_run_not_available=True,
        comparisons_are_separate_runs_not_controlled_causal_identification=True,
        actual_mechanical_speed_not_independently_measured=True,
        OFF_kernel_cycles=3811,OFF_budget_cycles=4000,
        RUN_full_path_max_cycles=s['algorithm_fast_cycles'],RUN_existing_deadline_cycles=5312,
        RUN_full_path_not_within_4000=s['algorithm_fast_cycles']>4000,
        max_result_age_us=runtime['max_result_age_us'],estimate_limit_us=2000,
        observer_max_wall_us=runtime['max_wall_us'],observer_max_CPU_upper_us=runtime['max_cpu_upper_us'],
        raw_ADC_accepted_rows=len(adc['samples']),raw_ADC_max_UPDATE_CNT=max(x['timer_cnt_at_update'] for x in adc['samples']),
        UPDATE_limit_ticks=2048,raw_current_trip_A=1.35,all_limits_unchanged=True,
        earliest_saved_ADC_after_effective_mean_us=((adc['samples'][0]['cycles']-effective)&0xffffffff)/170,
        earliest_saved_ADC_after_endpoint_us=((adc['samples'][0]['cycles']-end)&0xffffffff)/170,
        limitation='Raw12 ADC rows follow the observer-input window; they do not contain all16 raw samples that formed its mean. Final NIS is not maximum NIS. Nominal RMS uses only178ms, less than a5Hz period.')
    write('analysis.json',result)
    assert all(p.sha(OUT/f)==h for f,h in load(OUT,'saved_files_sha256.json').items())
    write('analysis_files_sha256.json',{f.name:p.sha(f) for f in OUT.iterdir() if f.is_file() and f.name!='analysis_files_sha256.json'})
    print(json.dumps({k:result[k] for k in ('auto_stop_ms','nominal_RMS_last_window_A','NIS_before','NIS_after','OFF_kernel_cycles','RUN_full_path_max_cycles','max_result_age_us')}))
if __name__=='__main__':main()

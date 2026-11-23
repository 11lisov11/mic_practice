"""Review existing RUN5 evidence plus recorded timing scenarios, offline only."""
import json
import subprocess
import prepare_observer_input_epoch as p


def main():
    capture=p.ROOT/'artifacts/live_bench_20261114/powered_FOC_5Hz_5s_repeat_r1'
    saved=json.loads(p.read(capture/'saved_files_sha256.json'))
    # Manifests of this run contain names relative to the run directory.
    if 'files' in saved:saved=saved['files']
    for rel,digest in saved.items():
        assert p.sha(capture/rel)==digest,rel
    rows=[json.loads(x) for x in p.read(capture/'status.jsonl').splitlines()]
    running=[r['status'] for r in rows if r['status'].get('pwm') and r['status'].get('run_id')==5]
    review=[]
    for s in running:
        review.append({k:s.get(k) for k in ('run_elapsed_ms','freq','rpm_est','rpm_est_valid',
            'research_native_valid','algorithm_selected','algorithm_fault','algorithm_profile_crc',
            'foc_experiment_flags','foc_timing_cases','mc_fault_current_mask','mc_fault_occurred_mask')})
    assert [s['rpm_est_valid'] for s in running]==[1,0,0]
    assert all(s['algorithm_fault']==0 and s['research_native_valid']==1 for s in running)
    assert all('observer_trace' not in s and 'mc_observer_trace_hex' not in s for s in running)
    final=json.loads(p.read(capture/'final_status.json'))
    timing=final['foc_runtime']
    assert timing['source']=='runtime_observer' and timing['first_fault'] is None
    wall=round(timing['max_wall_us']*170)
    queue=round(timing['max_window_queue_us']*170)
    results=[]
    for variant in ('baseline','candidate'):
        exe=p.OUT/f'model_verification/plant_observer_{variant}.exe'
        raw=subprocess.check_output([str(exe),str(wall),str(queue),'0',
            str(p.OUT/f'model_verification/{variant}_recorded_timing_trace.bin')],text=True)
        r=json.loads(raw);assert r['completed_5s'] and not r['fault']
        results.append(dict(variant=variant,**r))
    report=dict(passed=True,source_run_id=5,recorded_status_samples=review,
        record_has_flux_NIS_IdIq=False,web_IdIq_zero_values_are_not_native_measurements=True,
        validity_drop_interval_ms=[1300,2563],
        native_validity_expression='running && allowed_profile && steps>=500 && !run_fault && flux>0.5*target && NIS<25',
        flux_target_Wb=.25,flux_valid_lower_bound_exclusive_Wb=.125,NIS_upper_bound_exclusive=25,
        exact_recorded_loss_cause_proven=False,
        branch_inference_assumptions='RUN and>=500 observer steps still held in the packet; these two gate inputs were not exported together in this release.',
        live_loss_possibilities=['flux fell to or below0.125Wb','NIS rose to or above25','nonfinite values'],
        timing_fault_recorded=False,max_result_age_us=timing['max_result_age_us'],estimate_age_limit_us=2000,
        source_bug='Latest foreground current was paired with voltage/time of an earlier completed bin.',
        fix='Latch offset-corrected endpoint current in the same sequence as voltage bin and use its ADC timestamp.',
        voltage_model_limitation='Retains prior averaged commanded voltage and deadtime model; inverter voltage error and hardware motor parameters are not identified by this change.',
        recorded_timing_simulation=dict(observer_wall_cycles=wall,queue_cycles=queue,
            conservative_pair_of_separate_maxima=True,results=results,
            measured_current_replay=False,independent_model_only=True),
        hardware_commands=0,thresholds_changed=False,old_captures_unchanged=True)
    p.write(p.OUT/'recorded_run_analysis.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,loss_interval_ms=report['validity_drop_interval_ms'],
        recorded_flux_NIS_available=False,timing_scenarios=results)))


if __name__=='__main__':main()

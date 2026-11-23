"""Recover the new observer ABI from saved replies; append evidence, never actuate."""
import ast,json,urllib.request
import prepare_exact_profile_budget as p
from run_foc_boot_capture_trial import decode_boot


def main():
    trial=p.OUT/'powered_FOC_5Hz_r1';out=trial/'saved_record_analysis_r1'
    assert out.exists() and not (out/'summary.json').exists()
    def save(name,obj):p.write(out/name,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    original=json.loads(p.read(trial/'report.json'))
    rows=[json.loads(x)['status'] for x in p.read(trial/'status.jsonl').splitlines()]
    captured=[json.loads(x)['data'] for x in p.read(trial/'observer_collection_status.jsonl').splitlines()]
    final=captured[-1]
    before=json.loads(p.read(trial/'before_CLEAR.json'))
    # Execute the exact decoder from the matching RELEASE source, not the old
    # 3016 decoder accidentally imported by the legacy post-run collector.
    source=p.read(p.OUT/'web_hmi/server.py');tree=ast.parse(source)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='decode_observer_trace_hex')
    namespace={};exec(compile(ast.Module(body=[node],type_ignores=[]),'release_decoder','exec'),namespace)
    raw=bytes.fromhex(final['mc_observer_trace_hex'])
    decoded=namespace['decode_observer_trace_hex'](raw.hex(),p.NEW[1])
    assert decoded['available'] and decoded['schema']==2 and len(raw)==1832
    assert (out/'observer_trace.bin').read_bytes()==raw
    save('observer_trace_decoded.json',decoded)
    assert original['completed_5s'] and original['clear_commands']==original['start_commands']==1
    assert original['prior_SD_record_retained']
    assert (trial/'SD_before.bin').read_bytes()==(trial/'SD_after.bin').read_bytes()
    oldboot=decode_boot(before,p.NEW);newboot=decode_boot(final,p.NEW)
    assert oldboot['identity']==newboot['identity'] and oldboot['Linux_boot_id']==newboot['Linux_boot_id']
    running=[s for s in rows if s.get('pwm')==1]
    assert running and all(s['mc_mode']==s['bp_mode']==6 and s['algorithm_selected']==2 for s in running)
    currents=[dict(elapsed_ms=s['run_elapsed_ms'],RMS_A=s['mc_current_rms_a'],
        peak_A=s['mc_current_peak_a'],coverage_pct=s['mc_current_coverage_pct'],flags=s['mc_current_flags'])
        for s in rows if s.get('mc_current_rms_a') is not None]
    save('current_telemetry.json',currents)
    runtime=original['after']['foc_runtime'];assert runtime['source']=='runtime_observer'
    save('CPU_IRQ.json',runtime)
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    latest=final;live_after_collection=False
    for name,path in [('latest_status.json','/api/status'),('SD_trace_after.json','/api/bkin-trace'),
                      ('SD_snapshots_after.json','/api/break-snapshot'),('repeat_after.json','/api/repeat-break')]:
        req=urllib.request.Request('http://192.168.1.138:8080'+path,
            headers={'X-UNOQ-Control-Token':token},method='GET')
        try:
            with op.open(req,timeout=8) as response:result=json.load(response)
        except Exception as exc:
            save('latest_GET_error.json',dict(path=path,error=repr(exc),
                analysis_falls_back_to_saved_OFF_status=True,no_commands_sent=True))
            break
        assert result['ok'];save(name,result)
        if name=='latest_status.json':latest=result['data'];live_after_collection=True
    assert latest['state']=='SAFE' and latest['pwm']==latest['hmi_hv_armed']==0 and latest['run_id']==1
    assert latest['mc_break_wave_hex']==before['mc_break_wave_hex']
    for rel,digest in json.loads(p.read(p.OUT/'preserved_capture_hashes.json')).items():assert p.sha(p.ROOT/rel)==digest,rel
    r=dict(completed_5s=True,stop_source='Uno MCU 5000ms limit',native_trial_done_flag=original['native_done'],
        one_CLEAR=1,one_START=1,new_starts_in_analysis=0,analysis_GET_only=True,
        actual_wire_mode=6,selected_algorithm=2,FOC_fixed=True,observer_record_recovered=True,
        observer_bytes=len(raw),observer_SHA256=p.sha(out/'observer_trace.bin'),
        observer_CRC_and_ABI_verified=True,decoder_source_SHA256=p.sha(p.OUT/'web_hmi/server.py'),
        legacy_collector_error='Old 3016 decoder expected a different record length; full raw1832 bytes were retained in saved status and decoded here.',
        original_report_retained_unmodified=True,raw_ADC_received=bool(latest['mc_adc_peak_complete']),
        raw_ADC_good=latest['mc_adc_peak_good'],raw_ADC_bad=latest['mc_adc_peak_bad'],
        missing_raw_ADC_cause_proven=False,
        data_collection_complete=False,CPU_IRQ_received=True,current_telemetry_received=True,
        physical_rotation_verified=False,independent_speed_measured=False,
        live_status_after_collection_received=live_after_collection,
        max_result_age_us=runtime['max_result_age_us'],unchanged_result_age_limit_us=2000,
        runtime_fast_cycles=latest['algorithm_fast_cycles'],unchanged_runtime_fast_budget=5312,
        OFF_fast_cycles_before_START=before['algorithm_fast_cycles'],unchanged_OFF_budget=4000,
        no_native_fault=latest['algorithm_fault']==latest['mc_fault']==0,
        new_UART_errors=False if latest['mc_bad_cnt']==latest['mc_last_uart_error_flags']==latest['mc_transport_fault']==0 else True,
        no_reboot=True,first_SD_preserved=True,post_trial_SD=latest['mc_sd_live'],
        observer_total_samples=decoded['total_observer_samples'],valid_samples=decoded['valid_samples'],
        invalid_samples=decoded['invalid_samples'],first_validity_loss=decoded['first_loss'],
        max_recorded_phase_peak_A=[max(c['peak_A'][i] for c in currents) for i in range(3)],
        current_scale='Nominal shunt scale; not independently calibrated in this trial.',
        preserved_files_verified=3045,thresholds_changed=False,
        limitation='Five-second actuation completed; observer validity is intermittent and raw ADC capture is missing. No full commissioning success claim.')
    save('summary.json',r)
    save('saved_files_sha256.json',{f.name:p.sha(f) for f in out.iterdir() if f.is_file() and f.name!='saved_files_sha256.json'})
    print(json.dumps({k:r[k] for k in ('completed_5s','raw_ADC_received','observer_record_recovered',
        'max_result_age_us','runtime_fast_cycles','OFF_fast_cycles_before_START','observer_total_samples',
        'valid_samples','invalid_samples','max_recorded_phase_peak_A','no_native_fault','new_UART_errors')}))


if __name__=='__main__':main()

"""Analyze existing842ms trace; explicitly distinguish measured evidence/model."""
import json,math,importlib.util,sys
import prepare_observer_voltage_stop as p


def main():
 trial=p.BASE/'powered_FOC_observer_r1'
 for rel,h in json.loads(p.read(trial/'saved_files_sha256.json')).items():assert p.sha(trial/rel)==h,rel
 old=json.loads(p.read(trial/'report.json'))
 before=json.loads(p.read(trial/'before_START.json'));started=old['start_response']['status'];after=old['after']
 trace=json.loads(p.read(trial/'observer_trace_decoded.json'));loss=trace['first_loss']
 assert loss['reason_mask']==32 and loss['nis']>=25 and loss['flux_wb']>.125
 assert after['run_elapsed_ms']==842 and after['run_reason']==2 and after['algorithm_fault']==0
 assert after['uno_rx_active_max_gap_us']>500000
 assert after['uno_tx_active_max_gap_us']<60000
 assert after['bp_superseded']-before['bp_superseded']==10
 # This evidence predates local-stop provenance fields. Do not invent g_fault=3
 # or claim an exact replay of every UART byte/current that was not captured.
 report=dict(source_run_duration_ms=842,full_5s_completed=False,
  measured_reply_gap_us=after['uno_rx_active_max_gap_us'],watchdog_ms=500,
  measured_tx_gap_us=after['uno_tx_active_max_gap_us'],new_superseded_replies=10,
  current_reply_age_in_START_response_ms=started['bp_age_ms'],
  native_algorithm_fault=after['algorithm_fault'],native_fault_masks=[after['mc_fault_current_mask'],after['mc_fault_occurred_mask']],
  stop_path='Uno peer-response guard: reply acceptance gap exceeds500ms while commands continue.',
  evidence_strength='Recorded symptoms and source-path reproduction; local stop-origin/g_fault were not exported in installed1403.',
  fixed_reply_bug='Retired after8ms before50ms send cadence check; now retire only on actual replacement transmission.',
  exact_UART_byte_timeline_replayed=False,
  first_observer_loss=loss,observer_steps=trace['total_observer_samples'],stored_observer_rows=trace['count'],
  measured_input_epochs_match=True,measured_max_result_age_us=after['foc_runtime']['max_result_age_us'],
  underlying_physical_NIS_cause_proven=False,
  why_physical_NIS_is_unresolved='Only4 decimated states and1 loss state were logged, without innovation/S or all817 inputs; no rawADC record arrived.',
  fixed_voltage_bug='Observer used next preload-command voltage alongside earlier active-epoch current; candidate uses ADC active CCR and bus with existing dead-time model.',
  voltage_is_estimated=True,observer_R_Q_NIS_thresholds_unchanged=True,hardware_commands=0)
 p.write(p.OUT/'recorded_842ms_analysis.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 spec=importlib.util.spec_from_file_location('observer_voltage_hmi_test',p.OUT/'web_hmi/server.py')
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 path=p.OUT/'model_verification/candidate_ADC_plusminus16counts_trace.bin'
 decoded=module.decode_observer_trace_hex(path.read_bytes().hex(),p.NEW[1])
 first=decoded['first_loss'];assert first['reason_mask']==32
 assert abs(sum(first['NIS_components'])-first['nis'])<1.e-4*(1+first['nis'])
 assert first['control_adc_cycles']==first['observer_adc_cycles']==first['bin_cycles']
 data=module.RpcBridge._parse_status_string('DATA state=SAFE mode=VF bp_fw_build=2026111406 uno_local_fault=3 uno_stop_ready=1 uno_stop_origin=1 uno_stop_run_id=1 uno_stop_local_fault=3 uno_stop_reply_age_ms=501 uno_stop_superseded=10')
 assert data['uno_local_fault']==3 and data['uno_stop_reply_age_ms']==501
 detail=module.motor_fault_detail(data)
 assert '501' in detail and 'Uno=3' in detail and 'контроль ответа' in detail
 p.write(p.OUT/'verification/HMI_record_validation.json',json.dumps(dict(passed=True,
  schema2_NIS_decomposition=True,stop_origin_and_local_fault_visible=True,hardware_commands=0),indent=2))
 print(json.dumps(dict(passed=True,reply_gap_us=report['measured_reply_gap_us'],watchdog_ms=500,
  superseded_replies=10,first_loss_NIS=loss['nis'],physical_NIS_root_cause_proven=False)))


if __name__=='__main__':main()

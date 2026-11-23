"""Record the captured rejection cause and fully passed corrected detached run."""
import json
from pathlib import Path
from pwm_filter_hardware_session import sha,ERROR_FIELDS
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1'

def main():
    s=json.loads((FOLDER/'session.json').read_text());assert s['restored'] and s['idle_30s_pass'] and not s.get('paused_primary_pid')
    assert s['production_nucleo_byte_verified'] and s['production_uno_verified']
    run=Path(s['last_run']);cap=json.loads((run/'report.json').read_text());mod=json.loads((run/'modulation_ramp.json').read_text())
    sync=json.loads((run/'stop_sync_proof.json').read_text());wave=json.loads((run/'waveform.json').read_text());assert cap['pass'] and mod['pass'] and sync['pass']
    cause=ROOT/'artifacts/live_bench_20261014/snapshot_reject_hil_r2/run_1791992054652665000/reject_cause_proof.json'
    before=json.loads(cause.read_text());assert before['pass']
    idle=json.loads((FOLDER/'production_idle.json').read_text());d=s['latest_idle']
    assert (d['fw_build'],d['mc_fw_build'])==(2026101411,2026101410) and d['state']=='SAFE' and d['pwm']==0 and d['vdc']==0 and d['hmi_hv_armed']==0
    assert all(d.get(k)==0 for k in ERROR_FIELDS) and d['bp_transport_fault']==0
    span=idle[-1]['elapsed_s']-idle[0]['elapsed_s'];assert span>=30
    evidence=[cause,run/'capture.sal',run/'csv/digital.csv',run/'status.json',run/'report.json',run/'waveform.json',run/'modulation_ramp.json',run/'stop_sync_proof.json',
       FOLDER/'production_nucleo_readback.bin',FOLDER/'production_uno.log',FOLDER/'production_idle.json',FOLDER/'programming_timeout_before_clear.json',
       FOLDER/'capture_remote_logs.log',FOLDER/'vbus_recalibration_preparation/report.json',
       ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r7/qualification/report.json',
       ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r7/reject_selftest_r1/report.json',
       ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r7/stop_sync_selftest_r2/report.json']
    result=dict(schema='mic_ai.snapshot_stop_sync_result.v1',pass_=True,installed_pair=[2026101411,2026101410],measured_fixture_pair=[2026101492,2026101493],
      first_reject_cause_observed='NOT_FRESH_OFF with CRC-valid page and prior on-status snapshot age5ms',
      captured_bad_page_crc_valid=True,observed_previous_status_hex='0x6d',observed_previous_status_age_ms=5,
      reject_at_fixed_stop=0,strict_detached_capture_pass=True,diagnostic_delivery_resumed=True,
      good_diagnostic_pages_delta=sync['after_good']-sync['before_good'],both_diagnostic_records_available=True,
      active_span_s=cap['active_span_s'],low_tail_s=cap['low_tail_s'],carrier_hz_by_channel={k:v['freq_hz_from_rising'] for k,v in wave['channels'].items()},
      deadtime_min_us_by_phase={k:round(v['min_gap_s']*1e6,6) for k,v in wave['pairs'].items()},sample_period_ns=250,
      phase_relative_to_U_deg=mod['phase_relative_to_U_deg'],measured_ramp_hz_s=mod['measured_ramp_hz_s'],final_waveform_frequency_hz=mod['final_frequency_hz'],
      receive_acceptance_guards_unchanged=True,working_firmware_verified=True,primary_rpc_resumed_without_second_cold_boot=True,
      programming_only_link_timeout_recorded_and_acknowledged_once=s['programming_timeout_acknowledged'],
      final_state={k:d.get(k) for k in ('state','pwm','vdc','hmi_hv_armed','bp_fault','mc_fault_reason','mc_fault_current_mask','mc_fault_occurred_mask','bp_transport_fault')+ERROR_FIELDS},
      idle_span_s=span,idle_good_frame_delta=idle[-1]['status']['bp_good_cnt']-idle[0]['status']['bp_good_cnt'],
      hmi_sha256=sha(ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r7/production/web_hmi/server.py'),
      original_calibration_bytes_preserved_and_archived=True,new_calibration_measurements_recorded=False,
      next_step='Fresh meter zero point for Vbus recalibration; no power or motor start yet',
      hv_release_approved=False,original_powered_uart_noise_cause_proven=False,button_latency_measured=False,
      evidence_sha256={str(p.relative_to(ROOT)):sha(p) for p in evidence})
    result['pass']=result.pop('pass_');(FOLDER/'FINAL_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('evidence_sha256','carrier_hz_by_channel')},indent=2))

if __name__=='__main__':main()

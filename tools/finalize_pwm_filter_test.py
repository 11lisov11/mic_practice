"""Summarize retained hardware evidence without changing the stand."""
import json,hashlib
from pathlib import Path
from install_passive_break_decoder_fix import ERROR_FIELDS
ROOT=Path(__file__).resolve().parents[1]
SESSION=ROOT/'artifacts/live_bench_20261014/pwm_filter_hil_r2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    s=json.loads((SESSION/'session.json').read_text());assert s['restored'] and s['idle_30s_pass']
    run=Path(s['last_run']);original=json.loads((run/'report.json').read_text());w=json.loads((run/'waveform.json').read_text())
    m=json.loads((run/'modulation_ramp.json').read_text());rows=json.loads((run/'status.json').read_text())
    idle=json.loads((SESSION/'production_idle.json').read_text());current=s['latest_idle']
    primary=[k for k in ERROR_FIELDS if k!='mc_break_rx_bad']
    assert m['pass'] and w['pass'] and all(all(r['status'].get(k)==0 for k in primary) for r in rows)
    assert (current['fw_build'],current['mc_fw_build'])==(2026101407,2026101406)
    assert current['state']=='SAFE' and current['pwm']==0 and current['hmi_hv_armed']==0 and current['vdc']==0
    assert s['production_nucleo_byte_verified'] and s['production_uno_verified']
    assembly=ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r4/qualification/production_TSK_HighFrequencyTask.asm'
    a=assembly.read_text();assert a.index('bpl.n')<a.index('<ACIM_VF_CalcAngle>') and 'PWM_SwitchOffPWM' in a and 'MCI_FaultProcessing' in a
    evidence=[run/'capture.sal',run/'csv/digital.csv',run/'report.json',run/'waveform.json',run/'modulation_ramp.json',run/'status.json',
      SESSION/'production_nucleo_readback.bin',SESSION/'production_uno.log',SESSION/'production_idle.json',SESSION/'capture_remote_logs.log',
      SESSION/'snapshot_policy_replay/report.json',assembly,
      ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r4/qualification/report.json',
      ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r4/fastmath/report.json']
    result=dict(schema='mic_ai.pwm_filter_hardware_result.v1',task_flash_and_retest_completed=True,
      installed_working_pair=[2026101407,2026101406],fixture_pair_measured=[2026101496,2026101497],
      working_pair_byte_verified=True,waveform_qualification_pass=True,primary_uart_error_free=True,
      strict_combined_capture_pass=original['pass'],unresolved_snapshot_rejections=1,
      snapshot_rejection_at_automatic_stop=True,snapshot_actual_packet_cause_proven=False,
      inactive_hft_guard_present_in_target_assembly=True,boot_false_software_fault_fixed=True,
      active_span_s=original['active_span_s'],low_tail_s=original['low_tail_s'],
      carrier_hz_by_channel={k:v['freq_hz_from_rising'] for k,v in w['channels'].items()},
      minimum_deadtime_us_by_phase={k:round(v['min_gap_s']*1e6,6) for k,v in w['pairs'].items()},
      phase_relative_to_U_deg=m['phase_relative_to_U_deg'],ramp_hz_s=m['measured_ramp_hz_s'],
      final_waveform_frequency_hz=m['final_frequency_hz'],sinusoidal_r_squared=[f['r_squared'] for f in m['duty_fits']],
      idle_observations=len(idle),idle_observed_span_s=idle[-1]['elapsed_s']-idle[0]['elapsed_s'],
      idle_new_good_frames=idle[-1]['status']['bp_good_cnt']-idle[0]['status']['bp_good_cnt'],
      final_status={k:current.get(k) for k in ('state','pwm','vdc','hmi_hv_armed','estop','bp_fault','mc_fault_reason',
          'mc_fault_current_mask','mc_fault_occurred_mask','hmi_vbus_hv_calibrated')+ERROR_FIELDS},
      saleae_probes_permanently_connected=True,operator_disconnects_only_saleae_usb=True,
      old_calibration_bytes_preserved=True,old_calibration_valid_for_new_pair=False,
      hmi_sha256=sha(ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r4/production/web_hmi/server.py'),
      hv_release_approved=False,physical_powered_incident_cause_proven=False,button_latency_measured=False,
      evidence_sha256={str(p.relative_to(ROOT)):sha(p) for p in evidence})
    (SESSION/'FINAL_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('evidence_sha256','carrier_hz_by_channel','sinusoidal_r_squared')},indent=2))

if __name__=='__main__':main()

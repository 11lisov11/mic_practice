"""Enrich the saved run with direction-specific fault evidence; no network I/O."""
import json
from pathlib import Path

P=Path(__file__).resolve().parent
r=json.loads((P/'report.json').read_text(encoding='utf-8'))
s=json.loads((P/'post_fault_status.json').read_text(encoding='utf-8'))
snapshot=json.loads((P/'after_break_snapshot.json').read_text(encoding='utf-8'))['data']
wave=json.loads((P/'after_bkin_trace.json').read_text(encoding='utf-8'))['data']
assert r['start_commands']==1 and r['clear_commands']==0 and r['outputs_off_confirmed']
assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0
assert s['mc_transport_fault']==2 and s['mc_fault_reason']==1 and s['mc_fault_sequence']==196
assert s['mc_fault_current_mask']==s['mc_fault_occurred_mask']==0
assert len(snapshot['mc_break_snapshots'])==2 and all(x['available'] and not x['captured'] for x in snapshot['mc_break_snapshots'])
assert not wave['available'] and wave['reason']=='not_received'
analysis={
    'classification':'Nucleo command transport fail-stop: UV3_BAD_CRC (2), first diagnostic CRC (1)',
    'direction':'Uno Q -> Nucleo command receiver',
    'last_fault_motor_state':s['mc_fault_motor_state'],
    'fault_sequence':s['mc_fault_sequence'],
    'first_reason_code':s['mc_fault_reason'],
    'transport_fault_code':s['mc_transport_fault'],
    'nucleo_rejected_count':s['mc_bad_cnt'],
    'uno_reply_integrity_rejections':s['mc_bad_integrity'],
    'mc_current_fault_mask':s['mc_fault_current_mask'],
    'mc_occurred_fault_mask':s['mc_fault_occurred_mask'],
    'break_recorded':False,'wave_received':False,
    'nucleo_noise_bytes_before':r['before']['mc_ne_observed'],
    'nucleo_noise_bytes_after':s['mc_ne_observed'],
    'nucleo_recovered_drop_count_before':r['before']['mc_recovered_drops'],
    'nucleo_recovered_drop_count_after':s['mc_recovered_drops'],
    'last_active_observed_reference_hz':r['controller_reference_max_hz'],
    'latched_reference_after_stop_hz':r['abort_status']['mc_frequency_reference_hz'],
    'targets_settled_hz':[x['target_hz'] for x in r['settled_steps']],
    'highest_target_sent_hz':15,'twenty_or_higher_commands_sent':False,
    'source_physical_identified':False,
    'limits':['UV3_BAD_CRC is also returned for framing/header resynchronization rejection',
        'The corrupted/raw command bytes and exact discard timestamps were not recorded',
        'Electrical interference versus parser/receive/sender defect is unresolved',
        'This transport stop is distinct from the earlier recorded TIM1 Break at 20 Hz',
        'No 15-Hz hold or 20-to-50-Hz operation was qualified in this run'],
    'future_work':'Capture raw rejected command bytes, parser state and discard reasons before any policy change; keep CRC/watchdog/Break intact',
}
r['fault_analysis']=analysis
r['post_fault_status']=s
r.update(physical_rotation_confirmed=True,speed_changes_confirmed=True,
    operator_observation='User confirmed smooth rotation and visible acceleration from 5 to 10 Hz before the stop.')
(P/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
(P/'fault_analysis.json').write_text(json.dumps(analysis,indent=2)+'\n',encoding='utf-8')
print(json.dumps(analysis))

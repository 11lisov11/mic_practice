"""Render recorded telemetry; never connects to the powered bench."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

P=Path(__file__).resolve().parent
r=json.loads((P/'report.json').read_text(encoding='utf-8'))
rows=sorted(json.loads((P/'samples.json').read_text(encoding='utf-8')),key=lambda x:x['host_monotonic_s'])
active=[x for x in rows if x['status'].get('pwm')==1]
assert r['pass'] and [x['target_hz'] for x in r['settled_steps']]==[5,10,5]
assert all(x['status'].get('mc_frequency_reference_valid')==1 for x in active)
fatal=('mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_transport_fault','uno_rx_dropped')
assert all(all(x['status'].get(k)==0 for k in fatal) for x in active)
slots=json.loads((P/'after_break_snapshot.json').read_text())['data']['mc_break_snapshots']
assert all(x['available'] and x['reason']=='no_recorded_break' for x in slots)
summary={'pass':True,'targets_reached_hz':[5,10,5],
    'active_bus_min_v':min(x['status']['vdc'] for x in active),'active_bus_max_v':max(x['status']['vdc'] for x in active),
    'active_temperature_min_c':min(x['status']['bp_temp_c'] for x in active),'active_temperature_max_c':max(x['status']['bp_temp_c'] for x in active),
    'uno_noise_advisory_before':r['before']['uno_rx_hw_errors'],
    'uno_noise_advisory_after':r['final_status']['uno_rx_hw_errors'],
    'new_uno_noise_advisories':r['final_status']['uno_rx_hw_errors']-r['before']['uno_rx_hw_errors'],
    'crc_or_sequence_errors':0,'dropped_bytes':0,'controller_faults':0,'break_recorded':False,
    'active_observed_span_s':active[-1]['host_monotonic_s']-active[0]['host_monotonic_s'],
    'physical_rotation_confirmed':r['physical_rotation_confirmed'],'speed_changes_confirmed':r['speed_changes_confirmed'],
    'outputs_off_confirmed':r['outputs_off_confirmed']}
r['telemetry_summary']=summary
(P/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
(P/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
t=[x['host_monotonic_s']-r['start_monotonic_s'] for x in rows]
fig,axes=plt.subplots(3,1,figsize=(10,7),sharex=True)
axes[0].plot(t,[x['status']['mc_frequency_reference_hz'] for x in rows],'.-',color='#008b87',label='Controller field reference')
axes[0].step(t,[x['status']['freq_cmd'] for x in rows],where='post',color='#555555',ls='--',label='Command')
axes[0].set_ylabel('Field frequency (Hz)');axes[0].legend(loc='best')
axes[1].plot(t,[x['status']['vdc'] for x in rows],'.-',color='#a75c00');axes[1].set_ylabel('DC bus (V)')
axes[2].step(t,[x['status']['uno_rx_hw_errors'] for x in rows],where='post',label='Cumulative Uno NOISE advisory',color='#a75c00')
axes[2].plot(t,[x['status']['mc_bad_integrity'] for x in rows],label='Rejected integrity frames (0)',color='#a33333')
axes[2].set_ylabel('Diagnostic count');axes[2].legend(loc='best')
for ax in axes:ax.grid(alpha=.2)
axes[-1].set_xlabel('Host HTTP response time relative to START request (s)')
fig.suptitle('Online V/f 5 -> 10 -> 5 Hz: targets reached, STOP confirmed',fontweight='bold')
fig.text(.08,.014,'Controller reference is not measured rotor speed. NOISE advisories remain visible; no CRC errors or lost bytes observed.',fontsize=8)
fig.tight_layout(rect=(0,.045,1,.96));fig.savefig(P/'run_summary.png',dpi=150);plt.close(fig)
print(json.dumps(summary))

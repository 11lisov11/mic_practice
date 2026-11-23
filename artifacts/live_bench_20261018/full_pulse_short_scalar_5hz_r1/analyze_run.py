"""Summarize saved run data only; no hardware or network operations."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

P=Path(__file__).resolve().parent
r=json.loads((P/'report.json').read_text(encoding='utf-8'))
rows=[json.loads(line) for line in (P/'status.jsonl').read_text(encoding='utf-8').splitlines()]
active=[x for x in rows if x['status'].get('pwm')==1]
assert active and max(x['status']['mc_frequency_reference_hz'] for x in active)==5
assert all(x['status']['mc_frequency_reference_valid']==1 for x in active)
errors=('mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_transport_fault')
assert all(all(x['status'][k]==0 for k in errors) for x in rows)
snap=json.loads((P/'after_break_snapshot.json').read_text())['data']
assert all(x['available'] and x['reason']=='no_recorded_break' for x in snap['mc_break_snapshots'])
r.update(physical_rotation_confirmed=True,operator_observation='User confirmed smooth physical rotation in this completed run.',
    new_uart_errors_observed=False,break_recorded=False,
    active_bus_min_v=min(x['status']['vdc'] for x in active),
    active_bus_max_v=max(x['status']['vdc'] for x in active),
    active_temperature_min_c=min(x['status']['bp_temp_c'] for x in active),
    active_temperature_max_c=max(x['status']['bp_temp_c'] for x in active),
    qualification_scope='One short scalar 5 Hz run only; does not qualify higher frequencies or establish previous trip cause.')
(P/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
t=[x['host_monotonic_s']-r['start_monotonic_s'] for x in rows]
fig,axes=plt.subplots(3,1,figsize=(9,7),sharex=True)
axes[0].plot(t,[x['status']['mc_frequency_reference_hz'] for x in rows],'.-',color='#008b87',label='Controller field reference')
axes[0].axhline(5,color='gray',lw=1,ls='--',label='Target 5 Hz');axes[0].set_ylabel('Field frequency (Hz)');axes[0].legend(loc='best')
axes[1].plot(t,[x['status']['vdc'] for x in rows],'.-',color='#a75c00');axes[1].set_ylabel('DC bus (V)')
axes[2].step(t,[x['status']['pwm'] for x in rows],where='post',color='#245e96',label='PWM status')
axes[2].plot(t,[x['status']['mc_transport_fault'] for x in rows],'.-',color='#a33333',label='UART fault')
axes[2].set_ylabel('Status');axes[2].set_yticks([0,1]);axes[2].legend(loc='best')
for ax in axes:ax.grid(alpha=.2)
axes[-1].set_xlabel('Host HTTP poll time relative to START request (s)')
fig.suptitle('Short scalar 5 Hz run: smooth rotation confirmed by operator',fontweight='bold')
fig.text(.08,.012,'Frequency is a controller reference, not measured rotor speed. HTTP samples do not measure exact PWM edge timing.',fontsize=8)
fig.tight_layout(rect=(0,.04,1,.96));fig.savefig(P/'run_summary.png',dpi=160);plt.close(fig)
print(json.dumps({k:r[k] for k in ('pass','physical_rotation_confirmed','controller_reference_max_hz','active_bus_min_v','active_bus_max_v','break_recorded','outputs_off_confirmed')}))

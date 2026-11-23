"""Summarize saved pre-START SD evidence; offline, no board communication."""
import json
from pathlib import Path

P = Path(__file__).resolve().parent
read = lambda name: json.loads((P / name).read_text(encoding='utf-8'))
report = read('read_only_report.json')
wave = read('bkin_trace.json')['data']
slots = read('break_snapshot.json')['data']['mc_break_snapshots']
status = read('final_status.json')
event = slots[0]
bdtr = event['raw']['tim_bdtr']
assert report['pass'] and report['independent_decode_matches']
assert wave['event_tick_ms'] == event['raw']['tick_ms']
assert wave['pulse_complete'] and wave['post_complete']
assert not any(wave[k] for k in ('timeout', 'dma_error', 'sampling_overrun', 'run_overflow', 'left_censored', 'right_censored'))
assert event['captured'] and not slots[1]['captured']
assert event['event']['bif'] and not event['event']['moe_at_irq']
assert not event['raw']['context_valid'] and not event['raw']['start_window']
assert (bdtr >> 16) & 15 == 9
analysis = dict(
    requested_run_completed=False, motor_start_commands=0, clear_commands=0,
    agent_reset_commands=0, flash_commands=0, reason_no_start='Pre-existing hardware Break, not a UART CRC failure',
    pair=[status['fw_build'], status['mc_fw_build']],
    event_tick_ms=wave['event_tick_ms'], event_before_start=True,
    moe_at_irq=False, pa6_high_at_irq=False, bkf_at_irq=9, bdtr_at_irq_hex=hex(bdtr),
    nominal_pulse_width_us=wave['pulse_width_us'], nominal_sample_period_us=wave['sample_period_us'],
    full_pulse_and_post_recorded=True, raw_decode_matches=True,
    source_identified=False, vbus_at_event_known=False, temperature_at_event_known=False,
    current_fault_mask=status['mc_fault_current_mask'], latched_fault_mask=status['mc_fault_occurred_mask'],
    current_state=status['state'], current_pwm=status['pwm'], current_sd=status['mc_sd_live']['level'],
    current_bus_v=status['vdc'], current_reported_temperature_c=status['bp_temp_c'],
    uart={k:status.get(k) for k in ('mc_bad_integrity', 'mc_bad_sequence', 'mc_uart_error_flags',
                                   'mc_transport_fault', 'uno_rx_dropped', 'uno_tx_short_writes',
                                   'uno_rx_hw_errors', 'uno_rx_hw_flags')},
    limitations=[
        'Nominal DMA sampling is not an independently calibrated analog measurement.',
        'The event has no cached bus/temperature context; current readings do not describe the event.',
        'A long SD signal before START does not identify OC, UVLO, or an external SD assertion.',
        'This boot event cannot determine whether BKF9 resolves the previous 22 Hz running event.',
    ])
(P / 'analysis.json').write_text(json.dumps(analysis, indent=2) + '\n', encoding='utf-8')
print(json.dumps(analysis))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(9, 3.5), layout='constrained')
for item in wave['runs']:
    ax.plot([item['from_us'] / 1000, item['to_us'] / 1000], [item['level']] * 2, color='#087f8c', linewidth=2)
for left, right in zip(wave['runs'], wave['runs'][1:]):
    ax.plot([left['to_us'] / 1000] * 2, [left['level'], right['level']], color='#087f8c', linewidth=2)
ax.axvline(0, color='#c23b22', linestyle='--', label='Break IRQ; MOE=0, before START')
ax.set(xlabel='Nominal time relative to Break IRQ, ms', ylabel='PA6 / SD', yticks=[0, 1],
       ylim=(-.15, 1.2), title='Pre-START SD LOW: 18.4618 ms; BKF=9')
ax.grid(alpha=.25)
ax.legend(loc='upper center')
fig.savefig(P / 'startup_sd.png', dpi=150)

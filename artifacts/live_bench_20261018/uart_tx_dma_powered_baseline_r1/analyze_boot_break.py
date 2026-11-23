"""Archive interpretation and confirm that motor preflight rejects this fault. No writes to hardware."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import run_uart_tx_dma_to_50 as trial

OUT = Path(__file__).resolve().parent
s = json.loads((OUT / 'final_status.json').read_text(encoding='utf-8'))
r = json.loads((OUT / 'read_only_report.json').read_text(encoding='utf-8'))
w = r['wave']
records = s['mc_break_snapshots']
first = records[0]
raw = first['raw']
result = {
    'firmware': [s['fw_build'], s['mc_fw_build']],
    'motor_run_attempted': False,
    'start_commands': 0, 'clear_commands': 0, 'reset_commands': 0,
    'flash_commands': 0, 'calibration_writes': 0,
    'motor_preflight_ready': trial.ready(s),
    'known_undervoltage_ack_allowed': trial.startup_ack_allowed(s),
    'transport_clean': trial.runner.transport_clean(s),
    'fault_occurred_mask': s['mc_fault_occurred_mask'],
    'fault_interpretation': '0x0400 MC_DP_FAULT / TIM1 Break, not the allowed 0x0004 startup undervoltage',
    'event_tick_ms_since_nucleo_boot': raw['tick_ms'],
    'break_irq': first['event'],
    'cached_motor_context_available': bool(raw['context_valid']),
    'start_window_recorded': records[1]['captured'],
    'pulse_complete': w['pulse_complete'],
    'pulse_width_us': w['pulse_width_us'],
    'wave_tick_matches_snapshot': w['event_tick_ms'] == raw['tick_ms'],
    'raw_decode_matches': r['independent_decode_matches'],
    'wave_error_flags': {k: w[k] for k in ('dma_error', 'sampling_overrun', 'run_overflow', 'timeout')},
    'live_sd': s['mc_sd_live'],
    'preflight_voltage_v': s['vdc'], 'preflight_reported_temperature_c': s['bp_temp_c'],
    'physical_cause_identified': False,
    'limitations': [
        'MOE was zero at the interrupt; no START was sent in this host session.',
        'Context was not initialized at this boot event; event bus voltage and temperature are unavailable.',
        'The SD pulse does not distinguish driver undervoltage, protection input activity or interference.',
        'This boot event is not proof of the cause of the earlier running-motor 20-Hz trip.',
        'Live HIGH is not an acknowledgment or rearm; first-event capture is occupied.',
        'The read-only helper pass refers to transport/archive checks, not permission to START.',
    ],
}
assert not result['motor_preflight_ready']
assert not result['known_undervoltage_ack_allowed']
assert result['transport_clean'] and result['raw_decode_matches']
assert result['wave_tick_matches_snapshot'] and result['pulse_complete']
assert result['fault_occurred_mask'] == 0x400
(OUT / 'boot_break_analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: result[k] for k in ('motor_preflight_ready', 'known_undervoltage_ack_allowed', 'transport_clean', 'event_tick_ms_since_nucleo_boot', 'pulse_width_us', 'physical_cause_identified')}))

"""Offline decode and summary of the one powered run. No hardware access."""
import importlib.util
import json
from pathlib import Path
import sys

P = Path(__file__).resolve().parent
ROOT = P.parents[2]
r = json.loads((P/'report.json').read_text())
rows = json.loads((P/'samples.json').read_text())
s = json.loads((P/'after_diagnostic_status.json').read_text())
wave = json.loads((P/'after_bkin_trace.json').read_text())['data']
snaps = json.loads((P/'after_break_snapshot.json').read_text())['data']['mc_break_snapshots']
raw = bytes.fromhex(s['mc_break_wave_hex'])
(P/'bkin_wave.bin').write_bytes(raw)
spec = importlib.util.spec_from_file_location('run_dma_hmi_decode', ROOT/'artifacts/live_bench_20261020/sd_break_filter_fix_r1/web_hmi/server.py')
m = importlib.util.module_from_spec(spec);sys.modules[spec.name] = m;spec.loader.exec_module(m)
decoded = m.bkin_wave_status(s)
def immutable(w):return {k:v for k,v in w.items() if k not in ('age_since_delivery_ms','live_peer_fresh','live_sd')}
assert immutable(decoded) == immutable(wave)
(P/'decoded_wave.json').write_text(json.dumps(decoded,indent=2)+'\n')
active = [x for x in rows if x['status'].get('pwm') == 1]
def bounds(key):
    values = [x['status'][key] for x in active if isinstance(x['status'].get(key),(int,float))]
    return [min(values),max(values)] if values else None
ctx = snaps[0]['cached_context']
keys = ('mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags',
        'mc_last_uart_error_flags','mc_transport_fault','uno_rx_dropped','uno_tx_short_writes')
counts = {k:{'before':r['before'].get(k),'after':s.get(k)} for k in keys}
lows = [x for x in wave['runs'] if x['level'] == 0]
result = {
    'run_completed_to_50_hz':False,
    'start_requests':r['start_commands'],'clear_commands':r['clear_commands'],
    'outputs_off_confirmed':r['outputs_off_confirmed'],
    'settled_controller_field_targets_hz':[x['target_hz'] for x in r['settled_steps']],
    'requested_target_at_trip_hz':r['abort_status']['freq_cmd'],
    'max_active_http_reference_hz':r['controller_reference_max_hz'],
    'cached_reference_before_break_hz':ctx['reference_electrical_hz'],
    'context_age_before_break_ms':ctx['age_at_irq_ms'],
    'active_samples':len(active),
    'active_vbus_range_v':bounds('vdc'),
    'active_reported_temperature_range_c':bounds('bp_temp_c'),
    'cached_vbus_v':ctx['vbus_v'],'cached_temperature_c':ctx['temperature_c'],
    'transport_counters':counts,
    'transport_counters_zero':all(v['before']==0 and v['after']==0 for v in counts.values()),
    'uno_noise_advisory':{k:{'before':r['before'].get(k),'after':s.get(k)} for k in ('uno_rx_hw_errors','uno_rx_hw_flags')},
    'fault_mask':r['abort_status']['mc_fault_occurred_mask'],
    'fault_name':'MC_DP_FAULT / TIM1 Break',
    'break_event':snaps[0]['event'],
    'event_tick_matches':wave['event_tick_ms']==snaps[0]['raw']['tick_ms'],
    'raw_wave_decode_matches':True,'record_bytes':len(raw),
    'sample_period_us':wave['sample_period_us'],
    'low_runs_count':len(lows),'low_run_samples':[x['samples'] for x in lows],
    'nearest_recorded_low_to_irq_us':wave['pulse_width_us'],
    'pulse_complete':wave['pulse_complete'],'post_complete':wave['post_complete'],
    'wave_error_flags':{k:wave[k] for k in ('dma_error','sampling_overrun','run_overflow','timeout')},
    'physical_source_identified':False,
    'physical_rotation_confirmed':r.get('physical_rotation_confirmed'),
    'speed_changes_confirmed':r.get('speed_changes_confirmed'),
    'break_filter_code_at_event':(snaps[0]['raw']['tim_bdtr'] >> 16) & 15,
    'clock_divisor_from_previously_verified_config':2,
    'filter_sampling_frequency_hz':10625000,
    'nominal_filter_qualification_ns':[7/10625000*1e9,8/10625000*1e9],
    'uniform_sampler_ideal_width_interval_us':[.4,.8],
    'width_interval_is_conditional_on_ideal_uniform_sampling':True,
    'filter_fix_eliminated_running_break':False,
    'limitations':[
        'Field reference is not independently measured rotor speed.',
        'The nearest sampled LOW is not independently proven to be the unique electrical cause of Break.',
        'The prehistory contains one-sample LOW runs at nominal 200-ns sampling; their true analog widths are not measured.',
        'The DMA sample rate is nominal; missed individual timer requests are not all detectable by flags.',
        'No qualified phase current, IPM VCC/CIN or internal junction temperature measurement is available.',
        'A 51-C cached temperature and DP mask do not identify or categorically exclude an internal thermal cause.',
        'Three nominal 200-ns LOW samples do not prove an exact 600-ns analog width; ideal sampling allows roughly400..800ns.',
        'That interval overlaps BKF9 qualification659..753ns; this trace does not demonstrate a broken filter.',
    ],
}
assert result['transport_counters_zero'] and result['event_tick_matches']
assert result['break_filter_code_at_event']==9
(P/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    t0 = r['start_monotonic_s']
    monitored = [x for x in rows if x['source']=='monitor' and x['host_monotonic_s']>=t0]
    fig,axes = plt.subplots(2,1,figsize=(10,6),layout='constrained')
    axes[0].step([x['host_monotonic_s']-t0 for x in monitored],[x['status'].get('freq_cmd',0) for x in monitored],where='post',label='Задание')
    axes[0].plot([x['host_monotonic_s']-t0 for x in monitored],[x['status'].get('mc_frequency_reference_hz',0) for x in monitored],'.-',label='Частота поля контроллера')
    axes[0].set(xlabel='Время после запроса START, с',ylabel='Гц',title='BKF9: ступени 5–20 Гц выдержаны; Break на этапе 25 Гц')
    axes[0].legend();axes[0].grid(alpha=.25)
    for x in wave['runs']:
        axes[1].plot([x['from_us'],x['to_us']],[x['level']]*2,color='#147c80',linewidth=1.5)
    for a,b in zip(wave['runs'],wave['runs'][1:]):
        axes[1].plot([a['to_us']]*2,[a['level'],b['level']],color='#147c80',linewidth=1)
    axes[1].axvline(0,color='#b84030',linestyle='--',label='Публикация Break IRQ')
    axes[1].set(xlabel='Номинальное время относительно публикации IRQ, мкс',ylabel='PA6 / SD',yticks=[0,1],ylim=(-.15,1.15),title='SD при BKF9: ближайший LOW — 3 отсчёта (номинально 0,6 мкс)')
    axes[1].legend();axes[1].grid(alpha=.25)
    fig.savefig(P/'run_and_sd.png',dpi=160)
except ImportError:
    print('Plot library unavailable; JSON and raw record preserved.')

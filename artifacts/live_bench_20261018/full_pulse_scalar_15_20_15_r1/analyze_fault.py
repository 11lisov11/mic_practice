"""Preserve and verify the saved Break evidence; no bench access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

P=Path(__file__).resolve().parent
ROOT=P.parents[2]
r=json.loads((P/'report.json').read_text(encoding='utf-8'))
snapshot=json.loads((P/'after_break_snapshot.json').read_text(encoding='utf-8'))['data']
wave=json.loads((P/'after_bkin_trace.json').read_text(encoding='utf-8'))['data']
raw=bytes.fromhex(snapshot['mc_break_wave_hex']);assert len(raw)==320
spec=importlib.util.spec_from_file_location('fault_wave_decoder',ROOT/'artifacts/live_bench_20261018/bkin_full_pulse_r1/web_hmi/server.py')
server=importlib.util.module_from_spec(spec);sys.modules[spec.name]=server;spec.loader.exec_module(server)
decoded=server.bkin_wave_status(dict(snapshot,mc_fw_build=2026101802,mc_age_ms=r['final_status']['mc_age_ms']))
for key in ('reason','event_tick_ms','runs','sample_count','flags'):
    assert decoded[key]==wave[key],key
boot=next(x for x in snapshot['mc_break_snapshots'] if x['kind']=='first_since_boot')
assert boot['captured'] and boot['raw']['tick_ms']==wave['event_tick_ms']
assert boot['event']['bif'] and not boot['event']['b2if'] and not boot['event']['moe_at_irq']
assert decoded['reason']=='low_not_observed' and decoded['pulse_width_us'] is None
assert not any(decoded[k] for k in ('dma_error','sampling_overrun','run_overflow','timeout'))
assert decoded['runs']==[{'level':1,'samples':129,'from_us':-64,'to_us':65}]
(P/'bkin_wave.bin').write_bytes(raw)
(P/'decoded_wave.json').write_text(json.dumps(decoded,ensure_ascii=False,indent=2),encoding='utf-8')
r.update(physical_rotation_confirmed=True,speed_changes_confirmed=False,
    operator_observation='User observed smooth rotation followed by stopping; full return to 15 Hz was not completed.',
    fault_analysis={'classification':'TIM1 Break / MC_DP_FAULT 0x0400',
        'wave_sha256':hashlib.sha256(raw).hexdigest(),'event_tick_ms':wave['event_tick_ms'],
        'context_age_before_irq_ms':23,'cached_field_reference_hz':20,
        'cached_vbus_v':318,'cached_temperature_c':51,
        'pa6_high_at_irq':True,'low_observed_in_dma':False,'pulse_width_us':None,
        'source_physical_identified':False,'trace_dma_error':False,
        'new_uno_noise_advisories':28-14,
        'not_established':['Exact pulse width','Sub-microsecond pulse versus an event preceding the 64-us history',
            'Overcurrent versus driver UVLO versus noise or another Break source',
            'Causal link to request to decrease from 20 to 15 Hz'],
        'notes':['Event context is cached, not simultaneous analog measurements.',
            'Command to decrease to 15 Hz overlaps the fault observation; controller reference was still 20 Hz.',
            'Only MC_DP_FAULT is recorded; no software temperature or bus-voltage fault was captured.',
            'Hardware NOISE advisory counts are not CRC or sequence failures.',
            'First-start snapshot flag was stale after RUN; this is a RUN fault, not a failed initial START.'],
        'primary_source':'https://www.st.com/resource/en/datasheet/stgib15ch60ts-l.pdf',
        'source_note':'SD fault management sections 4/4.1: CIN and VCC faults share the output; RC affects duration.',
        'next_measurement':'A longer pretrigger history and faster or hardware edge capture with bounded overflow reporting; do not mask Break.'})
if 'telemetry_summary' in r:r['telemetry_summary']['physical_rotation_confirmed']=True
(P/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'fault_record_verified':True,'event_tick_ms':wave['event_tick_ms'],
    'low_observed':False,'duration_unknown':True,'physical_rotation_confirmed':True,'motor_commands':0}))

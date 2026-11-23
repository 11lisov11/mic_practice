"""Offline candidate: coherent observer input and immutable first-loss trace.

Never writes a board or an existing release/capture. Observer tuning and motor
protection thresholds remain unchanged. Hardware qualification is still required.
"""
import inspect
import json
from pathlib import Path
import prepare_observer_trace as trace
from prepare_standstill_commissioning import ROOT, read, write, once
from prepare_cin_sd_diag import sha

BASE = ROOT / 'artifacts/live_bench_20261114/repeat_break_capture_r1'
OUT = ROOT / 'artifacts/live_bench_20261114/observer_input_epoch_r1'
NEW = (2026111403, 2026111404)


def main():
    assert not OUT.exists(), 'Never overwrite firmware or evidence'
    for rel, digest in json.loads(read(BASE / 'source_hashes.json')).items():
        assert sha(BASE / rel) == digest, rel
    # Reuse the reviewed first-loss recorder integration, targeting the ACTUAL
    # installed repeat-Break release rather than its older 3013/3014 ancestor.
    source = inspect.getsource(trace.main)
    source = source.replace('2026103013', '2026111401').replace('2026103014', '2026111402')
    source = source.replace('2026103016U', str(NEW[1]) + 'U')
    source = source.replace('3013-boot-capture', '111401-repeat-break')
    source = source.replace('3015-observer-trace', '111403-observer-input')
    scope = dict(trace.__dict__, BASE=BASE, OUT=OUT, NEW=NEW)
    exec(compile(source, __file__, 'exec'), scope)
    scope['main']()

    f = OUT / 'nucleo/Src/multi_native.c'
    s = read(f)
    s = once(s, 'static volatile float bin_va,bin_vb;', '''static volatile float bin_va,bin_vb;
/* Published by the SAME sequence as voltage and time. Never substitute the
 * newest foreground ADC sample for the endpoint of an older completed bin. */
static ma_current_sample bin_current;''')
    s = once(s, '  memset(&cached_sample,0,sizeof(cached_sample));return 1;',
        '  memset(&bin_current,0,sizeof(bin_current));\n  memset(&cached_sample,0,sizeof(cached_sample));return 1;')
    s = once(s, '''  ma_current_sample sample;
  if(!mic_current_fast(&sample)||!sample.valid||!sample.zero)return;
  /* Snapshot completed voltage accumulator''', '''  ma_current_sample sample;
  /* Snapshot completed voltage accumulator''')
    s = once(s, '  uint32_t seq=telemetry_seq,stamp=bin_cycles;float va=bin_va,vb=bin_vb;',
        '  uint32_t seq=telemetry_seq,stamp=bin_cycles;float va=bin_va,vb=bin_vb;\n  sample=bin_current;')
    s = once(s, '  const float dt=(float)(stamp-estimate_cycles)/SystemCoreClock;',
        '  if(!sample.valid||!sample.zero||sample.cycles!=stamp)return;\n  const float dt=(float)(stamp-estimate_cycles)/SystemCoreClock;')
    s = once(s, '++telemetry_seq;__DMB();bin_va=sum_va/16;bin_vb=sum_vb/16;bin_cycles=begin;',
        '++telemetry_seq;__DMB();bin_va=sum_va/16;bin_vb=sum_vb/16;\n    bin_current=sample;bin_cycles=sample.cycles;')
    write(f, s)
    # Explain explicitly that these are calculated estimates, not shaft truth.
    f = OUT / 'web_hmi/server.py'
    s = read(f).replace('Id/Iq и задания относятся к последнему fast-кадру входного bin;',
        'Токи, Id/Iq и задания относятся к сохранённому последнему ADC-кадру входного bin;')
    write(f, s)
    preserved = {}
    for folder in (BASE, ROOT / 'artifacts/live_bench_20261114'):
        for path in folder.rglob('*'):
            if path.is_file() and OUT not in path.parents and path.suffix in ('.json', '.jsonl', '.bin', '.log', '.txt', '.png'):
                preserved[path.relative_to(ROOT).as_posix()] = sha(path)
    write(OUT / 'preserved_capture_hashes.json', json.dumps(preserved, indent=2))
    m = json.loads(read(OUT / 'manifest.json'))
    m.update(base_pair=[2026111401, 2026111402], built=False, installed=False,
        coherent_bin_current=True, observer_tuning_changed=False,
        physical_cause_of_recorded_loss_proven=False, recorded_flux_NIS_IdIq_available=False,
        repeat_Break_capture_preserved=True, target_timing_requalification_required=True)
    write(OUT / 'manifest.json', json.dumps(m, indent=2) + '\n')
    print('Prepared coherent observer-input candidate', NEW, 'offline only')


if __name__ == '__main__':
    main()

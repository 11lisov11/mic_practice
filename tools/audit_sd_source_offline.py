"""Read saved SD evidence and write an offline source-localization report.

No network, GPIO writes, flash, reset or motor commands.
"""
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'artifacts/live_bench_20261030/observer_trace_r1'


def main():
    out = PACKAGE / 'SD_source_investigation_r1'
    out.mkdir(exist_ok=False)
    wave = ROOT / 'artifacts/live_bench_20261021/sd_dual_hv_idle_r1/bkin_wave.bin'
    raw = wave.read_bytes()
    header = struct.unpack_from('<16I', raw)
    assert len(raw) == 320 and header[0] == 0x314E4B42 and header[1] == 5
    assert header[15] == 1 and header[8] <= 32
    runs = [struct.unpack_from('<2I', raw, 64 + 8*i) for i in range(header[8])]
    assert sum(count for state, count in runs) == header[7]
    low6 = sum(count for state, count in runs if not state & 1)
    low4 = sum(count for state, count in runs if not state & 2)
    assert low6 == 90993 and low4 == 0
    audit = PACKAGE / 'SD_software_audit_r1'
    status = json.loads((audit / 'latest_status.json').read_text(encoding='utf-8'))['data']
    snapshots = json.loads((audit / 'latest_SD_snapshots.json').read_text(encoding='utf-8'))['data']
    first = snapshots['mc_break_snapshots'][0]['raw']
    bdtr = first['tim_bdtr']
    decoded = {
        'BDTR': bdtr, 'BKBID': bool(bdtr & (1 << 28)),
        'BKE': bool(bdtr & (1 << 12)), 'MOE': bool(bdtr & (1 << 15)),
        'AOE': bool(bdtr & (1 << 14)),
        'PA6_HIGH': bool(first['gpioa_idr'] & 64),
        'tick_ms': first['tick_ms'], 'context_valid': first['context_valid'],
    }
    assert not decoded['BKBID'] and decoded['BKE'] and not decoded['MOE']
    assert not decoded['PA6_HIGH']
    report = {
        'physical_root_cause_proven': False,
        'hardware_commands': 0, 'protection_changes': 0,
        'old_wave': {'path': str(wave), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'pa6_low_samples': low6, 'pa4_low_samples': low4,
                     'nominal_sample_ns': header[4], 'runs': runs},
        'new_snapshot': decoded,
        'latest_SD': status['mc_sd_live'],
        'zero_ready': status['mc_current_zero_ready'],
        'zero_offsets': status['mc_current_offsets_adc'],
        'nominal_SD_RC': {'R28_ohm': 10000, 'C20_pF': 330, 'tau_us': 3.3},
        'old_TP23_probe_continuity_independently_confirmed': False,
        'next_test': 'J1 and J4 OFF; controllers powered; unplug cable at STEVAL only; read PA6, no START',
        'HIGH_interpretation': 'LOW depends on STEVAL connection; does not prove internal IPM defect',
        'LOW_interpretation': 'LOW remains on cable/adapter/Nucleo side',
        'old_captures_modified': False,
    }
    (out / 'analysis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    note = '''# SD source investigation without START

The exact physical source is not established. A shared SD wire and one GPIO observation cannot distinguish an IPM open-drain output from another load or a wiring fault.

The new snapshot records Break at native tick 0, MOE=0 and no valid cached context. It predates FOC START. Its BDTR has BKBID=0, BKE=1 and AOE=0. The fresh live configuration check passes. RM0440 defines BKBID=0 as input mode, so releasing a supposed bidirectional-output latch is not a justified fix.

The installed source reads GPIOA IDR PA6 directly. The prior software audit checked all 256 flag combinations and separation from the stored fault mask. No native Src PA11 output initialization was found; this does not exclude hardware loading.

An independent unpack of the original saved 320-byte dual capture reproduces 90993 nominal 200-ns samples of PA6 LOW while PA4 stayed HIGH. The old TP23-to-PA4 branch continuity was not independently confirmed, so this motivates checking the signal route and does not prove an IPM defect.

UM2014 page 7 gives R28=10 kohm and C20=330 pF: tau=3.3 us. This nominal healthy RC alone cannot explain minutes of LOW. The actual fitted components have not been verified. Current zero-ready and midscale offsets do not qualify internal driver VCCL or identify UVLO.

STGIB15CH60TS-L fault management lists CIN overcurrent and VCC undervoltage as internal SD fault sources; SD is also an external shutdown input. No complete current pulse waveform or independent active-source readout is available. Do not infer UVLO, CIN fault or intrinsic module damage from the current single LOW.

Requested one passive split: with J1/J4 OFF and controllers powered, unplug the 34-pin cable at STEVAL, leaving it on IHM09M2. Read PA6 only. HIGH localizes dependence on the STEVAL connection; LOW leaves cable/adapter/Nucleo. No START is permitted with the protection connection removed. No protection edits, RESET, CLEAR or flashing were performed. Old records remain unchanged.

Primary references:
- https://www.st.com/resource/en/reference_manual/dm00355726-stm32g4-series-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf (TIM1/TIM8/TIM20 BDTR BKBID)
- https://www.st.com/resource/en/datasheet/stgib15ch60ts-l.pdf (DS10424 Rev10 fault management)
- https://www.st.com/resource/en/schematic_pack/x-nucleo-ihm09m2_schematic.pdf
- Local UM2014 Rev3, pages 7 and 11.
'''
    (out / 'REPORT.md').write_text(note, encoding='utf-8')
    hashes = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
              for f in out.iterdir() if f.is_file()}
    (out / 'saved_files_sha256.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print(json.dumps({'saved': str(out), 'old_wave_replayed': True,
                      'pa6_low_samples': low6, 'pa4_low_samples': low4,
                      'new_snapshot': decoded, 'hardware_commands': 0}))


if __name__ == '__main__':
    main()

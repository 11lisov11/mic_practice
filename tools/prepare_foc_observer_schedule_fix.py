"""Prepare an offline scheduling candidate; no hardware operations."""
import json
import os
import shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT, read, write, once

BASE = ROOT / 'artifacts/live_bench_20261029/foc_estimate_publish_fix_r2'
OUT = ROOT / 'artifacts/live_bench_20261029/foc_observer_schedule_fix_r1'
NEW = (2026103011, 2026103012)


def main():
    assert not OUT.exists()
    for folder in ('nucleo', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        def cp(src, dst):
            rel = Path(src).relative_to(BASE / folder)
            if folder == 'libraries' or (folder == 'nucleo' and rel.parts[0] in ('Drivers', 'MCSDK_v6.4.2-Full')):
                os.link(src, dst)
                return dst
            return shutil.copy2(src, dst)
        shutil.copytree(BASE / folder, OUT / folder, copy_function=cp,
            ignore=shutil.ignore_patterns('Debug', 'Release', '__pycache__', '*.pyc', '*.log'))
    for folder in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR', 'web_hmi'):
        for f in (OUT / folder).rglob('*'):
            if f.is_file():
                s = read(f)
                n = s.replace('2026103009', '2026103011').replace('2026103010', '2026103012').replace('3009-estimate-publish', '3011-observer-schedule')
                if n != s:
                    write(f, n)
    # Preserve every multiply/add and their order, with no fast-math or a new
    # covariance approximation. Only ask the compiler to remove the six-trip
    # induction/branch overhead in the three matrix dot products.
    f = OUT / 'nucleo/Inc/motor_control.h'
    s = read(f)
    for declaration in ('float aa=0;', 'float v=0;'):
        anchor = declaration + 'for(unsigned k0=0;k0<6;k0++)'
        count = 1 if declaration == 'float aa=0;' else 2
        assert s.count(anchor) == count
        s = s.replace(anchor, declaration + '\n#pragma GCC unroll 6\n    for(unsigned k0=0;k0<6;k0++)')
    s = s.replace('v+=f[i][k0]*o->p[k0][j];tmp[i][j]=v;',
                  'v+=f[i][k0]*o->p[k0][j];\n    tmp[i][j]=v;')
    write(f, s)
    # The UART ISR still receives every byte, with the same IRQ priorities,
    # CRC, frame deadline, recovery budget and fail-stop watchdog. Foreground
    # parsing yields between bytes rather than draining 43 before checking the
    # completed observer input again. STOP/CLEAR semantics are untouched.
    f = OUT / 'nucleo/Src/main.c'
    s = read(f)
    s = once(s, '    uno_consume_sample(byte, flags);',
        '    uno_consume_sample(byte, flags);\n    ma_native_service(); /* bounded foreground yield; never from USART IRQ */')
    write(f, s)
    # Reduce longest foreground CRC sections, without changing any wire bit or
    # accepting damaged packets. A small read-only reflected CRC32C nibble table
    # performs the same eight polynomial steps as two four-bit steps.
    table = []
    for nibble in range(16):
        crc = nibble
        for _ in range(4):
            crc = (crc >> 1) ^ (0x82f63b78 if crc & 1 else 0)
        table.append(crc)
    replacement = '''static inline uint32_t uv3_crc32c(const uint8_t *data, size_t length) {
  static const uint32_t table[16]={TABLE};
  uint32_t crc=UINT32_C(0xffffffff);
  for(size_t i=0;i<length;++i){
    crc^=data[i];
    crc=(crc>>4)^table[crc&15U];
    crc=(crc>>4)^table[crc&15U];
  }
  return ~crc;
}'''.replace('TABLE', ','.join('UINT32_C(0x%08x)' % x for x in table))
    from test_foc_update_latency_fix import function
    for folder in ('nucleo/Inc', 'UNOQ_MOTOR'):
        f = OUT / folder / 'uart_v3_transport.h'
        s = read(f)
        write(f, once(s, function(s, 'uv3_crc32c'), replacement))
    write(OUT / 'manifest.json', json.dumps(dict(pair=list(NEW), base_pair=[2026103009, 2026103010],
        built=False, installed=False, hardware_commands=0, START=0, CLEAR=0,
        trip_A=1.35, ADC_guard_ticks=2048, estimate_age_limit_ms=2,
        safety_cache_age_ms=1, fast_budget_cycles=5312,
        thresholds_changed=False, IRQ_priorities_changed=False, observer_equations_changed=False,
        observer_unroll_requested=True, UART_foreground_yields=True, CRC32C_wire_unchanged=True,
        physical_5s_not_proven=True), indent=2) + '\n')
    print('Prepared3011/3012 offline; no hardware access')


if __name__ == '__main__':
    main()

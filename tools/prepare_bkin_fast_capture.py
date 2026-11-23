"""Prepare an offline faster BKIN recorder. Never contacts a device."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'artifacts/live_bench_20261018/bkin_full_pulse_r1'
OUT = ROOT/'artifacts/live_bench_20261018/bkin_fast_capture_r1'
T = ROOT/'tools/bkin_fast_capture'

def read(p): return p.read_text(encoding='utf-8-sig')
def write(p, s): p.write_text(s, encoding='utf-8', newline='\n')
def once(s, a, b):
    assert s.count(a) == 1, (a, s.count(a))
    return s.replace(a, b)

def main():
    if OUT.exists(): raise RuntimeError('refusing to overwrite candidate')
    for name in ('nucleo', 'UNOQ_MOTOR', 'web_hmi'):
        shutil.copytree(BASE/name, OUT/name, ignore=shutil.ignore_patterns(
            'build', 'Debug', 'Release', '.metadata', '.settings', '__pycache__', '.lock'))
    for d in ('build/nucleo', 'build/uno', 'selftest'): (OUT/d).mkdir(parents=True)
    for folder in ('nucleo/Inc', 'UNOQ_MOTOR'):
        for name in ('pulse_core.h', 'pulse_record.h'): shutil.copyfile(T/name, OUT/folder/name)
    p = OUT/'nucleo/Inc/bkin_wave_capture.h'
    s = read(p).replace('1000000U', '5000000U').replace('1024U', '8192U').replace('SCHEMA 3U', 'SCHEMA 4U')
    write(p, s)
    p = OUT/'nucleo/Src/main.c'; s = read(p)
    s = once(s, 'volatile uint32_t mic_bkin_ring[', 'volatile uint16_t mic_bkin_ring[')
    a = s.index('static bool mic_bkin_dma_initialized;'); b = s.index('static void mic_bkin_wave_packet(', a)
    write(p, (s[:a]+read(T/'firmware.inc')+'\n'+s[b:]).replace('2026101802', '2026101804'))
    for rel in ('nucleo/Inc/break_wire.h', 'UNOQ_MOTOR/break_wire.h',
                'UNOQ_MOTOR/nucleo_fault_diagnostics.h', 'UNOQ_MOTOR/UNOQ_MOTOR.ino'):
        p = OUT/rel
        write(p, read(p).replace('2026101802', '2026101804').replace('2026101803', '2026101805'))
    p = OUT/'UNOQ_MOTOR/bkin_wave_wire.h'
    s = once(read(p), 'static inline bool bkw_receive(', '''static inline void bkw_reset(bkw_receiver *rx) {
  memset(rx,0,sizeof(*rx));
}

/* Share the ordinary reply's reboot/gap decision with the snapshot cache. */
static inline bool bkw_peer_reset(bkw_receiver *rx, uint32_t old_build,
    uint32_t new_build, uint32_t old_good, uint32_t new_good, uint32_t old_age_ms) {
  const bool reset=bw_peer_reset_required(old_build,new_build,old_good,new_good,old_age_ms);
  if (reset) bkw_reset(rx);
  return reset;
}

static inline bool bkw_receive(''')
    write(p, s)
    p = OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino'
    s = once(read(p), '  if (bw_peer_reset_required(previous_build,g_bp_fw_build,previous_good,g_bp_good_cnt,previous_age))',
        '  if (bkw_peer_reset(&g_bkin_wave,previous_build,g_bp_fw_build,previous_good,g_bp_good_cnt,previous_age))')
    write(p, s)
    p = OUT/'web_hmi/server.py'
    s = read(p).replace('2026101802', '2026101804').replace('2026101803', '2026101805')
    s = once(s, '        (2026101805, 2026101804),',
        '        (2026101803, 2026101802),\n        (2026101805, 2026101804),')
    a = s.index('def bkin_wave_status('); b = s.index('\n\nSTATE_NAMES =', a)
    write(p, s[:a]+read(T/'decoder.py')+s[b:])
    files = {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR', 'web_hmi')
        for p in (OUT/folder).rglob('*') if p.is_file()}
    m = dict(schema='mic_ai.bkin_fast_capture_candidate.v1', candidate=str(OUT), predecessor=str(BASE),
        pair_compatibility_ids=[2026101805,2026101804], source_sha256=files,
        calibration_changed=False, control_protocol_changed=False, pwm_or_motor_control_changed=False,
        hardware_commands=0, mcu_flash_commands=0, motor_commands=0, operationally_qualified=False,
        hv_release_approved=False, built=False, selftest_pass=False,
        requested_sample_rate_hz=5000000, sample_period_ns=200, prehistory_samples=2048,
        prehistory_us=409.6, ring_samples=8192, ring_bytes=16384, max_post_trigger_ms=100)
    write(OUT/'manifest.json', json.dumps(m, indent=2)+'\n')
    print(OUT)

if __name__ == '__main__': main()

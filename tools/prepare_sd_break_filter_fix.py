"""Prepare a narrowly scoped BKIN filter candidate; no device access."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/live_bench_20261018/uart_tx_dma_fix_r2'
HMI = ROOT / 'artifacts/live_bench_20261018/uart_tx_dma_manual_hmi_fix_r1/server.py'
OUT = ROOT / 'artifacts/live_bench_20261020/sd_break_filter_fix_r1'
OLD = (2026101813, 2026101812)
NEW = (2026102001, 2026102002)
FILTER_OLD = '  sBreakDeadTimeConfig.BreakFilter = 3;'
FILTER_NEW = '''  /* BKF=9: fDTS/8, eight consecutive samples. With TIM1=170 MHz,
   * CKD=2 this is 659..753 ns qualification (sampling phase dependent).
   * Reject sub-600 ns SD disturbances; retain BKE and hardware IPM shutdown.
   * This intentionally adds <1 us to MCU Break, not to internal IPM protection.
   * Do not replace by software debounce or automatic restart after a fault. */
  sBreakDeadTimeConfig.BreakFilter =
      LL_TIM_BREAK_FILTER_FDIV8_N8 >> TIM_BDTR_BKF_Pos;'''
CONFIG_OLD = '          (TIM_BDTR_BKE | TIM_BDTR_BKP);'
CONFIG_NEW = '''          (TIM_BDTR_BKE | TIM_BDTR_BKP) &&
      (TIM1->BDTR & TIM_BDTR_BKF) == LL_TIM_BREAK_FILTER_FDIV8_N8 &&
      (TIM1->CR1 & TIM_CR1_CKD) == TIM_CLOCKDIVISION_DIV2 &&
      (TIM1->BDTR & TIM_BDTR_AOE) == 0U;'''


def read(p):
    return p.read_text(encoding='utf-8-sig')


def once(s, old, new):
    assert s.count(old) == 1, (old, s.count(old))
    return s.replace(old, new)


def hmi_source():
    s = read(HMI)
    s = once(s, '        (2026101813, 2026101812),',
             '        (2026101813, 2026101812),\n        (2026102001, 2026102002),')
    s = once(s, '(2026101813,2026101812)) and', '(2026101813,2026101812),(2026102001,2026102002)) and')
    # Only peer allowlists; never turn a two-element identity pair into a triple.
    lines = []
    for line in s.splitlines(keepends=True):
        if 'not in (' in line:
            line = line.replace(',2026101812)', ',2026101812,2026102002)')
            line = line.replace(', 2026101812)', ', 2026101812, 2026102002)')
        lines.append(line)
    return ''.join(lines)


def main():
    if OUT.exists():
        raise RuntimeError('preserve existing candidate')
    assert hashlib.sha256(HMI.read_bytes()).hexdigest() == '1f9393cb777564609a287deab2aece802ddd8480a5ec8151ef2a8fe26bde66f1'
    for tree in ('nucleo', 'UNOQ_MOTOR', 'web_hmi'):
        shutil.copytree(BASE / tree, OUT / tree, ignore=shutil.ignore_patterns(
            'build', 'Debug', 'Release', '.metadata', '.settings', '__pycache__', '.lock'))
    for tree in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR'):
        for p in (OUT / tree).rglob('*'):
            if p.is_file():
                before = read(p)
                after = before.replace(str(OLD[0]), str(NEW[0])).replace(str(OLD[1]), str(NEW[1]))
                if after != before:
                    p.write_text(after, encoding='utf-8', newline='\n')
    p = OUT / 'nucleo/Src/main.c'
    s = once(read(p), FILTER_OLD, FILTER_NEW)
    s = once(s, CONFIG_OLD, CONFIG_NEW)
    p.write_text(s, encoding='utf-8', newline='\n')
    p = next((OUT / 'nucleo').glob('*.ioc'))
    p.write_text(once(read(p), 'TIM1.BreakFilter=3\n', 'TIM1.BreakFilter=9\n'), encoding='utf-8', newline='\n')
    # Preserve the working old identities too: HMI is deployed before the MCUs.
    (OUT / 'web_hmi/server.py').write_text(hmi_source(), encoding='utf-8', newline='\n')
    m = dict(schema='mic_ai.sd_break_filter_fix.v1', pair_compatibility_ids=list(NEW),
             predecessor=str(BASE), hmi_predecessor=str(HMI), built=False, selftest_pass=False,
             calibration_changed=False, control_protocol_changed=False, vf_or_pwm_timing_changed=False,
             break_filter_changed=True, break_filter_before=3, break_filter_after=9,
             break_filter_sampling_hz=10625000, break_filter_samples=8,
             break_qualification_phase_range_ns=[7 / 10625000 * 1e9, 8 / 10625000 * 1e9],
             internal_ipm_protection_changed=False, automatic_restart_added=False,
             recovery_budget_changed=False, watchdog_changed=False, tx_backend_changed=False,
             hardware_commands=0, motor_commands=0, mcu_flash_commands=0,
             operationally_qualified=False, physical_sd_cause_proven=False,
             limitations=['Digital filter timing model is not a hardware qualification.',
                          'Short SD source remains unproven; actual IPM faults must still stop PWM.',
                          'IPM datasheet 24/70 us hold times are typical, not guaranteed minima.'])
    (OUT / 'manifest.json').write_text(json.dumps(m, indent=2) + '\n', encoding='utf-8')
    print(OUT)


if __name__ == '__main__':
    main()

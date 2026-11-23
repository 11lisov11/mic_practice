"""Prepare additive SD telemetry; never touches the bench or its calibration."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/live_bench_20261018/uart_resync_fix_r1'
OUT = ROOT / 'artifacts/live_bench_20261018/sd_live_diagnostics_r1'


def read(path):
    return path.read_text(encoding='utf-8-sig')


def write(path, source):
    path.write_text(source, encoding='utf-8', newline='\n')


def once(source, before, after):
    assert source.count(before) == 1, (before, source.count(before))
    return source.replace(before, after)


def main():
    if OUT.exists():
        raise RuntimeError('preserve the existing candidate')
    for tree in ('nucleo', 'UNOQ_MOTOR', 'web_hmi'):
        shutil.copytree(BASE / tree, OUT / tree, ignore=shutil.ignore_patterns(
            'build', 'Debug', 'Release', '.metadata', '.settings', '__pycache__', '.lock'))
    # Keep all earlier calibration identities accepted, including the running pair.
    for tree in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR'):
        for path in (OUT / tree).rglob('*'):
            if path.is_file():
                source = read(path)
                updated = source.replace('2026101807', '2026101809').replace('2026101806', '2026101808')
                if updated != source:
                    write(path, updated)
    shutil.copyfile(ROOT / 'tools/sd_live_status.h', OUT / 'nucleo/Inc/sd_live_status.h')
    path = OUT / 'nucleo/Src/main.c'
    source = read(path)
    source = once(source, '#include "pulse_core.h"', '#include "pulse_core.h"\n#include "sd_live_status.h"')
    source = once(source, '  reply[21] = UNO_TEMP_VALID;', '''  reply[21] = UNO_TEMP_VALID;
  /* Additive status only: read GPIO/timer registers, never drive SD or rearm.
     Upper temperature-flag bits were reserved in older peer identities. */
  const bool sd_config_ok =
      ((GPIOA->MODER >> 12U) & 3U) == 2U &&
      (GPIOA->OTYPER & GPIO_PIN_6) != 0U &&
      ((GPIOA->PUPDR >> 12U) & 3U) == 1U &&
      ((GPIOA->AFR[0] >> 24U) & 15U) == 6U &&
      (TIM1->AF1 & (TIM1_AF1_BKINE | TIM1_AF1_BKINP)) ==
          (TIM1_AF1_BKINE | TIM1_AF1_BKINP) &&
      (TIM1->BDTR & (TIM_BDTR_BKE | TIM_BDTR_BKP | TIM_BDTR_BKBID)) ==
          (TIM_BDTR_BKE | TIM_BDTR_BKP);
  reply[21] |= sd_live_encode((GPIOA->IDR & GPIO_PIN_6) != 0U,
      (TIM1->DIER & TIM_DIER_BIE) != 0U,
      mic_bkin_capture_state == MIC_BKIN_RUNNING,
      mic_bkin_record_ready != 0U, sd_config_ok);''')
    write(path, source)
    path = OUT / 'web_hmi/server.py'
    source = read(path)
    # Accept both existing record identities; old saved evidence stays readable.
    source = source.replace("!=2026101806:", " not in (2026101806,2026101808):")
    source = source.replace('peer!=2026101806', 'peer not in (2026101806,2026101808)')
    source = once(source, '2026101702, 2026101806) or not',
                  '2026101702, 2026101806, 2026101808) or not')
    source = once(source, 'h[:4]!=(0x31545255,1,320,2026101806)',
                  "h[:4]!=(0x31545255,1,320,_as_int(data,'mc_fw_build',0))")
    source = once(source, '        (2026101807, 2026101806),',
                  '        (2026101807, 2026101806),\n        (2026101809, 2026101808),')
    source = once(source, 'def bkin_wave_status(data):',
                  read(ROOT / 'tools/sd_live_decoder.py') + '\n\ndef bkin_wave_status(data):')
    source = once(source, '        data["mc_fault_detail"] = motor_fault_detail(data)',
                  '        data["mc_fault_detail"] = motor_fault_detail(data)\n'
                  '        data["mc_sd_live"] = sd_live_status(data)\n'
                  '        data["mc_fault_detail"] += "; " + data["mc_sd_live"]["summary_ru"]')
    source = once(source,
                  "            'event_tick_ms':tick,'sample_period_us':0.2,'sample_rate_hz':5000000,",
                  "            'event_tick_ms':tick,'sample_period_us':0.2,'sample_rate_hz':5000000,\n"
                  "            'live_sd':sd_live_status(data),")
    source = once(source,
                  "summary=('PA6 не завершил импульс за окно 100 мс. Запись обрезана по тайм-ауту; полной длительности нет.'",
                  "summary=('В сохранённом окне PA6 оставался LOW до конца 100 мс. Текущий уровень этим не измерен; полная длительность неизвестна.'")
    write(path, source)
    path = OUT / 'web_hmi/static/app.js'
    source = read(path)
    source = once(source, '  d.driveDiagPower.textContent = `DC-шина ${vdcText} · радиатор IPM ${tempText}`;',
                  '  const sdText = data.mc_sd_live?.summary_ru || "Текущий SD: нет измерения";\n'
                  '  d.driveDiagPower.textContent = `DC-шина ${vdcText} · радиатор IPM ${tempText} · ${sdText}`;')
    source = once(source, '`Активный PA6 LOW: ${pulses || "не обнаружен"}; `',
                  '`Сохранённый PA6 LOW: ${pulses || "не обнаружен"}; `')
    start = source.index('    const pulses = (trace.pa6_low_intervals || [])')
    end = source.index('\n  } catch (error) {', start)
    source = source[:start] + '    bkinTraceStatus.textContent = describeBkinTrace(trace);' + source[end:]
    source = once(source, 'async function loadBkinTrace() {',
                  read(ROOT / 'tools/sd_trace_description.js') + '\n\nasync function loadBkinTrace() {')
    write(path, source)
    manifest = dict(schema='mic_ai.sd_live_diagnostics.v1', pair_compatibility_ids=[2026101809,2026101808],
        predecessor=str(BASE), built=False, selftest_pass=False, calibration_changed=False,
        control_protocol_changed=False, pwm_or_motor_control_changed=False, recovery_budget_changed=False,
        watchdog_changed=False, physical_sd_cause_proven=False, operationally_qualified=False,
        hv_release_approved=False, hardware_commands=0, motor_commands=0, mcu_flash_commands=0)
    write(OUT / 'manifest.json', json.dumps(manifest, indent=2)+'\n')
    print(OUT)


if __name__ == '__main__':
    main()

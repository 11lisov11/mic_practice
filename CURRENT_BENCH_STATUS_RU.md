# Текущий статус стенда

- Сформировано: `2026-07-26T23:32:40`
- Проект: `C:\mic_practice`
- Active PWM разрешен: **ДА**
- Build-only preflight свежий и прошел: **ДА**
- Bringup/readiness готов: **НЕТ**

## Решение

Bench-gate сейчас зеленый. Перед активным запуском все равно вручную проверь E-STOP, ограничение тока, схему коммутации и фактическое питание стенда.

## Последние доказательства

- Bench-gate summary: `C:\mic_practice\tools\_preflight_exports\bench_gate_report_20260726_233228\summary.json`
- Bench-gate operator steps: `C:\mic_practice\tools\_preflight_exports\bench_gate_report_20260726_233228\NEXT_STEPS_RU.md`
- Build-only summary: `C:\mic_practice\tools\_preflight_exports\full_system_preflight_20260726_223022_486670\summary.json`
- Readiness summary: `C:\mic_practice\tools\_readiness_exports\research_readiness_20260726_233238_607662\summary.json`

## Запреты до зеленого gate

- Не запускать active PWM без `ready_for_active_pwm=true`.
- Не выполнять `bluepill_runtime_static_preflight.py --confirm-hv-off`, пока HV/J7 не отключена и DC-шина не разряжена.
- Не выполнять `bluepill_static_low_preflight.py --confirm-hv-off`, пока HV/J7 не отключена и DC-шина не разряжена.
- UART loopback делать только при отключенных TX/RX от STM32: коротить TX-RX нужно на стороне USB-UART/изолятора.
- Не держать HMI/serial monitor открытым во время UART loopback на том же COM-порту.
- Если JSON и этот файл расходятся, главным считается свежий `summary.json`; затем нужно заново запустить генератор статуса.
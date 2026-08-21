# Текущий статус стенда

- Сформировано: `2026-08-21T05:46:06`
- Проект: `C:\mic_practice`
- Active PWM разрешен: **НЕТ**
- Build-only preflight свежий и прошел: **ДА**
- Bringup/readiness готов: **НЕТ**

## Решение

Active PWM сейчас **не запускать**. Не подавать `START` и не включать HV/J7 для обхода красного gate.

## Почему gate красный

- Runtime-static: реального upload+Saleae static capture для актуальной прошивки нет или он не прошел; последний summary: `C:\mic_practice\tools\_preflight_exports\bluepill_runtime_static_preflight_20260809_202000_627164_47008\summary.json`.
- Важно: свежий build-only доказывает только сборку firmware/tooling; Blue Pill считается неподтвержденным, пока `bluepill_runtime_static_preflight.py --confirm-hv-off` не прошьет актуальную runtime-прошивку и не снимет новый Saleae static capture.
- Saleae freshness: статический Saleae capture старше свежей build-only сборки; capture: `C:\mic_practice\tools\_preflight_exports\post_enable_confirm_static_retry_20260809\saleae_highlevel_probe_20260809_204839_485516_15400\summary.json`, build: `C:\mic_practice\tools\_preflight_exports\full_system_preflight_20260821_054507_338182\summary.json`. После прошивки нужен новый static capture CH0..CH6.
- UART STM32: protocol не подтвержден, next_actions=write_ok_no_bluepill_response; port=COM3: WCH USB serial device; verify this is the isolated USB-UART wired to STM32 PA2/PA3; visible_ports=pyserial=['COM3', 'COM4']; windows_pnp=['COM6', 'COM3', 'COM10', 'COM5', 'COM4']; counts=protocol=1,open_ok=1,write_returned=1,write_ok=1,flush_ok=1,write_timeouts=0,flush_timeouts=0,no_response=1,responses=0; auto_port_selection=selected=COM3,COM4; pnp_not_ok_skipped=COM6(Unknown, WCH CH340/CH341 USB-UART) | COM10(Unknown, Arduino UNO Q USB interface) | COM5(Unknown, Arduino UNO Q USB interface); ошибка=protocol_attempts:COM3@115200 no response; pc_direct_hmi=not_running; summary: `C:\mic_practice\tools\_preflight_exports\bluepill_uart_diagnose_20260808_204031_596867_41496\summary.json`.
- UART inventory-only: свежий безопасный снимок COM есть, но это не доказывает protocol/link; selected=COM3; visible=pyserial=['COM3', 'COM4']; windows_pnp=['COM6', 'COM3', 'COM10', 'COM5', 'COM4']; pc_direct_hmi=not_running; summary: `C:\mic_practice\tools\_preflight_exports\bluepill_uart_diagnose_20260808_204010_554853_41108\summary.json`.
- HMI /api/status: нет свежего live-status (URLError: <urlopen error timed out>).

## Что делать дальше

1. `check_stm32_uart_wiring_or_firmware`
   ПК уже может писать в UART, но STM32 не отвечает. Проверь перекрестные TX/RX, общий GND на изолированной стороне, питание STM32, USART2 PA2/PA3 и что загружена UART runtime-прошивка.

   ```powershell
   py -3 -u .\tools\bluepill_uart_diagnose.py --port COM3 --dtr-rts-matrix
   ```

2. `restore_hmi_safe_status`
   Восстанови live HMI/status до безопасного состояния. `/api/status` должен отвечать и показывать `SAFE`, `pwm=0`, `enable=false`, `estop=0`, `bp_fault=0`, `bp_bad/bp_bad_cnt=0`. Если выше есть `run_uart_loopback`, сначала заверши loopback, убери перемычку TX-RX и верни TX/RX к STM32; HMI и loopback не должны одновременно держать один COM-порт. Для PC-direct используй команду ниже; она не включает активный PWM и поднимает только safe status/HMI. Для UNO Q/ADB используй `ui_access.py` или `adb forward`.

   ```powershell
   py -3 -u .\tools\pc_direct_hmi_service.py start --serial COM3 --baud 115200 --port 18080
   ```

3. `run_runtime_static_preflight`
   Отключи HV/J7, дождись разряда DC-шины и только потом запускай команду ниже. Проверка прошьет актуальную runtime-прошивку Blue Pill и докажет через Saleae, что CH0..CH6 находятся в безопасном статическом состоянии. Если любой PWM-вход останется HIGH, active PWM запрещен до исправления GPIO, проводки или входов IPM.

   ```powershell
   py -3 -u .\tools\bluepill_runtime_static_preflight.py --confirm-hv-off
   ```

4. `refresh_saleae_static_probe`
   Сними новый статический захват Saleae по CH0..CH6 и пересчитай анализ PWM до любых активных тестов.

## Последние доказательства

- Bench-gate summary: `C:\mic_practice\tools\_preflight_exports\bench_gate_report_20260821_054552\summary.json`
- Bench-gate operator steps: `C:\mic_practice\tools\_preflight_exports\bench_gate_report_20260821_054552\NEXT_STEPS_RU.md`
- Build-only summary: `C:\mic_practice\tools\_preflight_exports\full_system_preflight_20260821_054507_338182\summary.json`
- Readiness summary: `C:\mic_practice\tools\_readiness_exports\research_readiness_20260821_054604_105989\summary.json`

## Запреты до зеленого gate

- Не запускать active PWM без `ready_for_active_pwm=true`.
- Не выполнять `bluepill_runtime_static_preflight.py --confirm-hv-off`, пока HV/J7 не отключена и DC-шина не разряжена.
- Не выполнять `bluepill_static_low_preflight.py --confirm-hv-off`, пока HV/J7 не отключена и DC-шина не разряжена.
- UART loopback делать только при отключенных TX/RX от STM32: коротить TX-RX нужно на стороне USB-UART/изолятора.
- Не держать HMI/serial monitor открытым во время UART loopback на том же COM-порту.
- Если JSON и этот файл расходятся, главным считается свежий `summary.json`; затем нужно заново запустить генератор статуса.
# Текущий статус стенда

- Сформировано: `2026-08-26T01:26:00`
- Проект: `C:\mic_practice`
- Активный motor backend: `nucleo_mcsdk_acim`
- Active PWM разрешен: **НЕТ**
- Build-only preflight свежий и прошел: **ДА**
- Bringup/readiness готов: **НЕТ**

## Решение

Active PWM сейчас **не запускать**. Не подавать `START` и не включать HV/J7 для обхода красного gate.

## Почему gate красный

- `nucleo_mcsdk_runtime_validation`: Аппаратное подтверждение ожидает платы: прошить обе платы при отключённой HV/J7, затем проверить UART и статические уровни PWM.

## Что делать дальше

1. `validate_nucleo_mcsdk_hardware`
   Оставить HV/J7 отключённой, разрядить DC-шину, прошить проверенные артефакты UNO Q и Nucleo, проверить sequence/CRC/тайм-аут 300 мс через USART1 PB6/PB7 и подтвердить Saleae безопасные статические уровни всех шести PWM-входов IPM.

## Последние доказательства

- Nucleo MCSDK build preflight: `C:\mic_practice\mcsdk_reference\AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV\STM32CubeIDE\Debug\mcsdk_release_preflight.json`
- Nucleo MCSDK runtime preflight: `нет`
- Build-only summary: `C:\mic_practice\tools\_preflight_exports\full_system_preflight_20260826_012447_774251\summary.json`
- Readiness summary: `C:\mic_practice\tools\_readiness_exports\research_readiness_20260826_012548_207012\summary.json`

## Запреты до зеленого gate

- Не запускать active PWM без `ready_for_active_pwm=true`.
- Не прошивать и не испытывать Nucleo/IPM с подключенной HV/J7 до статической проверки шести PWM-входов и аварийного останова.
- Не считать предупреждение `nucleo_mcsdk_hv_release_gate` разрешением на подачу высокого напряжения.
- UART loopback делать только при отключенных TX/RX от STM32: коротить TX-RX нужно на стороне USB-UART/изолятора.
- Не держать HMI/serial monitor открытым во время UART loopback на том же COM-порту.
- Если JSON и этот файл расходятся, главным считается свежий `summary.json`; затем нужно заново запустить генератор статуса.

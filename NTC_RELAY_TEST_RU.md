# Проверка Байпасного Реле NTC

Цель патча: проверить линию `NTC bypass relay` без запуска инвертора и без PWM.

Важно: это не внешнее `RELAY1 SRD-12VDC-SL-C` из `MIC_AI.pdf`.
Внешнее реле предзаряда по схеме управляется от `PB4`; для него см. `PRECHARGE_RELAY_TEST_RU.md`.

## Что Подключить

| Сигнал | Куда Подключить |
|---|---|
| Blue Pill `PB1` | STEVAL-IPM15B `J2-21 NTC bypass relay` |
| Blue Pill `GND` | общий логический `GND` STEVAL |
| Saleae `CH7` | Blue Pill `PB1` или STEVAL `J2-21`, опционально |
| Saleae `GND` | общий логический `GND` |

Для этого теста `J7/HV/DC bus` не нужен. Держать силовую шину отключенной.

## Что Делает Новый Режим

Команда `IOTEST ON` переводит UNO Q в сервисный I/O-режим:

- `pwm=0` остается выключенным;
- duty всех фаз передается как `0`;
- Blue Pill получает `ENABLE + MODE_DIAG`, но без `DIAG_PWM`;
- Blue Pill поэтому применяет внешний флаг `NTC`, но оставляет PWM-выходы выключенными;
- `IOTEST OFF`, `STOP` и `CLEAR` возвращают стенд в безопасное состояние.

## Быстрая Проверка Без Saleae

```powershell
py -3 -u .\tools\ntc_relay_preflight.py --url http://127.0.0.1:18080
```

Критерий:

- `overall_pass=true`;
- `state=SAFE`;
- `pwm=0`;
- `estop=0`;
- `bp_fault=0`;
- `bp_bad_cnt=0` или `bp_bad=0`;
- `ntc` переключается `1/0`;
- если поле `bp_ext` доступно, бит `0x01` переключается вместе с `ntc`.

## Проверка С Saleae

```powershell
py -3 -u .\tools\ntc_relay_preflight.py --url http://127.0.0.1:18080 --la-channel 7
```

Критерий Saleae:

- на `CH7` видно минимум `2 * cycles - 1` фронтов;
- `high_ratio` лежит в диапазоне `0.10..0.90`;
- финальный статус снова безопасный: `SAFE`, `pwm=0`, `ntc=0`.

## Ручные Команды

Если нужно дернуть реле вручную через HMI/API:

```text
IOTEST ON
NTC ON
NTC OFF
IOTEST OFF
STOP
CLEAR
```

Не использовать `START` для проверки этого реле.

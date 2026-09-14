# HIL-проверка аварийной линии STEVAL-IPM15B SD -> Nucleo BKIN

## Зачем нужен отдельный тест

Проверка шести сигналов PWM логическим анализатором подтверждает частоту, dead-time и отсутствие сквозного открытия, но не подтверждает аварийное отключение силового модуля. Поэтому `ipm_sd_bkin_hardware_trip_validated` остаётся отдельным обязательным release-gate.

По официальной документации ST:

- `STEVAL-IPM15B J2-1` называется `emergency stop` и электрически связан с двунаправленным open-drain выводом `SD`; контрольная точка этой цепи - `TP23`;
- `X-NUCLEO-IHM09M2 J7-1` проводит этот сигнал на `PA6/PA11 DIAG/ENABLE/BKIN1`;
- в текущем проекте `STM32G431RBT6` выбран `PA6 = TIM1_BKIN`, внешний сигнал активен низким уровнем, а `TIM_AUTOMATICOUTPUT_DISABLE` запрещает самопроизвольное восстановление PWM.

Источники: [ST UM2014](https://www.st.com/resource/en/user_manual/um2014-1500-w-motor-control-power-board-based-on-stgib15ch60tsl-sllimm-2nd-series-ipm-stmicroelectronics.pdf), [ST UM3030](https://www.st.com/resource/en/user_manual/um3030-getting-started-with-the-xnucleoihm09m2-motor-control-connector-expansion-board-for-stm32-nucleo-stmicroelectronics.pdf), [схема X-NUCLEO-IHM09M2](https://www.st.com/resource/en/schematic_pack/x-nucleo-ihm09m2_schematic.pdf).

## Условия низковольтного HIL

Этот тест выполняется отдельно от силового пуска. На этом этапе ПК и Saleae подключать разрешается, потому что сеть и DC-шина физически отсутствуют.

Обязательные условия:

- сетевой ввод отсоединён;
- мультиметр подтверждает менее `2 В` между `DC+` и `DC-`;
- разъём `STEVAL J7` снят;
- двигатель отключён от `J3 U/V/W`;
- используется только низковольтное питание логики и вспомогательное питание `J4`, не выше предела платы;
- общий провод Saleae подключён к общей логической земле только в этом обесточенном режиме.

Не считать отключение сетевого выключателя достаточным доказательством: требуется физически снятый `J7` и измеренная разряженная шина.

## Что записать

На Saleae одновременно записываются:

| Канал | Сигнал Nucleo | Назначение |
|---|---|---|
| CH0 | `PA8` | `UH` |
| CH1 | `PA7` | `UL` |
| CH2 | `PA9` | `VH` |
| CH3 | `PB0` | `VL` |
| CH4 | `PA10` | `WH` |
| CH5 | `PB1` | `WL` |
| CH6 | `PA6` или `STEVAL TP23` | `SD/BKIN`, active-low |

Названия относятся к текущему проекту MCSDK для `NUCLEO-G431RB + IHM09M2`; старую распиновку Blue Pill применять нельзя.

Запись должна доказать полный цикл:

1. При высоком уровне `SD` все шесть PWM работают в разрешённом низковольтном тестовом режиме.
2. Перевод `SD` в низкий уровень аппаратно прекращает переключения всех шести выходов.
3. После отпускания `SD` PWM не возобновляется сам.
4. Телеметрия Nucleo содержит ненулевой защёлкнутый отказ и `PWM_ACTIVE=0`.
5. Повторный запуск невозможен без явных `CLEAR`, нового `ARM` и новой команды `START`.

Линию `SD/TP23` разрешается принудительно тянуть вниз только в заранее проверенной низковольтной оснастке с последовательным резистором. Не замыкать контрольную точку случайным проводом и не выполнять этот тест при установленном `J7`.

## Протокол доказательства

Release-gate принимает только JSON `mic_ai.ipm_sd_bkin_hil.v1`, связанный SHA-256 с прошитым Nucleo HEX и исходным файлом захвата. Минимальная структура:

```json
{
  "schema": "mic_ai.ipm_sd_bkin_hil.v1",
  "pass": true,
  "tested_at": "2026-09-14T12:00:00+03:00",
  "operator": "Фамилия И.О.",
  "power_stage": "STEVAL-IPM15B",
  "adapter": "X-NUCLEO-IHM09M2",
  "mcu": "STM32G431RBT6",
  "conditions": {
    "mains_disconnected": true,
    "dc_bus_below_2v": true,
    "j7_disconnected": true,
    "motor_disconnected": true,
    "auxiliary_vcc_only": true
  },
  "checks": {
    "sd_normal_high": true,
    "sd_forced_low": true,
    "all_six_pwm_inactive_on_trip": true,
    "mc_fault_latched": true,
    "pwm_stays_inactive_after_sd_release": true,
    "explicit_clear_and_rearm_required": true
  },
  "nucleo_hex_sha256": "<SHA-256 прошитого HEX>",
  "capture": {
    "path": "capture/sd_bkin_trip.csv",
    "sha256": "<SHA-256 исходного захвата>"
  }
}
```

Проверка запускается вместе со сборкой:

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_firmware_bundle.ps1 `
  -IpmSdBkinEvidence C:\path\to\ipm_sd_bkin_hil.json
```

До появления такого протокола отсутствие ошибок компиляции, обычная осциллограмма PWM и программный `ESTOP` не закрывают этот gate.

## Переход к автономному HV

После низковольтного HIL все провода ПК, ST-Link, USB, Saleae и осциллографа снимаются физически. Нулевая и рабочая точки Vbus затем проверяются отдельно с телефона по Wi-Fi и автономным мультиметром по `AUTONOMOUS_VBUS_CALIBRATION_RU.md`. Эти две проверки не заменяют друг друга.

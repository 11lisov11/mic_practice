# PC Direct STM32 Architecture

> **REV 2.0:** PC-direct означает связь через carrier-board `ISO7721DWR`.
> `PC/USB-UART GND` остаётся `SAFE_GND` и не соединяется напрямую с Blue Pill
> `HOT_GND`. Любая старая прямая коммутация допустима только как отдельная
> диагностика при физически снятом J7/HV и разряженной DC-шине.

## Цель

Убрать UNO Q из runtime-цепочки управления силовой частью.

Новая цепочка:

```text
ПК / AI / HMI
  -> USB-UART 3.3 В на SAFE стороне
  -> JP_UART_TX/RX = PC
  -> ISO7721DWR
  -> STM32 Blue Pill
  -> STEVAL/IPM
```

UNO Q можно оставить позже как отдельную панель/экран, но не как обязательный
мост для PWM.

## Распределение ответственности

- ПК: AI/MIC, HMI, логирование, сценарии тестов, команды высокого уровня.
- STM32: PWM, deadtime, fault latch, timeout watchdog, ADC, AS5600, fan,
  precharge, brake, безопасное отключение при потере связи.
- STM32 обязан сам выключить PWM при потере кадров дольше `TIMEOUT_MS`.

## Текущие файлы

- `bluepill_uart_pwm_pio/` - firmware STM32.
- `tools/bluepill_uart_diagnose.py` - текущая безопасная диагностика
  USB-UART/loopback/protocol-связи со STM32.
- `tools/bluepill_direct_probe.py` - низкоуровневый legacy helper протокола;
  вручную для gate-проверок не запускать.
- `tools/unoq_web_server.py` - PC-direct HTTP/HMI над прямым UART к STM32.

Название `unoq_web_server.py` историческое. В режиме PC-direct он работает без
UNO Q и говорит напрямую с Blue Pill.

## Коммутация PC -> ISO7721 -> STM32

| Сигнал | SAFE сторона | HOT сторона после ISO7721 |
|---|---|---|
| TXD | USB-UART TX -> `JP_UART_TX.PC` | `PA3 / USART2_RX` |
| RXD | USB-UART RX <- `JP_UART_RX.PC` | `PA2 / USART2_TX` |
| GND | USB-UART GND -> `SAFE_GND` | Blue Pill GND -> `HOT_GND` |
| питание USB-UART | `NC` | Blue Pill питается отдельно от `HOT_3V3` |

Важно:

- Уровни UART должны быть 3.3 В, не 5 В.
- TX/RX перекрестно проходят через ISO7721: SAFE TX -> HOT PA3, HOT PA2 -> SAFE RX.
- Между `SAFE_GND` и `HOT_GND` нет медного соединения.
- Power pin USB-UART не подключать; `SAFE_3V3` задаётся отдельным селектором.
- ST-Link нужен только для прошивки/debug, не для runtime-команд.

## Коммутация STM32 -> STEVAL/IPM

| STM32 | Назначение |
|---|---|
| PA8 | PWM-1H |
| PB13 | PWM-1L |
| PA9 | PWM-2H |
| PB14 | PWM-2L |
| PA10 | PWM-3H |
| PB15 | PWM-3L |
| PB12 | EM_STOP / shutdown |
| PB4 | precharge relay |
| PB1 | NC, analog/high-impedance |
| PB5 | PFC sync |
| PB9 | dissipative brake PWM |
| PB3 | fan PWM |
| PA11 | fan tach |
| PB10/PB11 | AS5600 I2C |
| PA5 | HV bus voltage ADC |
| PB0 | heat sink temperature |
| PA6/PA7 | measure phase A/B |

## Проверка прямой связи

Сначала проверить, что runtime-прошивка собирается:

```powershell
py -3 -m platformio run -d bluepill_uart_pwm_pio -e bluepill_uart_pwm
```

На стенде не использовать прямой `platformio ... upload` как обычный путь прошивки.
Правильный безопасный путь: когда HV/J7 отключен и DC-шина разряжена, запустить
runtime-static preflight. Он прошьет актуальную runtime-прошивку Blue Pill и сразу
проверит Saleae CH0..CH6 в безопасном статическом состоянии:

```powershell
py -3 -u .\tools\bluepill_runtime_static_preflight.py --confirm-hv-off
```

Сначала безопасно определить USB-UART порт без записи в COM-порт:

```powershell
py -3 -u .\tools\bluepill_uart_diagnose.py --inventory-only --port auto
```

Если TX/RX сейчас отключены от STM32, проверить сам USB-UART/изолятор
loopback-тестом: замкнуть TX-RX на изолированной стороне адаптера и запустить:

```powershell
py -3 -u .\tools\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080
```

Если loopback прошел, снять перемычку TX-RX, вернуть перекрестное подключение
к STM32 и запустить protocol-диагностику:

```powershell
py -3 -u .\tools\bluepill_uart_diagnose.py --port COM3 --dtr-rts-matrix --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0
```

Если все попытки дают write-timeout, сначала проверить сам USB-UART/изолятор
loopback-тестом: отключить TX/RX адаптера от STM32, замкнуть TX на RX на
изолированной стороне и запустить:

```powershell
py -3 -u .\tools\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080
```

`uart_loopback_preflight.py` сам остановит PC-direct HMI, выполнит
`bluepill_uart_diagnose.py --loopback` и поднимет HMI обратно. `summary.json`
от `bluepill_uart_diagnose.py` содержит `uart_wiring_contract`:
`USB-UART TX -> PA3/USART2_RX`, `USB-UART RX <- PA2/USART2_TX`, общий
GND изолированной стороны и только 3.3 V TTL уровни. В `next_actions` теперь
есть готовая `command` для следующего безопасного шага; использовать её, а не
старую команду из памяти, если порт/baud изменились.

Интерпретация:

- `adapter_loopback_ok`: USB-UART/изолятор умеет писать и читать байты; вернуть
  TX/RX к STM32 перекрестно и запускать обычную protocol-диагностику без
  `--loopback`.
- `adapter_loopback_failed`: проблема до STM32 - USB-изолятор, USB-UART, питание
  изолированной стороны, кабель или драйвер.
- protocol-диагностика проходит по записи, но Blue Pill не отвечает: проверить TX/RX cross, общий
  изолированный GND, PA2/PA3, питание STM32 и залитую UART firmware.

Loopback должен быть свежее последней обычной UART protocol-диагностики. Если
сначала был старый loopback, а потом новый write-timeout на STM32, старый
loopback больше не считается доказательством: повторить loopback заново.

Ожидаемый признак успеха:

- `OK`
- `link_ok=true`
- `fault_text` может быть `OK` после `CLEAR`, либо временно `TIMEOUT` до серии кадров.

## PC-direct HMI

Штатно поднимать и останавливать direct-HMI теперь через service-manager:

```powershell
py -3 -u .\tools\pc_direct_hmi_service.py status --port 18080
py -3 -u .\tools\pc_direct_hmi_service.py start --serial COM3 --baud 115200 --port 18080
py -3 -u .\tools\pc_direct_hmi_service.py stop --port 18080
py -3 -u .\tools\pc_direct_hmi_service.py restart --serial COM3 --baud 115200 --port 18080
```

`stop` завершает только процессы `unoq_web_server.py` с указанным `--port`,
не трогая другие Python/PlatformIO задачи. Перед UART loopback обязательно
выполнить `stop`, потому что HMI и loopback не могут одновременно держать `COM3`.

Прямой запуск оставлен только как ручной fallback:

```powershell
py -3 -u .\tools\unoq_web_server.py --serial COM3 --baud 115200 --port 18080
```

Если используется `web_hmi/server.py` напрямую с serial-endpoint на Linux/UNO Q,
baud задавать явно, иначе старые установки могли остаться на 115200:

```powershell
py -3 -u .\web_hmi\server.py --router serial:/dev/ttyUSB0 --serial-baud 115200 --port 8080
```

Открыть:

```text
http://127.0.0.1:18080
```

API совместим по базовым endpoint:

- `GET /api/status`
- `POST /api/cmd` с JSON `{"cmd":"STOP"}`

Сервисные команды direct-HMI, без скрытого `START` двигателя:

- `FAN PWM 0.00..1.00`, `FAN ON`, `FAN OFF`
- `PRECHARGE ON|OFF`
- `PFC ON|OFF`
- `BRAKE PWM 0.00..1.00`, `BRAKE OFF`
- `IOTEST ON|OFF` - безопасный сервисный режим для старых relay-preflight скриптов; мост не включает.

`START` и включающие service-команды (`FAN >0`, `PRECHARGE/PFC ON`,
`BRAKE >0`, `IOTEST ON`) проходят только при свежем `SAFE`-статусе STM32:
`link=true`, `pwm=0`, `estop=0`, `bp_fault=0`, `bp_bad=0` и `Vbus <= 60 V`
по умолчанию. Команды выключения (`FAN OFF`, `PRECHARGE OFF`,
`PFC OFF`, `BRAKE OFF`, `IOTEST OFF`, `STOP`, `CLEAR`) разрешены как аварийное
снятие выходов.

В `MODE_OFF` прошивка STM32 держит силовой PWM выключенным, но разрешает проверять
сервисные выходы `PB4/PB5/PB9/PB3`. `PB1` всегда остаётся высокоомным входом.
`CLEAR`, `ESTOP` и `IOTEST OFF` гасят
сохраненное состояние сервисных выходов.

## Безопасные первые команды

```powershell
curl http://127.0.0.1:18080/api/status
```

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:18080/api/cmd -Method Post -ContentType application/json -Body '{"cmd":"STOP"}'
Invoke-RestMethod -Uri http://127.0.0.1:18080/api/cmd -Method Post -ContentType application/json -Body '{"cmd":"CLEAR"}'
```

Не запускать `START`, пока:

- UART protocol-диагностика не проходит стабильно;
- bench-gate не показывает `ready_for_active_pwm=true`;
- Saleae не подтверждает свежий статический SAFE-захват PWM-линий;
- режим питания не выбран явно: для low-voltage теста HV/J7 отключена и DC-шина разряжена, для HV-пуска есть свежий HV/J7 PASS, ограничение тока и внешний E-STOP;
- `fault_text=OK`;
- `pwm=0`;
- внешний E-STOP готов.

## Сводный Gate Перед Активным PWM

Перед любой попыткой включать `START` или запускать self-test через ST-Link
собрать безопасный сводный отчет:

```powershell
py -3 -u .\tools\bench_gate_report.py --timeout 1.0
```

Для такой же проверки через общий readiness-инструмент, без требований
научной матрицы/HV/calibration, использовать профиль bring-up:

```powershell
py -3 -u .\tools\research_readiness_check.py --profile bringup
```

Этот скрипт не включает PWM. Он берет последние evidence-файлы и проверяет:

- последний `full_system_preflight.py --build-only` прошел;
- UART diagnosis видел ответ STM32 на безопасный кадр `MODE_OFF+CLEAR_FAULT`;
- Saleae-захват содержит `CH0..CH6`;
- в статике нет фронтов и нет high-high overlap по парам `U/V/W`;
- `CH6/PB12/EM_STOP` удерживает shutdown активным низким уровнем;
- live-HMI, если доступен, не показывает включенный PWM.

Если итог `ready_for_active_pwm=false`, активный PWM не запускать. Смотреть
`next_actions` в `summary.json`. Gate различает обычную UART protocol-диагностику
и loopback USB-UART. Актуальный loopback засчитывается только если его
`summary.json` свежее последнего protocol-fail.

Типовые `next_actions`:

- `run_runtime_static_preflight`: при HV/J7 отключенной и разряженной DC-шине
  прошить свежую рабочую STM32 firmware и снять статический Saleae `CH0..CH6`.
  `--dry-run` здесь не считается допуском к active PWM.
- `run_static_low_isolation_preflight`: если runtime/static или пассивный Saleae
  показывает `low_side_static_high`, при HV/J7 отключенной и разряженной шине
  прошить диагностическую firmware без TIM1/команд, которая только держит
  `PA8/PA9/PA10/PB13/PB14/PB15/PB12` в LOW, снять Saleae и восстановить runtime.
  Если static-low проходит, а runtime-static нет, проблема в TIM1/runtime init;
  если static-low тоже показывает HIGH, искать проводку, GND Saleae, каналы или
  подтяжки/опору входов IPM.
- `run_uart_loopback`: отключить TX/RX от STM32 и проверить сам USB-UART/изолятор.
- `fix_usb_uart_loopback`: loopback не прошел; чинить USB-UART, изолятор, кабель,
  питание изолированной стороны или драйвер.
- `reconnect_stm32_uart_and_rerun_protocol`: loopback прошел; вернуть TX/RX
  перекрестно на STM32 и повторить protocol-диагностику.
- `check_stm32_uart_wiring_or_firmware`: ПК пишет байты, но STM32 не отвечает;
  проверить PA2/PA3, GND, питание и прошивку `bluepill_uart_pwm`.

## Контракт Безопасного PWM-Off

В прошивке STM32 `pwm_outputs_enable(false)` теперь обязан не только сбрасывать
`TIM1 MOE`, но и принудительно переводить все шесть PWM-пинов в GPIO-low:

- `PA8/PB13` - фаза U;
- `PA9/PB14` - фаза V;
- `PA10/PB15` - фаза W.

Это защита поверх `EM_STOP`, а не замена `EM_STOP`. Контракт проверяется
автоматически:

```powershell
py -3 -u .\tools\firmware_config_safety_check.py
```

В отчете должен быть `pwm_safe_disable_forces_gpio_low: ok=true`.

Дополнительные firmware-инварианты, которые должны оставаться зелеными:

- `STATUS_PWM_ACTIVE` выставляется только после `control_tick()`, когда duty уже
  применен и TIM1 реально включен.
- fault, bad-frame и timeout используют общий `force_safe_outputs()`, чтобы
  одинаково гасить PWM, `EM_STOP`, service outputs, brake PWM и fan duty.
- при `OVERTEMP` общий safe-output сначала гасит выходы, затем fan принудительно
  включается на 100%.

## Заготовка Для Переноса На UNO Q

Логика протокола уже отделена от физического runtime:

- STM32 firmware принимает одинаковые 32-байтные кадры независимо от источника.
- PC-direct HMI формирует те же кадры, что раньше формировала UNO Q.
- Позже можно перенести верхний уровень обратно на UNO Q Linux, если нужно:
  `unoq_web_server.py` запускается на Linux и вместо `COM3` открывает UART/USB-UART
  к Blue Pill.

Правильная граница переноса:

```text
command/HMI/AI logic
  -> BluePill protocol frame
  -> transport: PC serial сейчас, UNO Q serial позже
```

То есть менять нужно будет только transport, а не safety/PWM протокол.

## Текущее Состояние На 2026-07-04

- ST-Link виден и прошивка `bluepill_uart_pwm` ранее загружалась успешно.
- Текущая firmware после правок protocol decode и service-I/O собирается успешно:
  `py -3 -m platformio run -d bluepill_uart_pwm_pio -e bluepill_uart_pwm`.
- Последний build-only gate проходит:
  `py -3 -u .\tools\full_system_preflight.py --build-only`.
- Последний bench-gate не разрешает активный PWM из-за блокеров:
  runtime-static не подтвержден свежим upload+Saleae, static-low isolation не
  выполнен, UART write-timeout и live `/api/status` недоступен.
  Ожидаемые `next_actions`: `run_runtime_static_preflight`,
  `run_static_low_isolation_preflight`, `run_uart_loopback`,
  `restore_hmi_safe_status`.
- COM3 виден как USB-UART, но последняя protocol-диагностика падала на записи:
  `SerialTimeoutException: Write timeout`.
- Это ниже уровня STM32-протокола: ПК не может нормально записать кадр в COM3,
  поэтому тесты связи/реле/вентилятора сейчас физически заблокированы.
- Нужно проверить сам адаптер loopback-тестом после последнего write-timeout:
  отключить TX/RX от STM32, замкнуть TX-RX на изолированной стороне USB-UART и
  запустить `uart_loopback_preflight.py --confirm-loopback-wired` по всем baud:
  `--bauds 460800,115200,230400,921600`.
- SAFE-static Saleae сейчас стабильно показывает `CH0=0 CH1=1 CH2=0 CH3=1 CH4=0 CH5=1 CH6=0`.
  Это не доказывает сквозное открытие, но запрещает активный PWM до проверки свежей
  runtime-прошивки через `bluepill_runtime_static_preflight.py --confirm-hv-off`
  при отключенной и разряженной HV-шине.
- Если после свежей runtime-прошивки `CH1/CH3/CH5` остаются HIGH, следующий
  обязательный шаг — `bluepill_static_low_preflight.py --confirm-hv-off`.
  Для текущего шаблона мерить цепочку `PB13/PB14/PB15` на Blue Pill -> входы IPM
  -> Saleae `CH1/CH3/CH5` с GND на STM32 logic GND.
- После каждого `bench_gate_report.py` смотреть не только `summary.json`, но и
  `NEXT_STEPS_RU.md` в папке конкретного прогона: там лежит актуальный порядок
  действий и готовые команды.
- Для короткой проверки из корня проекта обновить `CURRENT_BENCH_STATUS_RU.md`:
  `py -3 -u .\tools\current_bench_status.py`.
  После обновления проверить актуальность файла:
  `py -3 -u .\tools\current_bench_status.py --check`.
- Для полного безопасного обновления всего статусного пакета одной командой:
  `py -3 -u .\tools\refresh_bench_status.py --build-if-stale`.

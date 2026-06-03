# Поэтапная Сборка Стенда

Этот файл нужен для сборки стенда по шагам.
Логика простая:
- собираешь только текущий этап;
- делаешь проверку;
- переходишь дальше только если критерий этапа выполнен.

Основная карта соединений лежит в [CONNECTION_MATRIX_RU.md](/C:/mic_practice/CONNECTION_MATRIX_RU.md).
Этот файл не заменяет карту, а задает правильный порядок сборки.

## Правила До Начала
- Не включать HV/DC-шину инвертора, пока не пройдены все низковольтные этапы.
- Любая перепроводка делается только при снятом питании.
- У всех устройств должен быть общий логический `GND`.
- `Saleae` подключать только к логическим линиям, не к силовой части.
- Текущая рабочая конфигурация проекта:
  - `UNO Q <-> Blue Pill = UART 460800`
  - `Blue Pill PWM = TIM1 PA8/PA9/PA10 + PB13/PB14/PB15`
  - `EM_STOP = PB12`
  - `AS5600 = PB10/PB11`

## Этап 0. Подготовка Инструментов
### Что должно быть
- `PC`
- `UNO Q`
- `Blue Pill`
- `ST-Link`
- `Saleae Logic`
- `AS5600`
- `STEVAL-IPM15B`

### Что проверить
1. На `PC` доступны `arduino-cli`, `python`, `platformio`.
2. UNO Q виден по USB/ADB.
3. ST-Link виден системой.
4. Saleae определяется Logic2.

### Команды проверки
```powershell
adb devices
py -3 -m platformio --version
arduino-cli version
py -3 -u .\tools\la_probe.py
```

### Переход дальше
Идти дальше можно только если:
- `adb devices` показывает UNO Q
- `la_probe.py` не пишет `devices []`

## Этап 1. Прошивка Плат Без Силовой Части
### Что подключить
- `PC <-> UNO Q` по USB-C
- `PC <-> ST-Link` по USB
- `ST-Link <-> Blue Pill` по SWD

### Что пока НЕ подключать
- `IPM15`
- `AS5600`
- `Saleae` щупы
- HV питание

### Что сделать
1. Прошить UNO Q.
2. Прошить Blue Pill.
3. Убедиться, что UNO Q поднимает `web_hmi`.

### Команды
```powershell
arduino-cli compile --fqbn arduino:zephyr:unoq .\UNOQ_MOTOR
arduino-cli upload -p COM5 --fqbn arduino:zephyr:unoq .\UNOQ_MOTOR

cd .\bluepill_uart_pwm_pio
py -3 -m platformio run -t upload
cd ..

py -3 .\tools\adb_deploy_web_hmi.py --restart
adb forward tcp:18080 tcp:8080
```

### Проверка
Открыть:
`http://127.0.0.1:18080/api/status`

### Переход дальше
Идти дальше можно только если `/api/status` отвечает.

## Этап 2. Собрать Только Канал Управления UNO Q <-> Blue Pill
### Что подключить
| Откуда | Куда |
|---|---|
| UNO Q `D1 (TX)` | Blue Pill `PA3 (USART2_RX)` |
| UNO Q `D0 (RX)` | Blue Pill `PA2 (USART2_TX)` |
| UNO Q `GND` | Blue Pill `GND` |

### Что пока НЕ подключать
- `IPM15`
- `AS5600`
- Hall
- HV

### Что проверить
UNO Q должен начать видеть reply от Blue Pill.

### Команды
```powershell
adb forward tcp:18080 tcp:8080
```

Потом открыть:
`http://127.0.0.1:18080/api/status`

### Что должно быть в `/api/status`
- `bp_age_ms` меняется и остается маленьким
- `bp_fault = 0`
- `bp_bad = 0`
- `state = SAFE`

### Переход дальше
Идти дальше можно только если:
- Blue Pill виден по статусу
- нет роста `bp_bad`
- `bp_fault = 0`

## Этап 3. Подключить AS5600
### Что подключить
| Blue Pill | AS5600 |
|---|---|
| `PB10 (I2C2_SCL)` | `SCL` |
| `PB11 (I2C2_SDA)` | `SDA` |
| `3.3V` | `VCC` |
| `GND` | `GND` |

### Что пока НЕ подключать
- `IPM15`
- HV

### Что проверить
Сначала проверить, что датчик просто читается.

### Команда
```powershell
py -3 -u .\tools\encoder_test.py --url http://127.0.0.1:18080 --duration 10 --poll 0.05
```

### Критерий этапа
Идти дальше можно только если:
- `enc_ok_ratio = 1.000`
- `enc_raw` читается стабильно
- при повороте магнита/вала `enc_raw` меняется

Если `enc_ok = 0`, дальше идти нельзя.

## Этап 4. Подключить Saleae К Логической Части Blue Pill
### Что подключить
| Saleae | Blue Pill |
|---|---|
| `CH0` | `PA8` |
| `CH1` | `PB13` |
| `CH2` | `PA9` |
| `CH3` | `PB14` |
| `CH4` | `PA10` |
| `CH5` | `PB15` |
| `CH6` | `PB12` |
| `GND` | общий логический `GND` |

### Что пока НЕ подключать
- `IPM15`
- HV

### Что проверить
Нужно убедиться, что Logic2 реально видит анализатор.

### Команда
```powershell
py -3 -u .\tools\la_probe.py
```

### Переход дальше
Идти дальше можно только если `la_probe.py` видит реальный девайс, а не пустой список.

## Этап 5. Подключить Только Логическую Часть IPM15
### Что подключить обязательно
| IPM15 J2 | Blue Pill |
|---|---|
| `J2-1 EM_STOP` | `PB12` |
| `J2-3 PWM-1H` | `PA8` |
| `J2-5 PWM-1L` | `PB13` |
| `J2-7 PWM-2H` | `PA9` |
| `J2-9 PWM-2L` | `PB14` |
| `J2-11 PWM-3H` | `PA10` |
| `J2-13 PWM-3L` | `PB15` |
| `J2-25 +V power` | `+5V` |
| `J2-28 VDD_m` | `+3.3V` |
| `J2-29 PWM VREF` | `+3.3V` |
| `J2 GND pins` | общий `GND` |

Важно:
- кроме `J2`, для правильного питания STEVAL нужен и `J4`;
- `J2` даёт логические `+5V` и `+3.3V`;
- `J4` даёт auxiliary `VCC` драйвера, типично `+15V`, максимум `20V`;
- не путать `J4` с будущей силовой DC/HV шиной `J7`.

### Что подключить по питанию STEVAL на этом этапе
| Разъём | Что подать |
|---|---|
| `J2-25` | `+5V` |
| `J2-28` | `+3.3V` |
| `J2-29` | `+3.3V` |
| `J4 +` | `+15V typ` |
| `J4 -` | `GND / return` |

### Что пока можно НЕ подключать
- `J2-14/15/17/19` аналоговую телеметрию
- `J2-21` NTC relay
- `J2-23` brake PWM
- `J2-27` PFC sync
- `J2-31/33` phase measurement; `J2-34` stays not connected in this firmware

### Что категорически НЕ подключать
- `J7` HV/DC bus

### Что проверить
Сначала быстрый DIAG-захват.

### Команда
```powershell
py -3 -u .\tools\ui_pwm_case.py --url http://127.0.0.1:18080 --mode DIAG --tag diag --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

### Критерий этапа
Идти дальше можно только если:
- PWM виден на `CH0..CH5`
- `CH6` ведет себя как `EM_STOP/BRAKE`
- нет `bp_fault`
- после теста система возвращается в `SAFE`

## Этап 6. Подключить Дополнительные I/O IPM15
### Что подключить
| IPM15 J2 | Blue Pill | Зачем |
|---|---|---|
| `J2-21` | `PB1` | `NTC` relay |
| `J2-23` | `PB9` | `BRAKE PWM` |
| `J2-27` | `PB5` | `PFC sync` |

### Что проверить
Проверить, что команды UI реально переключают выходы.

### Базовый прогон
```powershell
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 --skip-sweep --skip-estop --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

### Критерий этапа
Идти дальше можно только если:
- `NTC`, `PFC`, `BRAKE PWM` отражаются в `/api/status`
- логика не уходит в fault

## Этап 7. Подключить Аналоговую Телеметрию IPM15
### Что подключить
| IPM15 J2 | Blue Pill |
|---|---|
| `J2-14 HV bus voltage` | `PA5` |
| `J2-15 current phase A` | `PA0` |
| `J2-17 current phase B` | `PA1` |
| `J2-19 current phase C` | `PA4` |
| `J2-26 heat sink temperature` | `PB0` |

### Опционально
| IPM15 J2 | Blue Pill |
|---|---|
| `J2-31 measure phase A` | `PA6` |
| `J2-33 measure phase B` | `PA7` |
| `J2-34 measure phase C` | not connected, virtual C is computed from A/B |

### Что проверить
В `/api/status` должны появляться осмысленные `ia`, `ib`, `ic`, `vdc`.
Для DC bus основной источник теперь Blue Pill: `J2-14 -> PA5`, а диагностические поля `bp_vbus_raw`, `bp_vdc`, `bp_vbus_age_ms` должны быть живыми. `UNO Q A0` для HV telemetry не используется как основной путь.
В текущей UART-схеме `PA5` должен быть свободен от старой SPI-линии `UNO Q D13/SCK`; если этот провод остался, `bp_vdc` может показывать почти ноль даже при реальных 310..315 В на DC-шине.

### Критерий этапа
Идти дальше можно только если:
- напряжение и токи не выглядят явно мусорными
- нет выбросов в fault только из-за подключения измерительных линий

## Этап 8. Полный Низковольтный Bring-Up
На этом этапе уже должны быть подключены:
- `UNO Q`
- `Blue Pill`
- `AS5600`
- `Saleae`
- `IPM15` логическая часть
- дополнительные I/O
- аналоговая телеметрия

### Команда
```powershell
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 --capture-every-hz 1 --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

### Переход дальше
Думать о следующем этапе можно только если:
- suite проходит без падений
- `bp_bad = 0`
- `bp_fault = 0` вне ожидаемых `ESTOP` кейсов
- после теста система возвращается в `SAFE`

## Этап 9. Проверка Управления Перед Любой Силовой Частью
Перед тем как вообще рассматривать силовой запуск, отдельно проверить:

1. `START`
2. `STOP`
3. `ESTOP`
4. `ESTOP CLEAR`
5. `DIAG`
6. `VF`
7. `FOC`

### Что должно быть
- `STOP` всегда приводит в `SAFE`
- `ESTOP` всегда снимает PWM
- `ESTOP CLEAR` корректно восстанавливает возможность старта
- `bp_bad` не растет

## Этап 10. Стоп-Точка Перед HV
Если не пройдены все этапы выше, HV включать нельзя.

Только после этого можно говорить, что:
- связь собрана правильно
- логическая коммутация правильная
- safety работает
- PWM реально доходит до драйвера

Но даже после этого:
- сначала внешний E-STOP
- потом предохранители/ограничение питания
- и только потом обсуждать силовой запуск

## Этап 11. Ручные Силовые Шаги Только Через Bounded Runner
После появления HV на шине любые ручные шаги с `START` выполнять только через один persistent ADB/router socket. Не гонять цикл, который на каждый `DUTY` делает отдельный `adb shell`: при HV это плохая модель управления, потому что зависание канала может задержать останов.

### Безопасная проверка канала без старта
Эта команда не снимает `ESTOP CLEAR` и не включает PWM:
```powershell
py -3 -u .\tools\adb_router_sequence.py --cmd STOP --cmd ESTOP
```

Критерий:
- команды проходят через один socket-сеанс;
- финальный `/api/status` показывает `SAFE`;
- `pwm = 0`;
- `bp_bad` не растет.

### Защита от случайного старта под HV
Если в последовательности есть `START`, а `VBUS` выше `--max-vdc`, инструмент обязан отказаться без явного `--allow-hv`:
```powershell
py -3 -u .\tools\adb_router_sequence.py --dry-run --duty-rotate --mag 0.20 --dwell-s 0.10 --cycles 1
```

Силовой пример допустим только когда стенд подготовлен, оператор у питания, внешний E-STOP доступен:
```powershell
py -3 -u .\tools\adb_router_sequence.py --allow-hv --duty-rotate --mag 0.20 --dwell-s 0.25 --cycles 1
```

## Короткий Маршрут По Этапам
1. Инструменты и софт готовы.
2. Прошиты UNO Q и Blue Pill.
3. Работает `UNO Q <-> Blue Pill` по UART.
4. Читается `AS5600`.
5. Работает `Saleae`.
6. Подключена логическая часть `IPM15`.
7. Подключены I/O и аналоговая телеметрия.
8. Полный low-voltage suite пройден.
9. Перед HV пройдена стоп-точка.
10. Ручные HV шаги выполняются только через bounded runner.
# CURRENT CRITICAL UPDATE: HEATSINK TEMPERATURE BEFORE HV
- Before any HV/PWM run, wire STEVAL/IPM15 `J2-26 heat sink temperature` to Blue Pill `PB0 (ADC1_IN8)`.
- Set UM2014 `SW3` to `NTC` (`2-3`).
- Do not connect `J2-34 measure phase C` to `PB0`; current firmware uses `PB0` for heatsink temperature.
- Connect `J2-31 measure phase A -> PA6` and `J2-33 measure phase B -> PA7`; `measure phase C` is virtual in firmware.
- Required `/api/status` before run: `bp_temp_valid=1`, `bp_temp_fault=0`, `bp_fault=0`.
- If `bp_fault=6`, this is `OVERTEMP` or open NTC line: keep 220/315V off and fix temperature wiring first.

# Карта Коммутации Стенда

Этот файл фиксирует фактическую коммутацию стенда `PC <-> UNO Q <-> Blue Pill <-> STEVAL-IPM15B`, а также подключение `AS5600`, `Saleae Logic` и `ST-Link`.

Текущее состояние проекта:
- основной UI и логика: `UNOQ_MOTOR/UNOQ_MOTOR.ino`
- силовая PWM-часть: `bluepill_uart_pwm_pio`
- связь `UNO Q <-> Blue Pill`: `UART`, `460800`
- основной контур ШИМ в боевом стенде идет через `Blue Pill`, не через локальные PWM-пины UNO Q

## 0. Условия, при которых эта схема верна
Эта карта коммутации проверена под текущие compile-time настройки проекта:

- на UNO Q:
  - `USE_EXTERNAL_PWM = true`
  - `USE_NUCLEO_SPI = false`
  - `USE_NUCLEO_UART_FALLBACK = true`
- на Blue Pill:
  - `LINK_USE_SPI = 0`
  - `UART_BAUD = 460800`
  - `USE_AS5600 = 1`
  - `USE_TIM1_BKIN = 0`
  - `FOC_REQUIRE_HALL = 1`

Практический смысл:
- эта схема точно соответствует текущей рабочей прошивке;
- если переключить проект на `SPI` вместо `UART`, часть ADC-пинов на Blue Pill изменится;
- если включить `USE_TIM1_BKIN = 1`, `PB12` нельзя оставлять на `EM_STOP`;
- если убрать и `AS5600`, и `Hall`, режим `FOC` на Blue Pill не сможет работать.

## 1. Сводная матрица
| Откуда | Интерфейс | Куда | Коммутация | Назначение |
|---|---|---|---|---|
| PC | USB | UNO Q | USB-C кабель | `ADB`, доступ к `web_hmi`, `arduino-cli upload`, питание логики UNO Q |
| PC | USB | ST-Link | USB кабель | прошивка Blue Pill |
| ST-Link | SWD | Blue Pill | `SWDIO`, `SWCLK`, `GND`, опц. `NRST`, опц. `3.3V` | прошивка/отладка STM32F103 |
| PC | USB | Saleae Logic | USB кабель | захват логических сигналов через Logic2 Automation |
| UNO Q | UART | Blue Pill | `D1(TX) -> PA3(RX)`, `D0(RX) <- PA2(TX)`, `GND <-> GND` | управление Blue Pill и прием телеметрии |
| Blue Pill | PWM + GPIO + ADC | STEVAL-IPM15B J2 | см. таблицу ниже | силовой интерфейс, safety, телеметрия |
| Внешний БП | auxiliary VCC | STEVAL-IPM15B J4 | `+15V typ`, `20V max`, `+/-` | питание драйвера IPM (`VCC`) |
| Внешний БП | DC bus | STEVAL-IPM15B J7 | `125..400V DC`, `+/-` | силовая шина инвертора |
| Blue Pill | I2C2 | AS5600 | `PB10(SCL)`, `PB11(SDA)`, `3.3V`, `GND` | абсолютный энкодер |
| Saleae | digital probes | Blue Pill logic side | `CH0..CH6`, `GND` | контроль PWM/ESTOP |

## 2. PC / Ноутбук
| Прибор | Куда подключается | Для чего |
|---|---|---|
| PC -> UNO Q | USB-C | `ADB`, `http://127.0.0.1:18080` через `adb forward`, `arduino-cli compile/upload` |
| PC -> ST-Link | USB | `platformio run -t upload`, `openocd`, SWD debug |
| PC -> Saleae Logic | USB | Logic2, automation API, `tools/ui_pwm_case.py`, `tools/ui_pwm_suite.py` |

## 3. UNO Q
### 3.1. Внешние подключения UNO Q
| Пин UNO Q | Куда идет | Назначение |
|---|---|---|
| `D1 (TX)` | Blue Pill `PA3 (USART2_RX)` | передача команд в Blue Pill |
| `D0 (RX)` | Blue Pill `PA2 (USART2_TX)` | прием reply/телеметрии от Blue Pill |
| `GND` | Blue Pill `GND` | общий ноль UART |
| USB-C | PC | ADB, web_hmi, прошивка, питание логики UNO Q |

### 3.2. Внутренние/локальные пины UNO Q
Это пины, которые используются sketch-ом, но в текущем боевом стенде основная силовая коммутация идет через Blue Pill:

| Пин UNO Q | Роль в sketch |
|---|---|
| `D3` | `PWM_UH_PIN` |
| `D5` | `PWM_UL_PIN` |
| `D6` | `PWM_VH_PIN` |
| `D8` | `PWM_VL_PIN` |
| `D9` | `PWM_WH_PIN` |
| `D10` | `PWM_WL_PIN` |
| `D4` | `BRAKE_PIN` |
| `A0` | legacy/fallback local `ADC_VDC_PIN`, не основной HV telemetry path |
| `A1` | `ADC_IA_PIN` |
| `A2` | `ADC_IB_PIN` |
| `A3` | `ADC_IC_PIN` |

Практический смысл:
- эти пины нужны для локального fallback/debug внутри sketch;
- в текущей рабочей конфигурации силовой тракт и deadtime реализованы на Blue Pill;
- не надо пытаться одновременно строить основной боевой PWM и с UNO Q, и с Blue Pill на один и тот же драйвер.

## 4. Blue Pill
### 4.1. UNO Q <-> Blue Pill
| Blue Pill пин | Куда подключается | Назначение |
|---|---|---|
| `PA3 (USART2_RX)` | UNO Q `D1 (TX)` | прием кадров от UNO Q |
| `PA2 (USART2_TX)` | UNO Q `D0 (RX)` | ответ/статус в UNO Q |
| `GND` | UNO Q `GND` | общий ноль |

Текущий baud: `460800`.

### 4.2. Blue Pill <-> AS5600
| Blue Pill пин | AS5600 | Назначение |
|---|---|---|
| `PB10 (I2C2_SCL)` | `SCL` | такт I2C |
| `PB11 (I2C2_SDA)` | `SDA` | данные I2C |
| `3.3V` | `VCC` | питание AS5600 |
| `GND` | `GND` | общий ноль |

Примечания:
- адрес AS5600 по проекту: `0x36`
- скорость I2C: `100 kHz`
- если на модуле нет подтяжек, поставить `4.7k..10k` к `3.3V`

### 4.3. Blue Pill <-> ST-Link
Стандартная SWD-коммутация STM32F103:

| ST-Link | Blue Pill | Назначение |
|---|---|---|
| `SWDIO` | `PA13` | SWD data |
| `SWCLK` | `PA14` | SWD clock |
| `NRST` | `NRST` | reset, рекомендуется |
| `GND` | `GND` | общий ноль |
| `3.3V` | `3.3V` | опционально, только если Blue Pill реально питается от ST-Link |

Важно:
- если Blue Pill уже питается от внешних `3.3V/5V`, не надо бездумно запараллеливать питание от ST-Link;
- `GND` должен быть общим в любом случае.

## 5. Blue Pill <-> STEVAL-IPM15B (J2)
### 5.1. Основные сигналы J2
| J2 pin | Сигнал UM2014 | Blue Pill | Назначение |
|---|---|---|---|
| `J2-1` | `EM_STOP` | `PB12` | shutdown / BRAKE / ESTOP, активный низкий уровень на стороне IPM |
| `J2-3` | `PWM-1H` | `PA8 (TIM1_CH1)` | high-side phase U |
| `J2-5` | `PWM-1L` | `PB13 (TIM1_CH1N)` | low-side phase U |
| `J2-7` | `PWM-2H` | `PA9 (TIM1_CH2)` | high-side phase V |
| `J2-9` | `PWM-2L` | `PB14 (TIM1_CH2N)` | low-side phase V |
| `J2-11` | `PWM-3H` | `PA10 (TIM1_CH3)` | high-side phase W |
| `J2-13` | `PWM-3L` | `PB15 (TIM1_CH3N)` | low-side phase W |

### 5.2. Аналоговая телеметрия J2
| J2 pin | Сигнал UM2014 | Blue Pill | Назначение |
|---|---|---|---|
| `J2-14` | `HV bus voltage` | `PA5 (ADC1_IN5)` | контроль шины DC |
| `J2-15` | `current phase A` | `PA0 (ADC1_IN0)` | ток фазы A |
| `J2-17` | `current phase B` | `PA1 (ADC1_IN1)` | ток фазы B |
| `J2-19` | `current phase C` | `PA4 (ADC1_IN4)` | ток фазы C |
| `J2-26` | `heat sink temperature` | `PB0 (ADC1_IN8)` | IPM heatsink NTC, SW3=NTC 2-3 |
| `J2-31` | `measure phase A` | `PA6 (ADC1_IN6)` | phase measurement A |
| `J2-33` | `measure phase B` | `PA7 (ADC1_IN7)` | phase measurement B |
| `J2-34` | `measure phase C` | not connected | firmware computes virtual C from A/B |

Эта раскладка верна именно для текущего `LINK_USE_SPI = 0`.
Если когда-либо включить `LINK_USE_SPI = 1`, проект переедет на альтернативную схему:
- `IC` уйдет на `PA2`
- `VBUS` уйдет на `PA3`
- `PA6/PA7/PB0` под `USE_PHASE_MEAS` будут отключены

### 5.3. Дополнительные I/O J2
| J2 pin | Сигнал UM2014 | Blue Pill | Назначение |
|---|---|---|---|
| `J2-21` | `NTC bypass relay` | `PB1` | реле обхода NTC |
| `J2-23` | `dissipative brake PWM` | `PB9 (TIM4_CH4)` | тормозной ШИМ |
| `J2-27` | `PFC sync.` | `PB5` | PFC sync output |

### 5.4. Питание и земля J2
| J2 pin | Сигнал | Куда подключать |
|---|---|---|
| `J2-25` | `+V power` | стабильные `+5V` |
| `J2-28` | `VDD_m` | `+3.3V` |
| `J2-29` | `PWM VREF` | `+3.3V` |
| `J2-2/4/6/8/10/12/16/18/20/22/24/30/32` | `GND` | общий логический `GND` |

Важно:
- `J2` не заменяет auxiliary питание драйвера;
- по локальной документации UM2014 через `J2` на плату действительно подаются внешние `+5V` и `+3.3V`;
- HV-шину `125..400V DC` не включать, пока не подтверждены PWM, `EM_STOP`, `STOP`, `ESTOP`, timeout и BRAKE на логическом уровне;
- аналоговые выходы UM2014 должны укладываться в `0..3.3V` на ADC Blue Pill.

### 5.5. Питание J4
| Разъём | Сигнал | Что подавать |
|---|---|---|
| `J4` | `VCC supply` | внешний auxiliary БП |
| `J4 +` | positive | `+15V typ` |
| `J4 -` | negative | `GND / return` |

Важно:
- по UM2014 `J4` это `VCC supply (20 VDC max)`;
- на схеме платы рядом с `J4` указан типовой уровень `15V`;
- без `J4` плата STEVAL как силовой драйвер подключена неполноценно, даже если на `J2` уже есть `+5V` и `+3.3V`;
- не путать `J4` с `J7`: `J4` это auxiliary low-voltage питание драйвера, `J7` это основная DC bus силовой части.

### 5.6. Питание J7
| Разъём | Сигнал | Что подавать |
|---|---|---|
| `J7` | DC bus | `125..400V DC` по документации UM2014 |
| `J7-1` | positive | `DC+` |
| `J7-2` | negative | `DC-` |

Важно:
- `J7` не подключать до завершения low-voltage bring-up;
- сначала проверяются `J2`, `J4`, `EM_STOP`, PWM и логические тесты.

## 6. J9 / Hall / Encoder на UM2014
| J9 pin | Назначение по UM2014 | Комментарий |
|---|---|---|
| `J9-1` | `Hall input 1 / encoder A+` | может быть заведен на `PB6` как Hall fallback |
| `J9-2` | `Hall input 2 / encoder B+` | может быть заведен на `PB7` как Hall fallback |
| `J9-3` | `Hall input 3 / encoder Z+` | может быть заведен на `PB8` как Hall fallback |
| `J9-4` | `3.3V или 5V` | питание внешнего Hall/encoder модуля |
| `J9-5` | `GND` | общий ноль |

Текущий рабочий стенд использует `AS5600 по I2C`, а не `A/B/Z`, поэтому J9 сейчас не обязателен.
Но по коду Hall входы в проекте поддерживаются:
- `PB6` = `Hall 1`
- `PB7` = `Hall 2`
- `PB8` = `Hall 3`

Если `AS5600` снять или он перестанет читаться, а нужен `FOC`, тогда Hall-датчики уже надо реально заводить.

## 7. Saleae Logic
Подключать только к логической стороне Blue Pill/IPM15, не к силовой HV-части.

| Канал Saleae | Куда цеплять | Что видно |
|---|---|---|
| `CH0` | `PA8` | `PWM-1H` |
| `CH1` | `PB13` | `PWM-1L` |
| `CH2` | `PA9` | `PWM-2H` |
| `CH3` | `PB14` | `PWM-2L` |
| `CH4` | `PA10` | `PWM-3H` |
| `CH5` | `PB15` | `PWM-3L` |
| `CH6` | `PB12` | `EM_STOP / BRAKE` |
| `GND` | любой общий `GND` логики | опорная земля для всех каналов |

Практика:
- земля Saleae должна быть подключена обязательно;
- если Logic2 не видит девайс, automation-тесты не имеют смысла;
- проверка выполняется через `tools/la_probe.py`.

## 8. Минимальная рабочая коммутация для bring-up
Если собирать стенд с нуля, минимально нужны:

1. `PC <-> UNO Q` по USB.
2. `PC <-> ST-Link` по USB.
3. `ST-Link <-> Blue Pill` по SWD.
4. `UNO Q <-> Blue Pill` по UART `D1/PA3`, `D0/PA2`, `GND`.
5. `Blue Pill <-> IPM15 J2` по `EM_STOP`, `PWM-1H/1L`, `PWM-2H/2L`, `PWM-3H/3L`, плюс питание и земли.
6. `Blue Pill <-> AS5600` по `PB10/PB11`, `3.3V`, `GND`.
7. `Saleae <-> Blue Pill` по `CH0..CH6` и `GND`.

## 9. Что не перепутать
- Основная телеметрия DC bus в текущем проекте идёт через Blue Pill: `STEVAL J2-14 HV bus voltage -> Blue Pill PA5`.
- `UNO Q A0` не является основным входом HV bus в рабочей конфигурации; это только legacy/fallback локального ADC.
- В текущей UART-схеме `PA5` нельзя одновременно использовать как старую SPI-линию `UNO Q D13/SCK`; если этот провод остался, он конфликтует с `J2-14` и может давать почти нулевой `bp_vdc` при реально заряженной DC-шине.
- Не подключать Saleae и любые низковольтные измерители к HV-шине.
- Не забывать общий `GND` между `UNO Q`, `Blue Pill`, `AS5600`, `Saleae`, `ST-Link`, `IPM15` логической частью.
- Не возвращать baud в старое значение `921600`: текущая рабочая конфигурация проекта `460800`.
- Если когда-то включать `USE_TIM1_BKIN=1`, `PB12` больше нельзя оставлять под `EM_STOP` без переназначения.
- `MIC` не включится, если энкодер физически не видит вращение вала, даже если I2C-связь с AS5600 исправна.
- Для текущей рабочей схемы обязательны: `UART`, `EM_STOP`, 6 линий `TIM1 PWM`, питание `+5V/+3.3V`, общий `GND`, и хотя бы один валидный датчик угла/положения (`AS5600` или Hall).
# CURRENT CRITICAL UPDATE: IPM HEATSINK TEMPERATURE
- Wire STEVAL/IPM15 `J2-26 heat sink temperature` to Blue Pill `PB0 (ADC1_IN8)`.
- Set UM2014 `SW3` to `NTC` (`2-3`).
- Do not wire `J2-34 measure phase C` to `PB0` in the current firmware; `PB0` is reserved for heatsink temperature.
- Wire `J2-31 measure phase A -> PA6` and `J2-33 measure phase B -> PA7`; firmware reports virtual `measure phase C` from A/B.
- Blue Pill reports `/api/status`: `bp_temp_raw`, `bp_temp_v`, `bp_temp_c`, `bp_temp_valid`, `bp_temp_fault`.
- Phase telemetry in `/api/status`: `bp_phase_a_v`, `bp_phase_b_v`, `bp_phase_c_v`, `bp_phase_valid`, `bp_phase_c_virtual`.
- Blue Pill latches `bp_fault=6` (`OVERTEMP`) on overtemperature/open NTC and disables PWM/EM_STOP.

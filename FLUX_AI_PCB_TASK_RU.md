# ТЗ Для Flux AI: Полная PCB MIC_AI / UNO Q / Blue Pill / STEVAL-IPM15B

> **АРХИВ / НЕ СОБИРАТЬ КАК НОВУЮ РЕВИЗИЮ.** Это ТЗ относится к старой carrier-плате Blue Pill. Целевая архитектура переведена на `NUCLEO-G431RB + X-NUCLEO-IHM09M2`; использовать [NUCLEO_G431_MIGRATION_RU.md](NUCLEO_G431_MIGRATION_RU.md). В частности, запрещено переносить отсюда прямое соединение земель UNO Q/Blue Pill и реле `SRD-12VDC-SL-C` в цепь 325 ВDC.

Нужно спроектировать печатную плату для стенда/устройства `MIC_AI`: интерфейсная и силовая carrier-плата между `UNO Q`, `Blue Pill STM32F103C8T6`, `STEVAL-IPM15B`, энкодером `AS5600`, предзарядом DC-шины и внешними измерительными/отладочными приборами.

Плата должна заменить текущую макетную коммутацию, уменьшить риск ошибок подключения и сохранить все уже проверенные программные интерфейсы проекта.

## 1. Главная Цель

Спроектировать PCB, которая:

- принимает вход `220..230 VAC` для формирования `DC+ / DC-` силовой шины через мост и предзаряд;
- управляет реле предзаряда `RELAY1` от `Blue Pill PB4`;
- выдает DC-шину на `STEVAL-IPM15B J7`;
- выдает auxiliary `+15V`, `+5V`, `+3.3V` для логики и интерфейса STEVAL;
- соединяет `Blue Pill` с `STEVAL-IPM15B J2` по PWM, safety, ADC и GPIO;
- соединяет `UNO Q` с `Blue Pill` по UART;
- соединяет `AS5600` с `Blue Pill` по I2C2;
- дает удобные разъемы/test-points для `ST-Link`, `Saleae`, мультиметра и осциллографа;
- физически разделяет HV/mains зону и low-voltage/control зону.

Не нужно проектировать силовой IPM заново. `STEVAL-IPM15B` остается внешней силовой платой/модулем, подключаемой через `J2/J4/J7`.

## 2. Обязательное Предупреждение По Безопасности

На плате есть потенциально смертельно опасные напряжения:

- `220..230 VAC`;
- после моста до `~310..325 VDC`;
- `J7 DC bus` для инвертора.

Flux AI должен:

- не смешивать HV-зону с USB/PC/SELV-зоной;
- не называть `DC-` обычным безопасным `GND`, если он связан с выпрямленной сетью;
- явно разделить nets: `HV_L`, `HV_N`, `HV_DC+`, `HV_DC-`, `IPM_COM`, `LOGIC_GND`, `USB_GND`;
- использовать net-tie только там, где это действительно требуется схемой и подтверждено человеком;
- добавить silk warnings: `DANGER HV`, `DISCHARGE BEFORE TOUCH`, `NO USB/Saleae ON HV unless isolated`;
- заложить creepage/clearance по целевому стандарту для 230 VAC / 325 VDC, не менее консервативного HV-разноса, с прорезями/keepout где нужно;
- использовать предохранитель, MOV/varistor, bleeder, предзаряд и достаточные зазоры вокруг силовых резисторов;
- отметить, что итоговая PCB требует проверки инженером по электробезопасности перед реальным питанием от сети.

Если Flux AI не может гарантировать безопасность grounding/isolation, он должен остановиться и запросить уточнение, а не разводить плату как обычную low-voltage PCB.

## 3. Архитектура Платы

### 3.1. Управление

Контроллер силовой логики: `Blue Pill STM32F103C8T6`.

Предпочтительный вариант для прототипа:

- посадочное место под готовый модуль `Blue Pill`;
- 2 ряда штырей `2.54 mm`;
- подписи всех используемых пинов.

Не использовать `PB4` под JTAG. В прошивке JTAG отключается, SWD остается. На PCB все равно нужен SWD-разъем.

### 3.2. HMI / Верхний Контроллер

`UNO Q` остается внешней платой UI/HMI. Связь с Blue Pill:

| UNO Q | Blue Pill | Назначение |
|---|---|---|
| `D1 / TX` | `PA3 / USART2_RX` | команды в Blue Pill |
| `D0 / RX` | `PA2 / USART2_TX` | telemetry/reply от Blue Pill |
| `GND` | `LOGIC_GND` / общий интерфейсный GND | общий ноль UART |

Добавить разъем `UNOQ_UART` на 4 пина:

```text
1 GND
2 UNOQ_RX_FROM_BP / Blue Pill PA2
3 UNOQ_TX_TO_BP / Blue Pill PA3
4 optional +5V / NC by default
```

`+5V` на этом разъеме сделать через jumper/DNP, чтобы случайно не запитать платы друг от друга.

## 4. Силовая Входная Часть 220 VAC -> DC Bus

### 4.1. Вход Сети

Разъем `J_AC_IN`:

```text
1 AC_L
2 AC_N
optional PE/chassis if enclosure requires it
```

Требования:

- terminal block с достаточным шагом для сети;
- silk: `220-230 VAC DANGER`;
- fuse holder `F1` последовательно с `AC_L`;
- номинал fuse оставить как BOM option: `TBD slow-blow`, footprint под 5x20 mm или другой согласованный держатель;
- MOV/varistor между `AC_L` и `AC_N`: исходно использовался `S14K300`, допускается аналог после проверки под сеть 230 VAC;
- место под NTC/inrush option можно предусмотреть, но основной предзаряд ниже уже обязателен.

### 4.2. Мост

`D1 = KBPC5010` или эквивалентный мост с запасом по напряжению/току.

Nets:

```text
AC_L_FUSED -> D1 AC~
AC_N       -> D1 AC~
D1 +       -> PRECHARGE_IN / RECT_DC+
D1 -       -> HV_DC- / PWR_GND
```

Важно: `HV_DC-` не считать безопасным `USB_GND`.

### 4.3. Предзаряд DC+

Схема предзаряда по текущей проверенной логике:

```text
RECT_DC+ -> R4 20R 5W -> R5 20R 5W -> HV_DC+
RECT_DC+ -> RELAY1 contact bypass -> HV_DC+
HV_DC-  -> J7 DC-
HV_DC+  -> J7 DC+
```

Компоненты:

- `R4 = 20 ohm 5W`, flameproof/wirewound, pulse-rated;
- `R5 = 20 ohm 5W`, flameproof/wirewound, pulse-rated;
- `RELAY1`: исходный прототип `SRD-12VDC-SL-C`, но Flux должен проверить rating контактов для DC bus. Предпочтительно выбрать реле/контактор, рассчитанный на нужное DC-напряжение и inrush/bypass current. Если остается `SRD-12VDC-SL-C`, добавить warning: prototype only / verify DC rating.

Требования к PCB:

- широкие дорожки для `RECT_DC+`, `HV_DC+`, `HV_DC-`;
- силовые резисторы вынести от пластика/электролитов/логики, оставить термозазор;
- вокруг HV-реле и резисторов сделать keepout;
- добавить test-points: `TP_RECT_DC+`, `TP_HV_DC+`, `TP_HV_DC-`;
- добавить bleeder/разряд DC bus.

### 4.4. Bleeder / Делитель

Предусмотреть цепь разряда шины:

```text
HV_DC+ -> R6 100K -> R7 100K -> R8 100K -> R9 100K -> HV_DC-
```

Требования:

- резисторы с достаточным voltage rating;
- footprints не меньше 1206, лучше 2512/through-hole если доступно;
- silk: `BLEEDER`;
- не использовать этот делитель как единственный точный ADC без отдельного расчета.

## 5. Реле Предзаряда RELAY1 От PB4

Это реле уже проверено на стенде:

- `PB4` дает управляющий сигнал;
- команда `PRECHARGE ON/OFF` переключает `bp_ext=0x08`;
- Saleae на контакте реле видел `edges=9`;
- `pwm=0`, `bp_fault=0`.

Схема драйвера:

```text
DC15V -> R1 50R -> RELAY1 coil -> Q1 collector
Q1 emitter -> GND
PB4 -> R2 1K -> Q1 base
Q1 base -> R3 47K -> GND
D2 UF4007 across coil
```

Компоненты:

| Ref | Значение | Назначение |
|---|---|---|
| `RELAY1` | `SRD-12VDC-SL-C` или DC-rated аналог | реле bypass предзаряда |
| `Q1` | `2N2222A` / эквивалент NPN | low-side driver катушки |
| `R1` | `50R` | ограничение/балласт катушки от 15V |
| `R2` | `1K` | базовый резистор |
| `R3` | `47K` | pulldown базы |
| `D2` | `UF4007` / 1N4007 допустим для катушки | flyback diode |

Полярность `D2`:

```text
катод/полоска -> сторона DC15V/R1
анод          -> сторона Q1 collector
```

Обязательные test-points:

```text
TP_PB4_PRECHARGE
TP_Q1_BASE
TP_Q1_COLLECTOR
TP_RELAY_COIL_PLUS
TP_RELAY_CONTACT_A
TP_RELAY_CONTACT_B
```

## 6. Питания 15V / 5V / 3.3V

Нужно предусмотреть:

### 6.1. `DC15V`

Вариант A: внешний вход `J_DC15_IN`.

```text
1 DC15V
2 GND_15V
```

Вариант B: onboard AC/DC module.

Исходно в схеме был `HLK-20M15`:

```text
AC_L / AC_N -> HLK-20M15 -> DC15V / GND
```

Flux должен выбрать один основной вариант и оставить второй как DNP/optional, если это не усложняет safety.

### 6.2. `+5V`

`15V -> buck 5V`.

Исходно использовался `LM2596 (5V)`.

Назначение:

- `STEVAL J2-25 +V power`;
- опционально питание внешних модулей;
- не питать UNO Q через этот rail без jumper/защиты.

### 6.3. `+3.3V`

`15V -> buck/LDO 3.3V`.

Исходно использовался `LM2596 (3.3V)`.

Назначение:

- `STEVAL J2-28 VDD_m`;
- `STEVAL J2-29 PWM VREF`;
- `AS5600 VCC`;
- Blue Pill 3.3V, если выбран режим питания от carrier-board.

Добавить:

- power LEDs для `15V`, `5V`, `3.3V`;
- test-points `TP_15V`, `TP_5V`, `TP_3V3`, `TP_GND`;
- предохранители/polyfuse на low-voltage rails по необходимости.

## 7. STEVAL-IPM15B J2 Подключение

Сделать разъем/шлейф к `STEVAL-IPM15B J2`. Pin mapping обязательный:

| STEVAL J2 | Сигнал | Blue Pill / Rail | Примечание |
|---|---|---|---|
| `J2-1` | `EM_STOP` | `PB12` | active-low shutdown/BRAKE/ESTOP |
| `J2-3` | `PWM-1H` | `PA8` | TIM1_CH1 |
| `J2-5` | `PWM-1L` | `PB13` | TIM1_CH1N |
| `J2-7` | `PWM-2H` | `PA9` | TIM1_CH2 |
| `J2-9` | `PWM-2L` | `PB14` | TIM1_CH2N |
| `J2-11` | `PWM-3H` | `PA10` | TIM1_CH3 |
| `J2-13` | `PWM-3L` | `PB15` | TIM1_CH3N |
| `J2-14` | `HV bus voltage` | `PA5 ADC1_IN5` | 0..3.3V telemetry from STEVAL |
| `J2-15` | `current phase A` | `PA0 ADC1_IN0` | current ADC |
| `J2-17` | `current phase B` | `PA1 ADC1_IN1` | current ADC |
| `J2-19` | `current phase C` | `PA4 ADC1_IN4` | current ADC |
| `J2-21` | `NTC bypass relay` | `NC` | сеть на STEVAL-IPM15B не используется; `PB1` также NC |
| `J2-23` | `dissipative brake PWM` | `PB9 / TIM4_CH4` | brake PWM |
| `J2-25` | `+V power` | `+5V` | logic/interface power |
| `J2-26` | `heat sink temperature` | `PB0 ADC1_IN8` | IPM TSO/temp |
| `J2-27` | `PFC sync` | `PB5` | GPIO output |
| `J2-28` | `VDD_m` | `+3.3V` | logic reference |
| `J2-29` | `PWM VREF` | `+3.3V` | PWM reference |
| `J2-31` | `measure phase A` | `PA6 ADC1_IN6` | phase voltage measure |
| `J2-33` | `measure phase B` | `PA7 ADC1_IN7` | phase voltage measure |
| `J2-34` | `measure phase C` | `NC by default` | firmware computes virtual C |
| even pins | `GND` | interface/IPM ground | connect per STEVAL reference |

Добавить series resistors или 0R jumpers на PWM/GPIO линиях:

```text
PA8, PB13, PA9, PB14, PA10, PB15, PB12, PB5, PB9
```

Рекомендация: footprints `0603/0805` под `0R..100R` для отладки/демпфирования.

Для ADC-линий добавить:

- series resistor `100R..1K`;
- RC footprint к analog ground/interface ground, если нужно;
- test-points на `VBUS_ADC`, `IA`, `IB`, `IC`, `TEMP`, `PHASE_A`, `PHASE_B`.

## 8. STEVAL J4 И J7

### 8.1. J4 Auxiliary

Разъем на STEVAL `J4`:

```text
J4+ -> +15V typ
J4- -> GND / return
```

Подписать: `STEVAL J4 VCC 15V MAX 20V`.

### 8.2. J7 DC Bus

Разъем на STEVAL `J7`:

```text
J7-1 -> HV_DC+
J7-2 -> HV_DC-
```

Подписать:

```text
STEVAL J7 DC BUS 125..400VDC
DANGER
```

Flux должен использовать разъем с достаточным шагом/напряжением и механической защитой от случайного касания.

## 9. AS5600 Encoder

Разъем `J_AS5600`:

| Pin | Blue Pill / Rail |
|---|---|
| `SCL` | `PB10 / I2C2_SCL` |
| `SDA` | `PB11 / I2C2_SDA` |
| `VCC` | `+3.3V` |
| `GND` | `LOGIC_GND` |

Добавить footprints под pull-up:

```text
R_SCL_PULLUP = 4.7K..10K to 3.3V, DNP if AS5600 module already has pullups
R_SDA_PULLUP = 4.7K..10K to 3.3V, DNP if AS5600 module already has pullups
```

## 10. ST-Link / SWD

Разъем `J_SWD`:

| Pin | Signal |
|---|---|
| 1 | `3.3V target sense` |
| 2 | `SWDIO / PA13` |
| 3 | `SWCLK / PA14` |
| 4 | `GND` |
| 5 | `NRST` |

Важно: не питать Blue Pill от ST-Link, если carrier уже питает `3.3V`, без jumper/диода/защиты.

## 11. Saleae / HIL Header

Добавить отдельный logic analyzer header `J_SALEAE`, все сигналы 3.3V logic:

| Saleae CH | Signal |
|---|---|
| `CH0` | `PA8 PWM-1H` |
| `CH1` | `PB13 PWM-1L` |
| `CH2` | `PA9 PWM-2H` |
| `CH3` | `PB14 PWM-2L` |
| `CH4` | `PA10 PWM-3H` |
| `CH5` | `PB15 PWM-3L` |
| `CH6` | `PB12 EM_STOP` |
| `CH7` | selectable: `PB4_PRECHARGE` or relay dry contact sense |
| `GND` | logic ground |

Для `CH7` сделать jumper:

```text
CH7_A = PB4_PRECHARGE
CH7_B = RELAY1_CONTACT_SENSE_LOW_VOLTAGE
```

Не подключать Saleae к HV/DC bus.

## 11.1. Управляемый 3-Пиновый Вентилятор

Добавить разъем `J_FAN1` для 3-pin fan. Типовой 3-пиновый вентилятор имеет:

```text
1 GND
2 +12V
3 TACH open-collector/open-drain
```

Для регулирования оборотов 3-pin вентилятора нельзя подключать мотор напрямую к GPIO. Нужен силовой ключ.

Предпочтительная схема для PCB:

- питание вентилятора от отдельного `+12V_FAN`;
- `+12V_FAN` получить из `DC15V` через buck/LDO, не питать 12V fan напрямую от 15V;
- управление скоростью от `Blue Pill PB3` как `FAN_PWM`;
- tach-сигнал завести на `Blue Pill PA11` как `FAN_TACH`, через series resistor и pull-up к `3.3V`;
- если `PA11` занят/нежелателен из-за USB pins на Blue Pill module, Flux должен предложить другой свободный input и явно отметить конфликт.

Рекомендуемая силовая топология:

```text
PB3_FAN_PWM -> gate/driver -> high-side P-MOSFET or protected high-side switch
+12V_FAN -> high-side switch -> FAN1 pin +12V
FAN1 GND -> LOGIC_GND
FAN1 TACH -> PA11_FAN_TACH, pull-up 10K to 3.3V, series 1K
```

Почему high-side предпочтительнее:

- у 3-pin fan tach привязан к земле вентилятора;
- если делать low-side switching по GND, tach будет пропадать/искажаться во время PWM;
- high-side switching оставляет `FAN_GND` постоянным и делает tach читаемым.

Если Flux хочет упростить схему и tach не нужен, допускается low-side N-MOSFET:

```text
FAN + -> +12V_FAN
FAN - -> N-MOSFET drain
N-MOSFET source -> LOGIC_GND
PB3 -> gate через 100R..1K
gate pulldown 47K..100K
```

Но для финальной платы оставить footprints под high-side вариант или явно поставить `DNP` для tach.

Требования:

- добавить test-points `TP_FAN_PWM_PB3`, `TP_FAN_TACH_PA11`, `TP_12V_FAN`;
- добавить bulk capacitor рядом с fan connector, например `100uF + 100nF`;
- добавить protection/TVS по необходимости;
- подписать pinout на шелкографии;
- не использовать `PB3`, если JTAG не отключен. В текущей прошивке JTAG отключается, SWD остается активным.

## 12. Relay Contact Sense Для Теста

Чтобы проверять контакт реле безопасно, нужен low-voltage dry-contact sense:

```text
3.3V -> pull-up 10K -> RELAY_CONTACT_SENSE -> relay contact -> GND
```

или обратная логика через jumper.

Требование: эта цепь должна быть полностью отделена от HV-контакта, если контакт реле реально шунтирует `R4/R5` в HV DC+.

Если используется один и тот же силовой контакт для HV bypass, нельзя напрямую заводить его на Saleae/3.3V. Для проверки контакта нужен отдельный auxiliary contact реле или изолированный способ измерения. Если выбранное реле имеет только один контакт, `CH7` должен цепляться к `PB4`, а не к HV-контакту.

## 13. Разводка PCB

Минимальные правила:

- 2-layer FR-4 1.6 mm допустимо для прототипа, но Flux может предложить 4-layer только если HV-clearance не ухудшается;
- HV/mains zone физически отдельно от logic zone;
- no copper pour под HV slots/keepout;
- широкие дорожки для `HV_DC+`, `HV_DC-`, precharge path, relay contact path;
- low-voltage PWM/UART/I2C route away from bridge/relay contacts/resistors;
- под силовыми резисторами оставить thermal clearance;
- mounting holes M3, минимум 4 шт.;
- silk direction labels на всех разъемах;
- test-points доступны щупом мультиметра;
- все HV terminal blocks должны быть ориентированы к краю платы;
- no silkscreen-only safety: реальные clearance/slots важнее.

Flux должен вывести таблицу расчетных ширин дорожек под выбранный copper weight и ожидаемые токи.

## 14. Net Names

Использовать понятные имена:

```text
AC_L
AC_N
AC_L_FUSED
RECT_DC+
HV_DC+
HV_DC-
DC15V
PWR_5V
PWR_3V3
LOGIC_GND
IPM_COM
USB_GND
PB4_PRECHARGE
PB12_EM_STOP
PA8_PWM_1H
PB13_PWM_1L
PA9_PWM_2H
PB14_PWM_2L
PA10_PWM_3H
PB15_PWM_3L
PA5_VBUS_ADC
PA0_IA
PA1_IB
PA4_IC
PB0_HEATSINK_TEMP
PA6_PHASE_A
PA7_PHASE_B
PB10_AS5600_SCL
PB11_AS5600_SDA
UART_BP_TX_PA2
UART_BP_RX_PA3
```

## 15. Что Не Перепутать

Критически важно:

- `PB4` = внешнее физическое `RELAY1` предзаряда / bypass `R4+R5`;
- `PB1` = `NC`; STEVAL `J2-21` также оставить `NC`;
- `PB12` = `EM_STOP`, не переносить на `TIM1_BKIN`, пока прошивка не изменена;
- `PB0` = heatsink temperature, не использовать для `measure phase C`;
- `measure phase C` сейчас не подключен, firmware вычисляет virtual C из A/B;
- `AS5600` идет на `PB10/PB11`, а не на UNO Q;
- `UNO Q` не генерирует силовой PWM, он только HMI/UI/команды;
- deadtime/PWM реализованы на Blue Pill TIM1.

## 16. Проверенные Тесты, Которые PCB Должна Поддержать

После изготовления платы должны пройти:

### 16.1. PRECHARGE Relay Test

```powershell
py -3 -u .\tools\precharge_relay_preflight.py --url http://127.0.0.1:18080 --la-channel 7
```

Ожидаемо:

```text
overall_pass=true
precharge toggles 1/0
bp_ext toggles 8/0
pwm=0
bp_fault=0
Saleae CH7 edges >= 9
```

### 16.2. NTC Relay Test

```powershell
py -3 -u .\tools\ntc_relay_preflight.py --url http://127.0.0.1:18080 --la-channel 7 --relay ntc
```

Ожидаемо:

```text
ntc toggles 1/0
bp_ext bit 0x01 toggles
pwm=0
bp_fault=0
```

### 16.3. Full Low-Voltage HIL

```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080
```

Ожидаемо:

```text
overall_pass=true
full_suite_pass_count=80
full_suite_fail_count=0
final_safe=true
pwm=0
bp_fault=0
bp_bad_cnt=0
```

### 16.4. HV/J7 Только После Low-Voltage PASS

HV/J7 не включать до успешных low-voltage тестов.

Опционально:

```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080 --with-hv
```

Только при:

- внешнее ограничение тока готово;
- E-STOP готов;
- DC bus подключен правильно;
- оператор понимает риск HV.

## 17. Deliverables От Flux AI

Нужно получить:

- полную schematic;
- PCB layout;
- BOM;
- pick/place если применимо;
- Gerber/Drill;
- PDF schematic;
- изображение top/bottom платы;
- ERC/DRC report;
- отдельный список unresolved safety assumptions;
- таблицу connector pinout;
- таблицу creepage/clearance decisions;
- список test-points;
- рекомендации по корпусу/изоляции.

Flux AI не должен завершать проект, если:

- неясно, связаны ли `HV_DC-`, `IPM_COM`, `LOGIC_GND`, `USB_GND`;
- выбранное реле не подтверждено по DC contact rating;
- нет достаточного clearance между mains/HV и low-voltage;
- Saleae/USB может оказаться напрямую связан с неизоляционной HV-шиной;
- отсутствует fuse/bleeder/precharge.

## 18. Короткий Prompt Для Flux AI

Скопировать в Flux AI:

```text
Design a complete PCB for the MIC_AI motor-control bench. It is a carrier/interface/precharge board for UNO Q, Blue Pill STM32F103C8T6, STEVAL-IPM15B, AS5600 encoder, Saleae HIL header, ST-Link SWD, AC mains to DC bus precharge, and low-voltage power rails.

Do not redesign the IPM power stage; STEVAL-IPM15B remains external and connects via J2/J4/J7. Use the pin mapping and safety constraints from this document exactly.

Critical corrections:
- PB4 controls the external RELAY1 precharge bypass relay through R2/Q1.
- PB1 and STEVAL J2-21 are both NC; that named net is unused on STEVAL-IPM15B.
- PB12 is EM_STOP.
- PB10/PB11 are AS5600 I2C2.
- PB0 is heatsink temperature.
- Measure phase C is not connected by default; firmware computes virtual C.

The board includes 220-230 VAC input, fuse, MOV, KBPC5010 bridge, R4+R5 precharge resistors, relay bypass, DC bus output to STEVAL J7, 15V/5V/3.3V rails, Blue Pill module socket, UNO Q UART header, ST-Link SWD header, AS5600 connector, STEVAL J2/J4/J7 connectors, Saleae header CH0..CH7, and all listed test points.

Apply conservative HV/mains creepage/clearance and keep HV/mains physically separated from USB/PC/SELV logic. Do not silently tie HV_DC-, IPM_COM, LOGIC_GND, and USB_GND; show explicit net ties and ask if isolation assumptions are unclear. Add DANGER HV silkscreen warnings and no-HV-to-Saleae warnings.

Generate schematic, PCB, BOM, DRC/ERC, Gerbers, connector pinout table, test-point table, and a list of unresolved safety assumptions.
```

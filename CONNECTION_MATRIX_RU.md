# Карта Коммутации MIC_AI REV 2.0

> **Статус:** этот документ описывает проверенную legacy-коммутацию с Blue Pill. Новая целевая сборка на `NUCLEO-G431RB + X-NUCLEO-IHM09M2` описана в [NUCLEO_G431_MIGRATION_RU.md](NUCLEO_G431_MIGRATION_RU.md). Не смешивать распиновки двух архитектур.

Каноническая принципиальная схема: [output/pdf/MIC_AI_REV2_SCHEMATIC.pdf](output/pdf/MIC_AI_REV2_SCHEMATIC.pdf).
Полный список сетей и выводов: [hardware/mic_ai_rev2/MIC_AI_REV2_CONNECTIONS.csv](hardware/mic_ai_rev2/MIC_AI_REV2_CONNECTIONS.csv).

## 1. Главное Правило Земель

В установке два гальванически разделённых домена:

| Домен | Что в него входит | Земля |
|---|---|---|
| `SAFE` | PC, UNO Q, Saleae, кнопка/вспомогательный контакт E-STOP | `SAFE_GND` |
| `HOT/HV` | Blue Pill, STEVAL-IPM15B, AS5600, вентилятор, SWD-разъём | `HV_DC_MINUS_HOT_GND` |

`SAFE_GND`, `HOT_GND`, `AC_N` и `PE` не объединять. `HOT_GND` электрически равен `J7 DC-` и при включённой сети опасен относительно земли/корпуса.

Разрешённые переходы между доменами:

- UART только через `ISO7721DWR`;
- Saleae CH0..CH7 только через два `ISO7740FDWR`;
- аппаратный запрет PWM только через `LTV-817`;
- никаких прямых USB, UART-GND или щупов между SAFE и HOT при подключённой HV.

## 2. Сводная Матрица

| Откуда | Куда | Соединение |
|---|---|---|
| PC | UNO Q | USB-C/сеть, только SAFE domain |
| UNO Q или PC USB-UART | Blue Pill | через `JP_UART_TX/RX` и `ISO7721DWR`; одновременно один источник |
| Blue Pill | STEVAL J2 | прямые HOT-сигналы согласно разделу 4 |
| Saleae | J_SALEAE | `CH0..CH7 + SAFE_GND`, после ISO7740; не на Blue Pill напрямую |
| Blue Pill | AS5600 | `PB10/PB11/HOT_3V3/HOT_GND`, внутри закрытого HV-корпуса |
| Blue Pill | 4-pin fan | `PB3 PWM`, `PA11 TACH`, `HOT_12V`, `HOT_GND` |
| ST-Link | J_SWD | только при снятом J7/HV и разряженной DC-шине |
| Выпрямитель/предзаряд | STEVAL J7 | `HV_DC+` и `HV_DC-` |
| HOT_15V | STEVAL J4 | `J4+ = HOT_15V`, `J4- = HOT_GND` |
| PE | корпус, рама двигателя, доступный металлический радиатор | защитный проводник; не `HOT_GND` |

## 3. SAFE Сторона

### 3.1 UNO Q

| UNO Q | Куда |
|---|---|
| `VIN` | внешний SAFE источник `7..24V` или питание по USB-C |
| `GND` | только `SAFE_GND` |
| `D1 TX` | `JP_UART_TX.UNO` |
| `D0 RX` | `JP_UART_RX.UNO` |
| `OUT_3V3` | `JP_SAFE_3V3.UNO`, только как выход |
| `5V_USB` | не подключать к питанию carrier board |

Не подавать внешние 5 В или 3,3 В обратно в UNO Q. Для UART выбрать положение `UNO` на обоих джамперах TX/RX.

### 3.2 PC USB-UART

Используется адаптер с логическими уровнями 3,3 В:

| USB-UART | Куда |
|---|---|
| `TX` | `JP_UART_TX.PC` |
| `RX` | `JP_UART_RX.PC` |
| `GND` | `SAFE_GND` |
| вывод питания | `NC` |

Для PC-direct выбрать положение `PC` на обоих джамперах. UNO Q и PC не должны одновременно управлять одной линией.

### 3.3 Saleae

| Saleae | J_SALEAE | Сигнал HOT до изолятора |
|---|---|---|
| `CH0` | `CH0` | PWM_UH, STEVAL J2-3 |
| `CH1` | `CH1` | PWM_UL, STEVAL J2-5 |
| `CH2` | `CH2` | PWM_VH, STEVAL J2-7 |
| `CH3` | `CH3` | PWM_VL, STEVAL J2-9 |
| `CH4` | `CH4` | PWM_WH, STEVAL J2-11 |
| `CH5` | `CH5` | PWM_WL, STEVAL J2-13 |
| `CH6` | `CH6` | PB12 RUN до hardware interlock |
| `CH7` | `CH7` | PB4 external precharge command |
| `GND` | `SAFE_GND` | только безопасная сторона изоляторов |

### 3.4 Аппаратный Запрет PWM

`SAFE_5V -> нормально-замкнутый вспомогательный контакт E-STOP -> 680R -> LTV-817 -> SAFE_GND`.

На HOT стороне сигнал проходит через `74LVC1G14`, затем логически умножается на `PB12` в `74LVC1G08`. Только закрытый контур и `PB12=HIGH` разрешают `STEVAL J2-1=HIGH`. Обрыв провода, исчезновение SAFE_5V или LOW на PB12 дают PWM STOP.

Этот контур не заменяет силовой E-STOP. Настоящая кнопка должна также снимать сеть внешним контактором требуемой категории безопасности.

## 4. HOT Сторона: Blue Pill И STEVAL J2

Blue Pill питается только от `HOT_3V3`; его вывод `5V` остаётся `NC`. Все указанные ниже земли относятся к `HV_DC-/HOT_GND`.

| J2 | Сигнал | Blue Pill / питание |
|---|---|---|
| 1 | EM_STOP | выход hardware interlock через 220R; PB12 является входом AND |
| 3 | PWM-1H | PA8 TIM1_CH1 через 33R |
| 5 | PWM-1L | PB13 TIM1_CH1N через 33R |
| 7 | PWM-2H | PA9 TIM1_CH2 через 33R |
| 9 | PWM-2L | PB14 TIM1_CH2N через 33R |
| 11 | PWM-3H | PA10 TIM1_CH3 через 33R |
| 13 | PWM-3L | PB15 TIM1_CH3N через 33R |
| 14 | HV bus voltage | PA5 ADC1_IN5 через 100R |
| 15 | current phase A | PA0 ADC1_IN0 через 100R |
| 17 | current phase B | PA1 ADC1_IN1 через 100R |
| 19 | current phase C | PA4 ADC1_IN4 через 100R |
| 21 | NTC bypass relay | `NC`; сеть не используется на STEVAL-IPM15B |
| 23 | dissipative brake PWM | PB9 TIM4_CH4 через 100R |
| 25 | +V power | `HOT_5V` |
| 26 | heat sink temperature | PB0 ADC1_IN8 через 100R; SW3=`TSO 1-2` |
| 27 | PFC sync | PB5 через 100R |
| 28 | VDD_m | `HOT_3V3` |
| 29 | PWM VREF | `HOT_3V3` |
| 31 | measure phase A | PA6 ADC1_IN6 через 100R |
| 33 | measure phase B | PA7 ADC1_IN7 через 100R |
| 34 | measure phase C | `NC`; прошивка вычисляет виртуальную C из A/B |
| 2/4/6/8/10/12/16/18/20/22/24/30/32 | GND | подключить все к `HV_DC-/HOT_GND` |

На шести PWM и выходах PB5/PB9 стоят подтяжки 47K к HOT_GND. PB12 имеет отдельную подтяжку 47K до AND, а J2-1 - 47K после AND. PB1 и J2-21 остаются NC. При reset/power-loss команды по умолчанию LOW.

## 5. AS5600, Fan И SWD

### AS5600

| Blue Pill | AS5600 |
|---|---|
| PB10 | SCL |
| PB11 | SDA |
| HOT_3V3 | VCC |
| HOT_GND | GND |

Подтяжки 4,7K ставить только если их нет на модуле. Модуль и кабель находятся внутри недоступного HV-корпуса.

### Вентилятор

Стандартный 4-pin разъём: `1 GND`, `2 +12V`, `3 TACH`, `4 PWM`.

- `HOT_12V` и `HOT_GND` подаются постоянно;
- `PB3 -> 1K -> MMBT2222A`, коллектор на PWM, эмиттер на HOT_GND;
- частота PWM 25 кГц, инверсия учтена в прошивке;
- `TACH -> 1K -> PA11`, подтяжка 10K к HOT_3V3;
- Blue Pill USB при занятом PA11 не использовать;
- 3-pin fan на контактах 1..3 работает на полной скорости без регулировки.

### SWD

| ST-Link | J_SWD |
|---|---|
| VREF | HOT_3V3, только измерение уровня |
| SWDIO | PA13 |
| SWCLK | PA14 |
| GND | HOT_GND |
| NRST | NRST |

ST-Link отключить до подачи J7/HV. Не питать HOT-плату от ST-Link.

## 6. HOT Питание И Предзаряд

### Источник 15 В

`JP_HOT15_SRC` выбирает ровно один источник:

- `ONBOARD`: HLK-20M15 от `AC_L_FUSED + AC_N`;
- `EXTERNAL`: внешний изолированный 15 В только для стендовых low-voltage тестов при снятом J7/HV.

Не замыкать оба положения и отключать внешний БП перед подачей сети. Общий выход `HOT_15V` идёт на STEVAL J4 и преобразователи `12V/5V/3.3V`.

### Сеть И DC-шина

Правильная последовательность сетей:

`AC_L -> F1 -> AC_L_FUSED -> BR1.AC1`

`AC_N -> BR1.AC2`

`MOV1 S14K300` подключён между `AC_L_FUSED` и `AC_N`, то есть после F1.

`BR1.PLUS -> RECT_DC+ -> RPRE1 20R -> RPRE2 20R -> HV_DC+`

`K1 NO` подключён параллельно суммарным 40R. K1: TE Mini K `2-1904058-5`, катушка 12 В, контакты 400 VDC/20 A. `PB4` управляет катушкой через AO3400A; PB1 сюда не подключать.

`BR1.MINUS -> HV_DC-/HOT_GND -> J7 DC-`.

`PE` идёт только на корпус, раму двигателя и доступные металлические части. Не соединять PE с HOT_GND.

Номинал F1 остаётся `F1_VALUE_BY_LOAD`: его выбирают по току двигателя, проводам и координации защиты. Резисторы предзаряда должны быть импульсными минимум 25 Вт каждый; старые 20 Ом 5 Вт не использовать.

## 7. Запрещённые Соединения

- `UNO Q GND <-> Blue Pill GND` напрямую;
- `Saleae GND <-> Blue Pill/HOT_GND` при собранной HV-схеме;
- обычный ST-Link или USB Blue Pill при подключённой J7/HV;
- заземлённый осциллограф на HOT-сигналы без подходящего дифференциального HV-пробника;
- `AC_N <-> HV_DC-`, `PE <-> HV_DC-`, `SAFE_GND <-> HOT_GND`;
- одновременная подача внешнего и бортового HOT_15V;
- питание UNO Q через его выводы 5V/3.3V;
- подключение PB1 или STEVAL J2-21: оба контакта должны оставаться `NC`.

## 8. Перед Первой Подачей Сети

1. Омметром подтвердить разрыв `SAFE_GND-HOT_GND`, `PE-HOT_GND` и `AC_N-HV_DC-` при снятом BR1.
2. Проверить маркировку выводов KBPC5010 `+`, `-`, `~`, `~`, а не номера footprint.
3. Проверить, что K1 действительно параллелен 40R, а не стоит последовательно.
4. Выполнить low-voltage этапы из [BRINGUP_STEPS_RU.md](BRINGUP_STEPS_RU.md).
5. Провести отдельную проверку PCB по creepage, clearance, ширине HV-дорожек, прорезям, теплу и корпусу.
6. Подобрать F1 и внешний сетевой контактор. До этого 230VAC не подавать.

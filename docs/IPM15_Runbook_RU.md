# UNOQ_MOTOR: Запуск с STEVAL-IPM15B (UM2014 / IPM15)

Документ для bring-up и безопасного запуска связки `UNO Q (UI)` + `Blue Pill (PWM)` + `STEVAL-IPM15B`.

Важно для текущего стенда: основной runtime-путь управления сейчас PC-direct,
без UNO Q в цепочке команд:

```text
ПК / HMI / AI -> USB-изолятор -> USB-UART 3.3 В -> Blue Pill -> STEVAL/IPM
```

UNO Q остается поддерживаемым UI/экраном и заготовкой для переноса, но перед
активным PWM ориентироваться надо на `PC_DIRECT_STM32_RU.md` и
`tools/bench_gate_report.py`.

Перед любой командой ниже, которая может привести к `START`, PWM-свитчингу или
HV/J7-прогону, сначала обновить статус:

```powershell
py -3 -u .\tools\refresh_bench_status.py --url http://127.0.0.1:18080
```

Если `CURRENT_BENCH_STATUS_RU.md` показывает `Active PWM разрешен: НЕТ` или
`ready_for_active_pwm=false`, эти активные команды не запускать. Исключение
только для явно описанных offline/read-only проверок и для ST-Link static
preflight после физического подтверждения, что HV/J7 отключен и DC-шина
разряжена.

## 0. Состав системы (что за модуль и зачем)
* `ПК / PC-direct HMI`: текущий основной источник команд к Blue Pill через изолированный USB-UART 3.3 В.
* `UNO Q` (прошивка `UNOQ_MOTOR/UNOQ_MOTOR.ino`): поддерживаемый UI/экран и будущий перенос верхнего уровня; не обязателен для текущего PC-direct runtime.
* `Blue Pill (STM32F103C8)` (PlatformIO `bluepill_uart_pwm_pio`): генерация комплементарного ШИМ (TIM1 + deadtime), аппаратная "безопасность" (EM_STOP/BRAKE), таймаут связи, чтение энкодера AS5600 (I2C2).
* `STEVAL-IPM15B` (UM2014): силовой модуль (IPM STGIB15CH60TS-L) и интерфейсные сигналы на разъеме J2 (ШИМ, EM_STOP, токи/шина/температура и т.п.).
* `ST-LINK` (прошивка Blue Pill): `upload_protocol = stlink`.
* `Logic analyzer + Logic2` (Saleae Automation): автоматические захваты и проверка наличия PWM по CSV.

## 1. Питание (обязательно до любых тестов)
UM2014 прямо пишет: **плата требует +5 V и +3.3 V через J2** (см. `um2014-...pdf`, page 28/35).

Рекомендуемое:
* J2-25 `+V power` -> стабильные `+5V`
* J2-28 `VDD_m` -> `+3.3V`
* J2-29 `PWM VREF` -> `+3.3V` (как опорное для логики PWM)
* J4 `VCC supply` -> внешний auxiliary БП, типично `+15V`, максимум `20V`
* Любой(ые) `GND` пины -> общий `GND` (соединить "звездой", короткими проводами)

Важно:
* Не включать HV (125..400V DC) пока не проверены ШИМ, EM_STOP, таймауты и ESTOP на логическом уровне.
* Не путать `J4` и `J7`: `J4` это low-voltage auxiliary питание драйвера, `J7` это основная силовая DC bus.
* Логические уровни и аналоговые сигналы UM2014 должны попадать в диапазон АЦП Blue Pill (0..3.3V). Если UM2014 отдает больше, нужен делитель/буфер.

## 2. Коммутация (проводка)

### 2.1. Runtime UART ↔ Blue Pill (115200)
Текущий PC-direct вариант:

* USB-UART `TX` -> Blue Pill `PA3 (USART2_RX)`
* USB-UART `RX` <- Blue Pill `PA2 (USART2_TX)`
* Изолированная сторона `GND` -> Blue Pill `GND`
* UART уровни только 3.3 В.

Исторический UNO Q вариант, если верхний уровень снова переносится на UNO Q:

* UNO Q `D1 (TX)` -> Blue Pill `PA3 (USART2_RX)`
* UNO Q `D0 (RX)` <- Blue Pill `PA2 (USART2_TX)`
* `GND` -> `GND`

### 2.2. Blue Pill ↔ UM2014 (J2, Table 6)
PWM (TIM1 комплементарные):
* J2-3 `PWM-1H` -> `PA8`  (TIM1_CH1)
* J2-5 `PWM-1L` -> `PB13` (TIM1_CH1N)
* J2-7 `PWM-2H` -> `PA9`  (TIM1_CH2)
* J2-9 `PWM-2L` -> `PB14` (TIM1_CH2N)
* J2-11 `PWM-3H` -> `PA10` (TIM1_CH3)
* J2-13 `PWM-3L` -> `PB15` (TIM1_CH3N)

EM_STOP / BRAKE:
* J2-1 `emergency stop` -> `PB12` (GPIO, по умолчанию active-low shutdown line)

Аналоговые входы (для телеметрии и будущей защиты):
* J2-15 `current phase A` -> `PA0 (ADC1_IN0)`
* J2-17 `current phase B` -> `PA1 (ADC1_IN1)`
* J2-19 `current phase C` -> `PA4 (ADC1_IN4)`
* J2-14 `HV bus voltage` -> `PA5 (ADC1_IN5)`
* J2-26 `heat sink temperature` -> `PB0 (ADC1_IN8)`, current firmware: UM2014 `SW3=TSO 1-2`

Опциональные I/O:
* J2-21 `NTC bypass relay` -> `NC`; сеть на STEVAL-IPM15B не используется, `PB1` также оставить `NC`
* J2-27 `PFC sync.` -> `PB5` (GPIO out)
* J2-23 `dissipative brake PWM` -> `PB9` (TIM4_CH4, опционально)

Важно: `PB0` занят тепловой защитой IPM, поэтому `J2-34 measure phase C` в текущей прошивке не подключать. Blue Pill измеряет `J2-31/J2-33`, а `measure phase C` считает виртуально из двух фаз. При перегреве или rail-like/невалидной температурной телеметрии Blue Pill сам отключает PWM/EM_STOP и выставляет `bp_fault=6`.

GND:
* J2-2/4/6/8/10/12/16/18/20/22/24/30/32 -> `GND` (подключить минимум 2-3 земли)

### 2.3. Логический анализатор (каналы фиксированы)
Карта каналов (как у тебя):
* `CH0=PA8`, `CH1=PB13`, `CH2=PA9`, `CH3=PB14`, `CH4=PA10`, `CH5=PB15`, `CH6=PB12 (BRAKE)`

### 2.4. Энкодер AS5600 (I2C2)
Подключать к Blue Pill:
* `PB10` = `I2C2_SCL`
* `PB11` = `I2C2_SDA`
* `3.3V` и `GND`

Модуль AS5600 обычно уже имеет подтяжки на SDA/SCL. Если нет, поставить 4.7k..10k кОм на 3.3V.

## 3. Модель безопасности (что именно гарантируем)
Blue Pill делает "силовую" безопасность на своей стороне:
* На старте: PWM выключен, `EM_STOP` активирован (shutdown).
* При `STOP` или `MODE OFF` или `ENABLE=0`: PWM выключен, `EM_STOP` активирован.
* При `ESTOP`: защелка `fault_latched`, PWM выключен, `EM_STOP` активирован.
* При пропаже связи: `TIMEOUT_MS` (см. `bluepill_uart_pwm_pio/include/config.h`) переводит в безопасное состояние.
* Сброс защелки: `CLEAR` возможен только когда `MODE OFF` и `ENABLE=0` и `ESTOP=0`.
* В текущем `web_hmi` одна аварийная кнопка работает как `ESTOP` / `ESTOP CLEAR` по текущему состоянию защелки.
* Команда `START` на UNOQ также снимает локальную защелку `ESTOP`, но в UI доступен и явный сброс через ту же кнопку.

Не полагаться только на софт: для HV обязательно иметь внешний E-STOP/контактор/предохранители.

## 4. Доступ к UI (ПК и телефон)
Варианты:
* Телефон по Wi-Fi: `http://<IP UNOQ>:8080` (UNOQ сервер слушает `0.0.0.0`).
* ПК по USB/ADB: `adb forward tcp:18080 tcp:8080` и `http://127.0.0.1:18080`.
* Телефон через ПК (если Wi-Fi изоляция): поднять прокси `tools/ui_http_bridge.py` и заходить на `http://<IP ПК>:8080`.

Практически удобнее запускать:
```powershell
py -3 -u .\tools\ui_access.py --bridge
```

Скрипт сам делает `adb start-server`, поднимает `forward`, проверяет `/api/status` и, если ADB не поднялся, печатает состояние USB-инстансов UNO Q. Если он пишет `phantom`, плата физически не присутствует в Windows и тесты бессмысленно гонять до восстановления USB.

## 5. Быстрая проверка энкодера (положение магнита)
Команда (на ПК):
```powershell
py -3 -u .\tools\encoder_test.py --url http://127.0.0.1:18080 --duration 10 --poll 0.05
```
Ожидаем:
* `enc_ok` = 1
* `enc_raw` меняется при вращении магнита/вала
* `enc_deg` меняется 0..360

Если Logic2 открыт, но automation/анализатор не поднимается:
```powershell
py -3 -u .\tools\logic2_recover.py --restart
```

Скрипт отличает два сценария:
* Logic2 жив, но анализатор не виден;
* сам `Logic.exe` падает сразу после старта.

## 6. Тесты ШИМ (UI -> Blue Pill -> PWM -> LA -> метрики)
Если нужен не набор ручных команд, а один полный regression-run, использовать:
```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080
```

Этот раннер последовательно делает build, `ui_access`, encoder sanity, scalar preflight, FOC/MIC preflight, полный LA-suite и диагностический `mic_ai_compare`.

Перед запуском убедиться:
* `/api/status` доступен
* `tools/la_probe.py` показывает **не пустой** список `devices` (иначе захваты невозможны)

Один кейс:
```powershell
py -3 -u .\tools\ui_pwm_case.py --url http://127.0.0.1:18080 --mode VF --freq 5.0 --tag vf_5 ^
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Полный suite (sweep 0..50 шаг 0.1, захваты в ключевых точках):
```powershell
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 ^
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Рекомендуемый safety-прогон для проверки ключей инвертора:
```powershell
py -3 -u .\tools\scalar_vf_preflight.py --url http://127.0.0.1:18080 ^
  --freqs 0.1,0.5,1,2,5,10,20,30,40,50 --estop-freqs 0.5,10,50 ^
  --la-channels 0,1,2,3,4,5,6 --la-rate 24000000 --la-duration 0.003 ^
  --min-handoff-gap-ns 600
```

Рекомендуемый FOC/MIC preflight:
```powershell
py -3 -u .\tools\foc_mic_preflight.py --url http://127.0.0.1:18080 ^
  --foc-freqs 0.5,5,10,20,50 --foc-estop-freqs 10,50 --mic-freqs 5,10,20 ^
  --la-channels 0,1,2,3,4,5,6 --la-rate 24000000 --la-duration 0.003 ^
  --min-handoff-gap-ns 600
```

Рекомендуемый HV/J7 preflight:
```powershell
py -3 -u .\tools\hv_j7_preflight.py --url http://127.0.0.1:18080 ^
  --vf-freqs 0.5,1,2,5 --estop-freqs 1,5 ^
  --la-channels 0,1,2,3,4,5,6 --la-rate 24000000 --la-duration 0.02 ^
  --min-handoff-gap-ns 600
```

Если `vdc` на твоём стенде уже откалиброван и его масштаб понятен:
```powershell
py -3 -u .\tools\hv_j7_preflight.py --url http://127.0.0.1:18080 ^
  --vf-freqs 0.5,1,2,5 --estop-freqs 1,5 ^
  --vdc-min <MIN> --vdc-max <MAX> ^
  --la-channels 0,1,2,3,4,5,6 --la-rate 24000000 --la-duration 0.02 ^
  --min-handoff-gap-ns 600
```

Полный HIL-suite с deadtime-check:
```powershell
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 ^
  --capture-every-hz 1.0 --la-channels 0,1,2,3,4,5,6 ^
  --la-rate 24000000 --la-duration 0.06 --case-retries 2 --retry-delay 0.2 ^
  --min-handoff-gap-ns 600
```

Смысл этого режима:
* `scalar_vf_preflight.py` ждёт реальный steady-state в `VF`, а не только принятие `freq_cmd`.
* `foc_mic_preflight.py` отдельно ждёт `FOC_RUN` и проверяет `FOC/MIC` без смешивания с переходным `FOC_ALIGN`.
* `ui_pwm_suite.py` при `--min-handoff-gap-ns 600` валит кейс, если на комплементарной паре не подтверждён deadtime.
* Logic2 transient `StartCapture ABORTED` обрабатывается как retryable, а не как ложный итоговый FAIL.
* `hv_j7_preflight.py` нужен уже после успешного low-voltage HIL, когда `J7` действительно подан и требуется отдельно перепроверить ограниченный scalar/VF и `ESTOP/recover` под шиной.

Для единичных ложных `FAIL` из-за краткого сбоя transport/control plane доступны точечные повторы без маскировки реальной PWM-проблемы:
```powershell
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 --case-retries 1 --retry-delay 0.2
py -3 -u .\tools\ui_pwm_case.py --url http://127.0.0.1:18080 --mode VF --freq 5.0 --tag vf_5 --case-retries 1
```

Оба скрипта в конце всегда делают `STOP` + `CLEAR` (best-effort).

## 6.1. Когда вообще разрешено переходить к J7/HV
Перед подачей `J7` должны уже быть закрыты все пункты ниже:
* `full_system_preflight.py` без `--with-hv` завершился `overall_pass=true`
* `PASS=80 FAIL=0` в `ui_pwm_suite.py`
* scalar/VF и FOC/MIC preflight прошли
* `bp_fault=0`, `bp_bad_cnt=0` в финальном SAFE
* внешний E-STOP, ограничение тока и предохранение по шине готовы до подачи `J7`

После подачи `J7` не идти сразу в “боевой” режим. Сначала прогнать только `hv_j7_preflight.py`, и только если он чистый, двигаться дальше.

## 7. Если что-то не так (короткий чеклист)
Saleae: `devices []`
* В Logic2 должен быть виден реальный прибор (не Demo). Переподключить USB, перезапустить Logic2, проверить драйвер.

`enc_ok = 0`
* Проверить питание 3.3V, общий GND.
* Проверить `PB10/PB11` и адрес `0x36`.
* На Blue Pill LED в SAFE может быть редкое мигание как индикатор "энкодер жив".

PWM не видно на части каналов
* Проверить, что захват включает все `CH0..CH6`.
* Проверить, что именно TIM1 выводы подключены на нужные пины (PA8/PA9/PA10 и PB13/14/15).
* Проверить `EM_STOP` уровень: если shutdown активен, UM2014 может гасить драйвер.

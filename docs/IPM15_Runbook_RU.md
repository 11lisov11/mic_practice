# UNOQ_MOTOR: Запуск с STEVAL-IPM15B (UM2014 / IPM15)

Документ для bring-up и безопасного запуска связки `UNO Q (UI)` + `Blue Pill (PWM)` + `STEVAL-IPM15B`.

## 0. Состав системы (что за модуль и зачем)
* `UNO Q` (прошивка `UNOQ_MOTOR/UNOQ_MOTOR.ino`): UI по HTTP (`/api/cmd`, `/api/status`), логика режимов, отображение частоты на матрице, обмен с Blue Pill по UART.
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
* Любой(ые) `GND` пины -> общий `GND` (соединить "звездой", короткими проводами)

Важно:
* Не включать HV (125..400V DC) пока не проверены ШИМ, EM_STOP, таймауты и ESTOP на логическом уровне.
* Логические уровни и аналоговые сигналы UM2014 должны попадать в диапазон АЦП Blue Pill (0..3.3V). Если UM2014 отдает больше, нужен делитель/буфер.

## 2. Коммутация (проводка)

### 2.1. UNO Q ↔ Blue Pill (UART, 921600)
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

Опциональные I/O:
* J2-21 `NTC bypass relay` -> `PB1` (GPIO out)
* J2-27 `PFC sync.` -> `PB5` (GPIO out)
* J2-23 `dissipative brake PWM` -> `PB9` (TIM4_CH4, опционально)

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

## 5. Быстрая проверка энкодера (положение магнита)
Команда (на ПК):
```powershell
.\.venv\Scripts\python.exe -u .\tools\encoder_test.py --url http://127.0.0.1:18080 --duration 10 --poll 0.05
```
Ожидаем:
* `enc_ok` = 1
* `enc_raw` меняется при вращении магнита/вала
* `enc_deg` меняется 0..360

## 6. Тесты ШИМ (UI -> Blue Pill -> PWM -> LA -> метрики)
Перед запуском убедиться:
* `/api/status` доступен
* `tools/la_probe.py` показывает **не пустой** список `devices` (иначе захваты невозможны)

Один кейс:
```powershell
.\.venv\Scripts\python.exe -u .\tools\ui_pwm_case.py --url http://127.0.0.1:18080 --mode VF --freq 5.0 --tag vf_5 ^
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Полный suite (sweep 0..50 шаг 0.1, захваты в ключевых точках):
```powershell
.\.venv\Scripts\python.exe -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 ^
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Оба скрипта в конце всегда делают `STOP` + `CLEAR` (best-effort).

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

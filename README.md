# mic_practice — UNO Q ↔ Blue Pill (UART + PWM + UI + LA)

Запуск с инвертором (UM2014 / IPM15): `docs/IPM15_Runbook_RU.md`
Исследование MIC AI (FOC vs MIC): `docs/MIC_AI_Runbook_RU.md`

## Состав репозитория
- `bluepill_uart_pwm_pio` — прошивка Blue Pill (PWM, UART протокол).
- `UNOQ_MOTOR/` — основной sketch-dir UNO Q: `UNOQ_MOTOR.ino`, UI/RPC, режимы `VF/FOC/MIC`, дисплей 7x13, обмен с Blue Pill.
- `unoq_spi_master` — отдельный/вспомогательный скетч UNO Q для SPI master экспериментов.
- `web_hmi` — web‑GUI для UNO Q (без пароля, порт 8080).
- `tools/ui_pwm_case.py` — один тест‑кейс с LA захватом, CSV и `summary.json`.
- `tools/ui_pwm_suite.py` — полный набор тестов с LA захватами и `summary.csv`.
- `tools/scalar_vf_preflight.py` — жёсткий preflight scalar/VF: steady-state, ESTOP/recover, overlap и deadtime.
- `tools/foc_mic_preflight.py` — жёсткий preflight FOC/MIC: `FOC_RUN`, `ESTOP/recover`, overlap и deadtime.
- `tools/hv_j7_preflight.py` — опциональный HV/J7 preflight после low-voltage HIL: ограниченный scalar/VF, `ESTOP/recover`, overlap и deadtime под силовой шиной.
- `tools/mic_ai_compare.py` — сравнение FOC vs MIC по телеметрии (`timeseries_*.csv`, `summary.json`).
- `tools/full_system_preflight.py` — единый regression-runner: build, доступ к UNO Q, encoder sanity, scalar, FOC/MIC, полный LA-suite и MIC-диагностика.
- `tools/logic2_recover.py` — recovery Logic2/Saleae: рестарт приложения, проверка automation-port и видимости реального анализатора.
- `tools/la_probe.py` — проверка доступности Saleae Logic2 Automation.
- `tools/adb_router_sequence.py` — bounded runner для силовых DUTY/VF шагов через один persistent ADB/router socket с обязательным `STOP/ESTOP` cleanup.
- `tools/ui_http_bridge.py` — HTTP‑мост для доступа к UI с телефона через ПК.
- `tools/adb_deploy_web_hmi.py` — деплой web‑GUI на UNO Q через ADB.
- `tools/ui_access.py` — ADB‑форвард + проверка `/api/status` + (опц.) мост на LAN.
- `UNOQ_MOTOR/id_ref_lut_motor1.h`, `UNOQ_MOTOR/uno_q_control.h` — локальная MIC/LUT логика (без внешней зависимости на `C:\mic_ai`).
- `requirements.txt` — общие зависимости Python для LA/HTTP и локального запуска `web_hmi`.

## Установка зависимостей (Windows, PowerShell)
Важно: команды ниже предполагают, что ты находишься в папке `...\mic_practice`.

```powershell
py -3 -m venv .\.venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe -m pip install -U platformio
```

## Wi-Fi секреты для UNO Q
Репозиторий хранит только шаблон: `unoq_spi_master/arduino_secrets.h.example`.

Перед сборкой UNO Q создай локальный файл:
```powershell
Copy-Item .\unoq_spi_master\arduino_secrets.h.example .\unoq_spi_master\arduino_secrets.h
```
и заполни `SECRET_SSID` / `SECRET_PASS`.

## Build UNO Q (Arduino CLI)
Основной sketch UNO Q собирается из папки `UNOQ_MOTOR`:

```powershell
arduino-cli compile --fqbn arduino:zephyr:unoq .\UNOQ_MOTOR
```

## Доступ к UI (ПК по USB/ADB + телефон по Wi‑Fi)
Быстрый запуск: `python tools/ui_access.py --bridge`

`tools/ui_access.py` теперь:
- сам делает `adb start-server`;
- поднимает `adb forward`;
- проверяет `http://127.0.0.1:18080/api/status`;
- если ADB-девайс не найден, печатает состояние USB-инстансов UNO Q (`Present=True` vs `phantom`).

В текущем `web_hmi` одна аварийная кнопка работает как переключатель:
- если `ESTOP` не активен, отправляется `ESTOP`;
- если `ESTOP` уже активен, кнопка отправляет `ESTOP CLEAR`.

### ПК (через ADB)
1. `adb devices`
2. `adb -s <DEVICE_ID> forward tcp:18080 tcp:8080`
3. Открыть `http://127.0.0.1:18080`

Если `ui_access.py` пишет, что UNO Q виден только как `phantom`, это уже не проблема `web_hmi` или тестов: Windows не видит живой USB-девайс платы.

### Телефон (Wi‑Fi)
1. Узнать IP UNO Q (например `192.168.31.247`).
2. Открыть `http://<UNOQ_IP>:8080`.

Если Wi‑Fi изолирует клиентов и телефон не видит UNO Q:
1. Сделать ADB‑форвард как выше.
2. Запустить мост на ПК:
   `python -u tools/ui_http_bridge.py --listen-port 8080 --target http://127.0.0.1:18080`
3. На телефоне открыть `http://<IP_ПК>:8080`.

## Деплой GUI на UNO Q (ADB)
```
python tools/adb_deploy_web_hmi.py --device <ADB_ID> --restart
```

## LA (Saleae) канал‑маппинг
- CH0=PA8
- CH1=PB13
- CH2=PA9
- CH3=PB14
- CH4=PA10
- CH5=PB15
- CH6=PB12 (BRAKE)

## Рекомендуемый HIL safety-прогон
Если нужен один воспроизводимый полный прогон проекта:

```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080
```

Он:
- собирает UNO Q и Blue Pill;
- проверяет ADB/UI доступ;
- пытается поднять Logic2/Saleae через `tools/logic2_recover.py`;
- делает короткий `encoder_test`;
- гоняет `scalar_vf_preflight.py`;
- гоняет `foc_mic_preflight.py`;
- гоняет полный `ui_pwm_suite.py`;
- при явном `--with-hv` гоняет отдельный `hv_j7_preflight.py`;
- отдельно запускает `mic_ai_compare.py`, но честно помечает его как `diagnostic_only`, если MIC корректно загейтился из-за отсутствия реального вращения.

Артефакт верхнего уровня: `tools/_preflight_exports/full_system_preflight_<timestamp>/summary.json`

Если нужна не просто “наличие PWM”, а проверка на отсутствие сквозного открытия и подтверждение deadtime, использовать 24 MHz захват и порог deadtime:

Scalar/VF preflight:
```powershell
py -3 -u .\tools\scalar_vf_preflight.py --url http://127.0.0.1:18080 `
  --freqs 0.1,0.5,1,2,5,10,20,30,40,50 --estop-freqs 0.5,10,50 `
  --la-channels 0,1,2,3,4,5,6 --la-rate 24000000 --la-duration 0.003 `
  --min-handoff-gap-ns 600
```

FOC/MIC preflight:
```powershell
py -3 -u .\tools\foc_mic_preflight.py --url http://127.0.0.1:18080 `
  --foc-freqs 0.5,5,10,20,50 --foc-estop-freqs 10,50 --mic-freqs 5,10,20 `
  --la-channels 0,1,2,3,4,5,6 --la-rate 24000000 --la-duration 0.003 `
  --min-handoff-gap-ns 600
```

Полный suite c deadtime-check:
```powershell
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 `
  --capture-every-hz 1.0 --la-channels 0,1,2,3,4,5,6 `
  --la-rate 24000000 --la-duration 0.06 --case-retries 2 --retry-delay 0.2 `
  --min-handoff-gap-ns 600
```

HV/J7 preflight:
```powershell
py -3 -u .\tools\hv_j7_preflight.py --url http://127.0.0.1:18080 `
  --vf-freqs 0.5,1,2,5 --estop-freqs 1,5 `
  --la-channels 0,1,2,3,4,5,6 --la-rate 24000000 --la-duration 0.02 `
  --min-handoff-gap-ns 600
```

Если `vdc` у тебя уже откалиброван и ты понимаешь его масштаб на своей плате, можно добавить окно:
```powershell
py -3 -u .\tools\hv_j7_preflight.py --url http://127.0.0.1:18080 `
  --vf-freqs 0.5,1,2,5 --estop-freqs 1,5 `
  --vdc-min <MIN> --vdc-max <MAX> `
  --la-channels 0,1,2,3,4,5,6 --la-rate 24000000 --la-duration 0.02 `
  --min-handoff-gap-ns 600
```

Полный раннер с опциональным HV/J7 этапом:
```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080 --with-hv
```

Для ручных силовых DUTY шагов не запускать отдельный `adb shell` на каждый шаг. Использовать bounded runner, который держит один socket-сеанс и в любом исходе отправляет `STOP`, `ESTOP`, `STOP`:

```powershell
py -3 -u .\tools\adb_router_sequence.py --cmd STOP --cmd ESTOP
```

Любая последовательность с `START` при заметном `VBUS` блокируется без явного `--allow-hv`. Пример только для заранее подготовленного HV стенда с внешним E-STOP:

```powershell
py -3 -u .\tools\adb_router_sequence.py --allow-hv --duty-rotate --mag 0.20 --dwell-s 0.25 --cycles 1
```

Ожидаемый признак исправного стенда:
- `PASS=80 FAIL=0` в `tools/_la_exports/summary.csv`
- для scalar/VF `freq_pass=True`, `estop_pass=True`, `final_safe=True` в `tools/_preflight_exports/.../summary.json`

## UNO Q ↔ Blue Pill связь
Текущая конфигурация использует UART, чтобы не занимать SPI и не конфликтовать с IPM15 аналоговыми входами.
Подключение:
- UNO Q D1 (TX) → Blue Pill PA3 (RX, USART2)
- UNO Q D0 (RX) ← Blue Pill PA2 (TX, USART2)
- GND ↔ GND

## IPM15 (UM2014) — подключение Blue Pill
J2 (Table 6):
- J2‑1 `EM_STOP` → `PB12` (active‑low, BRAKE/ESTOP)
- J2‑3 `PWM-1H` → `PA8` (TIM1_CH1)
- J2‑5 `PWM-1L` → `PB13` (TIM1_CH1N)
- J2‑7 `PWM-2H` → `PA9` (TIM1_CH2)
- J2‑9 `PWM-2L` → `PB14` (TIM1_CH2N)
- J2‑11 `PWM-3H` → `PA10` (TIM1_CH3)
- J2‑13 `PWM-3L` → `PB15` (TIM1_CH3N)
- J2‑14 `HV bus voltage` → `PA5` (ADC1_IN5)
- J2‑15 `current phase A` → `PA0` (ADC1_IN0)
- J2‑17 `current phase B` → `PA1` (ADC1_IN1)
- J2‑19 `current phase C` → `PA4` (ADC1_IN4)
- J2‑21 `NTC bypass relay` → `PB1` (GPIO output, active‑high)
- J2‑23 `dissipative brake PWM` → `PB9` (TIM4_CH4, по умолчанию OFF)
- J2‑25 `+V power` → питание (не подключать к GPIO)
- J2‑26 `heat sink temperature` → вход АЦП (опционально, свободный ADC)
- J2‑27 `PFC sync.` → `PB5` (GPIO output)
- J2‑28 `VDD_m` → опорное/питание (не подключать к GPIO)
- J2‑29 `PWM VREF` → `3.3V`
- J2‑31 `measure phase A` → `PA6` (ADC1_IN6)
- J2‑33 `measure phase B` → `PA7` (ADC1_IN7)
- J2‑34 `measure phase C` → `PB0` (ADC1_IN8)

Дополнительное питание STEVAL:
- `J4` = auxiliary `VCC supply`
- подавать `+15V typ` (`20V max` по UM2014), `+/-`
- `J7` = основная DC bus силовой части, не подключать до завершения low-voltage проверок
- `J7` включать только после успешных `scalar_vf_preflight.py`, `foc_mic_preflight.py` и полного `ui_pwm_suite.py`
- J2‑2/4/6/8/10/12/16/18/20/22/24/30/32 → `GND`

DC bus telemetry in `/api/status` is sourced from Blue Pill `PA5/J2-14` (`bp_vbus_raw`, `bp_vdc`, `bp_vbus_age_ms`). UNO Q `A0` is only a legacy/fallback local ADC path and is not the primary HV bus measurement.

Critical wiring note: in the current UART configuration, Blue Pill `PA5` is only the DC bus ADC input. Do not leave any old SPI wire `UNO Q D13/SCK -> Blue Pill PA5`; it conflicts with `J2-14` and can make `/api/status` report near-zero `bp_vdc` while the DC bus is actually energized.

J9 (Hall/Encoder, UM2014):
- J9‑1 `Hall input 1 / encoder A+`
- J9‑2 `Hall input 2 / encoder B+`
- J9‑3 `Hall input 3 / encoder Z+`
- J9‑4 `3.3V или 5V` (выбор питания через джампер на плате)
- J9‑5 `GND`

Сейчас в проекте используется **AS5600 по I2C** (PB10/PB11) вместо A/B/Z.

AS5600 (абсолютный магнитный энкодер по I2C):
- `PB10` = `I2C2_SCL`
- `PB11` = `I2C2_SDA`
- `3.3V` и `GND`
- Адрес по умолчанию: `0x36`, скорость: `100 kHz` (см. `bluepill_uart_pwm_pio/include/config.h`)

Важно:
- Если включать `USE_TIM1_BKIN=1`, PB12 занят под BKIN и `EM_STOP` нужно переносить на другой GPIO.

Команды для IPM15 I/O (через UI `/api/cmd`):
- `NTC ON|OFF`
- `PFC ON|OFF`
- `BRAKE PWM 0.00..1.00` или `BRAKE OFF`

## Тесты ШИМ (UI → PWM)
Перед тестами проверь Saleae (Logic2 Automation):
```powershell
.\.venv\Scripts\python.exe -u .\tools\la_probe.py
```
Если `devices []`, то Logic2 запущен, но анализатор не виден. В этом состоянии захваты невозможны.

Один кейс:
```
python -u tools/ui_pwm_case.py --url http://127.0.0.1:18080 --mode VF --freq 5.0 --tag vf_5 \
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Полный suite:
```
python -u tools/ui_pwm_suite.py --url http://127.0.0.1:18080 --capture-every-hz 1.0 \
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Для единичных transport/control transient доступны аккуратные повторы только чистых PWM-кейсов:
```
python -u tools/ui_pwm_suite.py --url http://127.0.0.1:18080 --case-retries 1 --retry-delay 0.2
python -u tools/ui_pwm_case.py --url http://127.0.0.1:18080 --mode VF --freq 5.0 --tag vf_5 --case-retries 1
```

Частичные прогоны (например только hot‑switch и ESTOP):
```
python -u tools/ui_pwm_suite.py --url http://127.0.0.1:18080 --skip-sweep --skip-diag --skip-duty \
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Быстрый sanity‑check (DIAG + один захват):
```
python -u tools/ui_pwm_case.py --url http://127.0.0.1:18080 --mode DIAG --tag diag \
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

После любого кейса/сьюта скрипты автоматически делают `STOP` + `CLEAR`.

## Build + Flash (Blue Pill, PlatformIO)
```
cd bluepill_uart_pwm_pio
pio run -e bluepill_uart_pwm -t upload
```

## Публикация на GitHub
Если Git еще не настроен:
```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Первый коммит и push:
```powershell
git commit -m "chore: initial import"
git remote add origin https://github.com/<USERNAME>/<REPO>.git
git push -u origin main
```

## UNO Q дисплей и LED
- UNO Q показывает частоту с 1 знаком после запятой (например `50.0`).
- Blue Pill PC13: RUN (VF/FOC) — мигает, SAFE/STOP — погашен, FAULT/ESTOP — горит.

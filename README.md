# mic_practice — UNO Q ↔ Blue Pill (UART + PWM + UI + LA)

Запуск с инвертором (UM2014 / IPM15): `docs/IPM15_Runbook_RU.md`
Исследование MIC AI (FOC vs MIC): `docs/MIC_AI_Runbook_RU.md`

## Состав репозитория
- `bluepill_uart_pwm_pio` — прошивка Blue Pill (PWM, UART протокол).
- `unoq_spi_master` — скетч UNO Q (UART управление, дисплей 7x13).
- `web_hmi` — web‑GUI для UNO Q (без пароля, порт 8080).
- `tools/ui_pwm_case.py` — один тест‑кейс с LA захватом, CSV и `summary.json`.
- `tools/ui_pwm_suite.py` — полный набор тестов с LA захватами и `summary.csv`.
- `tools/mic_ai_compare.py` — сравнение FOC vs MIC по телеметрии (`timeseries_*.csv`, `summary.json`).
- `tools/la_probe.py` — проверка доступности Saleae Logic2 Automation.
- `tools/ui_http_bridge.py` — HTTP‑мост для доступа к UI с телефона через ПК.
- `tools/adb_deploy_web_hmi.py` — деплой web‑GUI на UNO Q через ADB.
- `tools/ui_access.py` — ADB‑форвард + (опц.) мост на LAN.
- `id_ref_lut_motor1.h`, `uno_q_control.h` — локальная MIC/LUT логика (без внешней зависимости на `C:\mic_ai`).
- `requirements.txt` — зависимости Python для LA/HTTP.

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

## Доступ к UI (ПК по USB/ADB + телефон по Wi‑Fi)
Быстрый запуск: `python tools/ui_access.py --bridge`

### ПК (через ADB)
1. `adb devices`
2. `adb -s <DEVICE_ID> forward tcp:18080 tcp:8080`
3. Открыть `http://127.0.0.1:18080`

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
- J2‑2/4/6/8/10/12/16/18/20/22/24/30/32 → `GND`

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


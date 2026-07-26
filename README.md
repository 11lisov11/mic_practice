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
- `tools/bpfoc_backend_preflight.py` — низковольтная проверка `BPFOC OFF/ON`: duty backend, запрет live-switch и активный Blue Pill `MODE_FOC`.
- `tools/fan_preflight.py` — низковольтная проверка `FAN PWM`: команда UNO Q, подтверждение duty на Blue Pill и опциональный tach.
- `tools/mic_ai_compare.py` — сравнение FOC vs MIC по телеметрии (`timeseries_*.csv`, `summary.json`).
- `tools/mic_research_matrix.py` — серия FOC vs MIC по частотам/повторам для научного отчета (`aggregate.csv`, общий `summary.json`).
- `tools/mic_research_report.py` — offline Markdown-отчет из `mic_research_matrix.py` summary.
- `tools/telemetry_calibration.py` — снимки телеметрии и расчет рекомендуемых Vbus/temperature calibration constants.
- `tools/research_readiness_check.py` — финальный gate: live `/api/status` + bench-gate + свежесть/наличие preflight, calibration и MIC research artifacts.
- `tools/bench_gate_report.py` — безопасный сводный отчёт текущего стенда: последний build-only, UART diagnosis, Saleae static/no-overlap и live `/api/status`.
- `tools/bluepill_runtime_static_preflight.py` — безопасная прошивка рабочей Blue Pill firmware через ST-Link + статический Saleae-захват `CH0..CH6` без активного PWM.
- `tools/bluepill_static_low_preflight.py` — изоляционный ST-Link тест для `low_side_static_high`: диагностическая firmware без TIM1/команд держит PWM GPIO в LOW, снимает Saleae и восстанавливает runtime.
- `tools/full_system_preflight.py` — единый regression-runner: build, доступ к UNO Q, encoder sanity, scalar, FOC/MIC, полный LA-suite и MIC-диагностика.
- `tools/logic2_recover.py` — recovery Logic2/Saleae: рестарт приложения, проверка automation-port и видимости реального анализатора.
- `tools/la_probe.py` — проверка доступности Saleae Logic2 Automation.
- `tools/adb_router_sequence.py` — bounded runner для силовых DUTY/VF шагов через один persistent ADB/router socket с обязательным `STOP/ESTOP` cleanup.
- `tools/ui_http_bridge.py` — HTTP‑мост для доступа к UI с телефона через ПК.
- `tools/adb_deploy_web_hmi.py` — деплой web‑GUI на UNO Q через ADB.
- `tools/bluepill_uart_diagnose.py`, `tools/unoq_web_server.py` — прямой PC -> STM32/Blue Pill режим без UNO Q, см. `PC_DIRECT_STM32_RU.md`.
- `tools/ui_access.py` — ADB‑форвард + проверка `/api/status` + (опц.) мост на LAN.
- `UNOQ_MOTOR/id_ref_lut_motor1.h`, `UNOQ_MOTOR/uno_q_control.h` — локальная MIC/LUT логика (без внешней зависимости на `C:\mic_ai`).
- `requirements.txt` — общие зависимости Python для LA/HTTP и локального запуска `web_hmi`.

Текущий безопасный bring-up стенда ведется по PC-direct архитектуре:
`ПК -> USB-изолятор -> USB-UART 3.3 В -> STM32 Blue Pill -> STEVAL/IPM`.
UNO Q остается поддерживаемым UI/экраном и заготовкой для переноса, но не
является обязательным runtime-мостом для проверки ШИМ. Актуальные команды,
loopback-порядок и gate-состояние находятся в `PC_DIRECT_STM32_RU.md`.

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
arduino-cli compile --fqbn arduino:zephyr:unoq:link_mode=static .\UNOQ_MOTOR
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
   `py -3 -u tools\ui_http_bridge.py --listen-port 8080 --target http://127.0.0.1:18080`
3. На телефоне открыть `http://<IP_ПК>:8080`.

### Телефон/планшет -> Wi‑Fi точка -> LAN ПК -> UNO Q при включенном VPN
Основной безопасный запуск на ПК:
`py -3 -u tools\ui_access.py --bridge --bridge-port 8080`

Скрипт поднимает `adb forward tcp:18080 tcp:8080`, проверяет `http://127.0.0.1:18080/api/status`, затем запускает LAN-мост. Мост печатает список Windows adapter URLs. Для точки доступа, подключенной к ПК по LAN, открывать надо адрес интерфейса `Ethernet`/`LAN`, не VPN-интерфейс.

Если VPN блокирует входящие на `0.0.0.0`, привяжи мост явно к LAN IP ПК:
`py -3 -u tools\ui_access.py --bridge --bridge-host <IP_ПК_В_LAN_ТОЧКИ> --bridge-port 8080`

Мост принудительно ходит к ADB-forward target `127.0.0.1:18080` без системного proxy/VPN proxy (`NO_PROXY` + direct opener), поэтому команды идут: клиент Wi‑Fi -> точка -> LAN IP ПК -> `ui_http_bridge.py` -> `127.0.0.1:18080` -> ADB -> UNO Q `web_hmi` -> MCU RPC.

## Деплой GUI на UNO Q (ADB)
```
python tools/adb_deploy_web_hmi.py --device <ADB_ID> --restart
```

### Wi-Fi прошивка логики UNO Q
Сначала один раз включить endpoint через USB/ADB. Локальный token-file не коммитится:

```powershell
py -3 -c "import pathlib,secrets; pathlib.Path('.unoq_firmware_update_token').write_text(secrets.token_urlsafe(32)+'\n', encoding='utf-8')"
py -3 -u tools\adb_deploy_web_hmi.py --device <ADB_ID> --restart --firmware-update-token-local-file .unoq_firmware_update_token
```

Проверка без записи флеша:

```powershell
py -3 -u tools\unoq_wifi_firmware_update.py --url http://<UNOQ_IP>:8080 --source-ip <LAN_IP_ПК> --token-file .unoq_firmware_update_token
```

Реальная прошивка только при отключенной HV-шине:

```powershell
py -3 -u tools\unoq_wifi_firmware_update.py --url http://<UNOQ_IP>:8080 --source-ip <LAN_IP_ПК> --token-file .unoq_firmware_update_token --flash --confirm-hv-off
```

Сервер перед приемом firmware делает `STOP` и требует `SAFE`, `pwm=0`, `estop=0`, `bp_fault=0`, `vdc<=10 В`. Если PowerShell блокируется антивирусом, запускать ту же команду из `cmd.exe`.

## LA (Saleae) канал‑маппинг
- CH0=PA8
- CH1=PB13
- CH2=PA9
- CH3=PB14
- CH4=PA10
- CH5=PB15
- CH6=PB12 (BRAKE)

Перед любым активным PWM-тестом статический SAFE-захват должен показывать:
- `CH0..CH5 = 0` без фронтов;
- `CH6 = 0`, то есть `EM_STOP` удерживает shutdown;
- `saleae_static_no_pair_overlap=true`;
- `saleae_static_pwm_lines_low=true` в `tools/bench_gate_report.py`.

Если `bench_gate_report.py` пишет `pattern=low_side_static_high`
(`CH1/CH3/CH5=1`, `CH0/CH2/CH4=0`), активный запуск запрещен. Сначала
проверить, что Blue Pill прошит свежей `bluepill_uart_pwm`, Saleae подключен
именно к логическим PWM GPIO (`PA8/PB13/PA9/PB14/PA10/PB15`) с общим `GND`, а
`pwm_force_safe_gpio()` уже на boot и `pwm_outputs_enable(false)` после TIM1
init реально переводят все шесть PWM-пинов в GPIO LOW.
До исправления держать `EM_STOP` активным и HV/J7 отключенным.

## Blue Pill Runtime Static Preflight Через ST-Link
Это следующий безопасный шаг, если `bench_gate_report.py` показывает
`pattern=low_side_static_high` или есть сомнение, что на STM32 прошита свежая
runtime-прошивка. Скрипт не включает PWM и не отправляет `START`: он только
собирает/прошивает `bluepill_uart_pwm`, снимает статический Saleae `CH0..CH6`
и требует `CH0..CH5=0`, `CH6=0`, отсутствие фронтов и overlap.

Запускать только при отключенной и разряженной HV-шине:

```powershell
py -3 -u .\tools\bluepill_runtime_static_preflight.py --confirm-hv-off
```

Проверка без прошивки и без захвата:

```powershell
py -3 -u .\tools\bluepill_runtime_static_preflight.py --dry-run
```

Критерий PASS: `static_checks.pass=true`, `pattern=all_pwm_low_safe`.
Если снова `pattern=low_side_static_high`, не запускать PWM: проверять
маппинг Saleae, фактические провода `PB13/PB14/PB15`, питание/землю Blue Pill,
pull-up/pull-down на входах IPM и то, что прошивка действительно обновилась.
Порядок разбора именно такой:
1. HV/J7 отключена, DC-шина разряжена, `EM_STOP` удерживает shutdown.
2. Прошить и проверить runtime через `bluepill_runtime_static_preflight.py --confirm-hv-off`.
3. Если `CH1/CH3/CH5` всё еще HIGH, выполнить изоляционный static-low тест:
   ```powershell
   py -3 -u .\tools\bluepill_static_low_preflight.py --confirm-hv-off
   ```
4. Если static-low проходит, а runtime-static нет, искать ошибку в TIM1/runtime init или в том, что прошивается не тот target.
5. Если static-low тоже показывает HIGH, измерить прямо на Blue Pill `PB13/PB14/PB15`.
6. Если на Blue Pill LOW, а у IPM HIGH, искать ошибку в проводке, уровне GND/reference или подтяжках входов IPM.

## Blue Pill PWM Self-Test Через ST-Link
Если прямой UART к Blue Pill не работает, активные PWM-линии можно проверить
без командного канала: отдельная прошивка `bluepill_pwm_selftest` циклично
генерирует TIM1 PWM на `PA8/PB13/PA9/PB14/PA10/PB15`, но держит `PB12
EM_STOP` в shutdown-состоянии. Это тест логических PWM-выводов для Saleae, не
команда на запуск двигателя.

Запускать только при отключенной и разряженной HV-шине:

```powershell
py -3 -u .\tools\bluepill_pwm_selftest_preflight.py --confirm-hv-off
```

Скрипт делает полный цикл:
- собирает `bluepill_pwm_selftest` и рабочую `bluepill_uart_pwm`;
- прошивает self-test через ST-Link;
- снимает Saleae `CH0..CH6`;
- анализирует `CH0/CH1`, `CH2/CH3`, `CH4/CH5` на PWM-активность и overlap;
- в `finally` возвращает рабочую `bluepill_uart_pwm`.

Проверка без прошивки железа:

```powershell
py -3 -u .\tools\bluepill_pwm_selftest_preflight.py --dry-run
```

Тот же self-test можно включить в общий regression-runner:

```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080 `
  --with-bluepill-pwm-selftest --confirm-hv-off --with-fan --with-bpfoc
```

Важно: текущий подключенный Saleae/Logic2 может ограничивать частоту до
`500 kS/s`. Этого достаточно для грубой проверки наличия PWM и отсутствия
явного overlap, но недостаточно для точного подтверждения `PWM_DEADTIME_NS=800`
нс. Для строгого deadtime-теста нужен захват с существенно большей частотой
дискретизации.

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
- при явном `--with-fan` гоняет `fan_preflight.py`;
- при явном `--with-bpfoc` гоняет `bpfoc_backend_preflight.py`;
- при явном `--with-hv` гоняет отдельный `hv_j7_preflight.py`;
- отдельно запускает `mic_ai_compare.py`; `diagnostic_only` допустим только когда `AS5600` читается (`enc_ok=1`), но вал не вращается и MIC корректно загейтился по measured speed. Если `enc_ok=0`, это blocker/fail, а не diagnostic-only.

Артефакт верхнего уровня: `tools/_preflight_exports/full_system_preflight_<timestamp>/summary.json`
Итоговые флаги (`build_only_pass`, `overall_pass`, `required_hil_pass`,
`full_suite_pass`, `final_safe` и stage-pass поля) записываются и в объект
`summary`, и на верхний уровень JSON, чтобы ручная проверка и tooling читали
одинаковые значения.

Новые `summary.json`/`run_metadata.json` содержат `run_metadata`: git branch, commit, dirty status, командную строку, Python/platform. Для научного отчета не удалять этот блок: он связывает CSV/Saleae capture с конкретной версией прошивки и tooling.

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

MIC research matrix (после успешного preflight и только когда мотор реально вращается):
```powershell
py -3 -u .\tools\mic_research_matrix.py --url http://127.0.0.1:18080 `
  --freqs 2,5,10,20 --repeats 3 --duration 10 --warmup 1.0 --require-encoder `
  --motor-label "<motor/nameplate>" --load-note "<load condition>" --supply-note "<supply/current-limit>"
```

По умолчанию матрица считается низковольтной: перед каждым raw-прогоном она требует `SAFE`, `pwm=0`, `estop=0`, `bp_fault=0`, `bp_bad_cnt=0`, при `--require-encoder` требует `enc_ok=1` и блокирует `START`, если Vbus не читается или `|Vbus| > --max-start-vdc` (по умолчанию 60 В).

Для воспроизводимости `mic_research_matrix.py` пишет `bench_context` в summary. Его можно задать отдельными флагами (`--motor-label`, `--load-note`, `--supply-note`, `--ambient-c`, `--instrumentation-note`, `--bench-note`) или JSON-файлом через `--bench-config`.

Для силовой научной серии добавлять `--allow-hv` только после успешного `full_system_preflight.py --with-hv`, с внешним E-STOP и зафиксированными условиями стенда:
```powershell
py -3 -u .\tools\mic_research_matrix.py --url http://127.0.0.1:18080 `
  --freqs 2,5,10,20 --repeats 3 --duration 10 --warmup 1.0 --require-encoder --allow-hv
```

Выход:
- `tools/_research_exports/<tag>_<timestamp>/aggregate.csv`
- `tools/_research_exports/<tag>_<timestamp>/summary.json`
- raw `mic_ai_compare.py` summaries по каждому повтору

`mic_ai_compare.py` — telemetry-only: для него не нужен Saleae/Logic2/grpc, только HMI `/api/status` и `/api/cmd`.

В `summary.json` матрицы и raw `mic_ai_compare.py` summaries есть `run_metadata.git.commit` и `run_metadata.git.dirty`. Если `dirty=true`, в отчете нужно явно указать, что данные получены на незакоммиченной рабочей версии.

`mic_research_matrix.py` ходит к `127.0.0.1` без системного proxy/VPN proxy и ограничивает каждый raw-прогон таймаутом. По умолчанию таймаут рассчитывается автоматически; для длинных точек можно задать явно:
```powershell
py -3 -u .\tools\mic_research_matrix.py --url http://127.0.0.1:18080 `
  --freqs 2,5,10,20 --repeats 3 --duration 30 --case-timeout-s 600 --require-encoder
```

Markdown report из готового summary:
```powershell
py -3 -u .\tools\mic_research_report.py .\tools\_research_exports\<run>\summary.json `
  --calibration-summary .\tools\_calibration_exports\<run>\summary.json
```

`mic_research_report.py` пишет `report.md` и SVG-графики рядом с `summary.json`:
- `mic_active_ratio.svg`
- `p_proxy_delta_pct.svg`
- `i_rms_delta_pct.svg`
- `enc_rpm_delta_pct.svg`

В отчете есть раздел `Run Metadata` с git commit/dirty status и предупреждение, если данные сняты на незакоммиченном рабочем дереве.
Если передан `--calibration-summary`, отчет добавляет `Calibration Evidence`: `pass`, `zero_current_sanity`, Vbus/temp constants и нулевые токовые метрики.

Полный suite c deadtime-check:
```powershell
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 `
  --capture-every-hz 1.0 --la-channels 0,1,2,3,4,5,6 `
  --la-rate 24000000 --la-duration 0.06 --case-retries 2 --retry-delay 0.2 `
  --min-handoff-gap-ns 600
```

HV/J7 preflight:
Запускать только после зеленого `bench_gate_report.py` (`ready_for_active_pwm=true`),
свежего low-voltage regression, внешнего E-STOP, ограничения тока/предохранителя
и проверенной развязки USB/Saleae. Если gate красный, эта команда не является
следующим шагом: сначала выполнить `CURRENT_BENCH_STATUS_RU.md -> Что делать дальше`.

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
То же правило: `--with-hv` использовать только на подготовленном HV-стенде после
зеленого active-PWM gate. Build-only PASS сам по себе не разрешает этот запуск.

```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080 --with-hv
```

Расширенный low-voltage раннер для research-readiness без силовой шины:
```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080 --with-fan --with-bpfoc
```

Если `PA11_FAN_TACH` реально подключен и нужен строгий контроль тахометра:
```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080 --with-fan --fan-require-tach --with-bpfoc
```

В `summary.json` верхнего уровня при этих флагах появляются `fan_stage_enabled/fan_pass` и `bpfoc_stage_enabled/bpfoc_pass`; если флаг включен, отсутствие `summary.json` или `"pass": false` блокирует `overall_pass`.

Автоматический readiness gate перед научной серией:
```powershell
py -3 -u .\tools\research_readiness_check.py --url http://127.0.0.1:18080 --profile science
```

Для проверки только низковольтной подготовки без требования HV/J7, calibration и MIC matrix:
```powershell
py -3 -u .\tools\research_readiness_check.py --url http://127.0.0.1:18080 --profile low_voltage
```

`ready=false` не включает PWM и не трогает силовую часть; он означает, что не хватает свежих evidence-файлов или live-статус стенда не соответствует безопасному состоянию. Результат пишется в `tools/_readiness_exports/<tag>_<timestamp>/summary.json`; смотреть `failed_checks` и `next_actions` с конкретными командами следующего шага. Freshness считается по прошивкам/HMI/tooling/config; правки документации фиксируются отдельно и сами по себе не инвалидируют HIL/HV artifacts.

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
- J2‑21 `NTC bypass relay` → `NC` (сеть на STEVAL-IPM15B не используется); `PB1` → `NC`
- J2‑23 `dissipative brake PWM` → `PB9` (TIM4_CH4, по умолчанию OFF)
- J2‑25 `+V power` → питание (не подключать к GPIO)
- J2‑26 `heat sink temperature` → `PB0` (ADC1_IN8, IPM thermal telemetry/protection, current firmware: SW3=TSO 1-2)
- J2‑27 `PFC sync.` → `PB5` (GPIO output)
- J2‑28 `VDD_m` → опорное/питание (не подключать к GPIO)
- J2‑29 `PWM VREF` → `3.3V`
- J2‑31 `measure phase A` → `PA6` (ADC1_IN6)
- J2‑33 `measure phase B` → `PA7` (ADC1_IN7)
- J2‑34 `measure phase C` → not connected; firmware computes virtual C from `J2‑31/J2‑33`

Дополнительное питание STEVAL:
- `J4` = auxiliary `VCC supply`
- подавать `+15V typ` (`20V max` по UM2014), `+/-`
- `J7` = основная DC bus силовой части, не подключать до завершения low-voltage проверок
- `J7` включать только после успешных `scalar_vf_preflight.py`, `foc_mic_preflight.py` и полного `ui_pwm_suite.py`
- J2‑2/4/6/8/10/12/16/18/20/22/24/30/32 → `GND`

DC bus telemetry in `/api/status` is sourced from Blue Pill `PA5/J2-14` (`bp_vbus_raw`, `bp_vdc`, `bp_vbus_age_ms`). UNO Q `A0` is only a legacy/fallback local ADC path and is not the primary HV bus measurement.

Critical wiring note: in the current UART configuration, Blue Pill `PA5` is only the DC bus ADC input. Do not leave any old SPI wire `UNO Q D13/SCK -> Blue Pill PA5`; it conflicts with `J2-14` and can make `/api/status` report near-zero `bp_vdc` while the DC bus is actually energized.

Telemetry calibration snapshots:
```powershell
py -3 -u .\tools\telemetry_calibration.py --url http://127.0.0.1:18080 --samples 100
```

По умолчанию этот snapshot также проверяет zero-current sanity: все samples должны быть в `SAFE/pwm=0`, а `ia/ib/ic/i_rms` должны оставаться в пределах порогов. Если это не проходит, научные сравнения токов/потерь делать рано: сначала исправить датчики/offset. Для специальных не-zero-current captures есть явный override `--skip-zero-current-check`.

Two-point Vbus calculation example after a bus-off capture and a known meter reading:
```powershell
py -3 -u .\tools\telemetry_calibration.py --vbus-zero-raw 1763 --vbus-cal-raw 3256 --meter-vdc 315 --allow-hv
```

Heat sink temperature protection: current firmware expects UM2014 `SW3=TSO` (`1-2`) and `J2-26 -> Blue Pill PB0`. `/api/status` exposes `bp_temp_raw`, `bp_temp_v`, `bp_temp_c`, `bp_temp_valid`, `bp_temp_fault`. Blue Pill latches `bp_fault=6` (`OVERTEMP`) if temperature is over limit or telemetry is rail-like/invalid. If SW3 is moved to `NTC` (`2-3`), rebuild/reflash both Blue Pill and UNO Q with the temperature sensor mode changed to NTC.

Phase measurement note: `J2-31 -> PA6` and `J2-33 -> PA7` are sampled as real phase-measure channels. `J2-34 measure phase C` is not wired because `PB0` is used for heatsink temperature; firmware reports virtual C as `C = center - ((A - center) + (B - center))`. `/api/status` exposes `bp_phase_a_v`, `bp_phase_b_v`, `bp_phase_c_v`, `bp_phase_valid`, `bp_phase_c_virtual`.

Cooling fan note: the carrier board uses a standard 4-pin fan. Blue Pill `PB3` drives the fan PWM input through an inverting MMBT2222A open collector (`TIM2_CH2`, 25 kHz), while `PA11` reads the open-collector tach signal. Do not use Blue Pill USB and `PA11_FAN_TACH` at the same time. A 3-pin fan may use header pins GND/+12V/TACH, but then runs at full speed; universal 3-pin speed control requires voltage regulation matched to the exact fan. Use the dedicated `HOT_12V` rail, not raw `DC15V`. `/api/status` exposes `fan_duty`, `bp_fan_duty`, `bp_fan_rpm`.

Control-backend note: by default the validated external bridge path commands Blue Pill `MODE_DUTY`; UNO Q computes the duty/SVPWM values and Blue Pill provides hardware TIM1 complementary PWM/deadtime/safety. For stricter measured-angle FOC research, enable the experimental backend with `BPFOC ON` while the bench is `SAFE/pwm=0`; then UNO Q sends `id/iq` setpoints and Blue Pill closes `MODE_FOC` using AS5600/Hall/current ADC. `/api/status` exposes `bp_foc_backend` and `bp_cmd_mode`; every research artifact must record these fields so the report does not confuse duty-backend FOC-like control with true Blue Pill FOC.

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
- `PRECHARGE ON|OFF`
- `PFC ON|OFF`
- `BRAKE PWM 0.00..1.00` или `BRAKE OFF`
- `FAN PWM 0.00..1.00`, `FAN ON`, `FAN OFF`
- `BPFOC ON|OFF` — экспериментальный выбор backend: `OFF` = проверенный UNO Q duty/SVPWM тракт, `ON` = Blue Pill `MODE_FOC` с measured-angle FOC по AS5600/Hall. Переключать только в `SAFE`, при `pwm=0`.

В HMI есть кнопка `BP FOC`; она автоматически блокируется, если стенд не в `SAFE` или `pwm != 0`. Это только удобный frontend-guard: прошивка UNO Q также отклоняет `BPFOC ON/OFF` при включенном PWM.

BPFOC backend low-voltage preflight:
```powershell
py -3 -u .\tools\bpfoc_backend_preflight.py --url http://127.0.0.1:18080 --freq 1.0
```
Критерий PASS: начальный `SAFE/pwm=0`, `enc_ok=1`, `BPFOC OFF` дает активный `bp_cmd_mode=2`, live-переключение `BPFOC ON` при `pwm=1` отвергается, затем `BPFOC ON` из `SAFE` дает активный `bp_cmd_mode=5`. Скрипт в cleanup возвращает `STOP`, `SET FREQ 0`, `BPFOC OFF`.

Fan low-voltage preflight:
```powershell
py -3 -u .\tools\fan_preflight.py --url http://127.0.0.1:18080
```
Перед `FAN PWM` скрипт требует `SAFE`, `pwm=0`, `estop=0`, `bp_fault=0`,
`bp_bad=0`, live Blue Pill link и `Vbus <= --max-vdc` (по умолчанию 60 В).
Для намеренного HV-режима нужен явный `--allow-hv`.
Если желтый `TACH` реально подключен к `PA11_FAN_TACH`, можно усилить проверку:
```powershell
py -3 -u .\tools\fan_preflight.py --url http://127.0.0.1:18080 --require-tach
```

## Тесты ШИМ (UI → PWM)
Офлайн-проверка safety-инвариантов PC-direct протокола, без железа и без PWM:
```powershell
py -3 -u .\tools\firmware_config_safety_check.py
py -3 -u .\tools\platformio_env_safety_check.py
py -3 -u .\tools\protocol_contract_check.py
py -3 -u .\tools\protocol_safety_selftest.py
py -3 -u .\tools\pc_direct_hmi_selftest.py
py -3 -u .\tools\pc_direct_hmi_service_selftest.py
py -3 -u .\tools\web_hmi_command_guard_selftest.py
py -3 -u .\tools\ui_pwm_case_selftest.py
py -3 -u .\tools\dense_overlap_sweep_selftest.py
py -3 -u .\tools\bluepill_uart_diagnose_selftest.py
py -3 -u .\tools\uart_loopback_preflight_selftest.py
py -3 -u .\tools\active_pwm_guard_selftest.py
py -3 -u .\tools\fan_preflight_selftest.py
py -3 -u .\tools\ntc_relay_preflight_selftest.py
py -3 -u .\tools\bpfoc_backend_preflight_selftest.py
py -3 -u .\tools\mic_ai_compare_selftest.py
py -3 -u .\tools\bluepill_runtime_static_preflight_selftest.py
py -3 -u .\tools\bench_gate_report_selftest.py
py -3 -u .\tools\current_bench_status_selftest.py
py -3 -u .\tools\refresh_bench_status_selftest.py
py -3 -u .\tools\start_guard_static_check.py
py -3 -u .\tools\saleae_highlevel_probe_selftest.py
py -3 -u .\tools\saleae_pwm_analyze_selftest.py
py -3 -u .\tools\bench_gate_report.py
py -3 -u .\tools\current_bench_status.py
py -3 -u .\tools\current_bench_status.py --check
py -3 -u .\tools\refresh_bench_status.py --build-if-stale
```
Первая команда проверяет safety-critical `config.h` и firmware-инварианты:
UART mode, deadtime, timeout, PB12/BKIN, Vbus calibration, heat-sink protection,
virtual phase C, fan PB3/PA11, принудительный GPIO-low при
`pwm_outputs_enable(false)`, отсутствие ложного `STATUS_PWM_ACTIVE` до
`control_tick()`, общий `force_safe_outputs()` для fault/timeout paths и
совпадение pole-pairs с UNO Q. Вторая проверяет, что
PlatformIO env-ы собирают правильные прошивки: runtime, relay-test и PWM-selftest
не подменяют друг друга. Третья сверяет
`bluepill_uart_pwm_pio/include/proto.h` с Python tooling:
размер кадра, offsets, flags, modes и раскладку service/fan/response bytes.
Четвёртая проверяет, что `CLEAR/ESTOP/IOTEST OFF` гасят service outputs,
service-команды не выставляют `FLAG_ENABLE`, а смена режима сбрасывает enable
перед новым режимом, а `START` не принимается без свежей безопасной связи с
Blue Pill. Пятая поднимает PC-direct HTTP/HMI с фейковым serial и проверяет,
что `/api/status` жив, выключающие команды принимаются, а `START` и включающие
service-команды без link отклоняются. Шестая проверяет server-side guard в
`web_hmi/server.py`: прямой `/api/cmd` не должен включать `START`, `FAN`,
`PRECHARGE/NTC/PFC`, `BRAKE` или `IOTEST` без свежего `SAFE`-статуса и
low-voltage Vbus. Седьмая проверяет, что `ui_pwm_case.py` не обходит safety-отказ
HMI через ADB fallback и блокирует `START` по Vbus до отправки команды.
Восьмая проверяет pre-start guard у `dense_overlap_sweep.py`: live link,
`pwm=0`, `estop=0`, `bp_fault=0`, `bp_bad`, читаемый Vbus, low-voltage limit,
явный `--allow-hv` и обязательный bench-gate перед любым `START` в sweep.
Девятая проверяет классификацию UART blocker-ов:
write-timeout, loopback ok/fail, no-response и занятый COM-порт. Десятая
проверяет `active_pwm_guard.py`: `START` fail-closed по `bench_gate_report.py`,
передает `next_actions` в лог, запускает bench-gate с live `/api/status`, если
caller передал URL стенда, и не разрешает legacy-обход
`UNOQ_ALLOW_UNGATED_START*`: эти переменные теперь только дают понятный отказ,
а запуск требует зеленого bench-gate. Одиннадцатая
проверяет fan service preflight:
`SAFE`, `pwm=0`, `estop=0`, `bp_fault=0`, `bp_bad=0`, live Blue Pill link и
low-voltage Vbus guard перед `FAN PWM`, включая отказ при отсутствующей Vbus
telemetry даже с `--allow-hv`. Двенадцатая проверяет NTC/PRECHARGE relay
preflight: `IOTEST ON` и включение реле разрешаются только после safe
low-voltage/live-link precheck, а missing Vbus fail-closed. Тринадцатая
проверяет BPFOC backend preflight: high Vbus допускается только с `--allow-hv`,
но missing Vbus telemetry всё равно блокирует тест. Четырнадцатая проверяет
MIC compare START guard: `--allow-hv` не обходит чтение Vbus, а только
разрешает превышение low-voltage порога. Пятнадцатая
проверяет runtime-static preflight: безопасный `all_pwm_low_safe`, фатальный
`low_side_static_high`, CH6 shutdown и отсутствие overlap-анализа. Шестнадцатая
проверяет, что `bench_gate_report.py` выдает правильные `next_actions` для
UART protocol/loopback состояний. Семнадцатая проверяет, что
`current_bench_status.py` пишет корневой операторский статус на русском,
fail-closed при отсутствии evidence и не пропускает английские bench-detail
строки в `CURRENT_BENCH_STATUS_RU.md`. Восемнадцатая проверяет safe wrapper
`refresh_bench_status.py`: красный gate/readiness не считается ошибкой refresh,
но провал обновления или `--check` блокирует результат; `--fail-if-not-ready`
возвращает код 1 при красном gate. Девятнадцатая статически проверяет исходники:
все START/service-capable tooling имеют явные Vbus/link/bench-gate/HV guard-токены.
Двадцатая проверяет runtime-поведение `saleae_highlevel_probe.py`:
`START` блокируется bench-gate до HTTP-запроса, не-START команды не проходят
через лишний START guard, а `--require-static-safe` возвращает `rc=5`, если
CH0..CH6 не доказывают безопасный static LOW. Двадцать первая на
синтетических CSV проверяет, что
`saleae_pwm_analyze.py` пропускает корректный PWM, ловит high-high overlap и
отклоняет статический no-PWM при `--expect-pwm`. `bench_gate_report.py` не включает PWM, а
собирает последние evidence-файлы в один `summary.json`; если UART не прошёл,
она честно пишет `ready_for_active_pwm=false`. Gate также проверяет свежесть:
последний `full_system_preflight.py --build-only` должен быть новее
safety-critical исходников (`tools/*.py`, STM32/UNO Q firmware и HMI server).
Если исходники менялись после preflight, `next_actions` сначала укажет
`run_full_build_only_preflight`. Gate также требует
`run_runtime_static_preflight`, если свежая рабочая STM32 firmware не была
реально загружена и проверена Saleae после последнего build-only. `--dry-run`
здесь не считается допуском к active PWM. Gate отдельно хранит обычную UART
protocol-диагностику и loopback USB-UART/изолятора; loopback считается
актуальным только если он свежее последнего protocol-fail. Поэтому `next_actions`
различает `run_uart_loopback`, `fix_usb_uart_loopback`,
`reconnect_stm32_uart_and_rerun_protocol` и проверку PA2/PA3/GND/firmware.
Каждый запуск `bench_gate_report.py` пишет рядом с `summary.json` файл
`NEXT_STEPS_RU.md` с текущим порядком действий на стенде. Финальная команда
`current_bench_status.py` обновляет корневой `CURRENT_BENCH_STATUS_RU.md` из
последних `summary.json`; если он расходится со свежим JSON, главным считается
JSON и статус нужно пересформировать. `current_bench_status.py --check`
проверяет, что корневой статус не устарел после последнего bench/readiness/build
артефакта. `refresh_bench_status.py --build-if-stale` последовательно запускает
bench-gate, при необходимости безопасный `full_system_preflight.py --build-only`,
readiness, атомарное обновление `CURRENT_BENCH_STATUS_RU.md` и `--check`; он не
запускает active PWM.

Полный build-only прогон без HMI/UART/Saleae/PWM:
```powershell
py -3 -u .\tools\full_system_preflight.py --build-only
```
Этот режим проверяет compile/build/offline protocol guards и возвращает успешный
код при зелёной сборке, но не помечает `overall_pass=true`, потому что HIL не запускался.

Перед тестами проверь Saleae (Logic2 Automation):
```powershell
py -3 -u .\tools\la_probe.py
```
Если `devices []`, то Logic2 запущен, но анализатор не виден. В этом состоянии захваты невозможны.
`saleae_highlevel_probe.py --cmd START` также проходит через
`active_pwm_guard.py`; если bench-gate красный, команда `START` не отправляется,
а summary получает `command_pass=false`.
Для ручной проверки статического SAFE-состояния используй строгий режим:
```powershell
py -3 -u .\tools\saleae_highlevel_probe.py --channels 0,1,2,3,4,5,6 --rate 24000000 --auto-rate --duration 0.12 --require-static-safe
```

Один кейс:
```
py -3 -u .\tools\ui_pwm_case.py --url http://127.0.0.1:18080 --mode VF --freq 5.0 --tag vf_5 `
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Полный suite:
```
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 --capture-every-hz 1.0 `
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Для единичных transport/control transient доступны аккуратные повторы только чистых PWM-кейсов:
```
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 --case-retries 1 --retry-delay 0.2
py -3 -u .\tools\ui_pwm_case.py --url http://127.0.0.1:18080 --mode VF --freq 5.0 --tag vf_5 --case-retries 1
```

Частичные прогоны (например только hot‑switch и ESTOP):
```
py -3 -u .\tools\ui_pwm_suite.py --url http://127.0.0.1:18080 --skip-sweep --skip-diag --skip-duty `
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

Быстрый sanity‑check (DIAG + один захват):
```
py -3 -u .\tools\ui_pwm_case.py --url http://127.0.0.1:18080 --mode DIAG --tag diag `
  --la-channels 0,1,2,3,4,5,6 --la-rate 2000000 --la-duration 0.7
```

После любого кейса/сьюта скрипты автоматически делают `STOP` + `CLEAR`.

## Build + Flash (Blue Pill, PlatformIO)
Сборка без прошивки:

```powershell
py -3 -m platformio run -d bluepill_uart_pwm_pio -e bluepill_uart_pwm
```

На стенде не прошивать Blue Pill прямой PlatformIO upload-командой как обычным
путем. Когда HV/J7 отключен и DC-шина разряжена, используй безопасный wrapper:
он прошивает runtime и сразу доказывает через Saleae, что CH0..CH6 в SAFE/static.

```powershell
py -3 -u .\tools\bluepill_runtime_static_preflight.py --confirm-hv-off
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

# MIC AI (LUT) — методика исследования на железе

В этом проекте `MIC` реализован как **безопасный MCU‑fallback**: не PyTorch на Linux, а LUT‑политика `id_ref(omega_ref, load)` + гейты/ограничения скорости изменения.

Логика MIC/LUT теперь хранится прямо в этом репозитории:
- `uno_q_control.h` (гейты + rate limit)
- `id_ref_lut_motor1.h` (LUT `Id_ref(omega_ref, load)`)

При необходимости LUT можно пересобрать/обновить из внешних утилит `C:\\mic_ai\\...`, но для работы проекта это уже не требуется.

Перед любым сравнением `FOC`/`MIC`, матрицей или preflight, который может
отправить `START`, сначала проверить текущий gate:

```powershell
py -3 -u .\tools\refresh_bench_status.py --url http://127.0.0.1:18080
```

Если `CURRENT_BENCH_STATUS_RU.md` показывает `Active PWM разрешен: НЕТ`, научную
серию не запускать. Сначала закрыть next-actions из `CURRENT_BENCH_STATUS_RU.md`
и `tools\_preflight_exports\...\NEXT_STEPS_RU.md`.

## 1) Что считается “MIC” в UNOQ_MOTOR
- Режим UI: `MODE MIC`
- Контур тока/FOC остается штатным, меняется только `Id_ref` (магнитизация).
- LUT: `UNOQ_MOTOR/UNOQ_MOTOR.ino` включает `id_ref_lut_motor1.h` и вызывает `unoq_motor1_id_ref_query(...)`.
- Гейты:
  - AI выключается на переходных (пока скорость не “устаканилась” по внутреннему рефу)
  - если энкодер валиден, в гейт добавляется контроль рассогласования с измеренной скоростью
  - на fault/estop/stop AI всегда выключен
  - при деградации связи UNOQ <-> Blue Pill (`link_flags`) AI всегда выключен
  - `Id_ref` всегда ограничен по диапазону и по скорости изменения

Поля в `/api/status`:
- `mode`: `FOC` или `MIC`
- `mic_active`: 1 если LUT реально применяется (гейты разрешили), иначе 0
- `id_ref`: текущее заданное `Id_ref` (A)
- `mic_saving_pct`: оценка экономии потерь (%) по простой модели (см. `mic_estimate_p_loss()` в прошивке)

## 2) Подключение энкодера (для omega_meas / slip)
Сейчас используется **AS5600 по I2C** на Blue Pill:
- `PB10` = `I2C2_SCL`
- `PB11` = `I2C2_SDA`
- `3.3V` и `GND`

Проверка (на ПК):
```powershell
py -3 -u .\tools\encoder_test.py --url http://127.0.0.1:18080 --duration 10 --poll 0.05
```

## 3) Сравнение FOC vs MIC (timeseries)
Скрипт запускает **два конечных прогона**: `FOC`, затем `MIC`.
На каждом:
1) `CLEAR` → `MODE ...` → `SET FREQ ...` → `START`
2) ждёт статус `pwm=1` + совпадение `mode` + `freq_cmd`
3) делает warmup
4) снимает `duration` секунд телеметрии
5) делает `STOP` + `CLEAR` (best-effort)

Запуск:
```powershell
py -3 -u .\tools\mic_ai_compare.py --url http://127.0.0.1:18080 --freq 10.0 --duration 8 --poll 0.05 --warmup 0.8
```

`mic_ai_compare.py` использует только HTTP `/api/status` и `/api/cmd`; Saleae/Logic2/grpc для него не требуются.

Выход:
- `tools/_mic_ai_exports/<tag>_<timestamp>/timeseries_foc.csv`
- `tools/_mic_ai_exports/<tag>_<timestamp>/timeseries_mic.csv`
- `tools/_mic_ai_exports/<tag>_<timestamp>/summary.json`

## 3.1) Матрица Для Научного Исследования

Один `mic_ai_compare.py` нужен для отладки точки. Для отчета/научной работы использовать серию с повторами:

```powershell
py -3 -u .\tools\mic_research_matrix.py --url http://127.0.0.1:18080 `
  --freqs 2,5,10,20 --repeats 3 --duration 10 --warmup 1.0 --require-encoder `
  --motor-label "<motor/nameplate>" --load-note "<load condition>" --supply-note "<supply/current-limit>"
```

Скрипт перед стартом требует безопасный стенд: `SAFE`, `pwm=0`, `estop=0`, `bp_fault=0`, `bp_bad_cnt=0`.
Серия по умолчанию низковольтная: матрица и каждый raw `mic_ai_compare.py` блокируют `START`, если Vbus не читается или выше `--max-start-vdc` (по умолчанию 60 В). Это защита от случайного запуска на 315 В, когда серия задумана как отладочная.
Условия стенда сохраняются в `bench_context`: мотор, нагрузка, питание, температура, приборы и свободная заметка. Можно передать JSON через `--bench-config` или отдельные флаги `--motor-label`, `--load-note`, `--supply-note`, `--ambient-c`, `--instrumentation-note`, `--bench-note`.
Для каждой частоты и повтора он запускает `mic_ai_compare.py`, сохраняет raw summary, затем пишет:

- `tools/_research_exports/<tag>_<timestamp>/aggregate.csv`
- `tools/_research_exports/<tag>_<timestamp>/summary.json`

Для реальной HV-серии после успешного `full_system_preflight.py --with-hv` и проверки внешнего E-STOP запускать матрицу только с явным `--allow-hv`:
```powershell
py -3 -u .\tools\mic_research_matrix.py --url http://127.0.0.1:18080 `
  --freqs 2,5,10,20 --repeats 3 --duration 10 --warmup 1.0 --require-encoder --allow-hv
```

Матрица ходит к локальному HMI без системного proxy/VPN proxy. Каждый raw-прогон ограничен таймаутом: по умолчанию он рассчитывается автоматически из `duration/warmup/status-timeout`, но для длинных точек можно задать явно:
```powershell
py -3 -u .\tools\mic_research_matrix.py --url http://127.0.0.1:18080 `
  --freqs 2,5,10,20 --repeats 3 --duration 30 --case-timeout-s 600 --require-encoder
```

Главный флаг в общем summary: `aggregate.research_ready`. Он становится `true` только если все повторы прошли и `mic_active_ratio` во всех точках не ниже порога.

После матрицы можно собрать Markdown-отчет:

```powershell
py -3 -u .\tools\mic_research_report.py .\tools\_research_exports\<run>\summary.json `
  --calibration-summary .\tools\_calibration_exports\<run>\summary.json
```

Отчет пишет `report.md` рядом с `summary.json`: provenance metadata, общие средние, стандартное отклонение, таблицу по частотам, ссылки на raw summaries и SVG-графики:
- `mic_active_ratio.svg`
- `p_proxy_delta_pct.svg`
- `i_rms_delta_pct.svg`
- `enc_rpm_delta_pct.svg`
Если передан `--calibration-summary`, добавляется раздел `Calibration Evidence` с `zero_current_sanity` и нулевыми токовыми метриками.

Важно для методики: перед серией явно зафиксировать backend управления. По умолчанию UNO Q командует Blue Pill `MODE_DUTY` и сам рассчитывает duty/SVPWM. Для строгого measured-angle FOC включить `BPFOC ON` только в `SAFE/pwm=0`, после чего Blue Pill должен отвечать `bp_cmd_mode=5` и `bp_foc_backend=1`. Эти поля попадают в `timeseries_*.csv` и summary; без них нельзя честно утверждать, что серия была выполнена именно на measured-angle FOC.

Перед такой серией сначала выполнить низковольтный gate:
```powershell
py -3 -u .\tools\bpfoc_backend_preflight.py --url http://127.0.0.1:18080 --freq 1.0
```

Если нужен единый evidence-прогон перед научной серией, можно включить BPFOC и fan gates прямо в общий runner:
```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080 --with-fan --with-bpfoc
```

При подключенном `PA11_FAN_TACH` добавлять `--fan-require-tach`. В верхнем `summary.json` должны быть `fan_pass=true`, `bpfoc_pass=true`, `overall_pass=true`.

Перед матрицей снять calibration snapshot:
```powershell
py -3 -u .\tools\telemetry_calibration.py --url http://127.0.0.1:18080 --samples 100
```

В его `summary.json` должны быть `pass=true` и `zero_current_sanity.pass=true`. Если zero-current sanity падает, сначала исправить offset/датчики токов, иначе сравнение `i_rms` и `p_proxy` будет научно слабым.

Перед научной серией можно запустить общий gate доказательств:
```powershell
py -3 -u .\tools\research_readiness_check.py --url http://127.0.0.1:18080 --profile science
```

Он не включает PWM: только читает live `/api/status` и проверяет, что последние preflight/calibration/matrix artifacts существуют, свежие относительно прошивок/HMI/tooling/config и проходят нужные флаги. Правки документации видны в summary отдельно, но сами по себе не инвалидируют HIL/HV artifacts. Если вывод `ready=false`, сначала закрыть `failed_checks`; поле `next_actions` в `tools/_readiness_exports/.../summary.json` даст порядок действий и готовые команды.

PASS/FAIL:
- PASS если оба режима успешно отработали и одновременно выполняются пороги:
  - `mic_active_ratio >= min_mic_active_ratio` (по умолчанию `0.05`)
  - `i_rms_pct <= max_i_rms_increase_pct` (по умолчанию `2.0%`)
  - `p_proxy_pct <= max_p_proxy_increase_pct` (по умолчанию `3.0%`)
  - `mic_saving_pct_mean >= min_mic_saving_pct` (по умолчанию `0.0%`)
  - если есть `enc_rpm`, дополнительно `|enc_rpm_pct| <= max_enc_rpm_delta_pct` (по умолчанию `8.0%`)
  - при `--require-encoder` обязательно `enc_ok_ratio >= 0.7` в обоих режимах

## 4) Что смотреть в результатах
В `summary.json`:
- `foc.mean_i_rms` vs `mic.mean_i_rms`
- `mic.mean_mic_saving_pct`
- `mean_enc_rpm` и `mean_speed_err_rpm` (если энкодер подключен)
- `mic.mic_enable_ai_ratio`, `mic.mic_gated_ratio`
- `mic.mean_mic_freq_meas_hz`, `mic.mean_mic_speed_err_hz`, `mic.mean_mic_speed_tol_hz`
- `mic.mic_link_flags_values`, `mic.mic_status_flags_values`, `mic.mic_enc_used_values`

Важно:
- На асинхроннике `speed_cmd` (синхронная) и `enc_rpm` (реальная) различаются из‑за скольжения.
  Это нормально: в гейтах используется допуск по slip, чтобы не блокировать MIC в штатном режиме.

Практический смысл новых полей:
- `mic_enable_ai_ratio > 0`, но `mic_active_ratio = 0` означает, что AI в принципе разрешался, но потом гейт/условия не дали ему удержаться.
- `mic_gated_ratio = 1.0` при `enc_ok=1`, `mic_link_flags_values=[0]` и `mic_status_flags_values=[0]` обычно значит не проблема связи/ошибки, а проблема физики стенда: нет реального вращения или измеренная скорость не совпадает с ожидаемой.
- Если AS5600 читается (`enc_ok=1`), но вал фактически не вращается, `mic_ai_compare.py` должен считаться диагностическим, а не “проходным” тестом эффективности MIC.
- Если `enc_ok=0`, это blocker/fail по физике I2C/питания AS5600, а не `diagnostic_only`.

Для полного проекта это уже встроено в верхнеуровневый раннер:
```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080
```

Он не маскирует реальный fail, но и не врёт: если `AS5600` читается и `MIC` корректно загейтился по измеренной скорости, итоговый статус `mic_compare` будет `diagnostic_only`, а не псевдо-ошибка прошивки.

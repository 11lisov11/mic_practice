# MIC AI (LUT) — методика исследования на железе

В этом проекте `MIC` реализован как **безопасный MCU‑fallback**: не PyTorch на Linux, а LUT‑политика `id_ref(omega_ref, load)` + гейты/ограничения скорости изменения.

Логика MIC/LUT теперь хранится прямо в этом репозитории:
- `uno_q_control.h` (гейты + rate limit)
- `id_ref_lut_motor1.h` (LUT `Id_ref(omega_ref, load)`)

При необходимости LUT можно пересобрать/обновить из внешних утилит `C:\\mic_ai\\...`, но для работы проекта это уже не требуется.

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
.\.venv\Scripts\python.exe -u .\tools\encoder_test.py --url http://127.0.0.1:18080 --duration 10 --poll 0.05
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
.\.venv\Scripts\python.exe -u .\tools\mic_ai_compare.py --url http://127.0.0.1:18080 --freq 10.0 --duration 8 --poll 0.05 --warmup 0.8
```

Выход:
- `tools/_mic_ai_exports/<tag>_<timestamp>/timeseries_foc.csv`
- `tools/_mic_ai_exports/<tag>_<timestamp>/timeseries_mic.csv`
- `tools/_mic_ai_exports/<tag>_<timestamp>/summary.json`

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
.\.venv\Scripts\python.exe -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080
```

Он не маскирует реальный fail, но и не врёт: если `AS5600` читается и `MIC` корректно загейтился по измеренной скорости, итоговый статус `mic_compare` будет `diagnostic_only`, а не псевдо-ошибка прошивки.

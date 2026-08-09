# Готовность проекта к научному исследованию

Дата последней проверки низковольтного стенда: 2026-07-26.

Текущий `bench_gate_report.py` возвращает `ready_for_active_pwm=true` для
безсилового стенда: runtime-static имеет шаблон `all_pwm_low_safe`, связь
`ПК/HMI -> UNO Q -> STM32` живая, команды `START/STOP/E-STOP/CLEAR` проходят,
а Saleae подтверждает отсутствие перекрытия всех трех комплементарных пар.

Это разрешение относится только к низковольтному HIL без HV/J7. Формальный
профиль `research_readiness_check.py --profile low_voltage` пока остается
`ready=false`: после последних правок tooling нужен новый расширенный
`full_system_preflight.py` и отдельный свежий Blue Pill PWM self-test artifact.
HV/нагрузочные испытания, калибровка измерений и воспроизводимая MIC-матрица
по-прежнему не закрыты и не должны объявляться выполненными.

Этот файл фиксирует не просто готовность "покрутить двигатель", а готовность получить воспроизводимые данные, которые можно использовать в отчете, статье или защите.

## Проверено На Стенде 2026-07-26

- `py -3 -u tools\full_system_preflight.py --build-only --timeout-build 300`
- `py -3 -u tools\protocol_contract_check.py`
- `py -3 -u tools\firmware_config_safety_check.py`
- `py -3 -u tools\protocol_safety_selftest.py`
- `py -3 -u tools\pc_direct_hmi_selftest.py`
- `arduino-cli compile --fqbn arduino:zephyr:unoq:link_mode=static .\UNOQ_MOTOR`
- `py -3 -m platformio run` в `bluepill_uart_pwm_pio`
- `py -3 -u tools\bluepill_uart_diagnose.py --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --dtr-rts-matrix`
- `py -3 -u tools\bench_gate_report.py`
- `py -3 -u tools\research_readiness_check.py`
- `git diff --check`

В этом проходе active PWM выполнялся только без силовой части. Проверены частоты
0,1/0,5/1,0 Гц, E-STOP и восстановление, кнопочный `START`, общий захват шести
PWM и точные парные захваты 24 Мвыб/с. HV/J7, двигатель под нагрузкой и реальные
MIC/FOC исследовательские серии в этот проход не выполнялись.

## Что уже готово

- Низковольтный software/HIL-контур: сборка прошивок, HMI, Saleae/Logic2 tooling, проверка ШИМ, dead-time, запрет сквозного открытия и возврат в `SAFE`.
- Blue Pill генерирует комплементарный TIM1 PWM с dead-time и выключает силовые выходы при fault, timeout и E-STOP.
- Подтвержденный runtime-контур сейчас: `ПК/HMI -> ADB-router UNO Q -> UART -> STM32 Blue Pill`. PC-direct USB-UART сохранен как альтернативный диагностический маршрут.
- В HMI выведены основные данные стенда: состояние, PWM, частота, токи, Vbus, температура радиатора, фазы A/B и вычисленная C, AS5600, precharge, fan, Blue Pill status.
- Подготовлен контур вентилятора: `PB3_FAN_PWM`, `PA11_FAN_TACH`, команды `FAN ON/OFF/PWM`, preflight `tools/fan_preflight.py`.
- Управляемый precharge-контур удален: `PB4` high-Z, K1 отсутствует, legacy-бит `0x08` обязан оставаться нулевым.
- Подготовлен экспериментальный BPFOC backend: команда `BPFOC ON` включает режим, где Blue Pill получает FOC-команду и должен работать по измеренному углу.
- Усилен `tools/bpfoc_backend_preflight.py`: перед каждым `START` он заново проверяет Vbus, SAFE, живую связь Blue Pill, encoder, `bp_mode`, `bp_cmd_mode` и биты `ENABLED/PWM_ACTIVE`.
- `tools/full_system_preflight.py` включает fan и BPFOC gates; научный допуск требует отключенного precharge-stage и нулевого legacy-бита PB4.
- Новые evidence-файлы пишут `run_metadata`: git branch/commit, dirty status, командную строку и среду запуска. Это закрывает требование привязки измерений к конкретной версии прошивки/tooling.
- Есть матрица научных прогонов: `tools/mic_research_matrix.py` делает повторы FOC/MIC по частотам и пишет `aggregate.csv`.
- Матрица научных прогонов теперь имеет собственный low-voltage guard: перед каждым повтором проверяет `SAFE`, `pwm=0`, ошибки Blue Pill, `enc_ok` при `--require-encoder` и Vbus-порог; HV-серия требует явный `--allow-hv`.
- Есть генератор отчета по данным матрицы: `tools/mic_research_report.py` пишет `report.md`, provenance-раздел и SVG-графики по частотам.
- Есть помощник калибровки телеметрии: `tools/telemetry_calibration.py`; он также проверяет zero-current sanity в `SAFE/pwm=0` по `ia/ib/ic/i_rms`.
- Есть автоматический gate готовности: `tools/research_readiness_check.py` проверяет live `/api/status`, последний `bench_gate_report.py`, свежесть последнего `full_system_preflight`, наличие calibration artifacts и MIC/FOC матрицы.

## Что еще не закрыто

0. Два обязательных предзапусковых блокера bench gate.
   Сначала нужен свежий USB-UART loopback после последнего write-timeout:
   отключить TX/RX от STM32, замкнуть TX-RX на изолированной стороне USB-UART и
   выполнить `tools\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080`.
   Затем при отключенной и разряженной HV-шине выполнить
   `tools\bluepill_runtime_static_preflight.py --confirm-hv-off` и получить
   `pattern=all_pwm_low_safe`.
   Если после runtime-static снова `low_side_static_high`, выполнить
   `tools\bluepill_static_low_preflight.py --confirm-hv-off`. Если static-low
   проходит, искать TIM1/runtime init; если static-low тоже показывает HIGH,
   искать физику: `PB13/PB14/PB15` на Blue Pill, входы IPM, Saleae GND/каналы.

1. Свежий HV/J7 regression на последней прошивке.
   Нужно прошить актуальные UNO Q и Blue Pill, закрыть `ready_for_active_pwm=true`
   на low-voltage стенде, подтвердить ограничение тока/предохранитель, внешний
   E-STOP и развязку USB/Saleae, и только после этого выполнять
   `tools/full_system_preflight.py --with-hv`. Без такого HV PASS нельзя честно
   говорить, что последняя версия проекта проверена с силовой шиной.

2. Проверка BPFOC на реальном железе.
   Код и preflight готовы, но нужно физически подтвердить, что при `BPFOC ON` Blue Pill реально переходит в `MODE_FOC`, держит PWM active и не уходит в fault на низком напряжении, а потом на HV/J7.

3. Научное сравнение MIC против FOC на вращающемся двигателе.
   Старый `mic_compare=diagnostic_only` допустим для неподвижного вала, но для исследования нужен реальный прогон с вращением, где `mic_active_ratio` больше заданного порога и есть сравнение токов, скорости и потерь.

4. Калибровка измерений.
   Vbus уже имеет рабочую калибровку, но для научных графиков нужно сохранить отдельные calibration artifacts. Также нужно откалибровать фазные токи, температуру радиатора и tach вентилятора.

5. Методика нагрузки.
   Для исследования мало холостого хода. Нужны одинаковые точки нагрузки или хотя бы явно описанные условия: частота, время прогрева, длительность, повторность, температура, питание, нагрузка на вал.

6. Статистическая обработка.
   Базовые CSV, Markdown-отчет и SVG-графики уже есть. Еще нужно добавить финальные графики по калиброванной мощности/температуре после реальных HV-прогонов и калибровки датчиков.

7. Защита стенда перед длительными прогонами.
   До серии HV-экспериментов нужно отдельно подтвердить precharge, bleeder, предохранитель/ограничение тока, внешний E-STOP, развязку USB/Saleae и отсутствие опасной общей земли с HV DC-.

8. PCB review.
   Схему платы нужно прогнать через ERC/DRC и отдельно проверить HV/logic separation, creepage/clearance, ширину силовых дорожек, землю, тест-поинты и разъемы.

9. Версионирование доказательств.
   Каждый научный прогон должен сохранять git SHA, версии прошивок, дату, параметры стенда и ссылки на `summary.json`, `aggregate.csv`, Saleae capture и отчет.

## Минимальный план перед научной серией

1. Выполнить свежий USB-UART loopback после последнего write-timeout.
2. При отключенной и разряженной HV-шине прошить и проверить runtime static:
   `py -3 -u tools\bluepill_runtime_static_preflight.py --confirm-hv-off`
3. Если runtime-static снова показывает `low_side_static_high`, выполнить:
   `py -3 -u tools\bluepill_static_low_preflight.py --confirm-hv-off`
4. Зафиксировать безопасное состояние: `SAFE`, `pwm=0`, `estop=0`, `bp_fault=0`, `bp_bad_cnt=0`.
5. Прошить актуальную Blue Pill; UNO Q прошивать только если он используется как UI/панель, а не для PC-direct runtime.
6. С HV отключенной шиной выполнить расширенный низковольтный regression:
   `py -3 -u tools\full_system_preflight.py --url http://127.0.0.1:18080 --with-fan --with-bpfoc`
7. Если tach вентилятора подключен к `PA11`, повторить или сразу запускать с:
   `--fan-require-tach`
8. После успешного низковольтного прогона выполнить HV/J7 regression только если
   `bench_gate_report.py` уже показывает `ready_for_active_pwm=true`, силовая часть
   собрана с ограничением тока/предохранителем, внешний E-STOP доступен, а
   USB/Saleae развязаны от HV DC-. При красном gate этот пункт пропустить и сначала
   выполнить `next_actions` из `CURRENT_BENCH_STATUS_RU.md`:
   `py -3 -u tools\full_system_preflight.py --url http://127.0.0.1:18080 --with-hv`
9. Снять калибровку телеметрии:
   `py -3 -u tools\telemetry_calibration.py --url http://127.0.0.1:18080 --samples 100`
   В `summary.json` должно быть `pass=true` и `zero_current_sanity.pass=true`.
10. Провести MIC/FOC матрицу:
   `py -3 -u tools\mic_research_matrix.py --url http://127.0.0.1:18080 --freqs 2,5,10,20 --repeats 3 --duration 10 --require-encoder --motor-label "<motor>" --load-note "<load>" --supply-note "<supply>"`
   Для HV-серии тот же запуск делать только после HV/J7 PASS и только с явным `--allow-hv`; без этого флага матрица блокирует `START`, если Vbus выше `--max-start-vdc` или не читается.
11. Сгенерировать отчет:
   `py -3 -u tools\mic_research_report.py <папка_прогона>\summary.json`
12. Запустить итоговый readiness gate:
   `py -3 -u tools\research_readiness_check.py --url http://127.0.0.1:18080 --profile science`
   Для текущего предзапускового этапа до активного PWM использовать `--profile bringup`.
   Для полного низковольтного этапа без требований HV/calibration/matrix использовать `--profile low_voltage`.
   Если `bench_gate_ready_for_active_pwm=false`, сначала выполнить `next_actions`
   из readiness summary. Для текущего стенда ожидаемые физические шаги:
   `run_runtime_static_preflight` после отключения HV/J7 и разряда DC-шины,
   при повторе low-side HIGH — `run_static_low_isolation_preflight`, затем
   `run_uart_loopback` с отключенными от STM32 TX/RX и восстановление HMI/status.

## Критерий готовности к научным выводам

Проект можно считать готовым к научным выводам только когда одновременно выполнено:

- Последний расширенный low-voltage regression проходит без fail: `overall_pass=true`, `precharge_relay_stage_enabled=false`, `precharge_relay_pass=null`, `precharge_relay_saleae_enabled=false`, `fan_pass=true`, `bpfoc_pass=true`.
- Последний HV/J7 regression проходит без fail.
- BPFOC backend подтвержден на железе, а не только сборкой и fake-HMI smoke.
- MIC имеет реальные активные интервалы на вращающемся двигателе.
- Есть минимум 3 повтора на каждую точку частоты/нагрузки.
- В `mic_research_matrix.py` summary заполнен `bench_context`: мотор, нагрузка, питание/ограничение тока, температура/приборы.
- Все исходные артефакты сохранены: `summary.json`, `aggregate.csv`, лог HMI, capture логического анализатора, `run_metadata.git.commit` и dirty status.
- `tools/research_readiness_check.py --profile science` возвращает `ready=true`; если он возвращает `ready=false`, смотреть `failed_checks` и `next_actions` в его `summary.json`.

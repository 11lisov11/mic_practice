# MIC_AI: UNO Q + NUCLEO-G431RB + STEVAL-IPM15B

Текущая конфигурация проекта:

`телефон/ноутбук <- Wi-Fi -> UNO Q -> прямой UART 3.3 В -> NUCLEO-G431RB -> X-NUCLEO-IHM09M2 -> FC-34P -> STEVAL-IPM15B -> AIR56B2`.

В силовом режиме весь цифровой тракт находится внутри закрытого корпуса. `HOT_GND` электрически связан с `STEVAL J7 DC-`; USB, ST-Link, Ethernet, UART-адаптер, Saleae и осциллограф подключать нельзя. Наружу выходит только Wi-Fi. Wi-Fi не заменяет двухполюсный выключатель и аппаратный аварийный останов.

## Текущий статус

- Целевая плата управления двигателем: `NUCLEO-G431RB`, микроконтроллер `STM32G431RBT6U`.
- Силовая плата: `STEVAL-IPM15B` через `X-NUCLEO-IHM09M2` и прямой шлейф `FC-34P 2x17`.
- Двигатель: `AIR56B2`, 0,25 кВт, 220 В, соединение обмоток треугольником.
- Активная прошивка Nucleo поддерживает только scalar `V/f`. FOC и MIC остаются последующими этапами и блокируются HMI до появления соответствующей capability в прошивке.
- Внешний soft-start автономный; управляющего реле предзаряда от MCU нет.
- Программные тесты и статические проверки выполняются без силовой части. Физическая HIL-проверка пока не завершена: `hardware_validated=false`.

## Главные документы

- `research/AIR56B2_ENERGY_VALUE_METHOD_RU.md` - энергетический выбор измерений, уравнения и ограничения; моделирование поверх FOC.
- `research/AIR56B2_ENERGY_VALUE_PROTOCOL_RU.md` - замороженная основная проверка; воспроизведение: `tools/run_air56b2_energy_value.ps1`.
- `research/AIR56B2_ENERGY_VALUE_LIGHT_LOAD_PROTOCOL_RU.md` - отдельная проспективная проверка при 10% нагрузки, не замена основной серии.
- `research/AIR56B2_ACTIVE_PROBE_RESULTS_RU.md` - 224 опыта и 21 уточнение: преимущество активного выбора не подтвердилось; результаты и ограничения.
- `research/AIR56B2_ACTIVE_PROBE_PROTOCOL_RU.md` - следующий опыт: информационный выбор парных проб и измеренная цена возврата; только моделирование.
- `research/AIR56B2_ACTIVE_PROBE_PRIOR_ART_RU.md` - шесть близких первоисточников; сочетание известных приёмов ещё не научная новизна.
- `research/AIR56B2_ACTIVE_PROBE_IDENTIFIABILITY_RU.md` - доказуемые свойства парного измерения и границы выводов из короткой истории.
- `research/AIR56B2_BUDGET_RESULTS_RU.md` - проверка нового кандидата: 192 опыта; преимущество фиксированного бюджета не подтвердилось.
- `research/AIR56B2_NOVELTY_AUDIT_20260909_RU.md` - ближайшие научные аналоги; новизна энергетического фильтра пока не установлена.
- `research/AIR56B2_BUDGET_PROTOCOL_RU.md` - протокол бюджета проб, условные границы и сравнение с отключением отдельных ограничений.
- `research/AIR56B2_DYNAMIC_POWER_RESULTS_RU.md` - динамическая проверка потерь, FOC и полных затрат проб (исследование на ПК).
- `research/AIR56B2_ENERGY_CORE_THEORY_RU.md` - новая энергетически согласованная модель, уравнения и ограничения выводов.

- `output/pdf/MIC_AI_NUCLEO_SYSTEM_WIRING.pdf` - семилистовая схема соединений.
- `hardware/nucleo_system_wiring/MIC_AI_NUCLEO_CONNECTIONS.csv` - таблица всех контактов.
- `hardware/nucleo_system_wiring/ASSEMBLY_RU.md` - порядок сборки.
- `docs/AUTONOMOUS_WIFI_OPERATION_RU.md` - автономная работа через роутер или точку доступа UNO Q.
- `docs/UNOQ_MCSDK_UART_CONTRACT_RU.md` - контракт UNO Q и Nucleo.
- `docs/BOARD_FIRMWARE_FLASH_RU.md` - прошивка плат только в сервисном режиме.
- `docs/FIRMWARE_STAGES_RU.md` - этапы V/f, FOC, обучение и MIC.
- `NUCLEO_G431_MIGRATION_RU.md` - принятые решения по переходу на G431.

## UART UNO Q - Nucleo

- `UNO Q D1 / PB6 / USART1_TX` -> `Nucleo PB7 / CN7-21 / USART1_RX`.
- `Nucleo PB6 / CN10-17 / USART1_TX` -> `UNO Q D0 / PB7 / USART1_RX`.
- `UNO Q GND` <-> `Nucleo GND` <-> `HOT_GND`.
- Шины `3.3 V` плат между собой не соединяются.

Тайм-аут motor-controller link на Nucleo составляет 300 мс. Потеря heartbeat браузера более чем на 3 секунды во время разрешённого запуска вызывает `STOP`, затем `ESTOP`.

## Сборка программного комплекта

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build_board_flash_package.ps1
```

Результат:

- `firmware/ready_to_flash/`
- `firmware/ready_to_flash.zip`

Проверка пакета:

```powershell
python .\tools\verify_board_flash_package.py .\firmware\ready_to_flash
```

Полный активный preflight без Blue Pill-зависимостей:

```powershell
python .\tools\nucleo_release_preflight.py
```

## Исследовательский пакет AIR56B2

Следующий динамический этап: `research/AIR56B2_DYNAMIC_POWER_RESULTS_RU.md`.
В нём потери стали включены в уравнения токов, а сравнение учитывает разгон,
нагрузку, энергию проб и отказы адаптации. Основная сетка объекта - 50 мкс,
регулятора - 100 мкс; дополнительно проверяется измельчение объекта.
Это усреднённое моделирование с энкодером, без новых весов ИИ и без изменения прошивок.

```powershell
powershell -ExecutionPolicy Bypass -File tools/run_air56b2_dynamic_power.ps1
```

Обновление 08.09.2026: добавлен эксперимент адаптации потока по измерительному
окну. Аудит выявил ошибки интерпретации момента и энергетического баланса в
старой модели потерь; её прежние проценты экономии требуют пересчёта.
В новом опыте используются исправленный расчёт, шум измерений и сопоставимые
условия для аналитического метода и нейросети.

- `research/AIR56B2_MEASUREMENT_ADAPTATION_RESULTS_RU.md` - новые результаты.
- `research/AIR56B2_MEASUREMENT_ADAPTATION_THEORY_RU.md` - математика, гипотезы и дальнейшие работы.
- `artifacts/measurement_adaptation_20260908_v2/` - протокол, веса и полные результаты.

Воспроизведение нового этапа:

```powershell
powershell -ExecutionPolicy Bypass -File tools/run_air56b2_measurement_adaptation.ps1
```

Полный воспроизводимый прогон моделирования и проверок:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_air56b2_research_pipeline.ps1 -Full
```

Историческая контрольная точка 28.08.2026: `220` автоматических тестов PASS и `41/41` ворот manifest v6 PASS. Она не включает новые проверки баланса потерь. Результаты относятся к SIL-моделированию; `hardware_release_ready=false` до идентификации реального двигателя и прохождения стендовой программы.

- `artifacts/air56b2_research_manifest.json` - канонический manifest с SHA-256.
- `research/AIR56B2_FINAL_RESULTS_RU.md` - итоговые численные результаты и ограничения.
- `docs/experiments/AIR56B2_PREREGISTRATION_RU.md` - заранее зафиксированная методика аппаратного эксперимента.
- `output/pdf/Dissertation_2_9_3_ACIM_AI_working_draft.pdf` - текущий текст диссертации.
- `output/pdf/AIR56B2_научно_технический_отчет_2026-08-28.pdf` - краткий научно-технический отчёт.

Генерация схемы:

```powershell
python .\tools\generate_nucleo_system_wiring.py
```

## Автономный HMI

Первичная установка выполняется по ADB только при физически отключённой сети, снятом J7 и измеренно разряженном DC-link:

```powershell
python .\tools\adb_deploy_web_hmi.py --standalone-hv --restart --confirm-service-mode
```

Настройка через существующий роутер:

```powershell
python .\tools\configure_unoq_autonomous_wifi.py --mode station --ssid "LAB_WIFI" --password "LONG_WIFI_PASSWORD" --confirm-service-mode
```

Автономная точка доступа:

```powershell
python .\tools\configure_unoq_autonomous_wifi.py --mode ap --ssid "MIC_AI_STAND" --password "LONG_AP_PASSWORD" --confirm-service-mode
```

## Legacy

Blue Pill, старая Rev2-схема, PC-direct режимы и связанные preflight-скрипты не входят в текущий пакет прошивки. Они пока сохранены для воспроизводимости прежних экспериментов и будут переноситься в `legacy/` только после отделения старого regression-runner.

Архив прежнего корневого описания: `docs/legacy/BLUEPILL_PROJECT_HISTORY_RU.md`. Использовать его распиновку для Nucleo запрещено.

# Выпускной пакет MCSDK: NUCLEO-G431RB + IHM09M2 + IPM15B

Этот документ определяет, что можно назвать готовым к прошивке пакетом. До выполнения всех пунктов существующие `nucleo_g431_uart_bridge_pio` сборки остаются только безопасными UART/PWM-bench прошивками, а не прошивкой привода.

## Основной пакет AIR56B2

Основной проект находится в `mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV`. Он создан из официального MCSDK примера `ACIM V/F Open Loop` для `NUCLEO-G431RB + X-NUCLEO-IHM09M2 + STEVAL-IPM15B`, но его параметры заменены на паспортные значения целевого двигателя `IEK AIR56B2`.

- MCSDK: `6.4.2`; STM32CubeMX: `6.18.1`; STM32Cube FW G4: `1.6.3`.
- Подключение двигателя: `220 В Delta`; `0,25 кВт`, `1,24 А`, `50 Гц`, `1 пара полюсов`, `2720 об/мин` номинально.
- В модели MCSDK задано `127 В phase-to-neutral` (`220 / sqrt(3)`), `FLUX_K=0,5717009 В·с` и ограничение `3000 об/мин`, соответствующее `50 Гц` для одной пары полюсов.
- Его `Debug`-сборка проходит с `0 errors, 0 warnings`.
- В `STM32CubeIDE/Debug` лежат согласованные `ELF`, `BIN`, `HEX` и JSON-манифест с размерами и SHA-256.
- Это прошивка-кандидат AIR56B2 для V/F по шильдику. Она не является допуском к силовому запуску: измерения двигателя и аппаратная блокировка предзаряда пока не подтверждены.

Пересобрать набор одной командой:

```powershell
powershell -ExecutionPolicy Bypass -File C:\mic_practice\tools\build_acim_reference.ps1
```

Скрипт не прошивает контроллер и не подаёт силовое питание. Когда появится заполненный профиль настоящего двигателя, gate запускается явно:

```powershell
powershell -ExecutionPolicy Bypass -File C:\mic_practice\tools\build_acim_reference.ps1 `
  -MotorProfile C:\path\to\actual_air56.json -RunReleaseGate
```

Для одновременной пересборки Nucleo AIR56B2 и его UNO Q UART-пира используйте `tools/build_firmware_bundle.ps1`. Без параметров команда собирает AIR56B2 V/F-пакет и проверяет совпадение числа пар полюсов в `.ioc` и UNO Q. Полный gate запускается так:

```powershell
powershell -ExecutionPolicy Bypass -File C:\mic_practice\tools\build_firmware_bundle.ps1 `
  -MotorProfile C:\path\to\actual_air56.json -RunReleaseGate
```

В эту же команду включена `tools/air56b2_firmware_profile_check.py`: она сверяет шильдик, `.ioc`, сгенерированные константы, ограничение частоты в UNO Q, ограничение в UART-адаптере Nucleo и SHA-256 собранных артефактов.

Описание кадра и выводов изолятора: `docs/UNOQ_MCSDK_UART_CONTRACT_RU.md`.

## Повторная генерация из `.ioc`

Полную регенерацию нельзя выполнять поверх единственного рабочего проекта: Workbench/CubeMX переписывают сгенерированные файлы. Для этого добавлен безопасный сценарий, который сначала создаёт отдельную копию, затем запускает Workbench, проверяет сохранность UART-адаптера, восстанавливает потерянный CubeMX include-путь CMSIS-DSP и собирает проект:

```powershell
powershell -ExecutionPolicy Bypass -File C:\mic_practice\tools\regenerate_mcsdk_project.ps1 `
  -SourceProject C:\mic_practice\mcsdk_reference\AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV `
  -OutputProject C:\mic_practice\mcsdk_reference\generated\ACIM-NUCLEOG431RB-IPM15B-VF_OL
```

Сценарий не прошивает Nucleo, не обращается к ST-Link и не подаёт силовое питание. Отчёт `mcsdk_regeneration_report.json` остаётся в каталоге новой копии. В установленной связке Workbench/CubeMX возможен ненулевой код Workbench после уже успешно выполненной генерации из-за проверки обновлений CubeMX; это считается **degraded**-результатом и по умолчанию завершает сценарий ошибкой уже после статической проверки и сборки. Не подавлять его без изучения отчёта и лога. Параметр `-AllowWorkbenchNonZero` нужен только для документированного повторения этого известного поведения и не делает образ разрешённым к прошивке двигателя.

## Базовая конфигурация MC Workbench

1. В `X-CUBE-MCSDK 6.4.2` открыть официальный пример `ACIM V/F Open Loop` для `NUCLEO-G431RB`, `X-NUCLEO-IHM09M2`, `STEVAL-IPM15B`.
2. Внести только паспортные и измеренные параметры реального асинхронного двигателя. Шаблон профиля: `docs/mcsdk_acim_motor_profile.template.json`.
3. Сгенерировать проект STM32CubeIDE с HAL. TIM1, ADC, break/fault, PWM и выводы motor-control не редактировать вручную.
4. В текущем проекте адаптер уже находится в пользовательских секциях `Src/main.c` и вызывает только публичный API MCSDK. Он не меняет вручную TIM1, ADC, break/fault или PWM motor-control.
5. Адаптер использует `USART1`: `PB6/TX -> ISO7721 -> UNO D0/RX`, `UNO D1/TX -> ISO7721 -> PB7/RX`. При timeout 300 мс, E-stop или fault он обязан выполнить API-останов MCSDK и потребовать новую явную команду запуска.
6. После повторной генерации из `.ioc` обязательно запустить `tools/uno_nucleo_mcsdk_contract_check.py` и пересобрать оба образа: USART1 добавлен как пользовательская часть приложения, а не как настройка Motor Control Workbench.

Для АИР56B2, соединённого физически в `Delta` с инвертором `220 В line-to-line`, каталожное напряжение одной обмотки равно `220 В`, но в MCSDK V/F должно стоять `127 В phase-to-neutral` (`220 / sqrt(3)`). Это не смена соединения: это эквивалентное представление треугольника внутри трёхфазной модели контроллера. Подготовлен предварительный каталожный профиль: `docs/mcsdk_acim_motor_profile.iek_air56b2_catalog_operator_confirmed_vf_candidate.json`. Он не считается профилем конкретного экземпляра до приложения фото шильдика, хэша и результатов идентификации.

## Что положить в пакет

- исходный сгенерированный MCSDK/CubeIDE-проект;
- исходный JSON профиля реального двигателя;
- `ELF`, `BIN` и `HEX` одной проверенной конфигурации сборки; текущий AIR56B2 V/F-пакет собирается как `Debug`;
- JSON-отчёт `mcsdk_release_preflight.py`;
- лог компиляции и хэш исходников;
- после появления железа: Saleae CSV/отчёт без J7 и HIL-отчёт с регулируемым источником.

Нельзя подменять профиль параметрами из `motor_identification_prior.example.json` или результатами synthetic-симуляции: они годятся лишь для проверки софта.

## Локальный gate

После сборки выполнить:

```powershell
py -3 C:\mic_practice\tools\mcsdk_release_preflight.py `
  --project C:\path\to\generated_mcsdk_project `
  --motor-profile C:\path\to\actual_motor.json `
  --artifacts C:\path\to\generated_mcsdk_project\Debug `
  --output C:\path\to\generated_mcsdk_project\Debug\mcsdk_release_preflight.json
```

Gate проверяет: фактический `STM32G431RB` в `.ioc`, маркеры `NUCLEO-G431RB` (либо `IHM09M2`), `IPM15B`, `ACIM`, реальный паспортный профиль двигателя и наличие согласованного набора `ELF/BIN/HEX` больше 1 KiB. Для профиля обязательны точная маркировка, соединение обмоток, линейное и фазное напряжения, ток, частота, число пар полюсов и номинальная скорость. Также обязательны измеренные `Rs`, `Rr`, `Lls`, `Llr`, `Lm`, инерция и ссылка на протокол измерения: именно эти величины сопоставляются с `M1_RS`, `RR`, `LLS`, `LLR`, `LMS`, `WB_UI_INERTIA` в `.ioc`.

Внешний precharge-релейный узел управляется Nucleo через `PB4`: реализованы порог измеренного Vbus, выдержка до разрешения PWM и размыкание при STOP, E-stop, UART timeout и fault MCSDK. Поэтому исходник содержит `MIC_PRECHARGE_INTERLOCK_IMPLEMENTED 1`. Отдельный `MIC_PRECHARGE_HIL_VALIDATED` остаётся равным `0`, пока на реальном стенде осциллографом не проверены полярность, порог, задержка и все аварийные пути. Release-gate требует оба признака и до HIL-проверки остаётся закрытым.

Отдельно gate сопоставляет профиль с уже сгенерированными константами MCSDK: пары полюсов, напряжение обмотки, допустимую механическую скорость и требуемую шину DC. Для `STEVAL-IPM15B` также запрещается профиль, которому требуется больше `400 В DC` по официальному пределу платы. Артефакты должны иметь общую базовую метку и лежать внутри того же каталога проекта. Gate не заменяет испытания на железе.

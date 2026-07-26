# История Блокера PWM Static: Low-Side HIGH

> Статус на 2026-07-26: **закрыт для низковольтного стенда без силовой части**.
> Актуальная runtime-прошивка прошла статический захват `all_pwm_low_safe`,
> сквозной прогон через HMI/UNO Q/STM32 и проверку всех трех комплементарных пар.
> Перекрытие U/V/W равно нулю; измеренный deadtime после стартового участка
> буфера Logic 2 составляет не менее 791 нс при заданных 800 нс.

Этот файл сохраняет диагностику устраненного дефекта. Описанный ниже запрет
был обязательным до исправления TIM1/GPIO sequencing и повторных Saleae-тестов.
Он снова вступает в силу, если свежий runtime-static gate перестает выдавать
`all_pwm_low_safe`.

## Исторический Симптом

| Saleae | STM32 | Сигнал | Последний уровень | Ожидание SAFE/static |
|---|---|---|---|---|
| CH0 | PA8 | PWM-1H | LOW | LOW |
| CH1 | PB13 | PWM-1L | HIGH | LOW |
| CH2 | PA9 | PWM-2H | LOW | LOW |
| CH3 | PB14 | PWM-2L | HIGH | LOW |
| CH4 | PA10 | PWM-3H | LOW | LOW |
| CH5 | PB15 | PWM-3L | HIGH | LOW |
| CH6 | PB12 | EM_STOP/shutdown | LOW | LOW |

Шаблон: `low_side_static_high`. Это не доказательство deadtime и не тест перекрытия фаз. Это статический блокер: нижние PWM-входы `PB13/PB14/PB15` стоят HIGH, когда должны быть LOW.

## Запреты

- Не подавать `START`.
- Не запускать active PWM.
- Не подавать HV/J7 для обхода этого gate.
- Не считать текущий Saleae-захват безопасным, даже если фронтов и overlap нет.

## Что Уже Исправлено В Коде

В актуальной Blue Pill runtime-прошивке TIM1 теперь не стартует через `HAL_TIM_PWM_Start()` / `HAL_TIMEx_PWMN_Start()`, потому что HAL F1 внутри этих функций поднимает `MOE` по одному каналу.

Текущий порядок в `pwm_tim1.cpp`:

1. PWM-пины держатся GPIO output LOW после `HAL_Init()`.
2. Во время `pwm_tim1_init()` пины остаются GPIO LOW.
3. При включении PWM сначала при `MOE=0` подготавливаются все шесть `CCER` output enable битов.
4. Выполняется `TIM1->EGR = TIM_EVENTSOURCE_UPDATE`.
5. Только после этого `pwm_outputs_enable(true)` поднимает `MOE` одним шагом.
6. При SAFE/STOP/TIMEOUT/FAULT все шесть PWM-пинов снова переводятся в GPIO LOW.

Эти инварианты проверяет:

```powershell
py -3 -u .\tools\firmware_config_safety_check.py
```

## Следующий Обязательный Шаг

Нужно прошить именно актуальную runtime-прошивку и снять новый статический Saleae-захват. Делать это можно только при отключенном HV/J7 и разряженной DC-шине:

```powershell
py -3 -u .\tools\bluepill_runtime_static_preflight.py --confirm-hv-off
```

PASS-критерий: `pass=true`, `static_checks.pass=true`, `pattern=all_pwm_low_safe`, `CH0..CH6 = LOW`, runtime static summary свежее последнего build-only summary.

Если этот runtime static preflight пройдет, можно переходить к восстановлению HMI/UART и общему bench gate. Если он снова покажет `low_side_static_high`, переходить к изоляционному тесту ниже.

## Изоляционный Static-Low Тест

Запускать только при HV/J7 OFF и разряженной DC-шине:

```powershell
py -3 -u .\tools\bluepill_static_low_preflight.py --confirm-hv-off
```

Этот тест прошивает диагностическую Blue Pill прошивку без TIM1/PWM/командного протокола. Она только держит `PA8/PA9/PA10/PB13/PB14/PB15/PB12` в GPIO LOW, снимает Saleae `CH0..CH6`, затем автоматически восстанавливает runtime-прошивку.

Интерпретация:

| Результат static-low | Вывод |
|---|---|
| PASS, но runtime-static FAIL | Ищем ошибку runtime/TIM1 init, target прошивки или фактически загруженную firmware. |
| FAIL на PB13/PB14/PB15 прямо на Blue Pill | Ищем STM32 target/прошивку, GPIO-конфигурацию, питание/GND, повреждение GPIO или конфликт на линии. |
| Blue Pill LOW, IPM входы HIGH | Ищем проводку, разъем, подтяжки или входную опору IPM. |
| Мультиметр/осциллограф LOW, Saleae HIGH | Ищем GND Saleae, перепутанный канал или точку подключения анализатора. |

## Где Мерить При `low_side_static_high`

Порядок измерений без HV/J7:

1. Ножки Blue Pill `PB13`, `PB14`, `PB15`.
2. Соответствующие входы IPM после проводки/разъема.
3. Saleae `CH1`, `CH3`, `CH5` с GND на STM32 logic GND.

Ожидание везде: LOW.

Если где-то появляется HIGH, проблема находится между предыдущей точкой LOW и текущей точкой HIGH.

## Требования К Saleae

- GND Saleae подключен к STM32 logic GND.
- CH0 = PA8, CH1 = PB13, CH2 = PA9, CH3 = PB14, CH4 = PA10, CH5 = PB15, CH6 = PB12.
- Saleae подключается к логическим PWM/EM_STOP линиям, не к фазным выходам U/V/W.
- Статический захват должен быть свежим относительно последней сборки и последней прошивки.

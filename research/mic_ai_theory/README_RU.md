# MIC AI: объединённый исследовательский срез

Этот каталог переносит проверяемую часть `C:\mic_theory` в основной проект
`C:\mic_practice`. Он не является второй активной прошивкой и не изменяет
силовой контур. Исходные данные, статьи и экспериментальные алгоритмы хранятся
здесь для воспроизводимости и подготовки научной серии.

## Что включено

- `articles/` — русская статья ПГУПС, черновик IEEE и статья SNH-PWM.
- `legacy_mic/three_motor_release/` — итоговые таблицы моделирования MIC/FOC для
  AIR56, AL31 и AO2.
- `legacy_mic/air56_deployment_reference/` — прежний референс переноса LUT на
  UNO Q/STM32; это не активная прошивка стенда.
- `legacy_mic/id_ref_lut_motor1_theory_reference.h` — сгенерированная LUT из
  теоретического проекта. Она не подменяет текущую стендовую LUT автоматически.
- `snh_pwm/historical_host_release/` — исторический host-only release SNH-PWM.
- `snh_pwm/source/` — исправленная исследовательская ревизия алгоритма и тестов.
- `snh_pwm/revalidation/snh_paired_0p2s.json` — исходный диагностический прогон,
  выявивший OC-защёлки в длинном окне.
- `snh_pwm/revalidation/snh_paired_0p2s_rev2.json` — контроль после исправления
  токового планирования и fallback.
- `snh_pwm/revalidation/snh_paired_mc10_0p2s_rev2.json` — основная усиленная
  серия до унификации event-trigger.
- `snh_pwm/revalidation/snh_paired_mc10_0p2s_rev3.json` — промежуточная усиленная
  серия: 10 парных повторов, четыре сценария и единое feedback-решение.
- `snh_pwm/revalidation/snh_paired_mc30_all31_0p2s_rev4_final.json` — канонический
  полный результат: 31 сценарий, 30 парных повторов, 8 контроллеров и 0,2 с на прогон.
- `snh_pwm/revalidation/snh_paired_mc30_all31_0p2s_rev4_final_audit.json` —
  машинный аудит полноты, безопасности и допустимых утверждений.
- `snh_pwm/revalidation/FINAL_MC30_SUMMARY_RU.md` — итоговая русская интерпретация.
- `snh_pwm/c6_rv_pwm/RESEARCH_RU.md` — математическая постановка C6-RV-PWM,
  граница относительно литературы, отрицательные результаты и следующие гипотезы.
- `snh_pwm/c6_rv_pwm/revalidation/c6_rv_lab_all31_mc5_0p2s_rev3_lazy.json` —
  полный exploratory-результат по 31 сценарию с MC5 и окном 0,2 с.
- `snh_pwm/c6_rv_pwm/revalidation/c6_rv_lab_all31_mc5_0p2s_rev3_lazy_audit.json` —
  машинный аудит, разрешающий только математическую exploratory-интерпретацию.
- `snh_pwm/c6_conformal_reachability/RESEARCH_RU.md` — формулировка и границы
  кандидата научной новизны C6-BCR: блочно-конформное множество ошибки модели.
- `snh_pwm/c6_conformal_reachability/revalidation/` — два независимых полных
  исторических исследования `20260810/20260811`, development-серия `20260809`, их
  индивидуальные и агрегированный аудиты, а также два сохранённых отрицательных этапа.
  В этих сериях использованы 24 разбиения, 400 calibration-блоков, 800 test-блоков
  и траектории по 40 переключений. Массовые test-блоки внутри одного разбиения
  зависят через общий conformal tube, поэтому прежние pooled-binomial p-value теперь
  считаются только исторической диагностикой. Подтверждающий coverage-gate требует
  нового прогона: одна test-траектория на каждую независимо сформированную
  calibration-выборку.
- `model_identification/` — новый воспроизводимый контур определения `Rs`, `Rr`,
  `Lm`, `J`, `B` с rank-gate, C6-многомасштабным возбуждением и nuisance-параметрами
  `Lsigma/Tload`; включены две независимые серии по 12 двигателей и агрегированный аудит.
- host-конфигурация `snh_pwm/source/config/env.py` теперь использует паспортную
  геометрию целевого AIR56B2: 220 В Delta, 1,24 А, одна пара полюсов, 2720 об/мин.
  Неидентифицированные `Rs/Rr/Lsigma/Lm/J/B` остаются simulation prior, а не
  параметрами для прошивки.

Научная интерпретация и допустимые формулировки приведены в
`../MIC_AI_RESEARCH_AUDIT_RU.md`.

## Проверка целостности

```powershell
py -3 -u tools\mic_theory_snapshot_check.py
```

Проверка перенесённых алгоритмов и исследовательских генераторов из корня
`mic_practice`:

```powershell
python -m pytest -q
```

Тестовый контур самодостаточен: для его запуска не требуется соседний каталог
`C:\mic_theory` и ручная настройка `PYTHONPATH`.

Манифест содержит SHA-256 каждого файла. После намеренного обновления снапшота:

```powershell
py -3 -u tools\mic_theory_snapshot_check.py --write
```

## Ограничение

Ни исторический release, ни SNH-PWM, ни C6-RV-PWM, ни C6-BCR, ни модельная
идентификация не подтверждают MCU, HIL или работу с реальным двигателем. Для силовой части единственным источником допуска остаются
preflight, Saleae/HIL-артефакты и физическая MIC/FOC-матрица `mic_practice`.

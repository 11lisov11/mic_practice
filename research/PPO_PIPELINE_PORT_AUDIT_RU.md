# Аудит переноса FOC+PPO supervisory для AIR56B2

Дата аудита: 27 августа 2026 г.

Источник: `C:\mic_theory`

Назначение переноса: `C:\mic_practice`
Целевой двигатель: IEK AIR56B2, `0,25 кВт`, `220 В Delta`, `1,24 А`,
`cos(phi)=0,78`, `eta=0,68`, `2720 об/мин`, `50 Гц`, `p=1`.

## 1. Краткий вывод

В `C:\mic_theory` имеется работоспособное общее ядро FOC+PPO: модель АД,
идеализированный инвертор, FOC, среда `ai_id_ref`, PPO actor-critic, online
supervisor, сценарное сравнение, поиск `id_ref`-LUT и экспорт LUT в C.

Однако **полного воспроизводимого конвейера для текущего AIR56B2 там нет**:

1. Целевой профиль `config/env_air56b2_iek_025kw_delta.py` существует только в
   незакоммиченном рабочем дереве и настроен на `sim.mode="scalar"`, а не FOC.
2. Пробный запуск `ai_id_ref` с этим профилем падает на первом шаге, потому что
   PPO пытается изменить `id_ref` у `ScalarVfParams`.
3. Все найденные checkpoint'ы с именем `air56` относятся к старому двигателю
   `380 В Y`, `0,70 А`, `cos(phi)=0,68`, `eta=0,75`, `1380 об/мин`, `p=2`.
4. Целевого checkpoint, целевого `id_ref_lut.json`, C-заголовка или результатов
   paired FOC/PPO для AIR56B2 2720 об/мин нет.
5. Обучение в `train_ai_id_ref.py` принудительно выполняется на
   `device="cpu"`; установленная RTX 5070 текущим кодом не используется.
6. Сохранённый `.pth` содержит только `state_dict`. Он не содержит порядка
   признаков, нормировок, паспорта, параметров модели, seed, версии исходников
   и критериев приёмки, поэтому один файл `.pth` не является воспроизводимым
   релизом.

Следствие: переносить можно ядро исходников, но старую политику, старые числа
supervisor и старые результаты переносить как результат для AIR56B2 нельзя.
Для AIR56B2 требуется новый FOC-профиль, обучение с нуля на паспортно
ограниченном ансамбле и новый комплект экспорта.

Аппаратная валидация этим аудитом не заявляется.

## 2. Паспорт и вычисляемые опорные величины

Паспортные данные в `config/env_air56b2_iek_025kw_delta.py` соответствуют
заданному двигателю. Из них однозначно вычисляются:

| Величина | Значение |
|---|---:|
| Синхронная скорость `n_sync=60*f/p` | `3000 об/мин` |
| Номинальное скольжение | `0,09333` (`9,33 %`) |
| Номинальная угловая скорость | `284,84 рад/с` |
| Номинальный момент `P2/omega` | `0,878 Н*м` |
| Ток физической обмотки Delta `I_L/sqrt(3)` | `0,716 А RMS` |
| Phase-neutral величина звёздного эквивалента | `127,02 В RMS` |
| Полная входная мощность | около `472,5 В*А` |
| Активная мощность по `U/I/cos(phi)` | около `368,6 Вт` |
| Активная мощность по `P2/eta` | `367,65 Вт` |
| Суммарные потери по `P2/eta-P2` | `117,65 Вт` |

`Rs`, `Rr`, `Lls`, `Llr`, `Lm`, `J` и `B` паспортом однозначно не задаются.
Функция `estimate_motor_params_from_nameplate()` делит потери в фиксированных
долях `30/40/30 %`, принимает ток намагничивания равным `0,35 I_phase` и задаёт
обе индуктивности рассеяния как `0,05 Гн`. Полученные в текущем профиле
`Rs=7,651 Ом`, `Rr=26,052 Ом`, `Lm=0,9316 Гн`, `J=1,5e-4 кг*м^2` и
`B=4,350e-4 Н*м*с` являются **оценкой для симуляции**, а не паспортными или
идентифицированными параметрами.

Для научного расчёта эти значения допустимы только как центр
`nameplate-constrained ensemble`; обучение и приёмка на одной такой точке
недостаточны.

## 3. Состояние исходного дерева

- ветка: `main`;
- HEAD: `539bbe502751f7389a556b1ae90d18d3e639f6ca`;
- рабочее дерево `C:\mic_theory` грязное;
- `config/env_air56b2_iek_025kw_delta.py` и
  `tests/test_air56b2_iek_profile.py` не отслеживаются Git;
- `config/env.py` и `control/scalar_vf.py` изменены локально, причём целевой
  профиль зависит от добавленного поля `ScalarVfParams.u_phase_nom`;
- `requirements.txt` задаёт только нижние границы версий, lock-файла нет.

Поэтому `git clone` на указанном HEAD не воспроизводит даже текущий профиль
AIR56B2. Перенос необходимо делать белым списком из рабочего дерева, затем
сразу фиксировать хэши и коммит уже в `C:\mic_practice`.

Контрольные SHA-256 текущего рабочего дерева:

| Файл | SHA-256 |
|---|---|
| `config/env_air56b2_iek_025kw_delta.py` | `6638ae287e5d16a98f40a8f6f747a8d55b65695ceef189d1dd311b09e3263d28` |
| `mic_ai/ai/train_ai_id_ref.py` | `8a92da37f6790aecce34bec7f75d67b1166f683084934cb65d5709c93f869272` |
| `mic_ai/ai/agents/ppo_voltage.py` | `4aaaa5b85dbc8d65412631a3ffd35bffc5027ffa3ba9b48c39b125b84d183678` |
| `mic_ai/ai/ai_env.py` | `c3703c10ddd1928c8267a7d7e0e06e3a997981b4f5014f110b607a7b8ab86188` |
| `control/vector_foc.py` | `769e0e2f6be8658e2aa979bbd256e8498f385f7b24af3eec5d7de5e7d4c2b60a` |

## 4. Фактическая цепочка FOC+PPO

Исполняемый путь выглядит так:

1. `config/env*.py` создаёт `EnvConfig` с моделью двигателя, инвертором,
   FOC и сценарием.
2. `mic_ai/core/env.py` загружает конфигурацию и дополнительные `ai_*` поля.
3. `simulation/gym_env.py` создаёт двигатель, инвертор, FOC и сценарий.
4. `mic_ai/ai/ai_env.py` оставляет внутренние контуры FOC и заменяет только
   `i_d_ref` действием PPO.
5. `mic_ai/ai/agents/ppo_voltage.py` реализует PPO actor-critic.
6. `mic_ai/ai/train_ai_id_ref.py` выполняет обучение, пишет per-episode
   checkpoint'ы, `run_config.json` и `training_metrics.json`.
7. `mic_ai/tools/scenario_compare.py` сравнивает FOC и AI по одинаковому
   сценарию.
8. `mic_ai/ai/id_ref_supervisor.py` может поверх actor корректировать действие
   экстремальным поиском по входной/удельной мощности.
9. `mic_ai/tools/id_ref_lut.py` строит таблицу оптимального `id_ref` перебором
   FOC, а `export_id_ref_lut_c.py` переводит её в C-заголовок.

Важное различие: существующий `id_ref_lut.py` строит **FOC search LUT**, а не
дистиллирует PPO. Называть его «PPO LUT» нельзя. Для PPO-LUT нужен отдельный
экспорт среднего действия actor по сетке наблюдений с проверкой паритета.

## 5. Минимальный белый список исходников

Рекомендуемое изолированное место назначения:
`C:\mic_practice\research\mic_ai_foc_ppo\source`. Изоляция нужна, чтобы не
смешать импорты `config`, `control` и `models` с уже существующим срезом
`research/mic_ai_theory/snh_pwm/source`.

### 5.1. Ядро, которое можно переносить

Вместе с `__init__.py` соответствующих каталогов:

- `config/env.py`;
- `control/vector_foc.py`, `control/scalar_vf.py`, `control/v3_ternary.py`,
  `control/hybrid_v3_foc.py`, `control/id_ref_lut.py`;
- `models/induction_motor.py`, `models/inverter_ideal.py`,
  `models/transformations.py`;
- `simulation/gym_env.py`, `simulation/scenarios.py`;
- `mic_ai/core/env.py`;
- `mic_ai/ident/motor_params.py`;
- `mic_ai/analysis/metrics.py`;
- `mic_ai/ai/agents/ppo_voltage.py`;
- `mic_ai/ai/ai_env.py`, `mic_ai/ai/ai_voltage_config.py`,
  `mic_ai/ai/id_ref_supervisor.py`, `mic_ai/ai/scenario_randomization.py`,
  `mic_ai/ai/curiosity.py`, `mic_ai/ai/world_model/__init__.py`;
- `mic_ai/ai/train_ai_id_ref.py`;
- `mic_ai/tools/checkpoint_adaptation.py`,
  `mic_ai/tools/scenario_compare.py`, `mic_ai/tools/plot_style.py`,
  `mic_ai/tools/id_ref_lut.py`, `mic_ai/tools/export_id_ref_lut_c.py`;
- `mic_ai/ai/distill_voltage.py` только как заготовку экспортера;
- `config/ai_voltage_config.json` только после удаления старых
  motor1/motor2-допущений или фиксации, что используются лишь curriculum-поля.

### 5.2. Минимальные переносимые тесты

- `tests/test_motor_model.py`;
- `tests/test_control.py`;
- `tests/test_sim_env.py`;
- `tests/test_ai_env.py`, `tests/test_ai_env_reward_gate.py`;
- `tests/test_ppo_voltage_anchor.py`;
- `tests/test_scenario_compare.py`;
- `tests/test_id_ref_lut.py`, `tests/test_export_id_ref_lut_c.py`;
- `tests/test_distill.py`;
- `tests/test_air56b2_iek_profile.py`, но его нужно расширить FOC/PPO smoke и
  проверками `cos(phi)`, `eta`, момента, скольжения и режима FOC.

### 5.3. Что требует исправления до первого обучения AIR56B2

| Файл/узел | Обязательное исправление |
|---|---|
| Целевой env | Создать отдельный `env_air56b2_iek_025kw_delta_foc.py`; `mode="foc"`, паспорт неизменен, нагрузка и FOC-параметры берутся из ансамбля/тюнинга. |
| `train_ai_id_ref.py` | Заменить жёсткую базу `2*pi*10/p` на явную номинальную/синхронную базу профиля; добавить `--device auto/cpu/cuda`; сохранять bundle metadata. |
| `foc_baseline.py` | Удалить ту же базу `10 Гц`; использовать `env.omega_base` или паспортную скорость. |
| `scenario_compare.py` | Удалить fallback `10 Гц`, запретить несовпадение feature profile и checkpoint manifest. |
| `ai_env.py` | Вместо независимого дрейфа вокруг одной точки подключить train/validation/holdout семейства AIR56B2 из `C:\mic_practice`. |
| FOC | Настроить PI на train-ансамбле и принять на blind holdout до PPO; generic gains `1/100`, `0,5/2,5` не считать готовыми. |
| Loss model | Добавить явно версионированные медные, магнитные, механические и inverter losses; иначе оптимизация `P_in` неполна. |
| Feature profile | Зафиксировать доступный при эксплуатации набор. Не обучать deploy-policy на признаках, которых нет в телеметрии. |
| Checkpoint | Сохранять actor отдельно от critic и рядом manifest с feature order, scales, action mapping, hashes, seed и версиями. |
| LUT | Принудительно создавать `InductionMotorEnv` в FOC mode; отдельно маркировать FOC-search LUT и PPO-distilled LUT. |
| Distillation | Реализовать настоящий teacher/student fit, C inference, нормировку, float/fixed-point parity и тестовые векторы. Текущий файл только создаёт пустого student и выгружает его веса. |

## 6. Файлы, завязанные на старый AIR56 1380 об/мин

Следующее запрещено переносить как данные или настройки текущего AIR56B2:

- `config/env_research_air56_025kw.py`;
- `config/env_air56_025kw.py` (`1450 об/мин`, также не текущий профиль);
- все `outputs/tmp_air56*.py`, импортирующие старый профиль;
- все `outputs/air56*` checkpoint'ы и результаты Step27/Step28;
- `config/checkpoint_registry.json` и `docs/checkpoint_registry.md` для ключа
  `air56`;
- `tools/train_3motors_pipeline.py` и `tools/step27_pipeline.py` без замены
  registry: оба отображают `air56` на старый config;
- `paper/ieee_2026` и `paper/pgups_2026` как доказательства для AIR56B2;
- `docs/physical_config_policy_3motors.*`;
- `tools/air56_unoq_bridge.py` без переработки: в нём жёстко записаны
  `1380 об/мин`, момент старого двигателя и диапазон `id_ref=1,10...1,70 А`;
- готовые `arduino/id_ref_lut_motor*.h`;
- `arduino/air56_unoq_ready` как платоспецифичную реализацию: пакет рассчитан
  на внутренний STM32U585 UNO Q, тогда как в текущем проекте реальный FOC должен
  исполняться на NUCLEO-G431RB по отдельному UART-контракту.

Контрольный старый checkpoint из registry:

```text
outputs/air56_ep002_loadheavy_wspeed2_20260408h/
  results_run/20260408_203735_tmp_air56_ep022_mix04_train_20260322_ai_id_ref/
  eval/actor_ep001.pth
bytes = 151688
sha256 = 5ac195758ba10b1a34e8cd3c868cf5431026d0a925063229ada0776180835692
architecture = 12 -> 128 -> 128 -> 1, actor+critic state_dict
source config = outputs/tmp_air56_ep022_mix04_train_20260322.py
base config = config/env_research_air56_025kw.py
```

Этот файл можно оставить только как исторический артефакт или эксперимент
negative-transfer. Warm start целевой политики из него по умолчанию запрещён.

## 7. Разрыв между обучением и эксплуатацией

Старые 11/12-признаковые политики используют энергетические признаки
`p_in_norm`, `p_el_filt`, `p_shaft_norm`, `eta_norm` и иногда
`eta_episode_norm`. `tools/air56_unoq_bridge.py` формирует только базовые
кинематические/токовые признаки; отсутствующие значения PPO молча получает как
нули. Это несовпадение train/runtime, а не корректный deploy.

Для первого целевого релиза рекомендуется профиль `deploy_v1`:

```text
omega_norm, omega_ref_norm, err_norm,
id_norm, iq_norm, slip_norm, load_torque_norm
```

Даже здесь `slip_norm` зависит от пока неидентифицированных `Rr/Lr`, а
`load_torque_norm` является оценкой. Поэтому нужны два варианта:

- `deploy_v1_7`: семь признаков, обучение с неопределённостью оценок;
- `deploy_v1_5`: без `slip_norm` и `load_torque_norm`, как обязательный robust
  baseline.

Энергетические признаки допустимы в offline-oracle варианте, но не в основной
deploy-policy, пока телеметрия и вычисления на UNO Q не обеспечат их тем же
определением и масштабированием.

## 8. Зависимости

Минимум для FOC+PPO host pipeline:

- Python `3.12`;
- NumPy;
- PyTorch;
- Matplotlib для графиков;
- pytest для regression;
- стандартная библиотека Python.

SciPy, tqdm и pyserial нужны расширенным инструментам/идентификации/транспорту,
но не минимальному обучению в симуляции. Gym необязателен: в
`simulation/gym_env.py` есть fallback.

Проверенная в ходе аудита среда:

```text
Python 3.12.10
numpy 2.5.2
torch 2.11.0+cu128
CUDA runtime 12.8
matplotlib 3.11.1
pytest 9.1.1
```

Для воспроизводимости после переноса нужен точный `requirements-lock.txt` или
`uv.lock`, а также запись версии драйвера, GPU и результата CPU/GPU parity.
Сам факт наличия CUDA не ускоряет текущий training loop, пока agent создаётся
на CPU и plant выполняется последовательным NumPy-кодом.

## 9. План переноса

### P0. Изолировать и зафиксировать источник

1. Создать `research/mic_ai_foc_ppo/source`.
2. Скопировать только белый список из раздела 5, не копировать `outputs`,
   публикационные данные и registry.
3. Сохранить `SOURCE_PORT_MANIFEST.json`: исходный HEAD, dirty-status, SHA-256
   каждого файла, дата, команда копирования.
4. Зафиксировать порт отдельным коммитом до смысловых исправлений.

### P1. Собрать целевой FOC baseline

1. Создать FOC-профиль AIR56B2 из точного паспорта и звёздного эквивалента.
2. Подключить уже созданный в `C:\mic_practice` nameplate-constrained ensemble.
3. Разделить seed на train, validation, blind holdout и OOD.
4. Настроить PI только на train, выбрать на validation, один раз оценить на
   blind holdout.
5. Проверить шаг интегрирования минимум `500/250/100 мкс`.

### P2. Перенести и исправить PPO

1. Ввести именованные feature profiles и строгую проверку размерности/порядка.
2. Добавить `device`; подтвердить CPU/GPU совпадение действий и метрик в
   заданном допуске.
3. Обучать actor с нуля на train-ансамбле, без старого AIR56 checkpoint.
4. Использовать одинаковые сценарии и реализации неопределённости для FOC и
   PPO в парном сравнении.
5. Настраивать supervisor только на validation family; blind holdout не
   использовать для подбора его параметров.

### P3. Экспорт

1. Основной вариант для UNO Q Linux: actor `.pth` плюс строгий manifest.
2. NUCLEO-G431RB оставляет у себя FOC, ограничения, timeout и fallback; от
   UNO Q получает только ограниченную команду `id_ref`.
3. Сформировать FOC-search LUT как независимый fallback.
4. PPO-LUT или TinyStudent выпускать только после teacher/student parity.
5. Добавить golden vectors: входные признаки, ожидаемое действие actor,
   supervisor output и итоговый `id_ref`.

### P4. Приёмка на ПК

Минимум три train seed и не менее 30 парных blind-holdout реализаций. Для
каждого сценария сохранять mean, CI, worst case, число отказов, ток, ошибку
скорости, одинаковую полезную работу и энергию. Отрицательные результаты не
удалять.

## 10. Команды воспроизведения

### 10.1. Проверки, которые выполняются на текущем исходнике

Запускать из `C:\mic_theory`:

```powershell
$py = 'C:\mic_practice\.venv-research-gpu\Scripts\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
& $py -m pytest -q -p no:cacheprovider `
  tests/test_air56b2_iek_profile.py `
  tests/test_ppo_voltage_anchor.py `
  tests/test_ai_env.py tests/test_ai_env_reward_gate.py `
  tests/test_scenario_compare.py tests/test_id_ref_lut.py `
  tests/test_export_id_ref_lut_c.py tests/test_distill.py `
  tests/test_control.py tests/test_motor_model.py tests/test_sim_env.py
```

Результат аудита: `27 passed`. Это проверяет компоненты по отдельности, но не
делает целевой FOC+PPO pipeline готовым.

Минимальный воспроизводитель текущего дефекта:

```powershell
$py = 'C:\mic_practice\.venv-research-gpu\Scripts\python.exe'
& $py -c "from mic_ai.ai.train_ai_id_ref import build_env,build_feature_keys; e=build_env('config/env_air56b2_iek_025kw_delta.py',8,'ai_id_ref',1,6,None,.05,0,2,1,0,1.2,False,False,True,.3,1,None,.5,None,None,.05,0,1,None,None,build_feature_keys(True,False)); print(type(e.base_env.controller).__name__); e.reset(); e.step([0.0])"
```

Фактический результат: controller=`ScalarVfController`, затем
`TypeError: ScalarVfParams.__init__() got an unexpected keyword argument 'id_ref'`.

### 10.2. Команды после выполнения P0-P2

Ниже предполагается существование исправленного
`config/env_air56b2_iek_025kw_delta_foc.py` и нового аргумента `--device`.
Рабочий каталог:
`C:\mic_practice\research\mic_ai_foc_ppo\source`.

FOC smoke до обучения:

```powershell
$py = 'C:\mic_practice\.venv-research-gpu\Scripts\python.exe'
& $py -m mic_ai.tools.scenario_compare `
  --env-config config/env_air56b2_iek_025kw_delta_foc.py `
  --scenarios speed_step,ramp,load_step,start_stop `
  --dt 0.0005 --t-end 2.0 --load-torque 0.87769 `
  --use-total-power --seed 101 `
  --out-dir C:\mic_practice\artifacts\foc_ppo_air56b2\foc_smoke
```

Один воспроизводимый train seed deploy-политики без недоступных энергетических
признаков:

```powershell
& $py -m mic_ai.ai.train_ai_id_ref `
  config/env_air56b2_iek_025kw_delta_foc.py `
  --control-mode ai_id_ref --device cuda `
  --episodes 600 --episode-steps 4000 `
  --scenarios speed_step,ramp,load_step,start_stop `
  --scenario-sample cycle --episode-seeds 101,202,303,404,505 `
  --omega-ref-range 31.4159,284.8377 `
  --load-torque-range 0.0,0.87769 `
  --relative --delta-id-max 0.30 `
  --seed 560225 --eval-interval 20 `
  --eval-scenarios speed_step,ramp,load_step,start_stop `
  --eval-dt 0.0005 --eval-t-end 2.0 --eval-use-total-power `
  --output-dir C:\mic_practice\artifacts\foc_ppo_air56b2\train_seed_560225 `
  --results-root C:\mic_practice\artifacts\foc_ppo_air56b2\runs_seed_560225
```

Здесь диапазон скорости задан в `рад/с`, а не через существующий
`--omega-ref-pu-range`, потому что старый код пересчитывает PU через жёсткую
базу `10 Гц`.

Paired validation одного checkpoint по фиксированным seed:

```powershell
$ckpt = 'C:\mic_practice\artifacts\foc_ppo_air56b2\train_seed_560225\checkpoints\env_air56b2_iek_025kw_delta_foc\best_actor.pth'
foreach ($seed in 101,202,303,404,505) {
  & $py -m mic_ai.tools.scenario_compare `
    --env-config config/env_air56b2_iek_025kw_delta_foc.py `
    --ai-checkpoint $ckpt --ai-control-mode ai_id_ref `
    --ai-id-relative --delta-id-max 0.30 `
    --scenarios speed_step,ramp,load_step,start_stop `
    --dt 0.0005 --t-end 2.0 --use-total-power `
    --error-tol-rel 0.02 --seed $seed `
    --out-dir "C:\mic_practice\artifacts\foc_ppo_air56b2\validation\seed_$seed"
}
```

FOC-search LUT как независимый fallback:

```powershell
& $py -m mic_ai.tools.id_ref_lut `
  --env-config config/env_air56b2_iek_025kw_delta_foc.py `
  --omega-ref-range 0.10,0.906667 --omega-ref-pu --omega-ref-steps 17 `
  --load-range 0.0,0.87769 --load-steps 13 `
  --id-ref-min 0.05 --id-ref-max 0.60 --id-ref-steps 23 `
  --dt 0.0005 --t-end 2.0 --use-total-power `
  --out-dir C:\mic_practice\artifacts\foc_ppo_air56b2\foc_search_lut

& $py -m mic_ai.tools.export_id_ref_lut_c `
  --lut C:\mic_practice\artifacts\foc_ppo_air56b2\foc_search_lut\id_ref_lut.json `
  --out C:\mic_practice\artifacts\foc_ppo_air56b2\foc_search_lut\air56b2_id_ref_lut.h `
  --symbol-prefix air56b2
```

## 11. Состав целевого checkpoint bundle

Каждый принятый seed должен выпускать каталог, а не одиночный `.pth`:

```text
actor_state_dict.pth
actor_manifest.json
feature_profile.json
normalization.json
action_mapping.json
motor_nameplate.json
ensemble_manifest.json
foc_tuning.json
supervisor_config.json
run_config.json
metrics_train.json
metrics_validation.json
metrics_blind_holdout.json
golden_vectors.json
requirements-lock.txt
source_manifest.json
```

`actor_manifest.json` обязан содержать SHA-256 всех файлов, точный порядок
признаков, `action_dim=1`, размеры слоёв, тип activation, seed, device,
версии Python/NumPy/PyTorch/CUDA, hash train/validation/holdout ensemble и
явный флаг `hardware_validated=false`.

## 12. Критерии готовности порта

Порт можно считать воспроизводимым на ПК только если одновременно:

- чистый checkout одной командой создаёт среду и повторяет smoke/train/eval;
- паспорт AIR56B2 нигде не подменён старым AIR56 1380 об/мин;
- целевой env действительно создаёт `FocController`;
- FOC проходит train/validation/blind holdout ensemble до запуска PPO;
- старые checkpoint'ы не используются как целевой warm start;
- feature profile совпадает в training, evaluation и Linux runtime;
- CPU/GPU parity проверен;
- supervisor настроен только на validation, не на blind holdout;
- PPO сравнен с постоянным `id_ref`, FOC-search LUT и offline oracle;
- LUT и actor проходят golden-vector parity;
- результаты содержат CI, worst case и failure count;
- любой выпуск явно содержит `hardware_validated=false` до реальных испытаний.

## 13. Итоговое решение по переносу

**Безопасно переносить:** общее ядро модели/FOC/PPO, supervisor, evaluation и
экспортные утилиты из белого списка, сохраняя их текущие хэши.

**Переносить только после исправления:** целевой env, train/eval speed base,
ensemble randomization, checkpoint format, GPU device, LUT mode и distillation.

**Не переносить:** старые AIR56 checkpoint'ы, registry, параметры supervisor,
графики/таблицы, готовые LUT и UNO-Q/U585 firmware как доказательство или
прошивку для текущего AIR56B2/NUCLEO-G431RB.

Текущий статус: программные строительные блоки есть, но целевой AIR56B2
FOC+PPO supervisory pipeline ещё нужно собрать и переобучить. Hardware
validation отсутствует и остаётся отдельным будущим этапом.

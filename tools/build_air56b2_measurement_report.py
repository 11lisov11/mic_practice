from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


REPO = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = REPO / "artifacts/measurement_adaptation_20260908_v2"
METHOD_NAMES = {"fixed": "Фиксированный ток", "best_probe": "Лучшая проба",
                "analytic_fit": "Аналитическая настройка", "neural_context": "НС: полное окно",
                "neural_single": "НС: исходная проба"}
CONDITION_NAMES = {"clean": "Без шума", "measurement_noise": "Шум измерений",
                   "systematic_power_bias": "Систематическая ошибка",
                   "load_drift": "Дрейф нагрузки", "ood_parameters": "Изменённые параметры"}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory: Path) -> tuple[dict, dict, list[dict]]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for relative, digest in manifest["files"].items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()) or _sha(path) != digest:
            raise ValueError(f"artifact hash mismatch: {relative}")
    for relative, digest in manifest["sources"].items():
        path = (REPO / relative).resolve()
        if not path.is_relative_to(REPO) or _sha(path) != digest:
            raise ValueError(f"source hash mismatch: {relative}; regenerate study")
    study = json.loads((directory / "study.json").read_text(encoding="utf-8"))
    protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
    row_path = directory / study["row_data"]["file"]
    if _sha(row_path) != study["row_data"]["sha256"]:
        raise ValueError("row hash mismatch")
    rows = [json.loads(line) for line in gzip.decompress(row_path.read_bytes()).splitlines()]
    if len(rows) != study["row_count"] or study["hardware_release_ready"] is not False:
        raise ValueError("row count or release contract mismatch")
    keys = [(r["condition"], r["seed"], r["measurement_realization"], r["sample_index"], r["case_index"], r["method"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate experimental records")
    if any(r["stop_requested"] and r["loss_saving_pct"] is not None for r in rows):
        raise ValueError("stopped cases cannot count as energy savings")
    if any(r["selected_feasible"] is False and r["loss_saving_pct"] is not None for r in rows):
        raise ValueError("infeasible actions cannot count as savings")
    source_input = Path(study["input"]["file"])
    if _sha(source_input) != study["input"]["sha256"]:
        raise ValueError("input fidelity bundle changed")
    return study, protocol, rows


def make_plots(study: dict, output: Path) -> list[Path]:
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 12,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "svg.fonttype": "none"})
    output.mkdir(parents=True, exist_ok=True)
    fig, (left, right) = plt.subplots(1, 2, figsize=(13, 5.5), layout="constrained")
    methods = ["best_probe", "analytic_fit", "neural_single", "neural_context"]
    data = [study["summary"]["measurement_noise"][method] for method in methods]
    means = np.asarray([item["mean_loss_saving_pct"] for item in data])
    ci = np.asarray([item["mean_loss_saving_motor_bootstrap_95ci"] for item in data])
    bars = left.barh(np.arange(len(methods)), means, color="white", edgecolor="black",
                     xerr=np.maximum(0, np.stack((means - ci[:, 0], ci[:, 1] - means))),
                     error_kw={"capsize": 3})
    for bar, hatch in zip(bars, ("//", "", "xx", "..")):
        bar.set_hatch(hatch)
    left.set_yticks(np.arange(len(methods)), [METHOD_NAMES[m] for m in methods])
    left.invert_yaxis()
    left.set_xlabel("Снижение расчётных потерь, %")
    left.set_title("а) Одинаковые скорость и нагрузка", fontsize=12, pad=14)
    left.grid(axis="x", alpha=0.25)
    conditions = ["clean", "measurement_noise", "systematic_power_bias", "load_drift", "ood_parameters"]
    paired = [next(item for item in study["paired_comparisons"]
                   if item["condition"] == c and item["second"] == "analytic_fit") for c in conditions]
    delta = np.asarray([item["mean_difference_w"] for item in paired])
    ci = np.asarray([item["motor_cluster_bootstrap_95ci_w"] for item in paired])
    right.errorbar(delta, np.arange(len(conditions)), xerr=np.maximum(0, np.stack((delta-ci[:, 0], ci[:, 1]-delta))),
                   fmt="o", color="black", capsize=4, markersize=5)
    right.axvline(0, color="0.4", linestyle="--", linewidth=1)
    right.set_yticks(np.arange(len(conditions)), [CONDITION_NAMES[c] for c in conditions])
    right.invert_yaxis()
    right.set_xlabel("Потери аналитики минус потери НС, Вт\nПоложительное значение: преимущество НС")
    right.set_title("б) Парное сравнение; 95%-интервалы", fontsize=12, pad=14)
    right.grid(axis="x", alpha=0.25)
    paths = []
    for suffix in ("png", "svg", "pdf"):
        path = output / f"measurement_adaptation_comparison.{suffix}"
        fig.savefig(path, dpi=180, facecolor="white")
        paths.append(path)
    plt.close(fig)
    return paths


def write_report(study: dict, protocol: dict, rows: list[dict], paths: list[Path], output: Path) -> None:
    noise = study["summary"]["measurement_noise"]
    primary = next(x for x in study["paired_comparisons"] if x["condition"] == "measurement_noise" and x["second"] == "analytic_fit")
    ablation = next(x for x in study["paired_comparisons"] if x["condition"] == "measurement_noise" and x["second"] == "neural_single")
    ci = primary["motor_cluster_bootstrap_95ci_w"]
    verdict = ("получила преимущество в выбранном опыте" if ci[0] > 0 else
               "уступила аналитической настройке" if ci[1] < 0 else
               "не показала статистически различимого преимущества")
    table = []
    for method in ("fixed", "best_probe", "analytic_fit", "neural_single", "neural_context"):
        item = noise[method]
        table.append(f"| {METHOD_NAMES[method]} | {item['mean_loss_saving_pct']:.3f} | "
                     f"{item['mean_input_power_saving_pct']:.3f} | {item['median_optimality_gap_pct']:.3f} | "
                     f"{item['worse_than_fixed_rows']} |")
    stress = []
    for name, methods in study["summary"].items():
        item = methods["neural_context"]
        stress.append(f"| {CONDITION_NAMES[name]} | {item['all_rows']} | {item['comparable_rows']} | "
                      f"{item['stop_requested_rows']} | {item['probe_constraint_violation_rows']} | "
                      f"{item['trial_constraint_violation_rows']} | {item['final_constraint_violation_rows']} | "
                      f"{item['worse_than_fixed_rows']} |")
    pair_rows = []
    for item in study["paired_comparisons"]:
        lo, hi = item["motor_cluster_bootstrap_95ci_w"]
        pair_rows.append(f"| {CONDITION_NAMES[item['condition']]} | {METHOD_NAMES[item['second']]} | "
                         f"{item['mean_difference_w']:+.4f} | [{lo:+.4f}; {hi:+.4f}] |")
    repeat_equal = study["gates"]["training_replay_bitwise_identical"]
    clean = [r for r in rows if r["condition"] == "clean" and r["method"] == "neural_context"
             and r["oracle_trust_region_id_a"] is not None]
    lower, upper = protocol["protocol"]["low_id_a"], protocol["protocol"]["high_id_a"]
    boundary_pct = 100.0 * sum(min(abs(r["oracle_trust_region_id_a"] - lower),
                                 abs(r["oracle_trust_region_id_a"] - upper)) < 1e-9 for r in clean) / len(clean)
    img = paths[0].resolve().as_posix()
    report = f"""# AIR56B2: результаты адаптации по измерительному окну

Дата: 08.09.2026. Источник: `artifacts/measurement_adaptation_20260908_v2/study.json`.
Тип результата: квазистационарное моделирование, не стендовые измерения.
Мощность поступает от виртуального ваттметра. Ветвь потерь в стали пока не
согласована с измерительными токами и напряжениями; реальный оценщик мощности
и динамика FOC этим опытом не проверены.

## Главный результат

Нейросеть с наблюдаемым контекстом {verdict}.
При шуме измерений её среднее снижение расчётных потерь относительно общего
фиксированного тока 0,83 А составляет {noise['neural_context']['mean_loss_saving_pct']:.3f}%,
у аналитического метода {noise['analytic_fit']['mean_loss_saving_pct']:.3f}%.
Парная разность потерь «аналитика минус НС» равна {primary['mean_difference_w']:+.4f} Вт,
95%-интервал [{ci[0]:+.4f}; {ci[1]:+.4f}] Вт. Знак плюс означал бы преимущество НС.
Это небольшой эффект в модели; перенос такой точности на физический стенд не доказан.

Дополнительные пробы относительно абляции нейросети дают
{ablation['mean_difference_w']:+.4f} Вт, интервал
[{ablation['motor_cluster_bootstrap_95ci_w'][0]:+.4f}; {ablation['motor_cluster_bootstrap_95ci_w'][1]:+.4f}] Вт.
Сами по себе более богатые входы не обеспечили доказанного практического выигрыша.

## Что реально выполнено

- Семейство AIR56B2 взято из существующего F1/F2/F3-пакета. Новые измеренные
  параметры двигателя не выдумывались; сопротивления, насыщение и тепловые
  константы остаются симуляционными допущениями.
- Разбиение по моделям: {len(protocol['splits']['train'])} train,
  {len(protocol['splits']['validation'])} validation, {len(protocol['splits']['holdout'])} holdout,
  {len(protocol['splits']['ood'])} отдельных моделей для изменённых параметров.
- На модель приходится 24 режима: три скорости, четыре момента на валу,
  два тепловых состояния. Эти режимы общие у train/test; проверка не является
  тестом переноса на невиданные скорости и нагрузки.
- Обучены две архитектуры с {len(protocol['training_seeds'])} начальными seed:
  полное измерительное окно и абляция с током, напряжением и скоростью
  исходной пробы. {study['train_rows']} обучающих и {study['validation_rows']} проверочных окон.
- Каждый обучающий seed проверен на тех же {len(protocol['evaluation_realizations'])} реализациях
  измерительного шума. Их выбор не зависит от порядка перечисления seed.
- Исключения при подготовке обучения: `{study['training_exclusions']}`;
  при подготовке validation: `{study['validation_exclusions']}`. Все запланированные
  тестовые режимы сохранены, включая недопустимые.
- Обучение выполнено на `{study['device']}`, PyTorch `{study['torch_version']}`.
  Битовый повтор обучения с тем же seed: `{repeat_equal}`.
- Сохранено {study['row_count']} записей сравнения пяти методов и пяти сценариев.
  Это не {study['row_count']} независимых двигателей: независимыми кластерами
  для доверительных интервалов служат модели, а seed и режимы остаются внутри них.

## Сравнение при шуме

Во всех строках сравниваются одинаковые скорость и момент на валу.
Потери и входная мощность имеют разные знаменатели. Временные переходы и
затраты энергии на получение проб в эти проценты не входят.

| Метод | Снижение потерь, среднее % | Снижение входной мощности, среднее % | Медианный разрыв с оптимумом, % | Ухудшений |
|---|---:|---:|---:|---:|
{chr(10).join(table)}

Оптимум рассчитан офлайн на том же ограниченном интервале 0,55–1,11 А.
Это не глобальный оптимум по всему диапазону токов. Идеальный регулятор
момента внутри модели предполагается, но не реализуется этой нейросетью.
В {boundary_pct:.2f}% чистых тестовых режимов ограниченный оптимум находится
на границе этого интервала. Аналитический метод достигает границы точно,
а выход sigmoid приближается к ней. Это один из факторов сравнения данной
архитектуры; результат не доказывает бесполезность любых нейросетевых методов.

![Сравнение методов]({img})

## Проверка отказов и ограничений

Таблица относится к нейросети с полным окном. «Сопоставимые» означает общую
выборку, где исходный режим и результаты всех пяти методов допустимы в модели
и ни один метод не запросил STOP. Это условное сравнение потерь на успешно
обслуженных режимах, его нужно читать вместе с частотой отказов.
Остановки и недопустимые действия не засчитываются как экономия. Все отклонённые и недопустимые
опыты сохранены в `rows.jsonl.gz`.

| Сценарий | Все записи | Сопоставимые | STOP | Нарушения в пробах | В проверочной пробе | После решения | Ухудшений |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(stress)}

Сначала диагностический прогон выявил ошибку постоянного ограничения напряжения.
В ревизии v2 оно следует за измеренной DC-шиной; исходный режим, нарушающий
измеренное ограничение, запрашивает STOP. Данные первого прогона сохранены
в `artifacts/measurement_adaptation_20260908` и не подменены улучшенной ревизией.

Сохранившиеся нарушения во время проб показывают предел этого протокола.
Отклонение результата после измерения не защищает саму пробу. Потребуется
динамический ограничитель тока и предварительный выбор допустимого возбуждения.
Ноль нарушений после решения нельзя выдавать за безопасность всей траектории.

## Проверка гипотез

| Сценарий | Соперник НС | Средняя разность потерь, Вт | 95%-интервал, Вт |
|---|---|---:|---|
{chr(10).join(pair_rows)}

Интервалы получены парным bootstrap по моделям двигателя; все повторы одной
модели переносятся в выборку вместе. При каждом повторе пересчитывается
отношение суммы к числу строк, что совпадает с оценкой среднего в таблице.
Это интервалы для исследованного семейства
priors при фиксированных обучающих выборках, а не доверительные границы ошибки
физической модели. Основное сравнение зафиксировано до открытия новых holdout
результатов. Ревизия v2 использует уже просмотренные наборы и является
исследовательской перепроверкой, не независимым подтверждающим испытанием.

## Вывод для дальнейшей разработки

Текущий результат обосновывает простую аналитическую адаптацию как обязательную
базу сравнения. Обучать более крупную сеть только ради уменьшения ошибки на том
же стационарном наборе сейчас недостаточно: разность мала, а систематическая
ошибка измерителя и допустимость проб влияют сильнее.

Следующие содержательные направления: согласованная электрическая модель
с потерями в стали; динамическое планирование проб; проверенный оценщик мощности;
обучаемая остаточная поправка и выбор момента повторной адаптации. Для sensorless
ветки требуется отдельное исследование наблюдателя с AS5600 как эталоном скорости.

Математика, критерии опровержения и первичные источники:
[AIR56B2_MEASUREMENT_ADAPTATION_THEORY_RU.md](AIR56B2_MEASUREMENT_ADAPTATION_THEORY_RU.md).

## Воспроизведение

```powershell
powershell -ExecutionPolicy Bypass -File tools/run_air56b2_measurement_adaptation.ps1
```

Только проверка контрольных сумм:

```powershell
.venv-research-gpu/Scripts/python.exe tools/build_air56b2_measurement_report.py --verify-only
```

Артефакты: шесть checkpoint-файлов, protocol, summary, полные сжатые записи,
manifest SHA-256, рисунок PNG/SVG/PDF. Прошивки плат этим этапом не изменялись.
`hardware_release_ready=false`.
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    study, protocol, rows = verify(args.directory)
    report_manifest_path = args.directory / "report_manifest.json"
    if not args.verify_only:
        paths = make_plots(study, REPO / "output/figures/measurement_adaptation_20260908")
        report_path = REPO / "research/AIR56B2_MEASUREMENT_ADAPTATION_RESULTS_RU.md"
        write_report(study, protocol, rows, paths, report_path)
        dependencies = [report_path, *paths, Path(__file__),
                        REPO / "research/AIR56B2_MEASUREMENT_ADAPTATION_THEORY_RU.md",
                        REPO / "tools/run_air56b2_measurement_adaptation.ps1",
                        args.directory / "manifest.json",
                        REPO / "artifacts/measurement_adaptation_20260908/legacy_loss_audit.json",
                        REPO / "artifacts/measurement_adaptation_20260908/legacy_loss_audit.md"]
        report_manifest_path.write_text(json.dumps(
            {"schema": "air56b2-measurement-report-manifest-v1",
             "files": {p.relative_to(REPO).as_posix(): _sha(p) for p in dependencies}}, indent=2), encoding="utf-8")
    if report_manifest_path.exists():
        for relative, digest in json.loads(report_manifest_path.read_text(encoding="utf-8"))["files"].items():
            if _sha(REPO / relative) != digest:
                raise ValueError(f"report dependency changed: {relative}; regenerate report")
    print(json.dumps({"verified": True, "rows": len(rows), "execution_status": study["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

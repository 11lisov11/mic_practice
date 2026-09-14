"""Generate the dynamic-energy research note and monochrome figure."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT/"artifacts/dynamic_power_adaptation_20260908")
    args = parser.parse_args()
    manifest = json.loads((args.input/"manifest.json").read_text())
    for name, digest in manifest["outputs"].items():
        if hashlib.sha256((args.input/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"stale input {name}")
    for name, digest in manifest["sources"].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"source changed since experiment: {name}")
    result = json.loads((args.input/"study.json").read_text())
    protocol = json.loads((args.input/"protocol.json").read_text())
    rows, pairs = result["rows"], result["pairs"]
    eligible = [p for p in pairs if p["eligible"]]
    fit_rows = [r for r in rows if r["method"] == "fit"]
    reasons = Counter(r["probe_reason"] or r["final_phase"] for r in fit_rows)
    figdir = ROOT/"output/figures/dynamic_power_adaptation_20260908"
    figdir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 13,
                         "mathtext.fontset": "stix", "pdf.fonttype": 42, "svg.fonttype": "none"})
    fig, axes = plt.subplots(3, 2, figsize=(11, 8.6), layout="constrained", sharex=True)
    # Fixed protocol illustration, not the best observed improvement.
    case, speed = protocol["cases"][0]["case"], max(protocol["speeds"])
    for col, disturbed in enumerate((False, True)):
        group = {r["method"]: r for r in rows if r["case"] == case and r["speed_fraction"] == speed
                 and r["disturbance"] == disturbed}
        if set(group) != {"fixed", "fit"}:
            raise ValueError("report requires both full-load scenarios for the first case")
        for method, style, label in [("fixed", "-", "Постоянный поток"), ("fit", "--", "Пробная настройка")]:
            trace = np.array([r[:9] for r in group[method]["trace"]], dtype=float)
            axes[0, col].plot(trace[:, 0], trace[:, 4], style, color="black", lw=1.4, label=label)
            axes[1, col].plot(trace[:, 0], trace[:, 1]-trace[:, 2], style, color="black", lw=1.1)
        a = np.array([r[:9] for r in group["fixed"]["trace"]], dtype=float)
        b = np.array([r[:9] for r in group["fit"]["trace"]], dtype=float)
        if len(a) != len(b) or not np.allclose(a[:, 0], b[:, 0]):
            raise ValueError("illustration traces do not have matched completed times")
        saving = (a[:, 6]-a[:, 7]-a[:, 8])-(b[:, 6]-b[:, 7]-b[:, 8])
        axes[2, col].plot(a[:, 0], saving, color="black", lw=1.5)
        axes[2, col].axhline(0, color=".5", lw=.7)
        axes[0, col].set_title("Ступень нагрузки 25 → 50 %" if disturbed else "Постоянная нагрузка 25 %")
        axes[2, col].set_xlabel("Время, с")
        for ax in axes[:, col]:
            ax.axvline(1.6, color=".55", ls=":", lw=.8)
            if disturbed:
                ax.axvline(2.6, color=".55", ls=":", lw=.8)
            ax.grid(axis="y", color=".85", lw=.5)
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_xlim(0, protocol["duration_s"])
    axes[0, 0].set_ylabel(r"Задание $i_d$, А")
    axes[1, 0].set_ylabel(r"Ошибка скорости, рад/с")
    axes[2, 0].set_ylabel("Снижение потерь энергии, Дж")
    axes[0, 0].legend(loc="best", fontsize=11, frameon=False)
    fig.suptitle(f"AIR56B2: динамическая проверка; n* = {speed:.0%} nном\n"
                 "Положительное снижение потерь означает выигрыш; вся энергия проб учтена", fontsize=14)
    paths = []
    for ext in ("png", "svg", "pdf"):
        path = figdir/f"dynamic_probe_energy.{ext}"
        fig.savefig(path, dpi=180)
        paths.append(path)
    plt.close(fig)
    savings = [p["loss_saving_j"] for p in eligible]
    mean_saving = np.mean(savings) if savings else float("nan")
    lines = ["# AIR56B2: динамическая проверка энергетической адаптации", "",
        "## Статус и границы вывода", "",
        "Это воспроизводимый вычислительный пилот, не испытания двигателя и не подтверждение готовности прошивки. "
        "Проверяется усреднённая модель на клеммах двигателя. Потери инвертора, переключения ключей, аппаратная защита, "
        "Wi-Fi/UART и время исполнения на MCU в этот эксперимент не входят. Энкодер используется; бездатчиковый режим не проверен.", "",
        f"- Прогонов: {len(rows)}; прошли численные критерии: {sum(r['status']=='PASS' for r in rows)}.",
        f"- Независимых исходных F1-образцов: {len(set(r['case'].split('_k')[0] for r in rows))}; "
        "варианты насыщения, скоростей и нагрузок не считаются новыми независимыми двигателями. "
        "В этой серии используется одна реализация измерительного шума для каждой пары, без статистического обобщения на парк двигателей.",
        f"- Допустимых пар для сравнения: {len(eligible)} из {len(pairs)}. Оба прогона должны завершиться, "
        "сохранить допустимые ток и ошибку скорости; различие полезной работы не более 1 %. Нужен завершённый цикл проб, включая откат.",
        f"- Финальное принятие настройки: {sum(r['final_phase']=='committed' for r in fit_rows)} из {len(fit_rows)}.",
        f"- Среднее снижение энергии потерь по допустимым парам за {protocol['duration_s']:g} с: {mean_saving:.4f} Дж. "
        "Отрицательный результат означает увеличение потерь. Это описательное среднее, не доверительный интервал.",
        f"- Максимальная невязка баланса одного шага: {max(r['max_step_balance_error_j'] for r in rows):.3e} Дж.", "",
        "Токовый критерий: максимальная наблюдаемая в расчёте амплитуда вектора тока не более 3,1 А. "
        "Скоростной критерий: средняя абсолютная ошибка на интервале от 1,2 с до конца опыта менее 3 рад/с. "
        "Это не ограничение мгновенного всплеска ошибки; переходы нагрузки включены в это среднее.", "",
        "## Методика", "",
        "Сравниваются одинаковые разгон, нагрузка, модель двигателя и реализация шума. Регулятор получает ток, "
        "реконструированное напряжение и оценку скорости по квантованному энкодеру. Истинные момент нагрузки, "
        "температуры и поток регулятору не передаются. Для всех объектов используются одни холодные параметры первого F1-образца.", "",
        "Исходная F1-модель ограничена округлёнными паспортными данными. Горячие сопротивления и механические потери "
        "взяты из F2-приоров. Новая ветвь Rc влияет на ток, а не добавляется к мощности постфактум. "
        "Насыщение задано отдельной пассивной гипотезой, не параметрами, якобы измеренными по паспорту. "
        "После изменения структуры модели паспортное соответствие всех режимов заново не доказано.", "",
        "Последовательность: исходный поток → пониженный → повышенный → повтор исходного → проверка кандидата. "
        "Учитываются ограничение скорости изменения задания, выдержка, устойчивость мощности и скорости, "
        "дрейф повторной пробы и минимальный выигрыш 2 Вт. Нарушение условий вызывает отказ и возврат к исходному заданию. "
        "Это надзорная логика, не аппаратная защита.", "",
        "Ступень нагрузки в этой серии задаётся на 2,6 с, во время проб. После принятия кандидата "
        "сохраняется проверка корректности наблюдений и электрических пределов, но повторная оптимизация "
        "после позднего изменения нагрузки автоматически не запускается. Для неё нужен отдельный детектор смены режима.", "",
        "Полезная работа и изменение запасённой энергии учитываются отдельно: "
        "Eвх = Aвала + ΔW + Eмедь_с + Eмедь_р + Eсталь + Eтрение. "
        "Поэтому разгон, недоотпущенная работа и изменение магнитной энергии не выдаются за снижение потерь.", "",
        "## Все парные результаты", "",
        "| Объект | Скорость / nном | Ступень нагрузки | Допустима | ΔEвх, Дж | ΔEпотерь, Дж | ΔAвала, Дж | ΔW, Дж |",
        "|---|---:|---|---|---:|---:|---:|---:|"]
    for pair in pairs:
        lines.append(f"| {pair['case']} | {pair['speed_fraction']:.0%} | {'Да' if pair['disturbance'] else 'Нет'} "
                     f"| {'Да' if pair['eligible'] else 'Нет'} | {pair['input_saving_j']:.4f} "
                     f"| {pair['loss_saving_j']:.4f} | {pair['work_delta_j']:.4f} | {pair['stored_delta_j']:.4f} |")
    lines += ["", "ΔE = постоянный поток минус адаптация; ΔAвала и ΔW = адаптация минус постоянный поток.",
        "", "## Исходы проб", ""]
    lines += [f"- `{reason}`: {count}." for reason, count in sorted(reasons.items())]
    lines += ["", "## Проверка численного шага", "",
        "Контрольный случай: первый объект, линейное намагничивание, скорость 70 % номинальной, нагрузка 25 %.",
        "В whole-loop меняются также частота регулятора и физическая постоянная фильтра скорости. "
        "В plant-only период регулятора и датчиков остаётся 100 мкс; напряжение и нагрузка удерживаются между обновлениями, "
        "используются те же отсчёты шума. Это отделяет дискретизацию объекта от изменения контроллера.", "",
        "| Проверка | Шаг объекта, мкс | Шаг регулятора, мкс | ΔEпотерь, Дж | Исход |",
        "|---|---:|---:|---:|---|"]
    refinement_inputs = {}
    refinement_metrics = []
    for name, label in [("dynamic_power_adaptation_20260908", "Основная"),
                         ("dynamic_power_dt50us", "Whole-loop"), ("dynamic_power_dt25us", "Whole-loop"),
                         ("dynamic_power_plant_sub2", "Plant-only"), ("dynamic_power_plant_sub4", "Plant-only"),
                         ("dynamic_power_plant_sub8", "Plant-only")]:
        folder = ROOT/"artifacts"/name
        check_manifest = json.loads((folder/"manifest.json").read_text())
        raw = (folder/"study.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != check_manifest["outputs"]["study.json"]:
            raise ValueError("refinement input hash mismatch")
        if check_manifest["sources"] != manifest["sources"]:
            raise ValueError("refinement and main sources differ")
        check = json.loads(raw)
        pair = next(p for p in check["pairs"] if p["case"] == case and p["speed_fraction"] == speed and not p["disturbance"])
        row = next(r for r in check["rows"] if r["case"] == case and r["speed_fraction"] == speed and not r["disturbance"] and r["method"] == "fit")
        lines.append(f"| {label} | {row['dt_s']*1e6/row.get('plant_substeps', 1):g} | "
                     f"{row['dt_s']*1e6:g} | {pair['loss_saving_j']:.5f} | {row['final_phase']} |")
        refinement_inputs[name] = check_manifest["outputs"]["study.json"]
        refinement_metrics.append({"name": name, "eligible": pair["eligible"], "dt_s": row["dt_s"],
            "loss_saving_j": pair["loss_saving_j"], "peak_current_a": row["peak_current_a"],
            "phase": row["final_phase"], "current_ok": row["checks"]["current_within_3p1a"]})
    same_controller = [r for r in refinement_metrics if r["dt_s"] == protocol["dt_s"]]
    numerical_delta = max(r["loss_saving_j"] for r in same_controller)-min(r["loss_saving_j"] for r in same_controller)
    peak_delta = max(r["peak_current_a"] for r in same_controller)-min(r["peak_current_a"] for r in same_controller)
    numerical_pass = (all(r["eligible"] and r["current_ok"] and r["phase"] == "committed" for r in refinement_metrics)
                      and numerical_delta < .05 and peak_delta < .05)
    lines += ["", f"Контроль сходимости объекта при неизменном контроллере: {'PASS' if numerical_pass else 'FAIL'}. "
        f"Разброс снижения потерь {numerical_delta:.5f} Дж (порог 0,05 Дж); "
        f"разброс пикового тока {peak_delta:.5f} А (порог 0,05 А). "
        "Дополнительно во всех вариантах требуются сохранение допустимости пары, токового критерия и исхода принятия настройки. "
        "Whole-loop показан отдельно: смена регулятора/фильтра не является чистой ошибкой интегрирования объекта.",
        "Основная серия использует шаг объекта 50 мкс при периоде регулятора 100 мкс. "
        "Исходный шаг объекта 100 мкс дал около 7,002 Дж в контрольном опыте, но не выполнил "
        "допуск 0,05 Дж относительно измельчения объекта; поэтому он не оставлен основным результатом."]
    lines += ["", "Отдельный тест сравнивает всю траекторию токов и интегралы потерь с Radau при Rc = 1200 и 4000 Ом "
        "из предварительно намагниченного состояния. Шаг 100 мкс не разрешает произвольный быстрый переход тока стали; "
        "при 0,5 мкс в проверенном тесте ошибка траектории меньше 0,005 А. Сохранение энергии не подменяет эту проверку."]
    lines += ["", "## Что это меняет в гипотезе исследования", "",
        "1. Статический минимум потерь недостаточен. Критерий запуска проб должен учитывать ожидаемую длительность "
        "режима и полную энергию настройки. Проверять нужно условие Eзатрат < ΔP × Tоставшееся, а не только ΔP > 0.",
        "2. Устойчивость наблюдателя важнее малой прибавки эффективности. Токовый наблюдатель избегает чистого "
        "интегрирования ошибки Rs, но сохраняет зависимость от Rr/Lr и ошибки из-за насыщения и тока стали. "
        "Его преимущество не является доказательством model-free управления.",
        "3. Старые нейросетевые веса пока нельзя объявлять пригодными для этой динамики: они обучались на другом "
        "статическом отображении мощности. Следующий набор данных должен содержать полные переходы, время установления, "
        "затраты проб и отказы. Разделять обучение и проверку нужно по двигателям, а не по соседним отсчётам.",
        "4. При сравнении ИИ с аналитическим регулятором нужны одинаковые датчики, токовые ограничения, качество "
        "отработки нагрузки и бюджет проб. Отказы остаются в статистике; итоговое улучшение не обещается заранее.",
        "", "## Воспроизведение", "",
        "`powershell -ExecutionPolicy Bypass -File tools/run_air56b2_dynamic_power.ps1`", "",
        "Данные: `artifacts/dynamic_power_adaptation_20260908/`. Манифест сохраняет хеши исходников, параметров "
        "и результатов. Рисунок: `output/figures/dynamic_power_adaptation_20260908/`. Уравнения и источники: "
        "`research/AIR56B2_ENERGY_CORE_THEORY_RU.md`.", ""]
    report = ROOT/"research/AIR56B2_DYNAMIC_POWER_RESULTS_RU.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    paths.append(report)
    report_manifest = {"input_study_sha256": manifest["outputs"]["study.json"],
        "refinement_inputs": refinement_inputs,
        "numerical_sensitivity": {"passed": numerical_pass, "max_loss_saving_spread_j": numerical_delta,
                                  "max_peak_current_spread_a": peak_delta, "runs": refinement_metrics},
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "outputs": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (args.input/"report_manifest.json").write_text(json.dumps(report_manifest, indent=2), encoding="utf-8")
    print(report)
    if not numerical_pass:
        raise SystemExit("Numerical sensitivity gate failed; report retains results with FAIL")


if __name__ == "__main__":
    main()

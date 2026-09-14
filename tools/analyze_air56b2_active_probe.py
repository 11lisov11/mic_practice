"""Offline matched-trajectory diagnostics; never supplies truth to controllers."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"research/mic_ai_theory/snh_pwm/source"
sys.path.insert(0, str(SOURCE))
from tools.run_air56b2_active_probe import KEYS, METHODS

LABELS = {"ungated":"Прежний\nпоиск", "budget_payback":"Прежний\nбюджет",
    "paired_fixed":"Парные:\nвсё фиксировано", "paired_cost":"Парные:\nизмеренная цена",
    "active_fixed_cost":"Выбор проб:\nфикс. цена", "active_cost":"Выбор проб:\nизмеренная цена"}


def load_study(folder):
    manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["outputs"].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"artifact changed: {folder/name}")
    return json.loads((folder/"study.json").read_text(encoding="utf-8"))


def archive_sources(folder):
    manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    files = {}
    for relative, digest in manifest["sources"].items():
        data = (ROOT/relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"source changed; cannot create faithful archive: {relative}")
        files[relative] = data
    for relative in ("research/AIR56B2_ACTIVE_PROBE_PROTOCOL_RU.md",
                     "tools/analyze_air56b2_active_probe.py", "tools/run_air56b2_active_probe.ps1"):
        files[relative] = (ROOT/relative).read_bytes()
    protocol = json.loads((folder/"protocol.json").read_text(encoding="utf-8"))
    if hashlib.sha256(files["research/AIR56B2_ACTIVE_PROBE_PROTOCOL_RU.md"]).hexdigest() != protocol["preregistered_note_sha256"]:
        raise ValueError("protocol note changed; cannot create faithful archive")
    runtime = dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,
                   matplotlib=matplotlib.__version__,
                   scope="source_and_model_inputs_not_a_bundled_Python_environment")
    files["RUNTIME.json"] = json.dumps(runtime,indent=2).encode()
    with zipfile.ZipFile(folder/"source_snapshot.zip","w",compression=zipfile.ZIP_DEFLATED) as archive:
        for relative,data in sorted(files.items()):
            info = zipfile.ZipInfo(relative,date_time=(1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    return runtime


def trace(row):
    return {key:np.array([r[i] for r in row["trace"]], dtype=object if key == "phase" else float)
            for i, key in enumerate(row["trace_columns"])}


def audit_cycles(study, keys=KEYS):
    bases = {tuple(r[k] for k in keys):r for r in study["rows"] if r["method"] == "fixed"}
    results = []
    for row in study["rows"]:
        if row["supervisor"] is None or "cycles" not in row["supervisor"]:
            continue
        a = trace(row)
        b = trace(bases[tuple(row[k] for k in keys)])
        if not np.array_equal(a["time_s"], b["time_s"]):
            results.append(dict(status="unmatched_grid",case=row["case"],method=row["method"]))
            continue
        t = a["time_s"]
        for cycle in row["supervisor"]["cycles"]:
            center = cycle["probe_point"][0]
            mask = (t >= center-.06) & (t <= center+.06)
            whole = (t > cycle["query_started_s"]) & (t <= cycle["end_s"])
            returning = whole & (t > cycle["return_started_s"])
            if not mask.any() or not whole.any():
                continue
            baseline = b["true_interval_terminal_power_w"]
            actual = a["true_interval_terminal_power_w"]
            difference = np.maximum(0., actual-baseline)
            spacing = np.diff(t, prepend=t[0]-(t[1]-t[0]))
            sampled_cost = float(np.sum(difference[whole]*spacing[whole]))
            sampled_return = float(np.sum(difference[returning]*spacing[returning]))
            actual_gain = float(np.mean(baseline[mask]-actual[mask]))
            estimate_error = cycle["gain_w"]-actual_gain
            results.append(dict(case=row["case"], method=row["method"],
                duration_s=row["duration_s"], speed_fraction=row["speed_fraction"],
                disturbance=row["disturbance"], plant_substeps=row["plant_substeps"],
                query_index=cycle["index"], gain_estimate_w=cycle["gain_w"],
                sampled_counterfactual_gain_w=actual_gain, gain_estimate_error_w=estimate_error,
                outside_heuristic_width=bool(abs(estimate_error) > cycle["error_width_w"]),
                bracket_cost_j=cycle["excess_j"], sampled_counterfactual_cost_j=sampled_cost,
                predicted_cost_j=cycle["predicted_cost_j"],
                cost_underpredicted=sampled_cost > cycle["predicted_cost_j"],
                bracket_return_j=cycle["recovery_excess_j"], sampled_counterfactual_return_j=sampled_return,
                return_duration_s=cycle["return_duration_s"], predicted_return_s=cycle["predicted_return_s"],
                return_time_underpredicted=cycle["return_duration_s"] > cycle["predicted_return_s"]))
    return results


def refinement_summary(study):
    result = []
    for method in METHODS[1:]:
        rows = [r for r in study["rows"] if r["method"] == method]
        pairs = [p for p in study["pairs"] if p["method"] == method]
        if len(rows) != 3 or {r["plant_substeps"] for r in rows} != {2,4,8}:
            raise ValueError("expected exactly one refinement scenario at 2/4/8 substeps")
        values = [p["loss_saving_j"] for p in pairs if p["loss_saving_j"] is not None]
        currents = [r["peak_current_a"] for r in rows]
        outcomes = {(r["probe_reason"], r["probe_complete"], r["supervisor"]["ever_committed"]) for r in rows}
        span = max(values)-min(values) if len(values)==3 else None
        current_span = max(currents)-min(currents)
        result.append(dict(method=method, saving_range_j=span, current_range_a=current_span,
            same_outcome=len(outcomes)==1, all_eligible=all(p["eligible"] for p in pairs),
            passed=bool(span is not None and span<.05 and current_span<.05 and len(outcomes)==1 and all(p["eligible"] for p in pairs))))
    return result


def audit_episodes(study, keys=KEYS):
    bases = {tuple(r[k] for k in keys):r for r in study["rows"] if r["method"] == "fixed"}
    results = []
    for row in study["rows"]:
        s = row["supervisor"]
        if s is None or "episodes" not in s:
            continue
        a, b = trace(row), trace(bases[tuple(row[k] for k in keys)])
        if not np.array_equal(a["time_s"],b["time_s"]):
            results.append(dict(method=row["method"],case=row["case"],status="unmatched_grid"))
            continue
        spacing = np.diff(a["time_s"],prepend=a["time_s"][0]-(a["time_s"][1]-a["time_s"][0]))
        delta = np.maximum(0.,a["true_interval_terminal_power_w"]-b["true_interval_terminal_power_w"])
        records = s["episodes"] + ([s["open_episode"]] if s["open_episode"] else [])
        for episode in records:
            mask = ((a["time_s"] > episode["start_s"])
                    & (a["time_s"] <= episode.get("end_s",a["time_s"][-1])))
            nonholding = mask & (a["phase"] != "committed")
            value = float(np.sum(delta[nonholding]*spacing[nonholding]))
            prediction = episode.get("predicted_cost_j")
            results.append(dict(method=row["method"],case=row["case"],duration_s=row["duration_s"],
                speed_fraction=row["speed_fraction"],disturbance=row["disturbance"],
                kind=episode["kind"],status="closed" if "end_s" in episode else "right_censored",
                interrupted=episode.get("interrupted"),recovery_observed=episode["recovery_window_observed"],
                sampled_nonholding_cost_j=value,predicted_cost_j=prediction,
                underpredicted=bool(value>prediction) if prediction is not None else None,
                missing_measurement_s=episode.get("missing_measurement_s")))
    return results


def figures(folder, study):
    plt.rcParams.update({"font.family":"serif", "font.serif":["Times New Roman", "DejaVu Serif"],
                        "font.size":12, "svg.fonttype":"none"})
    durations = sorted({p["duration_s"] for p in study["pairs"]})
    fig, axes = plt.subplots(1, len(durations), figsize=(7*len(durations),6), layout="constrained", squeeze=False, sharey=True)
    for ax, duration in zip(axes[0], durations):
        for index, method in enumerate(METHODS[1:]):
            pairs = [p for p in study["pairs"] if p["method"]==method and p["duration_s"]==duration]
            offsets = np.linspace(-.2,.2,len(pairs))
            for offset, pair in zip(offsets,pairs):
                if pair["loss_saving_j"] is None:
                    continue
                ax.scatter(index+offset, pair["loss_saving_j"], c="black", s=24,
                           marker="o" if pair["eligible"] else "x")
        ax.set_xticks(range(6), [LABELS[m] for m in METHODS[1:]], rotation=35, ha="right")
        ax.axhline(0,color=".5",lw=.8)
        ax.grid(axis="y",color=".85",lw=.5)
        ax.set_title(f"Горизонт {duration:g} с")
        ax.set_ylabel("Снижение энергии потерь, Дж")
    fig.suptitle("Все сценарии, без удаления отказов\nКруг: пригодная пара; крест: непригодная", fontsize=14)
    for suffix in ("png", "svg"):
        fig.savefig(folder/f"active_all_cases.{suffix}",dpi=180)
    plt.close(fig)
    chosen = {r["method"]:r for r in study["rows"] if r["case"] == "motor0_k0"
              and r["duration_s"] == 6 and r["speed_fraction"] == .7 and not r["disturbance"]
              and r["plant_substeps"] == 2}
    if not chosen:
        return
    fig, axes = plt.subplots(2,1,figsize=(11,7),layout="constrained",sharex=True)
    b = trace(chosen["fixed"])
    lb = b["input_j"]-b["shaft_work_j"]-b["stored_j"]
    for method, style in (("ungated",":"),("paired_cost","--"),("active_cost","-")):
        a = trace(chosen[method])
        axes[0].plot(a["time_s"],a["id_ref_a"],style,color="black",lw=1.4,
                     label=LABELS[method].replace("\n"," "))
        axes[1].plot(a["time_s"],lb-(a["input_j"]-a["shaft_work_j"]-a["stored_j"]),style,color="black",lw=1.4)
    axes[0].set_ylabel("Задание $i_d$, А")
    axes[1].set_ylabel("Накопленная экономия\nэнергии потерь, Дж")
    axes[1].set_xlabel("Время, с")
    axes[0].legend(loc="upper center",bbox_to_anchor=(.5,1.25),ncol=3,frameon=False,fontsize=11)
    for ax in axes:
        ax.set_xlim(1.5,chosen["fixed"]["total_simulation_s"])
        ax.axvline(6.,color=".5",lw=.8)
        ax.grid(color=".85",lw=.5)
    fig.suptitle("Заранее выбранный пример: двигатель 0, без насыщения, 0,7 номинальной скорости",fontsize=13)
    for suffix in ("png","svg"):
        fig.savefig(folder/f"active_trace.{suffix}",dpi=180)
    plt.close(fig)


def write_report(folder, study, audit, refinement, episodes):
    lines = ["# AIR56B2: информационный выбор парных проб", "",
        "Численное исследование с энкодером и усреднённым инвертором. Не стенд и не доказательство новизны.",
        f"Прогонов: {len(study['rows'])}; численные критерии PASS: {sum(r['status']=='PASS' for r in study['rows'])}.",
        "Незавершённые процедуры, отказы и отрицательная экономия не удалены.", "",
        "Ревизия 2: после горизонта управления всем дан общий 1-секундный участок восстановления.",
        "Его затраты включены. Проверяются также конечные потоковые состояния (с точностью общего угла),",
        "скорость и запасённая энергия. Это численная сопоставимость с заданным допуском, не точное равенство.", "",
        "| Горизонт, с | Метод | Пригодно / всего | Общая выборка | Принятий | Среднее снижение потерь, Дж |",
        "|---|---|---:|---:|---:|---:|"]
    for row in study["summary"]:
        value = row["mean_common_loss_saving_j"]
        lines.append(f"| {row['duration_s']:g} | {row['method']} | {row['eligible']}/{row['total']} | {row['common_n']} | {row['commitments']} | {'нет' if value is None else f'{value:.6f}'} |")
    lines += ["", "Общая выборка требует пригодности всех шести адаптивных методов в одном сценарии.",
        "Это условное сравнение после отбора по исходам, не несмещённая оценка на всей популяции.",
        "Все затраты пуска, проб, удержания и возврата включены. Выигрыш по входной энергии не подменяет",
        "снижение потерь: работа вала и запасённая энергия сохранены отдельно в study.json.", "",
        "## Вся сетка: завершённые по времени", "",
        "Средние ниже описательные: отказ или нарушение критериев не превращается в успешный опыт.",
        "Аварийно прерванные временные горизонты не имеют сопоставимой экономии и в среднее не входят.",
        "| Горизонт, с | Метод | Полный горизонт / всего | Среднее, Дж | Несовпавшие конечные состояния |",
        "|---|---|---:|---:|---:|"]
    for row in study["summary"]:
        value = row["mean_full_horizon_loss_saving_j"]
        lines.append(f"| {row['duration_s']:g} | {row['method']} | {row['full_horizon_n']}/{row['total']} | {'нет' if value is None else f'{value:.6f}'} | {row['endpoint_mismatches']} |")
    lines += ["",
        "## Проверка оценщика", "",
        "Эталон ниже использует парный постоянный режим только после расчёта. Он недоступен регулятору.",
        "Диагностика на редкой сетке трассы 5 мс, а не непрерывная или сертифицированная граница.",
        f"Завершённых парных циклов с сопоставимой трассой: {sum('gain_estimate_w' in r for r in audit)}; несопоставимых трасс: {sum(r.get('status')=='unmatched_grid' for r in audit)}; оценка выигрыша вне своей эвристической ширины: {sum(r.get('outside_heuristic_width') is True for r in audit)}.",
        f"Занижений прогнозной цены относительно редкосеточной оценки: {sum(r.get('cost_underpredicted') is True for r in audit)}; занижений времени возврата: {sum(r.get('return_time_underpredicted') is True for r in audit)}.",
        f"Отдельно проверено эпизодов с учётом прерванных/финальных: {len(episodes)}; занижений цены без удержания: {sum(e.get('underpredicted') is True for e in episodes)}; незакрытых: {sum(e['status']=='right_censored' for e in episodes)}.",
        "Эти числа включают повторения сценариев разными методами и не являются независимой статистикой.", "",
        "## Исходы", ""]
    for row in study["summary"]:
        lines.append(f"- {row['duration_s']:g} с, {row['method']}: {row['reasons']}.")
    lines += ["", "## Уточнение шага", ""]
    if refinement is None:
        lines.append("Не выполнено для этого отчёта; численные выводы предварительные.")
    else:
        lines += ["Один заранее выбранный сценарий, шаг объекта 50/25/12,5 мкс; шаг регулятора неизменен.",
            "| Метод | Разброс экономии, Дж | Разброс тока, А | Критерии выполнены |", "|---|---:|---:|---|"]
        for r in refinement:
            value = r["saving_range_j"]
            lines.append(f"| {r['method']} | {'нет' if value is None else f'{value:.6f}'} | {r['current_range_a']:.6g} | {r['passed']} |")
    lines += ["", "## Ограничения", "",
        "Форма гипотез, линейность дрейфа, перенос цены между амплитудами и будущее сохранение режима",
        "не доказаны. Завершение по мощности/скорости не удостоверяет восстановление магнитного состояния.",
        "Два исходных двигателя не дают подтверждающего вывода о популяции. Нейросеть не обучена,",
        "прошивки не менялись, научная новизна не установлена. Ближайшие известные методы разобраны",
        "в research/AIR56B2_ACTIVE_PROBE_PRIOR_ART_RU.md; нельзя выдавать их сочетание за новое решение."]
    (folder/"RESULTS_RU.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--refinement", type=Path)
    args = parser.parse_args()
    study = load_study(args.folder)
    runtime = archive_sources(args.folder)
    audit = audit_cycles(study)
    episodes = audit_episodes(study)
    refinement = refinement_summary(load_study(args.refinement)) if args.refinement else None
    data = dict(scope="offline_sampled_diagnostic_not_controller_input",cycles=audit,episodes=episodes,refinement=refinement)
    (args.folder/"estimator_audit.json").write_text(json.dumps(data,indent=2,allow_nan=False),encoding="utf-8")
    figures(args.folder, study)
    write_report(args.folder, study, audit, refinement, episodes)
    outputs = ["RESULTS_RU.md","estimator_audit.json","active_all_cases.png","active_all_cases.svg","source_snapshot.zip"]
    outputs += [p.name for p in args.folder.glob("active_trace.*")]
    manifest = dict(parent_sha256=hashlib.sha256((args.folder/"manifest.json").read_bytes()).hexdigest(),
        runtime=runtime,
        analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        refinement_manifest_sha256=(hashlib.sha256((args.refinement/"manifest.json").read_bytes()).hexdigest()
                                    if args.refinement else None),
        outputs={name:hashlib.sha256((args.folder/name).read_bytes()).hexdigest() for name in outputs})
    (args.folder/"analysis_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(dict(cycles=len(audit), refinement=refinement)),flush=True)


if __name__ == "__main__":
    main()

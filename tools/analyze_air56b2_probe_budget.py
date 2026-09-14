"""Offline falsification diagnostics and monochrome figures for budget pilot."""
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


def trace(row):
    return {key: np.asarray([r[i] for r in row["trace"]],
                           dtype=object if key == "phase" else float)
            for i, key in enumerate(row["trace_columns"])}


def audit_assumptions(row, base):
    budget = row["budget"]
    if budget is None or budget["anchor_time_s"] is None:
        return None
    a, b = trace(row), trace(base)
    if not np.array_equal(a["time_s"], b["time_s"]):
        return dict(status="unmatched_time_grid")
    cfg = budget["config"]
    t = a["time_s"]
    active = t >= budget["anchor_time_s"]
    baseline_band = (cfg["power_error_bound_w"] + cfg["baseline_drift_w_per_s"]
                     * np.maximum(0., t-budget["anchor_time_s"]))
    deviation = np.abs(b["true_interval_terminal_power_w"] - budget["anchor_power_w"])
    exceedance = np.maximum(0., deviation-baseline_band)
    excess = np.maximum(0., a["true_interval_terminal_power_w"]-b["true_interval_terminal_power_w"])
    result = dict(status="sampled_offline_diagnostic_not_continuous_certificate",
        baseline_band_violations=int(np.count_nonzero(exceedance[active] > 1e-9)),
        maximum_baseline_exceedance_w=float(np.max(exceedance[active], initial=0.)),
        positive_excess_cap_violations=int(np.count_nonzero(excess[active] > cfg["excess_power_cap_w"])),
        maximum_true_positive_excess_w=float(np.max(excess[active], initial=0.)),
        measurement_error_bound_falsified=bool(max(row["max_power_measurement_error_after_1p6s_w"],
                                                   base["max_power_measurement_error_after_1p6s_w"])
                                               > cfg["power_error_bound_w"]))
    accepted = next((e for e in budget["events"] if e["reason"] == "payback_accept"), None)
    if accepted:
        holding = ((t >= accepted["time_s"])
                   & (t <= accepted["time_s"]+accepted["hold_s"]))
        actual_gain = b["true_interval_terminal_power_w"]-a["true_interval_terminal_power_w"]
        lower = accepted["gain_lower_w"]-cfg["gain_deterioration_w_per_s"]*(t-accepted["time_s"])
        result["gain_envelope_violations"] = int(np.count_nonzero(actual_gain[holding]+1e-9 < lower[holding]))
        result["minimum_gain_envelope_slack_w"] = float(np.min(actual_gain[holding]-lower[holding])) if np.any(holding) else None
    return result


def make_figures(out, study):
    plt.rcParams.update({"font.family":"serif", "font.serif":["Times New Roman", "DejaVu Serif"],
                         "font.size":12, "axes.labelsize":13, "svg.fonttype":"none"})
    labels = {"fit":"Исходный поиск", "ungated":"Возврат без ограничений",
              "budget_only":"Только бюджет", "payback_only":"Только окупаемость",
              "budget_payback":"Бюджет + окупаемость"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8), layout="constrained", sharey=True)
    for axis, duration in zip(axes, [3., 6.]):
        for i, method in enumerate(labels):
            rows = [p for p in study["pairs"] if p["duration_s"] == duration and p["method"] == method]
            rows.sort(key=lambda p:(p["case"],p["speed_fraction"],p["disturbance"]))
            jitter = np.linspace(-.19,.19,len(rows))
            for j, row in enumerate(rows):
                axis.scatter(i+jitter[j], row["loss_saving_j"], color="black", s=28,
                             marker="o" if row["eligible"] else "x", linewidths=.8,
                             facecolors="none" if row["eligible"] else "black")
        axis.axhline(0, color="0.4", linewidth=.8)
        axis.set_xticks(range(5), [labels[m] for m in labels], rotation=30, ha="right", rotation_mode="anchor")
        axis.set_title(f"Горизонт {duration:g} с")
        axis.grid(axis="y", color=".85", linewidth=.5)
    axes[0].set_ylabel("Снижение энергии потерь, Дж\n(относительно постоянного потока)")
    fig.suptitle("Все сценарии: круги - пригодные пары; кресты - непригодные\nДва исходных двигателя; точки не являются независимыми повторениями", fontsize=13)
    fig.savefig(out/"budget_all_cases.png", dpi=180)
    fig.savefig(out/"budget_all_cases.svg")
    plt.close(fig)

    chosen = {r["method"]:r for r in study["rows"] if r["case"] == "motor0_k0"
              and r["duration_s"] == 6. and r["speed_fraction"] == .7 and not r["disturbance"]}
    if set(chosen) >= {"fixed", "fit", "ungated", "budget_payback"}:
        fig, axes = plt.subplots(2, 1, figsize=(10, 6.7), layout="constrained", sharex=True)
        b = trace(chosen["fixed"])
        loss_b = b["input_j"]-b["shaft_work_j"]-b["stored_j"]
        for method, style, color in [("fit","--",".5"),("ungated",":","black"),("budget_payback","-","black")]:
            a = trace(chosen[method])
            axes[0].plot(a["time_s"],a["id_ref_a"],style,color=color,label=labels[method],lw=1.5)
            saving = loss_b-(a["input_j"]-a["shaft_work_j"]-a["stored_j"])
            axes[1].plot(a["time_s"],saving,style,color=color,lw=1.5)
        axes[0].set_ylabel("Задание $i_d$, А")
        axes[1].set_ylabel("Накопленная экономия\nэнергии потерь, Дж")
        axes[1].set_xlabel("Время, с")
        axes[0].legend(loc="upper center",bbox_to_anchor=(.5,1.26), ncol=3,frameon=False,fontsize=11)
        for axis in axes:
            axis.grid(color=".85",linewidth=.5)
            axis.set_xlim(1.5,6.)
        axes[1].axhline(0,color=".4",linewidth=.8)
        fig.suptitle("Иллюстративный случай: motor0_k0, 70 % скорости, нагрузка 25 %",fontsize=13)
        fig.savefig(out/"budget_trace.png",dpi=180)
        fig.savefig(out/"budget_trace.svg")
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("study_dir",type=Path)
    parser.add_argument("--refinement",type=Path)
    args = parser.parse_args()
    out = args.study_dir
    manifest = json.loads((out/"manifest.json").read_text(encoding="utf-8"))
    for name,digest in manifest["outputs"].items():
        if hashlib.sha256((out/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"experiment artifact checksum mismatch: {name}")
    study = json.loads((out/"study.json").read_text(encoding="utf-8"))
    bases = {(r["case"],r["duration_s"],r["speed_fraction"],r["disturbance"]):r
             for r in study["rows"] if r["method"] == "fixed"}
    audits = []
    for row in study["rows"]:
        key = (row["case"],row["duration_s"],row["speed_fraction"],row["disturbance"])
        item = audit_assumptions(row,bases[key])
        if item is not None:
            audits.append(dict(case=key[0],duration_s=key[1],speed_fraction=key[2],
                               disturbance=key[3],method=row["method"],**item))
    (out/"assumption_audit.json").write_text(json.dumps(audits,indent=2,allow_nan=False),encoding="utf-8")
    make_figures(out,study)
    lines = ["# Проверка предпосылок и компонентов метода", "",
        "Диагностика выполнена после основной серии. Истинная мощность парного исходного прогона",
        "используется только здесь, не в регуляторе. Проверка на прореженной сетке способна опровергать",
        "предпосылки, но не доказывает их выполнение между сохранёнными отсчётами.", "",
        "| Горизонт, с | Ступень нагрузки | Проверенных адаптивных прогонов | Нарушена полоса исходной мощности | Нарушен предел превышения мощности |",
        "|---|---|---:|---:|---:|"]
    for duration in (3.,6.):
        for disturbance in (False,True):
            group = [a for a in audits if a["duration_s"]==duration and a["disturbance"]==disturbance]
            lines.append(f"| {duration:g} | {'да' if disturbance else 'нет'} | {len(group)} | {sum(a.get('baseline_band_violations',0)>0 for a in group)} | {sum(a.get('positive_excess_cap_violations',0)>0 for a in group)} |")
    lines += ["", "## Попарное отключение ограничений", "",
        "Это дополнительное описательное сравнение на общей пригодной выборке четырёх вариантов с",
        "запланированным возвратом. Исходный fit не включён в эту выборку, поскольку у него другой",
        "протокол завершения. Число исключённых сценариев показано; статистическая значимость не заявляется.", "",
        "| Горизонт, с | Общих сценариев / всего | Бюджет против ungated, Дж | Окупаемость против ungated, Дж | Оба против ungated, Дж |",
        "|---|---:|---:|---:|---:|"]
    for duration in (3.,6.):
        groups = {}
        for pair in study["pairs"]:
            if pair["duration_s"]==duration and pair["method"] != "fit":
                groups.setdefault((pair["case"],pair["speed_fraction"],pair["disturbance"]),{})[pair["method"]]=pair
        common = [g for g in groups.values() if len(g)==4 and all(p["eligible"] for p in g.values())]
        effects = [np.mean([g[m]["loss_saving_j"]-g["ungated"]["loss_saving_j"] for g in common]) if common else None
                   for m in ("budget_only","payback_only","budget_payback")]
        lines.append(f"| {duration:g} | {len(common)}/{len(groups)} | " + " | ".join('нет' if e is None else f'{e:.5f}' for e in effects)+" |")
    lines += ["", "Нарушение априорных границ отменяет их теоретическую гарантию, даже если ток и скорость",
        "прошли численные критерии. Успешный возврат и отказ от настройки сами по себе не доказывают",
        "энергетического преимущества. Фигуры: budget_all_cases.png и budget_trace.png."]
    refinement_digest = None
    if args.refinement is not None:
        refinement_manifest = json.loads((args.refinement/"manifest.json").read_text(encoding="utf-8"))
        for name,digest in refinement_manifest["outputs"].items():
            if hashlib.sha256((args.refinement/name).read_bytes()).hexdigest() != digest:
                raise ValueError("refinement checksum mismatch")
        refinement_digest = hashlib.sha256((args.refinement/"manifest.json").read_bytes()).hexdigest()
        refined = json.loads((args.refinement/"refinement.json").read_text(encoding="utf-8"))
        lines += ["", "## Дополненная проверка шага", "",
            "После основного пилота завершена отдельная проверка motor0_k0, 70 % скорости, без ступени нагрузки.",
            "Период регулятора/датчиков 100 мкс; шаг объекта 50, 25 и 12,5 мкс. Порог разброса энергии 0,05 Дж.",
            "Дополнительно требуются одинаковые исходы и токовый/скоростной критерии. Это один контрольный случай,",
            "не проверка сходимости каждого сценария основной серии.", "",
            "| Метод | Разброс энергии потерь, Дж | Проверка |", "|---|---:|---|"]
        for check in refined["checks"]:
            lines.append(f"| {check['method']} | {check['spread_j']:.6f} | {'PASS' if check['passed'] else 'FAIL'} |")
    (out/"ASSUMPTIONS_RU.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    outputs = [p for p in out.iterdir() if p.name not in (*manifest["outputs"],"manifest.json","analysis_manifest.json") and p.is_file()]
    result = dict(experiment_manifest_sha256=hashlib.sha256((out/"manifest.json").read_bytes()).hexdigest(),
                  analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  refinement_manifest_sha256=refinement_digest,
                  outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs})
    (out/"analysis_manifest.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(dict(audited=len(audits), baseline_band_falsified=sum(a.get("baseline_band_violations",0)>0 for a in audits))))


if __name__ == "__main__":
    main()

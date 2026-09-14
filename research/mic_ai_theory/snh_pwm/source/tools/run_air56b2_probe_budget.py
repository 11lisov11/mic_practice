"""Predeclared pilot and gate ablations; no firmware or live board access."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from control.air56b2_dynamic_probe import DynamicProbeConfig
from control.air56b2_probe_budget import ProbeBudgetConfig, BudgetedDynamicProbeSupervisor
from tools.run_air56b2_dynamic_power import build_cases, run_trial, source_hashes, _json_scalar

METHODS = ("fixed", "fit", "ungated", "budget_only", "payback_only", "budget_payback")
REPO = SOURCE.parents[3]


def run_job(job):
    name, plant, control, method, disturbance, duration, speed = job
    supervisor = None
    if method not in ("fixed", "fit"):
        supervisor = BudgetedDynamicProbeSupervisor(
            DynamicProbeConfig(dt_s=1e-4, start_after_s=1.6),
            ProbeBudgetConfig(hold_until_s=duration),
            budget_gate=method in ("budget_only", "budget_payback"),
            payback_gate=method in ("payback_only", "budget_payback"))
    row = run_trial(plant, control, method="fixed" if method == "fixed" else "fit",
                    duration_s=duration, disturbance=disturbance, speed_fraction=speed,
                    plant_substeps=2, supervisor=supervisor)
    row.update(case=name, method=method, budget=supervisor.summary() if supervisor else None)
    return row


def matched_results(rows):
    groups = {}
    for row in rows:
        key = tuple(row[k] for k in ("case", "duration_s", "speed_fraction", "disturbance",
                                     "noise_seed", "dt_s", "plant_substeps", "observer"))
        group = groups.setdefault(key, {})
        if row["method"] in group:
            raise ValueError("duplicate method within protocol")
        group[row["method"]] = row
    pairs = []
    for key, group in sorted(groups.items()):
        if set(group) != set(METHODS):
            raise ValueError("incomplete method group; cannot publish pilot")
        base = group["fixed"]
        for method in METHODS[1:]:
            row = group[method]
            work_delta = row["energy"]["shaft_work_j"] - base["energy"]["shaft_work_j"]
            complete = all(r["status"] == "PASS" and r["probe_complete"] for r in (base, row))
            eligible = complete and abs(work_delta) <= .01*max(abs(base["energy"]["shaft_work_j"]), 1.)
            pairs.append(dict(case=key[0], duration_s=key[1], speed_fraction=key[2],
                disturbance=key[3], method=method, eligible=bool(eligible),
                completed_and_pass=bool(complete), work_delta_j=work_delta,
                stored_delta_j=row["energy"]["stored_change_j"]-base["energy"]["stored_change_j"],
                input_saving_j=base["energy"]["input_j"]-row["energy"]["input_j"],
                loss_saving_j=base["energy"]["loss_j"]-row["energy"]["loss_j"],
                ever_committed=(row["budget"]["ever_committed"] if row["budget"] else
                                any(e["kind"] == "stage_started" and e["phase"] == "committed"
                                    for e in row["probe_events"])),
                reason=row["probe_reason"] or ("unfinished" if not row["probe_complete"] else "held_candidate"), bounds_not_falsified=(row["budget"]["bounds_valid"]
                    and row["max_power_measurement_error_after_1p6s_w"] <= row["budget"]["config"]["power_error_bound_w"])
                    if row["budget"] else None))
    return pairs


def aggregate(pairs):
    result = []
    for duration in sorted({p["duration_s"] for p in pairs}):
        # Complete-case common subset, not a different subset for every method.
        keys = {(p["case"], p["speed_fraction"], p["disturbance"]) for p in pairs
                if p["duration_s"] == duration}
        common = {k for k in keys if all(p["eligible"] for p in pairs
                  if p["duration_s"] == duration and (p["case"], p["speed_fraction"], p["disturbance"]) == k)}
        for method in METHODS[1:]:
            group = [p for p in pairs if p["duration_s"] == duration and p["method"] == method]
            used = [p for p in group if (p["case"], p["speed_fraction"], p["disturbance"]) in common]
            result.append(dict(duration_s=duration, method=method, total=len(group),
                eligible=sum(p["eligible"] for p in group), common_eligible=len(used),
                committed=sum(p["ever_committed"] for p in group),
                assumptions_not_falsified=sum(p["bounds_not_falsified"] is True for p in group),
                mean_loss_saving_common_j=(sum(p["loss_saving_j"] for p in used)/len(used)) if used else None,
                mean_loss_saving_completed_j=(sum(p["loss_saving_j"] for p in group if p["completed_and_pass"])
                    / sum(p["completed_and_pass"] for p in group)) if any(p["completed_and_pass"] for p in group) else None,
                reasons=dict(Counter(p["reason"] or "held_candidate" for p in group))))
    return result


def render_report(out, study):
    lines = ["# AIR56B2: пилот энергетического бюджета проб", "",
        "Новизна и преимущество не установлены заранее. Это усреднённая модель с энкодером, не стенд.",
        "Предпосылки границ заданы приорами. Даже отсутствие обнаруженного нарушения не доказывает их выполнение.", "",
        f"Прогонов: {len(study['rows'])}; PASS численных критериев: {sum(r['status']=='PASS' for r in study['rows'])}.",
        "Отказы и незавершённые пробы не удалены из study.json. Варианты насыщения не являются независимыми двигателями.", "",
        "| Горизонт, с | Метод | Пригодно / всего | Общая выборка | Принятия | Средняя экономия потерь на общей выборке, Дж |",
        "|---|---|---:|---:|---:|---:|"]
    for row in study["summary"]:
        value = row["mean_loss_saving_common_j"]
        shown = "нет общей выборки" if value is None else f"{value:.5f}"
        lines.append(f"| {row['duration_s']:g} | {row['method']} | {row['eligible']}/{row['total']} | {row['common_eligible']} | {row['committed']} | {shown} |")
    lines += ["", "Общая выборка требует пригодности всех пяти адаптивных вариантов в том же сценарии.",
        "Её отсутствие не исправляется усреднением разных удобных подмножеств. В JSON дополнительно есть среднее",
        "по завершившимся численно допустимым прогонам: это диагностика, а не сопоставимый итог.", "", "## Исходы", ""]
    for row in study["summary"]:
        lines.append(f"- {row['duration_s']:g} с / {row['method']}: {row['reasons']}; предпосылки не опровергнуты наблюдениями: {row['assumptions_not_falsified']}/{row['total']}.")
    lines += ["", "## Границы", "",
        "Граница окупаемости относится к входной энергии, таблица показывает потери. Работа вала и запасённая",
        "энергия сохранены отдельно в pairs. Прогноз будущей нагрузки отсутствует; объявленный срок задания",
        "не гарантирует постоянства режима. Проверка погрешности мощности использует истинную энергию объекта",
        "только для оценки результата, не передаёт её регулятору. Отдельный прогон с уменьшенным шагом для нового",
        "механизма ещё необходим перед окончательными численными выводами. ИИ здесь не обучался."]
    (out/"RESULTS_RU.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", type=int, default=2)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.models < 1 or args.workers < 1:
        parser.error("positive models and workers required")
    if args.out.exists():
        parser.error("choose a new output directory to preserve prior experiments")
    args.out.mkdir(parents=True)
    cases = build_cases(args.models, 92061)
    if args.smoke:
        cases = cases[:1]
    protocol = dict(schema=1, implementation_revision=2, seed=92061, independent_f1_models=args.models if not args.smoke else 1,
        methods=METHODS, budget=asdict(ProbeBudgetConfig()), durations=[3., 6.],
        speeds=[.3, .7], disturbance_times_s=[2.6], noise_seed=730,
        controller_dt_s=1e-4, plant_substeps=2, novelty_established=False,
        hardware_validated=False, neural_policy_trained=False,
        preregistered_note_sha256=hashlib.sha256((REPO/"research/AIR56B2_BUDGET_PROTOCOL_RU.md").read_bytes()).hexdigest(),
        cases=[dict(case=name, plant=asdict(p), controller=asdict(c)) for name,p,c in cases])
    if args.smoke:
        protocol.update(durations=[3.], speeds=[.7])
    (args.out/"protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    hashes = source_hashes()
    jobs = [(name,p,c,m,d,t,s) for name,p,c in cases for t in protocol["durations"]
            for s in protocol["speeds"] for d in ([False] if args.smoke else [False, True]) for m in METHODS]
    rows = []
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(run_job, job) for job in jobs]
        for future in as_completed(pending):
            row = future.result()
            rows.append(row)
            print(len(rows), "/", len(jobs), row["case"], row["duration_s"], row["speed_fraction"],
                  row["disturbance"], row["method"], row["status"], row["probe_reason"], flush=True)
    rows.sort(key=lambda r: (r["case"],r["duration_s"],r["speed_fraction"],r["disturbance"],r["method"]))
    pairs = matched_results(rows)
    study = dict(rows=rows, pairs=pairs, summary=aggregate(pairs), elapsed_s=time.monotonic()-started)
    if source_hashes() != hashes:
        raise RuntimeError("source changed during experiment; not publishing results")
    (args.out/"study.json").write_text(json.dumps(study, indent=2, allow_nan=False, default=_json_scalar), encoding="utf-8")
    render_report(args.out, study)
    manifest = dict(sources=hashes, outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in args.out.iterdir() if p.is_file()})
    (args.out/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(study["summary"], ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()

"""Reproducible offline evidence for finite-horizon excitation experiments."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
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
SOURCE = ROOT / "research/mic_ai_theory/snh_pwm/source"
sys.path.insert(0, str(SOURCE))
from tools.run_air56b2_energy_value import KEYS, METHODS
from tools.run_air56b2_active_probe import endpoint_comparison
from control.air56b2_energy_value_probe import EnergyValueProbeSupervisor
from control.air56b2_active_probe import ActiveProbeConfig
from control.air56b2_dynamic_probe import DynamicProbeConfig

_spec = importlib.util.spec_from_file_location("paired_energy_audit",ROOT/"tools/analyze_air56b2_active_probe.py")
paired_audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paired_audit)
_validation_spec = importlib.util.spec_from_file_location("energy_artifacts",ROOT/"tools/air56b2_energy_value_artifacts.py")
artifacts = importlib.util.module_from_spec(_validation_spec)
_validation_spec.loader.exec_module(artifacts)

NAMES = {"ungated":"Поиск", "guarded_fit":"Поиск\nс контролем",
         "entropy":"Информация", "greedy":"Первая\nlow/high",
         "greedy_high":"Первая\nhigh/low", "greedy_menu":"Первая\nполное меню", "energy_value":"Ценность\nэнергии"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(folder,expected_stage=None):
    return artifacts.load(folder,expected_stage=expected_stage)


def key(row):
    return tuple(row[k] for k in KEYS)


def mean(values):
    return float(np.mean(values)) if values else None


def cluster(case):
    return case.split("_k")[0]


def direct_comparisons(study):
    rows = {(*key(r),r["method"]):r for r in study["rows"]}
    pairs = {(*key(p),p["method"]):p for p in artifacts.canonical_pairs(study)}
    result = []
    for p in study["pairs"]:
        if p["method"] != "energy_value":
            continue
        p = pairs[(*key(p),"energy_value")]
        ev = rows[(*key(p),"energy_value")]
        for method in ("guarded_fit","greedy","greedy_high","greedy_menu","entropy"):
            b = pairs[(*key(p),method)]
            base = rows[(*key(p),method)]
            endpoint = endpoint_comparison(ev,base)
            work = ev["energy"]["shaft_work_j"]-base["energy"]["shaft_work_j"]
            direct_work = abs(work) <= .01*max(abs(base["energy"]["shaft_work_j"]),1.)
            full = p["full_horizon"] and b["full_horizon"]
            result.append(dict(**{k:p[k] for k in KEYS}, comparator=method,
                eligible=bool(p["eligible"] and b["eligible"] and endpoint["matched"] and direct_work),
                full_horizon=bool(full), endpoint=endpoint, work_delta_j=work,
                loss_advantage_j=(base["energy"]["loss_j"]-ev["energy"]["loss_j"] if full else None)))
    return result


def breakdown(study):
    groups = defaultdict(list)
    bases = {key(r):r for r in study["rows"] if r["method"]=="fixed"}
    for p in study["pairs"]:
        groups[(p["method"],cluster(p["case"]),p["duration_s"],
                p["speed_fraction"],p["disturbance"],p["initial_load_fraction"])].append(p)
    result = []
    for (method,motor,h,speed,disturbance,initial),ps in sorted(groups.items()):
        good = [p for p in ps if p["eligible"]]
        full = [p for p in ps if p["full_horizon"]]
        result.append(dict(method=method,motor=motor,duration_s=h,speed_fraction=speed,
            disturbance=disturbance,initial_load_fraction=initial,total=len(ps),eligible=len(good),
            commitments=sum(p["ever_committed"] for p in ps),
            eligible_mean_j=mean([p["loss_saving_j"] for p in good]),
            eligible_mean_loss_reduction_percent=mean([
                100*p["loss_saving_j"]/bases[key(p)]["energy"]["loss_j"] for p in good]),
            full_mean_j=mean([p["loss_saving_j"] for p in full])))
    return result


def refine(study):
    result = []
    canonical = {(*key(p),p["method"]):p for p in artifacts.canonical_pairs(study)}
    for h in sorted({p["duration_s"] for p in study["pairs"]}):
        for method in METHODS[1:]:
            ps = [p for p in study["pairs"] if p["method"]==method and p["duration_s"]==h]
            rs = [r for r in study["rows"] if r["method"]==method and r["duration_s"]==h]
            if len(ps)!=3 or {p["plant_substeps"] for p in ps}!={2,4,8}:
                raise ValueError("refinement must contain exactly 2/4/8 substeps per horizon and method")
            scenario_keys = {tuple(p[k] for k in KEYS if k!="plant_substeps") for p in ps}
            if len(scenario_keys)!=1 or {key(r) for r in rs}!={key(p) for p in ps}:
                raise ValueError("refinement mixes scenarios")
            ps = [dict(p,eligible=p["eligible"] and canonical[(*key(p),method)]["eligible"],
                       full_horizon=p["full_horizon"] and canonical[(*key(p),method)]["full_horizon"],
                       loss_saving_j=canonical[(*key(p),method)]["loss_saving_j"]) for p in ps]
            values = [p["loss_saving_j"] for p in ps if p["full_horizon"]]
            span = max(values)-min(values) if len(values)==3 else None
            current_span = max(r["peak_current_a"] for r in rs)-min(r["peak_current_a"] for r in rs)
            outcomes = {(p["reason"],p["complete"],p["ever_committed"]) for p in ps}
            passed = all(p["eligible"] for p in ps) and span is not None and span < .05 and current_span < .05 and len(outcomes)==1
            result.append(dict(duration_s=h,method=method,passed=passed,loss_span_j=span,
                               current_span_a=current_span,values_j=values,
                               eligible=sum(p["eligible"] for p in ps),same_outcome=len(outcomes)==1))
    return result


def archive(folder,manifest,protocol):
    files = {}
    for name, expected in manifest["sources"].items():
        path = ROOT/name
        if digest(path) != expected:
            raise ValueError(f"source changed: {name}")
        files[name] = path.read_bytes()
    note = ROOT/"research/AIR56B2_ENERGY_VALUE_PROTOCOL_RU.md"
    if digest(note) != protocol["protocol_note_sha256"]:
        raise ValueError("protocol note changed")
    for name in ("research/AIR56B2_ENERGY_VALUE_PROTOCOL_RU.md",
                 "tools/analyze_air56b2_energy_value.py","tools/run_air56b2_energy_value.ps1",
                 "tools/analyze_air56b2_active_probe.py","tools/run_air56b2_accepted_refinement.py",
                 "tools/air56b2_energy_value_artifacts.py",
                 "tools/run_air56b2_light_load.py",
                 "research/AIR56B2_ENERGY_VALUE_LIGHT_LOAD_PROTOCOL_RU.md",
                 "research/AIR56B2_ENERGY_VALUE_METHOD_RU.md",
                 "research/AIR56B2_ENERGY_VALUE_ADDITIONAL_REFINEMENT_RU.md"):
        files[name] = (ROOT/name).read_bytes()
    files["RUNTIME.json"] = json.dumps(dict(python=sys.version,platform=platform.platform(),
        numpy=np.__version__,matplotlib=matplotlib.__version__,environment_bundled=False,
        archive_scope="simulation core, frozen inputs and analysis tools",
        full_repository_bundled=False,full_test_suite_bundled=False),indent=2).encode()
    with zipfile.ZipFile(folder/"source_snapshot.zip","w",zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()):
            z.writestr(name,data)


def figures(study,out):
    plt.rcParams.update({"font.family":"Times New Roman","font.size":14,
                         "mathtext.fontset":"stix", "svg.fonttype":"none",
                         "axes.spines.top":False,"axes.spines.right":False})
    horizons = sorted({p["duration_s"] for p in study["pairs"]})
    fig,axes = plt.subplots(1,len(horizons),figsize=(16,6),squeeze=False,layout="constrained")
    for ax,h in zip(axes[0],horizons):
        ss = [s for s in study["summary"] if s["duration_s"]==h]
        for i,m in enumerate(METHODS[1:]):
            s = next(s for s in ss if s["method"]==m)
            v = s["mean_common_loss_saving_j"]
            if v is not None:
                ax.bar(i,v,facecolor="white",edgecolor="black",hatch="//" if m=="energy_value" else "",width=.65)
            # Dots retain every full-horizon motor-cluster mean, including failures.
            groups = defaultdict(list)
            for p in study["pairs"]:
                if p["duration_s"]==h and p["method"]==m and p["full_horizon"]:
                    groups[cluster(p["case"])].append(p["loss_saving_j"])
            for shift,vs in zip(np.linspace(-.18,.18,len(groups)),groups.values()):
                ax.plot(i+shift,mean(vs),"ko",ms=3)
        ax.axhline(0,color="black",lw=.7)
        ax.set_xticks(range(len(METHODS)-1),[NAMES[m] for m in METHODS[1:]],rotation=55,ha="right",fontsize=11)
        ax.set_title(f"Горизонт {h:g} с + 1 с возврата")
        ax.set_ylabel("Снижение потерь относительно fixed, Дж")
        ax.grid(axis="y",color=".85",lw=.5)
    fig.suptitle("Столбцы: общая пригодная выборка; точки: все полные прогоны, средние по двигателю",fontsize=14)
    for ext in ("png","svg"):
        fig.savefig(out/f"energy_value_comparison.{ext}",dpi=180)
    plt.close(fig)

    # A declared synthetic policy map, separate from held-out motor outcomes.
    horizons_map = np.linspace(3.,15.,49)
    values = []
    for horizon in horizons_map:
        supervisor = EnergyValueProbeSupervisor(DynamicProbeConfig(dt_s=1e-4,start_after_s=1.6),
                                                ActiveProbeConfig(hold_until_s=float(horizon)))
        values.append([supervisor.expected_query_value(i,1.87,{}) for i in range(4)])
    fig,ax = plt.subplots(figsize=(10,5.5),layout="constrained")
    for i,(id_a,style) in enumerate(zip((.65,1.,.74,.915),("-","--","-.",":"))):
        ax.plot(horizons_map,[np.nan if v[i] is None else v[i] for v in values],style,
                color="black",lw=1.6,label=f"$i_d$ = {id_a:g} А")
    ax.axhline(0,color=".5",lw=1.)
    ax.set(xlabel="Заявленный горизонт работы, с",ylabel="Прогноз будущей ценности пробы, Дж",
           title="Синтетическая карта решения при t = 1,87 с, до первого измерения")
    ax.legend(ncol=2)
    ax.grid(color=".85",lw=.5)
    for ext in ("png","svg"):
        fig.savefig(out/f"energy_value_horizon.{ext}",dpi=180)
    plt.close(fig)

    first = sorted({r["case"] for r in study["rows"]})[0]
    rs = [r for r in study["rows"] if r["case"]==first and r["duration_s"]==max(horizons)
          and r["speed_fraction"]==.7 and not r["disturbance"]]
    if not rs:
        return
    base = next(r for r in rs if r["method"]=="fixed")
    cols = base["trace_columns"]
    b = {c:np.array([v[i] for v in base["trace"]],dtype=object if c=="phase" else float) for i,c in enumerate(cols)}
    baseline_loss = b["input_j"]-b["shaft_work_j"]-b["stored_j"]
    fig,axes = plt.subplots(3,1,figsize=(12,9),sharex=True,layout="constrained")
    for method,style in (("fixed","-"),("guarded_fit","--"),("greedy","-."),("energy_value",":")):
        row = next(r for r in rs if r["method"]==method)
        a = {c:np.array([v[i] for v in row["trace"]],dtype=object if c=="phase" else float) for i,c in enumerate(cols)}
        t = a["time_s"]
        axes[0].plot(t,a["id_ref_a"],style,color="black",lw=1.5,label=NAMES.get(method,"Постоянное").replace("\n"," "))
        axes[1].plot(t,a["speed_rad_s"],style,color="black",lw=1.3)
        loss = a["input_j"]-a["shaft_work_j"]-a["stored_j"]
        axes[2].plot(t,np.interp(t,b["time_s"],baseline_loss)-loss,style,color="black",lw=1.3)
    axes[0].legend(ncol=2,fontsize=12)
    for ax,ylabel in zip(axes,("Ток возбуждения, А","Скорость, рад/с","Снижение потерь\nотносительно fixed, Дж")):
        ax.set_ylabel(ylabel)
        ax.grid(color=".85",lw=.5)
    axes[-1].set_xlabel("Время, с")
    fig.suptitle(f"Заранее выбранный пример: {first}, 0,7 скорости, нагрузка 25%")
    for ext in ("png","svg"):
        fig.savefig(out/f"energy_value_trace.{ext}",dpi=180)
    plt.close(fig)


def fmt(x):
    return "нет" if x is None else f"{x:.4f}"


def report(studies,details,out):
    lines = ["# AIR56B2: энергетическая ценность измерений", "",
        "Источник результата: цифровая модель, усреднённый инвертор, энкодер и неизменный FOC.",
        "Нейросеть, бездатчиковое управление и аппаратная безопасность этим опытом не подтверждаются.",
        "Новый критерий исследуется как эвристика; научный приоритет не установлен.", ""]
    for stage,(study,protocol,_) in studies.items():
        if protocol.get("exploratory_extension"):
            lines += ["## Отдельное расширение: нагрузка 10%", "",
                "Гипотеза сформулирована после просмотра промежуточных исходов основной серии,",
                "до расчётов новых seeds 92067/92068; код и пороги не менялись.",
                "Эти результаты не объединяются с первоначальной выборкой и относятся к малой нагрузке.", ""]
        if protocol.get("conditional_selection"):
            lines += ["## Условный выбор дополнительной траектории", "",
                "Случай выбран по факту пригодности и принятия EV: " + protocol.get("selection_rule","не указан"),
                "Это диагностика выбранной ветви, не независимая репликация и не новая выборка для среднего эффекта.", ""]
        lines += [f"## {stage}","",f"Полная матрица: {len(study['rows'])} прогонов; "
                  f"статусы {dict(Counter(r['status'] for r in study['rows']))}.","",
                  "| T, с | Метод | Пригодны / всего | Принятия | Общая выборка n | Средняя экономия, Дж | Все полные, Дж |",
                  "|---|---|---|---|---|---|---|"]
        for s in study["summary"]:
            lines.append(f"| {s['duration_s']:g} | {s['method']} | {s['eligible']}/{s['total']} | "
                         f"{s['commitments']} | {s['common_n']} | {fmt(s['mean_common_loss_saving_j'])} | "
                         f"{fmt(s['mean_full_horizon_loss_saving_j'])} |")
        lines += ["", "Общая выборка условна по исходам всех методов. Все полные прогоны включают",
                  "непригодные случаи и служат диагностикой, не доказательством эквивалентности работы.", ""]
        cycles = details[stage]["cycles"]
        episodes = details[stage]["episodes"]
        lines += [f"Диагностика прогноза: {len(cycles)} парных проб; "
                  f"выходов за эвристическую ширину: {sum(c.get('outside_heuristic_width',False) for c in cycles)}; "
                  f"недооценок цены эпизодов: {sum(e.get('underpredicted') is True for e in episodes)} "
                  f"из {len(episodes)} записей.",""]
        lines += ["| T, с | EV минус конкурент | Прямо сопоставимы / всего | Преимущество EV, Дж |",
                  "|---|---|---|---|"]
        for h in sorted({p["duration_s"] for p in details[stage]["direct"]}):
            for method in ("guarded_fit","greedy","greedy_high","greedy_menu","entropy"):
                ps = [p for p in details[stage]["direct"] if p["duration_s"]==h and p["comparator"]==method]
                good = [p["loss_advantage_j"] for p in ps if p["eligible"]]
                lines.append(f"| {h:g} | {method} | {len(good)}/{len(ps)} | {fmt(mean(good))} |")
        lines.append("")
        if not stage.endswith("refinement"):
            lines += ["### Каждый исходный двигатель: EV", "",
                "| Двигатель | T | Скорость | Скачок | Нач. нагрузка | Пригодны/всего | Экономия, Дж | Потери, % |",
                "|---|---|---|---|---|---|---|---|"]
            for d in details[stage]["breakdown"]:
                if d["method"] != "energy_value":
                    continue
                lines.append(f"| {d['motor']} | {d['duration_s']:g} | {d['speed_fraction']} | "
                    f"{d['disturbance']} | {d['initial_load_fraction']} | {d['eligible']}/{d['total']} | "
                    f"{fmt(d['eligible_mean_j'])} | {fmt(d['eligible_mean_loss_reduction_percent'])} |")
            lines += ["", "Процент относится к потерям двигателя в данном сценарии, не к его КПД в процентных пунктах.", ""]
    for stage in details:
        if not stage.endswith("refinement"):
            continue
        lines += [f"## Уточнение шага: {stage}", "", "| T | Метод | PASS | Разброс экономии, Дж | Пригодны / 3 |",
                  "|---|---|---|---|---|"]
        for r in details[stage]["refinement"]:
            lines.append(f"| {r['duration_s']:g} | {r['method']} | {r['passed']} | {fmt(r['loss_span_j'])} | {r['eligible']}/3 |")
    lines += ["", "## Интерпретация", "",
        "Положительная экономия относительно fixed означает полезную адаптацию в указанных режимах,",
        "но не превосходство над лучшим простым поиском. Для последнего нужны прямые сравнения выше.",
        "В деталях сохранены каждый двигатель, скорость, нагрузка, отказы и неполные/несопоставимые опыты.",
        "Варианты насыщения и режимы одного F1 не являются независимыми двигателями.",
        "Цена прогнозируется эвристически; её 8 Дж не являются доказанным физическим ограничением.",
        "Симуляция оплачивает электрические переходы и общий возврат, но не энергию процессора и задержки расчёта.",
        "Все версии development сохранены; независимые результаты не использованы для изменения кода.", "",
        "Архив source_snapshot.zip содержит вычислительное ядро, входные параметры и анализатор.",
        "Это не полный репозиторий: установленный Python и полный набор тестов в архив не входят.",
        "PowerShell-команда полного воспроизведения рассчитана на рабочий репозиторий с зависимостями."]
    (out/"RESULTS_RU.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("validation",type=Path)
    p.add_argument("--stress",type=Path)
    p.add_argument("--refinement",type=Path)
    p.add_argument("--accepted-refinement",type=Path)
    p.add_argument("--light-load",type=Path)
    p.add_argument("--light-load-refinement",type=Path)
    a = p.parse_args()
    studies = {"validation":load(a.validation,expected_stage="validation")}
    for stage in ("stress","refinement","accepted_refinement","light_load","light_load_refinement"):
        folder = getattr(a,stage,None)
        if folder:
            studies[stage] = load(folder,expected_stage=stage)
    if len({json.dumps(s[2]["sources"],sort_keys=True) for s in studies.values()}) != 1:
        raise ValueError("series have different source revisions")
    if ("accepted_refinement" in studies and studies["accepted_refinement"][1].get("source_study_sha256")
            != digest(a.validation/"study.json")):
        raise ValueError("accepted refinement belongs to another parent study")
    for stage in ("light_load","light_load_refinement"):
        if stage in studies:
            protocol = studies[stage][1]
            if (protocol.get("extension_note_sha256") != digest(ROOT/"research/AIR56B2_ENERGY_VALUE_LIGHT_LOAD_PROTOCOL_RU.md")
                    or protocol.get("runner_sha256") != digest(ROOT/"tools/run_air56b2_light_load.py")):
                raise ValueError("light-load protocol or runner changed")
    details = {}
    for stage,(study,protocol,manifest) in studies.items():
        details[stage] = dict(direct=direct_comparisons(study),breakdown=breakdown(study))
        details[stage].update(cycles=paired_audit.audit_cycles(study,keys=KEYS),
                              episodes=paired_audit.audit_episodes(study,keys=KEYS))
        if stage.endswith("refinement"):
            details[stage]["refinement"] = refine(study)
    out = a.validation
    (out/"analysis.json").write_text(json.dumps(details,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    report(studies,details,out)
    figures(studies["validation"][0],out)
    archive(out,studies["validation"][2],studies["validation"][1])
    names = ["analysis.json","RESULTS_RU.md","source_snapshot.zip"]
    names += [f"energy_value_{kind}.{ext}" for kind in ("comparison","trace","horizon") for ext in ("png","svg") if (out/f"energy_value_{kind}.{ext}").exists()]
    (out/"analysis_manifest.json").write_text(json.dumps({n:digest(out/n) for n in names},indent=2),encoding="utf-8")
    print(out/"RESULTS_RU.md")


if __name__=="__main__":
    main()

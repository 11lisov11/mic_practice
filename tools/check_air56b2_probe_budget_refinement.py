"""Keep controller/sensors fixed; refine only the plant in one named case."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"research/mic_ai_theory/snh_pwm/source"))
from control.air56b2_dynamic_probe import DynamicProbeConfig
from control.air56b2_probe_budget import BudgetedDynamicProbeSupervisor, ProbeBudgetConfig
from tools.run_air56b2_dynamic_power import build_cases, run_trial, source_hashes, _json_scalar


def job(method, substeps):
    name, plant, control = build_cases(2,92061)[0]
    supervisor = None
    if method != "fixed":
        supervisor = BudgetedDynamicProbeSupervisor(
            DynamicProbeConfig(dt_s=.0001,start_after_s=1.6), ProbeBudgetConfig(),
            budget_gate=method=="budget_payback", payback_gate=method in ("payback_only","budget_payback"))
    row = run_trial(plant,control,method="fixed" if method=="fixed" else "fit",
                    duration_s=6.,speed_fraction=.7,plant_substeps=substeps,supervisor=supervisor)
    row.update(method=method, case=name, budget=supervisor.summary() if supervisor else None)
    row.pop("trace")
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--workers",type=int,default=2)
    args = parser.parse_args()
    if args.out.exists() or args.workers < 1:
        parser.error("positive workers and a new output directory required")
    args.out.mkdir(parents=True)
    hashes = source_hashes()
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(job,m,n) for n in (2,4,8)
                   for m in ("fixed","ungated","payback_only","budget_payback")]
        for future in as_completed(pending):
            row = future.result()
            rows.append(row)
            print(row["method"],row["plant_substeps"],row["status"],row["probe_reason"],flush=True)
    checks = []
    for method in ("ungated","payback_only","budget_payback"):
        savings, peaks, outcomes = [], [], []
        valid = True
        for n in (2,4,8):
            base = next(r for r in rows if r["method"]=="fixed" and r["plant_substeps"]==n)
            row = next(r for r in rows if r["method"]==method and r["plant_substeps"]==n)
            savings.append(base["energy"]["loss_j"]-row["energy"]["loss_j"])
            peaks.append(row["peak_current_a"])
            outcomes.append((row["probe_reason"],row["budget"]["ever_committed"]))
            valid &= (all(r["status"]=="PASS" and r["probe_complete"] for r in (base,row))
                      and abs(base["energy"]["shaft_work_j"]-row["energy"]["shaft_work_j"])
                          <=.01*max(abs(base["energy"]["shaft_work_j"]),1.))
        spread = max(savings)-min(savings)
        checks.append(dict(method=method,loss_savings_j=savings,spread_j=spread,
                           peak_current_spread_a=max(peaks)-min(peaks),outcomes=outcomes,
                           passed=bool(valid and spread < .05 and max(peaks)-min(peaks)<.05
                                       and len(set(outcomes))==1)))
    if hashes != source_hashes():
        raise RuntimeError("source changed during refinement")
    result = dict(case="motor0_k0",speed_fraction=.7,disturbance=False,
                  controller_dt_s=.0001,plant_dt_s=[.00005,.000025,.0000125],
                  checks=checks,all_passed=all(c["passed"] for c in checks),rows=rows)
    path = args.out/"refinement.json"
    path.write_text(json.dumps(result,indent=2,allow_nan=False,default=_json_scalar),encoding="utf-8")
    (args.out/"manifest.json").write_text(json.dumps(dict(sources=hashes,
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        outputs={path.name:hashlib.sha256(path.read_bytes()).hexdigest()}),indent=2),encoding="utf-8")
    print(json.dumps(checks),flush=True)
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

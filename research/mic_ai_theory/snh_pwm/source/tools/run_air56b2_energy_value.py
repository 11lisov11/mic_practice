"""Development, prospective validation and stress tests of energy-value probes."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

SOURCE = Path(__file__).resolve().parents[1]
REPO = SOURCE.parents[3]
sys.path.insert(0,str(SOURCE))
from control.air56b2_active_probe import ActiveProbeSupervisor,ActiveProbeConfig
from control.air56b2_dynamic_probe import DynamicProbeConfig
from control.air56b2_probe_budget import BudgetedDynamicProbeSupervisor,ProbeBudgetConfig
from control.air56b2_energy_value_probe import EnergyValueProbeSupervisor,GuardedFixedProbeSupervisor
from tools.run_air56b2_dynamic_power import build_cases,run_trial,source_hashes,_json_scalar
from tools.run_air56b2_active_probe import matched_results,aggregate,KEYS as BASE_KEYS

METHODS = ("fixed","ungated","guarded_fit","entropy","greedy","greedy_high","greedy_menu","energy_value")
KEYS = (*BASE_KEYS,"initial_load_fraction","final_load_fraction","load_step_s")


def run_job(job):
    name,plant,control,method,disturbance,duration,speed,substeps,initial,final,step = job
    cfg = DynamicProbeConfig(dt_s=1e-4,start_after_s=1.6)
    active = ActiveProbeConfig(hold_until_s=duration)
    budget = ProbeBudgetConfig(hold_until_s=duration)
    if method == "fixed":
        supervisor = None
    elif method == "ungated":
        supervisor = BudgetedDynamicProbeSupervisor(cfg,budget,budget_gate=False,payback_gate=False)
    elif method == "guarded_fit":
        supervisor = GuardedFixedProbeSupervisor(cfg,budget)
    elif method == "entropy":
        supervisor = ActiveProbeSupervisor(cfg,active)
    elif method in ("greedy","greedy_high","greedy_menu","energy_value"):
        supervisor = EnergyValueProbeSupervisor(cfg,active,greedy=method!="energy_value",
            query_order=(1,0,3,2) if method=="greedy_high" else (0,1,2,3),
            greedy_full_menu=method=="greedy_menu")
    else:
        raise ValueError("unknown method")
    row = run_trial(plant,control,method="fixed" if supervisor is None else "fit",
        duration_s=duration+1.,disturbance=disturbance,speed_fraction=speed,
        plant_substeps=substeps,supervisor=supervisor,
        initial_load_fraction=initial,final_load_fraction=final,load_step_s=step)
    row.update(case=name,method=method,duration_s=duration,total_simulation_s=duration+1.,
               supervisor=supervisor.summary() if supervisor else None)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--stage",choices=["development","validation","stress","refinement"],required=True)
    parser.add_argument("--workers",type=int,default=12)
    args = parser.parse_args()
    if args.workers < 1 or args.out.exists():
        parser.error("positive worker count and new output directory required")
    args.out.mkdir(parents=True)
    seeds = dict(development=[92062],validation=[92063,92064],stress=[92065,92066],refinement=[92063])[args.stage]
    frozen_control = build_cases(2,92062)[0][2]
    cases = [(f"s{seed}_{name}",p,frozen_control) for seed in seeds for name,p,_ in build_cases(2,seed)]
    profiles = ([(h,False,.25,.5,2.6) for h in (6.,12.)] if args.stage in ("development","refinement") else
                [(h,d,.25,.5,2.6) for h in (3.,6.,12.) for d in (False,True)] if args.stage == "validation" else
                [(6.,True,.25,.5,4.2),(6.,False,.5,.5,2.6)])
    substeps = [2,4,8] if args.stage == "refinement" else [2]
    speeds = [.7] if args.stage == "refinement" else [.3,.7]
    if args.stage == "refinement":
        cases = cases[:1]
    protocol = dict(schema=1,revision=4,stage=args.stage,seeds=seeds,methods=METHODS,
        frozen_controller_seed=92062,profiles=profiles,speeds=speeds,substeps=substeps,
        control_dt_s=1e-4,recovery_tail_s=1.,noise_seed=730,novelty_established=False,
        hardware_validated=False,planning_cost_fractions=[.25,.5,1.],
        cases=[dict(case=n,plant=asdict(p),controller=asdict(c)) for n,p,c in cases],
        protocol_note_sha256=hashlib.sha256((REPO/"research/AIR56B2_ENERGY_VALUE_PROTOCOL_RU.md").read_bytes()).hexdigest())
    (args.out/"protocol.json").write_text(json.dumps(protocol,indent=2),encoding="utf-8")
    hashes = source_hashes()
    (args.out/"source_hashes.json").write_text(json.dumps(hashes,indent=2),encoding="utf-8")
    started = time.monotonic()
    jobs = [(name,p,c,m,d,h,s,n,initial,final,step) for name,p,c in cases
            for h,d,initial,final,step in profiles for s in speeds for n in substeps for m in METHODS]
    rows = []
    errors = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool, (args.out/"trials.jsonl").open("w",encoding="utf-8") as log:
        futures = {pool.submit(run_job,j):j for j in jobs}
        for f in as_completed(futures):
            job = futures[f]
            try:
                row = f.result()
                record = json.dumps(dict(kind="trial",row=row),allow_nan=False,default=_json_scalar)
            except Exception as exc:
                error = dict(case=job[0],method=job[3],duration_s=job[5],speed_fraction=job[6],
                    disturbance=job[4],plant_substeps=job[7],initial_load_fraction=job[8],
                    final_load_fraction=job[9],load_step_s=job[10],error=f"{type(exc).__name__}: {exc}")
                errors.append(error)
                log.write(json.dumps(dict(kind="error",**error))+"\n")
                log.flush()
                print("ERROR",error,flush=True)
                continue
            log.write(record+"\n")
            log.flush()
            rows.append(row)
            print(len(rows),"/",len(jobs),row["case"],row["duration_s"],row["speed_fraction"],
                  row["disturbance"],row["method"],row["status"],row["probe_reason"],flush=True)
    if errors:
        (args.out/"errors.json").write_text(json.dumps(errors,indent=2),encoding="utf-8")
        raise RuntimeError(f"{len(errors)} failed jobs; checkpoints retained, no success published")
    rows.sort(key=lambda r:tuple(r[k] for k in KEYS)+(r["method"],))
    pairs = matched_results(rows,methods=METHODS,keys=KEYS)
    result = dict(rows=rows,pairs=pairs,summary=aggregate(pairs,methods=METHODS,keys=KEYS),
                  elapsed_s=time.monotonic()-started)
    if source_hashes() != hashes:
        raise RuntimeError("source changed during experiment")
    (args.out/"study.json").write_text(json.dumps(result,indent=2,allow_nan=False,default=_json_scalar),encoding="utf-8")
    manifest = dict(sources=hashes,outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in args.out.iterdir() if p.is_file()})
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(result["summary"]),flush=True)


if __name__ == "__main__":
    main()

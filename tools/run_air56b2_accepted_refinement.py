"""Conditional numerical check of the first accepted held-out EV trajectory."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"research/mic_ai_theory/snh_pwm/source"
sys.path.insert(0,str(SOURCE))
from tools.run_air56b2_energy_value import METHODS, KEYS, run_job
from tools.run_air56b2_active_probe import matched_results, aggregate
from tools.run_air56b2_dynamic_power import source_hashes, _json_scalar
from models.induction_motor_energy_core import EnergyCoreParams
from models.induction_motor_alpha_beta import AlphaBetaMotorParams

_spec = importlib.util.spec_from_file_location("accepted_artifacts",ROOT/"tools/air56b2_energy_value_artifacts.py")
artifacts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(artifacts)


def select_case(study):
    candidates = [p for p in study["pairs"] if p["method"]=="energy_value" and p["eligible"]
                  and p["ever_committed"] and p["duration_s"]==12. and not p["disturbance"]]
    return min(candidates,key=lambda p:(p["case"],p["speed_fraction"]),default=None)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("validation",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--workers",type=int,default=6)
    args = p.parse_args()
    if args.out.exists() or args.workers<1:
        p.error("new output directory and positive workers required")
    study,protocol,manifest = artifacts.load(args.validation,expected_stage="validation")
    hashes = source_hashes()
    if hashes != manifest["sources"]:
        raise ValueError("refinement must use exactly the frozen source revision")
    chosen = select_case(study)
    args.out.mkdir(parents=True)
    if chosen is None:
        (args.out/"NO_ACCEPTED_CASE.json").write_text(json.dumps(dict(
            status="no_eligible_committed_12s_steady_case",rule="first_case_then_speed_not_largest_saving")),encoding="utf-8")
        print("No eligible accepted case; no substitute selected")
        return
    case = next(c for c in protocol["cases"] if c["case"]==chosen["case"])
    profile = [12.,False,chosen["initial_load_fraction"],chosen["final_load_fraction"],chosen["load_step_s"]]
    protocol.update(stage="accepted_refinement",cases=[case],profiles=[profile],
        speeds=[chosen["speed_fraction"]],substeps=[2,4,8],
        conditional_selection=True,selection_rule="first_eligible_committed_case_then_speed_not_saving",
        source_study_sha256=hashlib.sha256((args.validation/"study.json").read_bytes()).hexdigest(),
        additional_rule_sha256=hashlib.sha256((ROOT/"research/AIR56B2_ENERGY_VALUE_ADDITIONAL_REFINEMENT_RU.md").read_bytes()).hexdigest())
    (args.out/"protocol.json").write_text(json.dumps(protocol,indent=2),encoding="utf-8")
    (args.out/"source_hashes.json").write_text(json.dumps(hashes,indent=2),encoding="utf-8")
    plant,control = EnergyCoreParams(**case["plant"]),AlphaBetaMotorParams(**case["controller"])
    jobs = [(case["case"],plant,control,m,False,12.,chosen["speed_fraction"],n,*profile[2:])
            for n in (2,4,8) for m in METHODS]
    rows = []
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool, (args.out/"trials.jsonl").open("w",encoding="utf-8") as log:
        for f in as_completed([pool.submit(run_job,j) for j in jobs]):
            row = f.result()
            log.write(json.dumps(dict(kind="trial",row=row),allow_nan=False,default=_json_scalar)+"\n")
            log.flush()
            rows.append(row)
            print(len(rows),"/",len(jobs),row["method"],row["plant_substeps"],row["status"],flush=True)
    if source_hashes()!=hashes:
        raise RuntimeError("sources changed")
    rows.sort(key=lambda r:tuple(r[k] for k in KEYS)+(r["method"],))
    pairs = matched_results(rows,methods=METHODS,keys=KEYS)
    result = dict(rows=rows,pairs=pairs,summary=aggregate(pairs,methods=METHODS,keys=KEYS),elapsed_s=time.monotonic()-started)
    (args.out/"study.json").write_text(json.dumps(result,indent=2,allow_nan=False,default=_json_scalar),encoding="utf-8")
    manifest = dict(sources=hashes,outputs={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                                          for f in args.out.iterdir() if f.is_file()})
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")


if __name__=="__main__":
    main()

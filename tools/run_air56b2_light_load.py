"""Prospective, separately reported low-load experiment with the frozen rev4 policy."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"research/mic_ai_theory/snh_pwm/source"
sys.path.insert(0,str(SOURCE))
from tools.run_air56b2_energy_value import METHODS, KEYS, run_job
from tools.run_air56b2_dynamic_power import build_cases, source_hashes, _json_scalar
from tools.run_air56b2_active_probe import matched_results, aggregate


def design(stage):
    control = build_cases(2,92062)[0][2]
    seeds = [92067,92068] if stage=="light_load" else [92067]
    cases = [(f"s{seed}_{name}",p,control) for seed in seeds for name,p,_ in build_cases(2,seed)]
    if stage=="light_load_refinement":
        cases = cases[:1]
    elif stage!="light_load":
        raise ValueError("unknown stage")
    substeps = [2] if stage=="light_load" else [2,4,8]
    speeds = [.3,.7] if stage=="light_load" else [.7]
    profiles = [[12.,False,.1,.1,2.6]]
    jobs = [(n,p,c,m,d,h,s,k,initial,final,step) for n,p,c in cases
            for h,d,initial,final,step in profiles for s in speeds for k in substeps for m in METHODS]
    note = ROOT/"research/AIR56B2_ENERGY_VALUE_LIGHT_LOAD_PROTOCOL_RU.md"
    protocol = dict(schema=1,revision=4,stage=stage,seeds=seeds,methods=METHODS,
        frozen_controller_seed=92062,profiles=profiles,speeds=speeds,substeps=substeps,
        control_dt_s=1e-4,recovery_tail_s=1.,noise_seed=730,
        exploratory_extension=True,novelty_established=False,hardware_validated=False,
        cases=[dict(case=n,plant=asdict(p),controller=asdict(c)) for n,p,c in cases],
        protocol_note_sha256=hashlib.sha256((ROOT/"research/AIR56B2_ENERGY_VALUE_PROTOCOL_RU.md").read_bytes()).hexdigest(),
        extension_note_sha256=hashlib.sha256(note.read_bytes()).hexdigest(),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return protocol,jobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage",choices=["light_load","light_load_refinement"],required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--workers",type=int,default=12)
    args = parser.parse_args()
    if args.workers<1 or args.out.exists():
        parser.error("positive workers and a new output directory required")
    protocol,jobs = design(args.stage)
    hashes = source_hashes()
    args.out.mkdir(parents=True)
    for name,data in (("protocol.json",protocol),("source_hashes.json",hashes)):
        (args.out/name).write_text(json.dumps(data,indent=2),encoding="utf-8")
    rows,errors = [],[]
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool, (args.out/"trials.jsonl").open("w",encoding="utf-8") as log:
        futures = {pool.submit(run_job,j):j for j in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                row = future.result()
                record = json.dumps(dict(kind="trial",row=row),allow_nan=False,default=_json_scalar)
            except Exception as exc:
                error = dict(case=job[0],method=job[3],speed=job[6],substeps=job[7],error=f"{type(exc).__name__}: {exc}")
                errors.append(error)
                log.write(json.dumps(dict(kind="error",**error))+"\n")
                log.flush()
                continue
            rows.append(row)
            log.write(record+"\n")
            log.flush()
            print(len(rows),"/",len(jobs),row["case"],row["speed_fraction"],row["plant_substeps"],row["method"],row["status"],row["probe_reason"],flush=True)
    if errors:
        (args.out/"errors.json").write_text(json.dumps(errors,indent=2),encoding="utf-8")
        raise RuntimeError("failed jobs; checkpoints retained, no success published")
    if source_hashes()!=hashes or design(args.stage)[0]!=protocol:
        raise RuntimeError("source, runner or protocol changed during experiment")
    rows.sort(key=lambda r:tuple(r[k] for k in KEYS)+(r["method"],))
    pairs = matched_results(rows,methods=METHODS,keys=KEYS)
    study = dict(rows=rows,pairs=pairs,summary=aggregate(pairs,methods=METHODS,keys=KEYS),elapsed_s=time.monotonic()-started)
    (args.out/"study.json").write_text(json.dumps(study,indent=2,allow_nan=False,default=_json_scalar),encoding="utf-8")
    manifest = dict(sources=hashes,outputs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in args.out.iterdir() if f.is_file()})
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(study["summary"]),flush=True)


if __name__=="__main__":
    main()

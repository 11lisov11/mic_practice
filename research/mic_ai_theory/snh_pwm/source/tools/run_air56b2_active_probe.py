"""Paired active-probe pilot and 2x2 ablation; averaged simulation only."""
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
REPO = SOURCE.parents[3]
sys.path.insert(0, str(SOURCE))
from control.air56b2_active_probe import ActiveProbeConfig, ActiveProbeSupervisor
from control.air56b2_dynamic_probe import DynamicProbeConfig
from control.air56b2_probe_budget import BudgetedDynamicProbeSupervisor, ProbeBudgetConfig
from tools.run_air56b2_dynamic_power import build_cases, run_trial, source_hashes, _json_scalar

METHODS = ("fixed", "ungated", "budget_payback", "paired_fixed", "paired_cost",
           "active_fixed_cost", "active_cost")
KEYS = ("case", "duration_s", "speed_fraction", "disturbance", "noise_seed",
        "dt_s", "plant_substeps", "observer", "total_simulation_s")
RECOVERY_TAIL_S = 1.0


def endpoint_comparison(row, base):
    """Offline state check, modulo common electrical angle for a symmetric IM."""
    def aligned(state):
        rotor = complex(state[2], state[3])
        rotation = rotor.conjugate()/abs(rotor) if abs(rotor) > 1e-12 else 1.
        return tuple(complex(state[k], state[k+1])*rotation for k in (0,2,4))
    a, b = row["evaluation_final_state"], base["evaluation_final_state"]
    flux_error = max(abs(x-y) for x,y in zip(aligned(a),aligned(b)))
    speed_error = abs(a[6]-b[6])
    stored_error = abs(row["energy"]["stored_change_j"]-base["energy"]["stored_change_j"])
    return dict(flux_error_wb=flux_error, speed_error_rad_s=speed_error,
                stored_error_j=stored_error,
                matched=bool(flux_error <= .001 and speed_error <= .1 and stored_error <= .01
                             and abs(row["final_id_a"]-.83) < 1e-12))


def run_job(job):
    name, plant, control, method, disturbance, duration, speed, substeps = job
    if method not in METHODS:
        raise ValueError("unknown study method")
    supervisor = None
    cfg = DynamicProbeConfig(dt_s=1e-4, start_after_s=1.6)
    if method in ("ungated", "budget_payback"):
        supervisor = BudgetedDynamicProbeSupervisor(cfg, ProbeBudgetConfig(hold_until_s=duration),
            budget_gate=method == "budget_payback", payback_gate=method == "budget_payback")
    elif method != "fixed":
        supervisor = ActiveProbeSupervisor(cfg, ActiveProbeConfig(hold_until_s=duration),
            active_selection=method.startswith("active"), learned_cost=method in ("paired_cost", "active_cost"))
    row = run_trial(plant, control, method="fixed" if supervisor is None else "fit",
                    duration_s=duration+RECOVERY_TAIL_S, disturbance=disturbance, speed_fraction=speed,
                    plant_substeps=substeps, supervisor=supervisor)
    row.update(case=name, method=method, duration_s=duration,
               total_simulation_s=duration+RECOVERY_TAIL_S,
               supervisor=supervisor.summary() if supervisor else None)
    return row


def matched_results(rows, methods=METHODS, keys=KEYS):
    groups = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        group = groups.setdefault(key, {})
        if row["method"] in group:
            raise ValueError("duplicate method")
        group[row["method"]] = row
    pairs = []
    for key, group in sorted(groups.items()):
        if set(group) != set(methods):
            raise ValueError("incomplete group")
        base = group["fixed"]
        for method in methods[1:]:
            row = group[method]
            work_delta = row["energy"]["shaft_work_j"]-base["energy"]["shaft_work_j"]
            endpoint = endpoint_comparison(row, base)
            full_horizon = all(r["checks"]["complete"] and
                r["completed_steps"] == round(r["total_simulation_s"]/r["dt_s"]) for r in (row,base))
            eligible = (full_horizon and all(r["status"] == "PASS" and r["probe_complete"] for r in (base, row))
                        and endpoint["matched"]
                        and abs(work_delta) <= .01*max(abs(base["energy"]["shaft_work_j"]), 1.))
            pairs.append(dict(zip(keys, key), method=method, eligible=bool(eligible),
                endpoint=endpoint,
                full_horizon=bool(full_horizon),
                work_delta_j=work_delta,
                stored_delta_j=row["energy"]["stored_change_j"]-base["energy"]["stored_change_j"],
                input_saving_j=(base["energy"]["input_j"]-row["energy"]["input_j"] if full_horizon else None),
                loss_saving_j=(base["energy"]["loss_j"]-row["energy"]["loss_j"] if full_horizon else None),
                ever_committed=row["supervisor"]["ever_committed"],
                reason=row["probe_reason"], complete=row["probe_complete"], status=row["status"]))
    return pairs


def aggregate(pairs, methods=METHODS, keys=KEYS):
    summaries = []
    for duration in sorted({p["duration_s"] for p in pairs}):
        group = [p for p in pairs if p["duration_s"] == duration]
        eligible_keys = {tuple(p[k] for k in keys) for p in group}
        eligible_keys -= {tuple(p[k] for k in keys) for p in group if not p["eligible"]}
        for method in methods[1:]:
            subset = [p for p in group if p["method"] == method]
            common = [p for p in subset if tuple(p[k] for k in keys) in eligible_keys]
            full = [p for p in subset if p["full_horizon"]]
            summaries.append(dict(duration_s=duration, method=method, total=len(subset),
                eligible=sum(p["eligible"] for p in subset), common_n=len(common),
                commitments=sum(p["ever_committed"] for p in subset),
                mean_common_loss_saving_j=(sum(p["loss_saving_j"] for p in common)/len(common)
                                           if common else None),
                full_horizon_n=len(full),
                mean_full_horizon_loss_saving_j=(sum(p["loss_saving_j"] for p in full)/len(full) if full else None),
                endpoint_mismatches=sum(not p["endpoint"]["matched"] for p in subset),
                reasons=dict(Counter(p["reason"] or "none" for p in subset))))
    return summaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", type=int, default=2)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--refinement", action="store_true")
    args = parser.parse_args()
    if args.models < 1 or args.workers < 1 or (args.smoke and args.refinement):
        parser.error("positive models/workers; smoke and refinement are exclusive")
    if args.out.exists():
        parser.error("use a new output directory")
    args.out.mkdir(parents=True)
    cases = build_cases(args.models, 92062)
    if args.smoke or args.refinement:
        cases = cases[:1]
    durations = [6.] if args.smoke or args.refinement else [3., 6.]
    speeds = [.7] if args.smoke or args.refinement else [.3, .7]
    disturbances = [False] if args.smoke or args.refinement else [False, True]
    substeps = [2, 4, 8] if args.refinement else [2]
    protocol = dict(schema=1, revision=2, seed=92062, methods=METHODS, durations=durations,
        recovery_tail_s=RECOVERY_TAIL_S,
        speeds=speeds, disturbances=disturbances, plant_substeps=substeps, dt_s=1e-4,
        active_config=asdict(ActiveProbeConfig()), noise_seed=730,
        mode="refinement" if args.refinement else ("smoke" if args.smoke else "pilot"),
        hardware_validated=False, novelty_established=False, neural_policy_trained=False,
        cases=[dict(case=name, plant=asdict(p), controller=asdict(c)) for name,p,c in cases],
        preregistered_note_sha256=hashlib.sha256((REPO/"research/AIR56B2_ACTIVE_PROBE_PROTOCOL_RU.md").read_bytes()).hexdigest())
    (args.out/"protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    hashes = source_hashes()
    started = time.monotonic()
    jobs = [(name,p,c,m,d,t,s,n) for name,p,c in cases for t in durations for s in speeds
            for d in disturbances for n in substeps for m in METHODS]
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(run_job, j) for j in jobs]
        for future in as_completed(pending):
            row = future.result()
            rows.append(row)
            print(len(rows), "/", len(jobs), row["case"], row["duration_s"], row["speed_fraction"],
                  row["disturbance"], row["plant_substeps"], row["method"], row["status"], row["probe_reason"], flush=True)
    rows.sort(key=lambda r: tuple(r[k] for k in KEYS)+(r["method"],))
    pairs = matched_results(rows)
    study = dict(rows=rows, pairs=pairs, summary=aggregate(pairs), elapsed_s=time.monotonic()-started)
    if source_hashes() != hashes:
        raise RuntimeError("source/input changed during run; results not published")
    (args.out/"study.json").write_text(json.dumps(study, indent=2, allow_nan=False, default=_json_scalar), encoding="utf-8")
    manifest = dict(sources=hashes, outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in args.out.iterdir() if p.is_file()})
    (args.out/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(study["summary"]), flush=True)


if __name__ == "__main__":
    main()

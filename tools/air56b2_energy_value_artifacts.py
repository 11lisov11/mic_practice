"""Validate a frozen experiment's files, exact job matrix and derived evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research/mic_ai_theory/snh_pwm/source"))
from tools.run_air56b2_energy_value import METHODS, KEYS
from tools.run_air56b2_active_probe import matched_results, aggregate


def key(row):
    return tuple(row[k] for k in KEYS)+(row["method"],)


def canonical_pairs(study):
    return matched_results(study["rows"],methods=METHODS,keys=KEYS)


def validate(study,protocol):
    if set(protocol["methods"]) != set(METHODS):
        raise ValueError("method set differs from the analysis contract")
    expected_n = (len(protocol["cases"])*len(protocol["profiles"])*len(protocol["speeds"])
                  *len(protocol["substeps"])*len(protocol["methods"]))
    if len(study["rows"]) != expected_n:
        raise ValueError("incomplete preregistered matrix")
    expected = []
    for case in protocol["cases"]:
        for h,disturbance,initial,final,step in protocol["profiles"]:
            for speed in protocol["speeds"]:
                for substeps in protocol["substeps"]:
                    for method in protocol["methods"]:
                        expected.append(key(dict(case=case["case"],duration_s=h,
                            total_simulation_s=h+protocol["recovery_tail_s"],
                            speed_fraction=speed,disturbance=disturbance,
                            initial_load_fraction=initial,final_load_fraction=final,
                            load_step_s=step,noise_seed=protocol["noise_seed"],
                            dt_s=protocol["control_dt_s"],plant_substeps=substeps,
                            observer="current",method=method)))
    actual = [key(row) for row in study["rows"]]
    if len(set(expected))!=expected_n or len(set(actual))!=expected_n or set(actual)!=set(expected):
        raise ValueError("duplicate or unplanned jobs in matrix")
    pairs = canonical_pairs(study)
    computed = {key(p):p for p in pairs}
    stored = {key(p):p for p in study["pairs"]}
    if len(stored)!=len(study["pairs"]) or set(stored)!=set(computed):
        raise ValueError("duplicate or missing pairs")
    required = {"eligible","full_horizon","ever_committed","complete","status","reason","loss_saving_j"}
    for k,p in stored.items():
        if not required <= p.keys() or any(p[f]!=computed[k][f] for f in p if f in computed[k]):
            raise ValueError("stored pairs disagree with source rows")
    if study["summary"] != aggregate(pairs,methods=METHODS,keys=KEYS):
        raise ValueError("stored summary disagrees with source rows")


def load(folder,expected_stage=None):
    manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    for name,expected in manifest["outputs"].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=expected:
            raise ValueError(f"artifact changed: {folder/name}")
    if not {"study.json","protocol.json"} <= manifest["outputs"].keys():
        raise ValueError("critical artifact hashes missing")
    study = json.loads((folder/"study.json").read_text(encoding="utf-8"))
    protocol = json.loads((folder/"protocol.json").read_text(encoding="utf-8"))
    if expected_stage is not None and protocol.get("stage")!=expected_stage:
        raise ValueError("wrong experiment stage")
    validate(study,protocol)
    return study,protocol,manifest

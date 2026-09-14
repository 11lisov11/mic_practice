import copy
import importlib.util
import json
import math
from pathlib import Path

import pytest

from tools.run_air56b2_energy_value import METHODS, KEYS
from tools.run_air56b2_active_probe import matched_results

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location("energy_value_audit",ROOT/"tools/analyze_air56b2_energy_value.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def rows():
    return [dict(case="s92063_motor0_k0",duration_s=6.,total_simulation_s=7.,
        speed_fraction=.7,disturbance=False,noise_seed=730,dt_s=1e-4,plant_substeps=2,
        observer="current",initial_load_fraction=.25,final_load_fraction=.5,load_step_s=2.6,
        method=m,status="PASS",probe_complete=True,probe_reason="scheduled_return",
        checks=dict(complete=True),completed_steps=70000,final_id_a=.83,peak_current_a=2.,
        evaluation_final_state=[.1,0.,.09,0.,.08,0.,100.],
        supervisor=dict(ever_committed=True),
        energy=dict(shaft_work_j=100.,stored_change_j=2.,input_j=150.,loss_j=48.)) for m in METHODS]


def study(rs):
    return dict(rows=rs,pairs=matched_results(rs,methods=METHODS,keys=KEYS))


def test_direct_comparison_checks_nontransitive_endpoint_tolerance():
    rs = rows()
    next(r for r in rs if r["method"]=="energy_value")["evaluation_final_state"][-1] += .09
    next(r for r in rs if r["method"]=="greedy")["evaluation_final_state"][-1] -= .09
    data = study(rs)
    assert all(p["eligible"] for p in data["pairs"])
    direct = next(p for p in audit.direct_comparisons(data) if p["comparator"]=="greedy")
    assert not direct["eligible"]


def test_direct_sign_and_incomplete_experiment_are_preserved():
    rs = rows()
    ev = rs[-1]
    ev["energy"]["loss_j"] = 45.
    direct = audit.direct_comparisons(study(rs))
    assert all(p["loss_advantage_j"]==3. for p in direct)
    ev.update(checks=dict(complete=False),completed_steps=10)
    assert all(p["loss_advantage_j"] is None and not p["eligible"]
               for p in audit.direct_comparisons(study(rs)))


def test_refinement_retains_endpoint_failure():
    rs = []
    for n in (2,4,8):
        block = rows()
        for r in block:
            r["plant_substeps"] = n
        rs.extend(block)
    rs[-1]["evaluation_final_state"][-1] += .11
    result = audit.refine(study(rs))
    ev = next(r for r in result if r["method"]=="energy_value")
    assert ev["loss_span_j"]==0 and not ev["passed"] and ev["eligible"]==2


def test_refinement_requires_all_substeps():
    with pytest.raises(ValueError,match="2/4/8"):
        audit.refine(study(rows()))


def test_saturation_variants_are_one_motor_cluster():
    rs = rows()
    second = copy.deepcopy(rs)
    for r in second:
        r["case"] = "s92063_motor0_k0.4"
    detail = audit.breakdown(study(rs+second))
    assert len(detail)==len(METHODS)-1
    assert all(d["total"]==2 and d["motor"]=="s92063_motor0" for d in detail)


def test_altered_artifact_refused(tmp_path):
    (tmp_path/"study.json").write_text("{}")
    (tmp_path/"manifest.json").write_text(json.dumps(dict(outputs={"study.json":"bad"})))
    with pytest.raises(ValueError,match="artifact changed"):
        audit.load(tmp_path)


def test_missing_preregistered_jobs_refused(tmp_path):
    (tmp_path/"study.json").write_text(json.dumps(dict(rows=rows()[:-1])))
    protocol = dict(cases=[1],profiles=[1],speeds=[.7],substeps=[2],methods=METHODS)
    (tmp_path/"protocol.json").write_text(json.dumps(protocol))
    (tmp_path/"manifest.json").write_text(json.dumps(dict(outputs={
        name:audit.digest(tmp_path/name) for name in ("study.json","protocol.json")})))
    with pytest.raises(ValueError,match="incomplete preregistered"):
        audit.load(tmp_path)


@pytest.mark.parametrize("field,bad",[
    ("initial_load_fraction",-.01),("initial_load_fraction",1.01),
    ("final_load_fraction",-.01),("final_load_fraction",1.01),
    ("load_step_s",-1.),("load_step_s",math.inf),
    ("initial_load_fraction",math.nan),("final_load_fraction",math.inf),
])
def test_invalid_load_profile_rejected_before_plant_construction(field,bad):
    from tools.run_air56b2_dynamic_power import run_trial
    with pytest.raises(ValueError,match="load fractions"):
        run_trial(None,None,method="fixed",**{field:bad})

import copy

import pytest

from tools.run_air56b2_active_probe import METHODS, matched_results, aggregate, endpoint_comparison


def rows():
    return [dict(case="motor0_k0", duration_s=6., speed_fraction=.7, disturbance=False,
        noise_seed=730, dt_s=1e-4, plant_substeps=2, observer="current", method=m,
        status="PASS", probe_complete=True, probe_reason=None,
        checks=dict(complete=True),completed_steps=70000,
        total_simulation_s=7., final_id_a=.83,
        evaluation_final_state=[.1,0.,.09,0.,.08,0.,100.],
        supervisor=dict(ever_committed=m == "active_cost"),
        energy=dict(shaft_work_j=100., stored_change_j=2., input_j=150., loss_j=48.))
        for m in METHODS]


def test_all_methods_required_and_duplicates_rejected():
    with pytest.raises(ValueError, match="incomplete"):
        matched_results(rows()[:-1])
    with pytest.raises(ValueError, match="duplicate"):
        matched_results(rows()+[rows()[0]])


def test_work_and_stored_energy_not_mistaken_for_loss_saving():
    data = rows()
    data[-1]["energy"].update(input_j=148., stored_change_j=0.)
    pair = matched_results(data)[-1]
    assert pair["input_saving_j"] == 2
    assert pair["stored_delta_j"] == -2
    assert pair["loss_saving_j"] == 0


def test_one_failed_method_excludes_case_for_every_method_but_keeps_records():
    data = rows()
    data[-1]["probe_complete"] = False
    pairs = matched_results(data)
    assert len(pairs) == 6
    assert not pairs[-1]["eligible"]
    assert all(s["common_n"] == 0 and s["mean_common_loss_saving_j"] is None
               for s in aggregate(pairs))


def test_changed_protocol_not_paired():
    data = rows()
    data[-1]["noise_seed"] += 1
    with pytest.raises(ValueError, match="incomplete"):
        matched_results(data)


def test_common_comparison_does_not_mix_substeps_or_cases():
    data = rows()
    other = copy.deepcopy(data)
    for row in other:
        row["plant_substeps"] = 4
    other[-1]["status"] = "FAIL"
    summaries = aggregate(matched_results(data+other))
    assert all(s["common_n"] == 1 and s["total"] == 2 for s in summaries)


def test_endpoint_compares_relative_flux_state_not_arbitrary_electrical_angle():
    a, b = rows()[:2]
    a["evaluation_final_state"] = [0.,.1,0.,.09,0.,.08,100.]
    assert endpoint_comparison(a,b)["matched"]
    a["evaluation_final_state"][1] += .002
    assert not endpoint_comparison(a,b)["matched"]


def test_unrecovered_energy_or_speed_excludes_pair():
    for field in ("speed", "energy", "reference"):
        data = rows()
        if field == "speed":
            data[-1]["evaluation_final_state"][6] += .2
        elif field == "energy":
            data[-1]["energy"]["stored_change_j"] += .02
        else:
            data[-1]["final_id_a"] = .65
        assert not matched_results(data)[-1]["eligible"]


def test_early_fault_never_becomes_a_large_apparent_energy_saving():
    data = rows()
    data[-1].update(status="FAIL",checks=dict(complete=False),completed_steps=20000)
    data[-1]["energy"]["loss_j"] = 1.
    pairs = matched_results(data)
    assert pairs[-1]["loss_saving_j"] is None
    assert pairs[-1]["input_saving_j"] is None
    summary = aggregate(pairs)[-1]
    assert summary["full_horizon_n"] == 0
    assert summary["mean_full_horizon_loss_saving_j"] is None

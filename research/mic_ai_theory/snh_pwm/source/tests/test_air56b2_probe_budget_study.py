from copy import deepcopy

import pytest

from tools.run_air56b2_probe_budget import METHODS, aggregate, matched_results


def rows():
    return [dict(case="synthetic", duration_s=6., speed_fraction=.7,
        disturbance=False, noise_seed=730, dt_s=.0001, plant_substeps=2,
        observer="current", method=m, status="PASS", probe_complete=True,
        probe_reason=None, probe_events=[], budget=None,
        energy=dict(shaft_work_j=100., stored_change_j=1., input_j=121., loss_j=20.))
        for m in METHODS]


def test_all_methods_pair_and_do_not_mutate_input():
    data = rows()
    before = deepcopy(data)
    pairs = matched_results(data)
    assert len(pairs) == 5 and all(p["eligible"] for p in pairs)
    assert data == before
    assert all(p["loss_saving_j"] == 0 for p in pairs)


def test_duplicates_and_missing_methods_are_not_silently_dropped():
    with pytest.raises(ValueError, match="duplicate"):
        matched_results(rows() + rows()[:1])
    with pytest.raises(ValueError, match="incomplete"):
        matched_results(rows()[1:])


@pytest.mark.parametrize("field,value", [("duration_s",3.), ("noise_seed",731),
    ("dt_s",.0002), ("plant_substeps",4), ("observer","voltage"), ("disturbance",True)])
def test_mismatched_protocol_cannot_supply_pair(field, value):
    data = rows()
    data[-1][field] = value
    with pytest.raises(ValueError, match="incomplete"):
        matched_results(data)


def test_failed_method_excludes_same_case_for_every_aggregate():
    data = rows()
    data[-1]["status"] = "FAIL"
    pairs = matched_results(data)
    assert len(pairs) == 5
    assert sum(p["eligible"] for p in pairs) == 4
    assert all(r["common_eligible"] == 0 for r in aggregate(pairs))
    assert all(r["mean_loss_saving_common_j"] is None for r in aggregate(pairs))


def test_negative_results_remain_and_storage_identity_is_preserved():
    data = rows()
    data[-1]["energy"].update(input_j=127.5, loss_j=25., stored_change_j=2., shaft_work_j=100.5)
    pair = matched_results(data)[-1]
    assert pair["eligible"]
    assert pair["loss_saving_j"] == -5.
    assert pair["input_saving_j"] == pair["loss_saving_j"]-pair["work_delta_j"]-pair["stored_delta_j"]


def test_unfinished_probe_retained_with_explicit_reason():
    data = rows()
    data[1]["probe_complete"] = False
    pair = matched_results(data)[0]
    assert pair["reason"] == "unfinished"
    assert not pair["eligible"]


def test_detected_power_error_invalidates_conditional_assumption_status():
    data = rows()
    data[-1]["budget"] = dict(ever_committed=False, bounds_valid=True,
                               config=dict(power_error_bound_w=1.))
    data[-1]["max_power_measurement_error_after_1p6s_w"] = 1.01
    assert matched_results(data)[-1]["bounds_not_falsified"] is False


def test_supervisor_does_not_receive_oracle_or_future_load():
    import inspect
    from control.air56b2_probe_budget import BudgetedDynamicProbeSupervisor
    assert set(inspect.signature(BudgetedDynamicProbeSupervisor.step).parameters) == {
        "self", "time_s", "measured_power_w", "measured_current_peak_a",
        "measured_voltage_peak_v", "measured_speed_rad_s", "reference_speed_rad_s",
        "voltage_limit_v"}

from dataclasses import replace
import inspect
import math

import pytest

from control.air56b2_active_probe import (
    ActiveProbeConfig, ActiveProbeSupervisor, bracket_estimate,
    decision_information, gain_hypotheses,
)
from control.air56b2_dynamic_probe import (
    DynamicProbeConfig, DynamicProbeSample, SettledProbeWindow,
)
from control.air56b2_measured_loss_fit import ProbeMeasurement


def make(**changes):
    cfg = DynamicProbeConfig(dt_s=.01, start_after_s=.1,
        minimum_settle_s=.04, window_s=.06, max_stage_s=.8)
    active = replace(ActiveProbeConfig(hold_until_s=4.), **changes)
    return ActiveProbeSupervisor(cfg, active)


def tick(s, t, **changes):
    x = (s.id_ref_a-.83)/.18
    args = dict(measured_power_w=100+12*x+4*x*x,
                measured_current_peak_a=2., measured_voltage_peak_v=100.,
                measured_speed_rad_s=100., reference_speed_rad_s=100.)
    args.update(changes)
    return s.step(t, **args)


def run(s, end=4.):
    return [tick(s, k*.01) for k in range(round(end/.01)+1)]


@pytest.mark.parametrize("field", list(ActiveProbeConfig.__dataclass_fields__))
@pytest.mark.parametrize("bad", [True, "1", math.nan, math.inf, -math.inf, -1.])
def test_invalid_config(field, bad):
    with pytest.raises(ValueError):
        ActiveProbeConfig(**{field: bad})


@pytest.mark.parametrize("bad", [0, 1.2, 5])
def test_probe_count(bad):
    with pytest.raises(ValueError):
        ActiveProbeConfig(max_probes=bad)


def window(t, value, slope=0., gain=0., phase="baseline"):
    samples = tuple(DynamicProbeSample(t+k*.01, value+slope*(t+k*.01-.005)-gain,
                                      2., 100.) for k in range(7))
    mean = sum(s.power_w for s in samples)/len(samples)
    return SettledProbeWindow(phase, samples, ProbeMeasurement(.83, mean, 2., 100.),
                             0., 0., 0., 4.)


def test_bracket_cancels_affine_drift_and_measures_return_separately():
    before = window(1., 100., slope=2.)
    query = window(2., 100., slope=2., gain=5., phase="query")
    after = window(3., 100., slope=2., phase="return")
    intervals = [(1.5, .1, 100+2*1.45+3), (2.5, .1, 100+2*2.45+4)]
    r = bracket_estimate(before, query, after, intervals, 2., 1.)
    assert r["gain_w"] == pytest.approx(5)
    assert r["baseline_slope_w_per_s"] == pytest.approx(2)
    assert r["excess_j"] == pytest.approx(.7)
    assert r["recovery_excess_j"] == pytest.approx(.4)


def test_bracket_does_not_call_negative_savings_positive_cost():
    r = bracket_estimate(window(1., 100), window(2., 95), window(3., 100),
                         [(2., .1, 95)], 2.1, 1.)
    assert r["signed_excess_j"] == -.5
    assert r["excess_j"] == 0
    assert r["gain_lower_heuristic_w"] == 4


def test_zero_information_when_all_hypotheses_choose_same_action():
    assert decision_information(((3., 1.), (5., 2.)), 0, 1.) == 0
    assert decision_information(((3., 1.), (1., 3.)), 0, 1.) == pytest.approx(1.)


def test_negative_gain_keeps_baseline_in_decision_labels():
    assert decision_information(((-1.,), (1.,)), 0, .1) == pytest.approx(1.)


def test_incompatible_hypotheses_are_not_silently_refitted():
    s = make()
    for k in range(250):
        power = 100 if s.id_ref_a == .83 else 40
        tick(s, k*.01, measured_power_w=power)
    assert s.reason == "response_hypotheses_falsified"
    assert not s.hypotheses
    assert not s.ever_committed


def test_reference_slew_bounds_and_return_verified_by_new_window():
    s = make()
    outputs = run(s)
    assert s.cycles
    assert s.ever_committed
    assert outputs[-1].completed and outputs[-1].id_ref_a == .83
    assert s.recovery_observed
    assert any(o.phase == "rejected" and not o.completed for o in outputs)
    assert max(abs(a.id_ref_a-b.id_ref_a) for a, b in zip(outputs, outputs[1:])) <= .015+1e-12
    assert all(s.config.low_id_a <= o.id_ref_a <= s.config.high_id_a for o in outputs)


def test_expense_is_not_zeroed_after_each_cycle():
    s = make()
    run(s)
    assert s.spent_estimate_j == pytest.approx(sum(c["excess_j"] for c in s.cycles))
    assert all(c["end_s"] > c["return_started_s"] > c["query_started_s"] for c in s.cycles)
    assert s.summary()["certificate"].startswith("none_")


def test_empirical_cost_updates_but_fixed_cost_ablation_does_not():
    s = make()
    before = s.cycle_cost(.65)
    run(s)
    assert s.cycle_cost(.65) != pytest.approx(before)
    s.learned_cost = False
    assert s.cycle_cost(.65) == pytest.approx(before)


def test_zero_budget_and_short_deadline_never_issue_probe():
    for s in (make(max_estimated_cost_j=0), make(hold_until_s=.3)):
        outputs = run(s)
        assert not s.cycles and not s.ever_committed
        assert all(o.id_ref_a == .83 for o in outputs)
        assert outputs[-1].completed


def test_bad_time_does_not_mutate_state():
    s = make()
    tick(s, .1)
    before = s.summary()
    for t in (.1, -.1, math.nan):
        with pytest.raises(ValueError):
            tick(s, t)
        assert s.summary() == before


@pytest.mark.parametrize("field,bad", [("measured_power_w", math.nan),
    ("measured_current_peak_a", -1), ("measured_current_peak_a", 4),
    ("measured_voltage_peak_v", 180), ("voltage_limit_v", 0),
    ("reference_speed_rad_s", math.inf)])
def test_invalid_and_electrical_observations_stop_and_return(field, bad):
    s = make()
    for k in range(60):
        tick(s, k*.01)
    output = tick(s, .6, **{field: bad})
    assert output.rejected
    for k in range(61, 160):
        output = tick(s, k*.01)
    assert output.completed and output.id_ref_a == .83


def test_gap_rejects_active_probe_and_cannot_generate_bracket():
    s = make()
    for k in range(40):
        tick(s, k*.01)
    before = len(s.cycles)
    output = tick(s, .8)
    assert output.rejected and output.reason == "sample_gap"
    assert len(s.cycles) == before
    assert not output.completed


def test_hold_interruption_invalidates_prediction():
    s = make()
    for k in range(350):
        output = tick(s, k*.01)
        if output.committed:
            break
    assert output.committed
    tick(s, (k+1)*.01, reference_speed_rad_s=101.)
    assert s.projection_status == "invalidated_by_early_return"
    assert s.rejected


def test_active_query_uses_response_disagreement_not_fixed_order():
    s = make()
    # Opposite signs at query 1, all others uninformative.
    s.hypotheses = ((0., 8., 0., 0.), (0., -8., 0., 0.))
    for k in range(30):
        tick(s, k*.01)
    assert s.decisions[0]["selected_index"] == 1
    fixed = make()
    fixed.hypotheses = s.hypotheses
    fixed.active_selection = False
    for k in range(30):
        tick(fixed, k*.01)
    assert fixed.decisions[0]["selected_index"] == 0


def test_supervisor_interface_contains_no_motor_or_future_load():
    assert set(inspect.signature(ActiveProbeSupervisor.step).parameters) == {
        "self", "time_s", "measured_power_w", "measured_current_peak_a",
        "measured_voltage_peak_v", "measured_speed_rad_s", "reference_speed_rad_s",
        "voltage_limit_v"}
    assert len(gain_hypotheses((.65, 1., .74, .915), .83)) == 225


@pytest.mark.parametrize("phase", ["baseline", "query", "return", "candidateverify"])
def test_regime_change_during_any_measurement_stage_rejects(phase):
    s = make()
    for k in range(350):
        output = tick(s, k*.01)
        if output.phase == phase:
            break
    assert output.phase == phase
    output = tick(s, (k+1)*.01, measured_speed_rad_s=101., reference_speed_rad_s=101.)
    assert output.reason == "observed_regime_change" and output.rejected


def test_verification_cannot_bypass_estimated_cost_limit():
    s = make(max_probes=1)
    s.cycles = [dict(index=0, id_a=.65, gain_lower_heuristic_w=10., excess_j=4.,
                     amplitude_a=.18, return_duration_s=.2)]
    s.cycle_cost = lambda _: 6.1
    s._decide(.5)
    assert s.phase != "candidateverify"
    assert s.rejected


def test_second_best_affordable_candidate_is_not_blocked_by_expensive_best():
    s = make(max_probes=2)
    s._before = window(.1,100)
    s.cycles = [dict(index=i, id_a=s.ids[i], gain_lower_heuristic_w=gain, excess_j=2.,
                     amplitude_a=.18, return_duration_s=.2) for i,gain in ((0,20.),(1,10.))]
    s.cycle_cost = lambda id_a: 6.1 if id_a == .65 else 1.
    s._decide(.5)
    assert s.phase == "candidateverify" and s.candidate_id_a == 1.


def test_unclosed_episode_exports_measured_energy_and_missing_duration():
    s = make()
    for k in range(50):
        tick(s,k*.01)
    tick(s,.5,measured_power_w=math.nan)
    episode = s.summary()["open_episode"]
    assert episode is not None and episode["known_measured_terminal_j"] > 0
    assert episode["measured_duration_s"] > 0
    assert episode["missing_measurement_s"] == pytest.approx(.01)
    assert episode["predicted_cost_j"] > 0
    assert episode["full_cycle_excess_j"] is None


@pytest.mark.parametrize("field,bad,reason", [("measured_power_w",math.nan,"invalid_measurement"),
                                            ("measured_current_peak_a",4.,"current_limit")])
def test_fault_wins_over_simultaneous_scheduled_return(field,bad,reason):
    s = make()
    for k in range(401):
        t = k*.01
        due = (s.phase == "committed" and t+s.return_s(s.id_ref_a)+.02 >= 4.)
        output = tick(s,t,**{field:bad}) if due else tick(s,t)
        if due:
            break
    assert due
    assert output.reason == reason and output.aborted
    assert s.projection_status == "invalidated_by_early_return"


@pytest.mark.parametrize("phase", ["query", "candidateverify"])
def test_aborted_query_and_deployment_keep_return_cost_journal(phase):
    s = make()
    for k in range(350):
        output = tick(s,k*.01)
        if s.phase == phase and abs(s.id_ref_a-.83) > .03:
            break
    assert s.phase == phase
    tick(s,(k+1)*.01,measured_power_w=math.nan)
    for j in range(k+2,500):
        output = tick(s,j*.01)
    assert output.completed
    episode = s.episodes[-1]
    assert episode["interrupted"] and episode["recovery_window_observed"]
    assert episode["interval_count"] > 0
    assert "rejected" in episode["phases"]
    assert s.summary()["open_episode"] is None

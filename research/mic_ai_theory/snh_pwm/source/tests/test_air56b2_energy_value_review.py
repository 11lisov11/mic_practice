"""Freeze review: synthetic decision states and observations, no motor simulation.

Regression expectations are deliberately not xfailed: failures block validation.
"""
from collections import deque
from copy import deepcopy
import math

import pytest

from control.air56b2_active_probe import ActiveProbeConfig
from control.air56b2_dynamic_probe import (
    DynamicProbeConfig,
    DynamicProbeSample,
    SettledProbeWindow,
)
from control.air56b2_energy_value_probe import (
    EnergyValueProbeSupervisor,
    GuardedFixedProbeSupervisor,
    candidate_value,
)
from control.air56b2_measured_loss_fit import ProbeMeasurement
from control.air56b2_probe_budget import ProbeBudgetConfig


def window(phase, end, id_a=.83, power=100., dt=.0001):
    samples = tuple(
        DynamicProbeSample(end - (3 - k) * dt, power, 2., 100.)
        for k in range(4)
    )
    return SettledProbeWindow(
        phase, samples, ProbeMeasurement(id_a, power, 2., 100.), 0., 0., 0., 5.
    )


def energy(*, greedy=False, reverse=False, greedy_full_menu=False,
           learned_cost=True, **active_changes):
    active = ActiveProbeConfig(**{"hold_until_s": 12., **active_changes})
    supervisor = EnergyValueProbeSupervisor(
        DynamicProbeConfig(dt_s=.0001, start_after_s=1.6), active,
        greedy=greedy, query_order=(1, 0, 3, 2) if reverse else (0, 1, 2, 3),
        greedy_full_menu=greedy_full_menu, learned_cost=learned_cost,
    )
    supervisor._before = window("baseline", 2.)
    return supervisor


def cycle(supervisor, index, *, gain=8., cost=.2, return_s=.4):
    id_a = supervisor.ids[index]
    return dict(
        index=index, id_a=id_a, amplitude_a=abs(id_a - .83),
        gain_w=gain + 1., gain_lower_heuristic_w=gain, error_width_w=1.,
        excess_j=cost, return_duration_s=return_s,
        baseline_slope_w_per_s=0.,
    )


def observe(supervisor, time_s, **changes):
    values = dict(
        measured_power_w=90., measured_current_peak_a=2.,
        measured_voltage_peak_v=100., measured_speed_rad_s=100.,
        reference_speed_rad_s=100.,
    )
    values.update(changes)
    return supervisor.step(time_s, **values)


def holding(kind, time_s=2.):
    """A valid post-verification state; only the next observation is exercised."""
    if kind == "guarded":
        supervisor = GuardedFixedProbeSupervisor(
            DynamicProbeConfig(dt_s=.0001, start_after_s=1.6),
            ProbeBudgetConfig(hold_until_s=12.),
        )
        supervisor._holding_reference = 100.
        supervisor._holding_power = 90.
        supervisor._budget_last_time = time_s - supervisor.config.dt_s
        supervisor.payback_status = "gate_disabled"
    else:
        supervisor = energy()
        supervisor._hold_speed_ref = 100.
        supervisor._hold_power = 90.
        supervisor._regime_speed_ref = 100.
        supervisor.projection_status = "empirical_prediction_not_bound"
    supervisor.phase = "committed"
    supervisor.candidate_id_a = supervisor.config.low_id_a
    supervisor.id_ref_a = supervisor.candidate_id_a
    supervisor.ever_committed = True
    supervisor._last_time_s = time_s - supervisor.config.dt_s
    return supervisor


def due_holding(kind):
    supervisor = holding(kind)
    recovery = (supervisor.recovery_s() if kind == "guarded"
                else supervisor.return_s(supervisor.id_ref_a))
    time_s = 12. - recovery - supervisor.config.dt_s
    supervisor._last_time_s = time_s - supervisor.config.dt_s
    if kind == "guarded":
        supervisor._budget_last_time = supervisor._last_time_s
    return supervisor, time_s


def assert_invalidated(supervisor, kind):
    if kind == "guarded":
        assert supervisor.payback_status == "invalidated_by_early_return"
    else:
        assert supervisor.projection_status == "invalidated_by_early_return"


def test_one_decision_evaluation_per_observable_bin_and_cost(monkeypatch):
    supervisor = energy()
    supervisor.hypotheses = (
        (4.1, -20., 0., 0.), (5.9, 20., 30., -30.), (8.2, 0., 0., 0.),
    )
    measured = {1: {"gain_lower_heuristic_w": 6.}}
    calls = []

    def value(index, gain, time_s, spent, deployment_cost_j=None):
        calls.append((index, gain, deployment_cost_j))
        return gain

    monkeypatch.setattr(supervisor, "cycle_cost", lambda _: 1.)
    monkeypatch.setattr(supervisor, "_value", value)
    result = supervisor.expected_query_value(0, 2., measured)

    # Bin [4,6) selects the known gain 6; bin [8,10) selects the new gain 8.
    query_calls = [call for call in calls if call[0] == 0]
    assert query_calls == [
        (0, gain, cost) for gain in (4., 8.) for cost in (.475, .85, 1.6)
    ]
    assert len([call for call in calls if call[0] == 1]) == 6
    assert result == pytest.approx((2 * 6. + 8.) / 3. - (.25 + .5 + 1.) / 3.)


def test_same_bins_ignore_hidden_gain_variation_and_unobserved_optima():
    supervisor = energy()
    supervisor.hypotheses = ((4.1, -20., 0., 0.), (5.9, 20., 30., -30.))
    original = supervisor.expected_query_value(0, 2., {})
    supervisor.hypotheses = ((5.1, 200., 100., 90.), (4.9, -200., -100., -90.))
    assert supervisor.expected_query_value(0, 2., {}) == pytest.approx(original)


def test_reordering_and_replicating_all_hypotheses_preserves_branch_weights():
    supervisor = energy()
    hypotheses = ((4.1, 0., 0., 0.), (5.9, 0., 0., 0.), (8.2, 0., 0., 0.))
    supervisor.hypotheses = hypotheses
    original = supervisor.expected_query_value(0, 2., {})
    supervisor.hypotheses = tuple(reversed(hypotheses)) * 3
    assert supervisor.expected_query_value(0, 2., {}) == pytest.approx(original)


@pytest.mark.parametrize("spent,cost,allowed", [
    (0., 8., True), (0., 8.000001, False), (3., 5., True), (3., 5.000001, False),
])
def test_candidate_admission_budget_boundary(spent, cost, allowed):
    result = candidate_value(20., 4., cost, spent, 8., 2.)
    assert (result > 0) is allowed


def test_query_admission_uses_full_forecast_not_cheap_cost_fraction(monkeypatch):
    supervisor = energy()
    supervisor.hypotheses = ((24., 24., 24., 24.),)
    monkeypatch.setattr(supervisor, "cycle_cost", lambda _: 8.01)
    assert supervisor.expected_query_value(0, 2., {}) is None
    supervisor._decide(2.)
    assert supervisor.decisions[-1]["action"] == "stop"
    assert not supervisor.ever_committed


def test_query_admission_keeps_previously_spent_energy(monkeypatch):
    supervisor = energy()
    supervisor.cycles = [cycle(supervisor, 1, cost=6.)]
    monkeypatch.setattr(supervisor, "cycle_cost", lambda _: 2.01)
    assert supervisor.expected_query_value(0, 2., {1: supervisor.cycles[0]}) is None


def test_commit_rejects_expensive_best_and_selects_affordable_second(monkeypatch):
    supervisor = energy()
    supervisor.cycles = [
        cycle(supervisor, 0, gain=20., cost=2.),
        cycle(supervisor, 1, gain=8., cost=2.),
    ]
    monkeypatch.setattr(supervisor, "cycle_cost", lambda id_a: 4.01 if id_a == .65 else 1.)
    supervisor._decide(2.)
    assert supervisor.phase == "candidateverify"
    assert supervisor.candidate_id_a == 1.
    assert supervisor.spent_estimate_j == 4.
    assert not supervisor.ever_committed


def test_no_commit_when_every_measured_candidate_exceeds_budget(monkeypatch):
    supervisor = energy(max_probes=1)
    supervisor.cycles = [cycle(supervisor, 0, gain=20., cost=4.)]
    monkeypatch.setattr(supervisor, "cycle_cost", lambda _: 4.01)
    supervisor._decide(2.)
    assert supervisor.decisions[-1]["action"] == "stop"
    assert supervisor.phase != "candidateverify"


@pytest.mark.parametrize("reverse,first", [(False, 0), (True, 1)])
def test_first_good_order_and_early_verification_without_second_probe(reverse, first):
    supervisor = energy(greedy=True, reverse=reverse)
    supervisor._decide(2.)
    assert supervisor.decisions[-1]["selected_index"] == first
    supervisor.cycles = [cycle(supervisor, first, gain=8.)]
    supervisor._decide(3.)
    assert [decision["action"] for decision in supervisor.decisions] == [
        "query", "verify_measured_candidate",
    ]
    assert supervisor.candidate_id_a == supervisor.ids[first]
    assert supervisor.phase == "candidateverify"
    assert not supervisor.ever_committed


def test_reverse_first_good_tries_low_only_after_high_was_insufficient():
    supervisor = energy(greedy=True, reverse=True)
    supervisor.cycles = [cycle(supervisor, 1, gain=0.)]
    supervisor._decide(3.)
    assert supervisor.decisions[-1]["action"] == "query"
    assert supervisor.decisions[-1]["selected_index"] == 0


def test_reverse_first_good_does_not_substitute_an_inner_probe_for_blocked_low():
    supervisor = energy(greedy=True, reverse=True)
    supervisor.cycles = [cycle(supervisor, 1, gain=0., cost=3.)]
    measured = {1: supervisor.cycles[0]}
    assert supervisor.expected_query_value(0, 3., measured) is None
    assert supervisor.expected_query_value(3, 3., measured) is not None
    supervisor._decide(3.)
    assert supervisor.decisions[-1]["action"] == "stop", (
        "the declared high/low comparator must not quietly probe id=0.915 A"
    )


def test_rollout_admission_does_not_discount_a_known_verification_budget():
    supervisor = energy()
    supervisor.hypotheses = ((20., 0., 0., 0.),)
    admission_cost = supervisor.cycle_cost(supervisor.ids[0])
    observed_cost = .5 * admission_cost
    after_query = energy(max_probes=1)
    after_query.cycles = [cycle(after_query, 0, gain=20., cost=observed_cost)]
    after_query._decide(3.)
    assert observed_cost + after_query.cycle_cost(after_query.ids[0]) > 8.
    assert after_query.decisions[-1]["action"] == "stop"

    # The rollout's half-cost branch describes this observed query cost.
    # Once it is known, the unchanged full forecast must also gate verification.
    supervisor.cost_fractions = (.5,)
    predicted = supervisor.expected_query_value(0, 2., {})
    assert predicted == pytest.approx(-observed_cost), (
        f"rollout credits an inadmissible verification: {predicted=}, "
        f"spent={observed_cost}, next_forecast="
        f"{after_query.cycle_cost(after_query.ids[0])}"
    )


def test_query_time_reserves_its_own_learned_return_before_deployment():
    supervisor = energy(hold_until_s=4.6)
    supervisor.cycles = [cycle(supervisor, 1, gain=0., return_s=1., cost=.1)]
    supervisor.hypotheses = ((24., 0., 0., 0.),)
    time_s = 2.
    id_a = supervisor.ids[0]
    full_query = supervisor.stage_s(id_a) + supervisor.return_s(id_a)
    assert supervisor._hold_s(0, time_s + full_query) <= 0
    result = supervisor.expected_query_value(0, time_s, {1: supervisor.cycles[0]})
    assert result is None or result <= 0, (
        f"positive rollout with no holding time after two real returns: {result=}"
    )


def test_guarded_comparator_stays_ungated_and_holds_valid_observation():
    supervisor = holding("guarded")
    assert not supervisor.budget_gate and not supervisor.payback_gate
    result = observe(supervisor, 2.)
    assert result.committed and not result.rejected


@pytest.mark.parametrize("kind", ["guarded", "energy"])
@pytest.mark.parametrize("changes", [
    {"measured_power_w": 95.},
    {"measured_speed_rad_s": 103.01},
    {"reference_speed_rad_s": 101., "measured_speed_rad_s": 101.},
])
def test_holding_guard_rejects_observed_regime_change(kind, changes):
    supervisor = holding(kind)
    result = observe(supervisor, 2., **changes)
    assert result.rejected and result.reason == "observed_regime_change"
    assert_invalidated(supervisor, kind)
    assert abs(result.id_ref_a - .65) <= supervisor.config.slew_a_per_s * supervisor.config.dt_s + 1e-12


@pytest.mark.parametrize("changes", [
    {"measured_power_w": 94.}, {"measured_speed_rad_s": 103.},
])
def test_guarded_holding_guard_preserves_exact_tolerance_boundaries(changes):
    supervisor = holding("guarded")
    assert observe(supervisor, 2., **changes).committed


FAULTS = [
    ("measured_power_w", math.nan, "invalid_measurement"),
    ("measured_current_peak_a", 4., "current_limit"),
    ("measured_voltage_peak_v", 180., "voltage_limit"),
    ("measured_current_peak_a", math.nan, "invalid_measurement"),
    ("measured_voltage_peak_v", math.nan, "invalid_measurement"),
    ("voltage_limit_v", 0., "invalid_measurement"),
    ("voltage_limit_v", 90., "voltage_limit"),
    ("measured_current_peak_a", -1., "invalid_measurement"),
]


@pytest.mark.parametrize("field,bad,reason", FAULTS)
def test_guarded_fault_before_deadline_latches_and_invalidates(field, bad, reason):
    supervisor = holding("guarded")
    result = observe(supervisor, 2., **{field: bad})
    assert result.rejected and result.aborted and result.reason == reason
    assert_invalidated(supervisor, "guarded")


@pytest.mark.parametrize("kind", ["guarded", "energy"])
@pytest.mark.parametrize("field,bad,reason", FAULTS)
def test_fault_wins_over_simultaneous_scheduled_return(kind, field, bad, reason):
    supervisor, time_s = due_holding(kind)
    result = observe(supervisor, time_s, **{field: bad})
    assert result.rejected and result.aborted and result.reason == reason
    assert_invalidated(supervisor, kind)


@pytest.mark.parametrize("kind", ["guarded", "energy"])
def test_fault_during_scheduled_rollback_upgrades_normal_completion(kind):
    supervisor, time_s = due_holding(kind)
    normal = observe(supervisor, time_s)
    assert normal.reason == "scheduled_return" and not normal.aborted
    fault = observe(supervisor, time_s + supervisor.config.dt_s, measured_current_peak_a=4.)
    assert fault.reason == "current_limit" and fault.aborted
    assert_invalidated(supervisor, kind)


@pytest.mark.parametrize("kind", ["guarded", "energy"])
def test_electrical_fault_precedes_simultaneous_holding_drift(kind):
    supervisor = holding(kind)
    result = observe(supervisor, 2., measured_power_w=95., measured_current_peak_a=4.)
    assert result.reason == "current_limit" and result.aborted


@pytest.mark.parametrize("kind", ["guarded", "energy"])
def test_holding_gap_rejects_and_invalidates_in_both_comparators(kind):
    supervisor = holding(kind)
    result = observe(supervisor, 2. + supervisor.config.dt_s)
    assert result.rejected and result.reason == "sample_gap"
    assert_invalidated(supervisor, kind)


@pytest.mark.parametrize("time_s", [math.nan, -1., 1.9999])
def test_guarded_invalid_time_cannot_mutate_holding_state(time_s):
    supervisor = holding("guarded")
    before = deepcopy(supervisor.__dict__)
    with pytest.raises(ValueError):
        observe(supervisor, time_s)
    assert supervisor.__dict__ == before


def test_guarded_captures_verification_mean_not_last_instantaneous_power():
    cfg = DynamicProbeConfig(dt_s=.01, start_after_s=.1,
                             minimum_settle_s=.04, window_s=.06)
    supervisor = GuardedFixedProbeSupervisor(cfg, ProbeBudgetConfig(hold_until_s=12.))
    supervisor._windows = [window("baseline", .5), window("baseline_repeat", .8)]
    supervisor.phase = "candidateverify"
    supervisor.candidate_id_a = supervisor.id_ref_a = .65
    supervisor._stage_started_s = .8
    supervisor._settled_since_s = .85
    supervisor._last_time_s = supervisor._budget_last_time = .99
    supervisor._pending = deque(
        DynamicProbeSample(.94 + k * .01, 90., 2., 100.) for k in range(6)
    )
    result = observe(supervisor, 1., measured_power_w=92.)
    assert result.committed
    assert supervisor._holding_reference == 100.
    assert supervisor._holding_power == pytest.approx((6 * 90. + 92.) / 7.)
    assert supervisor._holding_power != 92.


@pytest.mark.parametrize("learned_cost", [False, True])
@pytest.mark.parametrize("history,query_index,observed_cost,index", [
    ((), 0, .25, 0),
    ((), 3, .5, 0),
    ((), 0, 2., 3),
    (((0, 5.),), 1, .1, 2),
    (((3, .1), (1, .4)), 2, 2., 0),
    (((2, .3),), 3, 0., 1),
])
def test_forecast_after_query_matches_live_cost_without_mutating_history(
        learned_cost, history, query_index, observed_cost, index):
    supervisor = energy(learned_cost=learned_cost)
    supervisor.cycles = [cycle(supervisor, j, cost=cost) for j, cost in history]
    before = deepcopy(supervisor.__dict__)
    prediction = supervisor.forecast_after_query(index, query_index, observed_cost)
    assert supervisor.__dict__ == before

    after_query = deepcopy(supervisor)
    after_query.cycles.append(cycle(after_query, query_index, cost=observed_cost))
    assert prediction == pytest.approx(after_query.cycle_cost(after_query.ids[index]))
    assert after_query.spent_estimate_j == pytest.approx(
        supervisor.spent_estimate_j + observed_cost
    )


@pytest.mark.parametrize("full_menu", [False, True])
def test_greedy_full_menu_explicitly_controls_inner_fallback(full_menu):
    supervisor = energy(greedy=True, reverse=True, greedy_full_menu=full_menu)
    supervisor.cycles = [cycle(supervisor, 1, gain=0., cost=3.)]
    supervisor._decide(3.)
    event = supervisor.decisions[-1]
    assert supervisor.summary()["greedy_full_menu"] is full_menu
    if full_menu:
        assert event["action"] == "query" and event["selected_index"] == 3
        assert [choice["index"] for choice in event["choices"]] == [0, 3, 2]
    else:
        assert event["action"] == "stop"
        assert [choice["index"] for choice in event["choices"]] == [0]


def test_greedy_full_menu_preserves_first_good_and_two_query_limit():
    supervisor = energy(greedy=True, greedy_full_menu=True)
    supervisor.cycles = [cycle(supervisor, 0, gain=8.)]
    supervisor._decide(3.)
    assert supervisor.decisions[-1]["action"] == "verify_measured_candidate"
    assert supervisor.candidate_id_a == supervisor.ids[0]
    assert not supervisor.ever_committed

    exhausted = energy(greedy=True, greedy_full_menu=True)
    exhausted.cycles = [cycle(exhausted, j, gain=0.) for j in (0, 1)]
    exhausted._decide(3.)
    assert exhausted.decisions[-1]["action"] == "stop"
    assert exhausted.decisions[-1]["choices"] == []


@pytest.mark.parametrize("bad", [None, 1, "true"])
def test_greedy_full_menu_requires_boolean(bad):
    with pytest.raises(TypeError, match="greedy_full_menu"):
        energy(greedy=True, greedy_full_menu=bad)


@pytest.mark.parametrize("method,greedy,full_menu,order", [
    ("greedy", True, False, (0, 1, 2, 3)),
    ("greedy_high", True, False, (1, 0, 3, 2)),
    ("greedy_menu", True, True, (0, 1, 2, 3)),
    ("energy_value", False, False, (0, 1, 2, 3)),
])
def test_runner_wires_eighth_comparator_without_running_a_plant(
        monkeypatch, method, greedy, full_menu, order):
    from tools import run_air56b2_energy_value as runner

    captured = []

    def no_plant(*args, **kwargs):
        captured.append(kwargs["supervisor"])
        return {}

    monkeypatch.setattr(runner, "run_trial", no_plant)
    assert len(runner.METHODS) == len(set(runner.METHODS)) == 8
    result = runner.run_job(("synthetic", None, None, method, False, 12., .7,
                             2, .25, .5, 2.6))
    assert len(captured) == 1
    supervisor = captured[0]
    assert supervisor.greedy is greedy
    assert supervisor.greedy_full_menu is full_menu
    assert supervisor.query_order == order
    assert supervisor.active.max_probes == 2
    assert result["method"] == method and result["total_simulation_s"] == 13.


@pytest.mark.parametrize("kind", ["guarded", "energy"])
def test_fault_upgrade_during_return_is_preserved_in_event_history(kind):
    supervisor, time_s = due_holding(kind)
    assert observe(supervisor, time_s).reason == "scheduled_return"
    fault_time = time_s + supervisor.config.dt_s
    result = observe(supervisor, fault_time, measured_current_peak_a=4.)
    assert result.aborted and result.reason == "current_limit"
    assert any(event.get("reason") == "current_limit"
               and event["time_s"] == fault_time for event in supervisor.events), (
        "final status is corrected, but the actual return fault is absent from the log"
    )

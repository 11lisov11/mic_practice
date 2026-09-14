from dataclasses import asdict, replace
import math

import numpy as np
import pytest

from control.air56b2_dynamic_probe import DynamicProbeConfig
from control.air56b2_probe_budget import (
    BudgetedDynamicProbeSupervisor, ProbeBudgetConfig, net_gain_lower_bound,
)


def make_supervisor(**changes):
    probe = DynamicProbeConfig(dt_s=.01, start_after_s=.1,
                               minimum_settle_s=.02, window_s=.04)
    cfg = replace(ProbeBudgetConfig(power_error_bound_w=.1,
                  baseline_drift_w_per_s=0., gain_deterioration_w_per_s=0.,
                  excess_power_cap_w=50., max_probe_excess_j=100.,
                  recovery_settle_s=.1), **changes)
    return BudgetedDynamicProbeSupervisor(probe, cfg)


def tick(s, t, **changes):
    args = dict(measured_power_w=200*s.id_ref_a**2 + 48.02/s.id_ref_a**2 + 50,
                measured_current_peak_a=2., measured_voltage_peak_v=140.,
                measured_speed_rad_s=100., reference_speed_rad_s=100.)
    args.update(changes)
    return s.step(t, **args)


def run(s, duration=6.):
    return [tick(s, k*.01) for k in range(round(duration/.01)+1)]


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "1"])
@pytest.mark.parametrize("name", list(ProbeBudgetConfig.__dataclass_fields__))
def test_config_requires_finite_nonboolean_numbers(name, bad):
    with pytest.raises(ValueError):
        ProbeBudgetConfig(**{name: bad})


@pytest.mark.parametrize("name", list(ProbeBudgetConfig.__dataclass_fields__))
def test_negative_config_rejected(name):
    with pytest.raises(ValueError):
        ProbeBudgetConfig(**{name: -1})


def test_net_bound_counts_probe_and_return_and_future_negative_gain():
    assert net_gain_lower_bound(3, 4, 2, 1, 2) == -7
    assert net_gain_lower_bound(3, 4, 2, 1, 0) == 9


def test_net_bound_is_conservative_for_random_envelopes():
    rng = np.random.default_rng(9309)
    for _ in range(200):
        gain, hold, spent, recovery, drift = rng.uniform(0, 5, 5)
        times = np.linspace(0, hold, 1001)
        actual_gain = gain - drift*times + rng.uniform(0, 1, len(times))
        actual_net = np.trapezoid(actual_gain, times) - spent - recovery
        assert actual_net >= net_gain_lower_bound(gain, hold, spent, recovery, drift) - 1e-12


def test_zero_budget_never_leaves_baseline():
    s = make_supervisor(max_probe_excess_j=0)
    outputs = run(s)
    assert {o.id_ref_a for o in outputs} == {.83}
    assert outputs[-1].completed
    assert outputs[-1].reason == "budget_entry_reserve"
    assert not s.ever_committed
    assert s.spent_upper_j == 0


def test_loose_bounds_accept_and_return_before_declared_deadline():
    s = make_supervisor()
    outputs = run(s)
    assert s.ever_committed and s.net_gain_lower_j > 0
    assert outputs[-1].id_ref_a == .83 and outputs[-1].completed
    assert outputs[-1].reason == "scheduled_return"
    assert s.bounds_valid


def test_small_remaining_horizon_declines_apparent_power_gain():
    s = make_supervisor(hold_until_s=1.7)
    run(s, duration=2.)
    assert not s.ever_committed
    assert any(e["reason"] == "payback_decline" for e in s.budget_events)


def test_recovery_is_not_declared_complete_on_arrival_of_reference():
    s = make_supervisor(hold_until_s=.8)
    outputs = run(s, duration=1.)
    assert any(o.phase == "rejected" and not o.completed for o in outputs)
    assert outputs[-1].completed


def test_budget_gate_terminates_without_resetting_accumulated_cost():
    s = make_supervisor(max_probe_excess_j=13)
    s.payback_gate = False
    run(s)
    assert s.reason == "probe_energy_budget"
    assert 0 < s.spent_upper_j <= s.budget.max_probe_excess_j


def test_gap_and_invalid_power_invalidate_assumptions():
    s = make_supervisor()
    tick(s, 0.)
    tick(s, .2, measured_power_w=math.nan)
    assert not s.bounds_valid
    assert s.bound_failures == {"sample_gap", "invalid_power"}
    assert s.rejected


def test_bad_timestamp_does_not_mutate_budget_state():
    s = make_supervisor()
    tick(s, 0.)
    before = s.summary()
    with pytest.raises(ValueError):
        tick(s, 0.)
    assert s.summary() == before


def test_ablation_disables_payback_but_preserves_scheduled_return():
    s = make_supervisor(hold_until_s=1.7)
    s.payback_gate = False
    outputs = run(s, duration=2.)
    assert s.ever_committed
    assert s.net_gain_lower_j < 0
    assert outputs[-1].id_ref_a == .83


def test_slew_remains_bounded_through_interventions():
    s = make_supervisor(max_probe_excess_j=13)
    outputs = run(s)
    assert max(abs(b.id_ref_a-a.id_ref_a) for a, b in zip(outputs, outputs[1:])) <= .015 + 1e-12


def test_recovery_completes_on_last_predeadline_control_tick():
    s = make_supervisor(hold_until_s=1.693)
    outputs = [tick(s, k*.01) for k in range(169)]
    assert outputs[-1].completed
    assert outputs[-1].id_ref_a == .83


def test_summary_is_json_serializable():
    import json
    s = make_supervisor()
    run(s)
    json.dumps(s.summary(), allow_nan=False)


def test_excess_cap_is_not_silently_clipped():
    s = make_supervisor()
    for k in range(30):
        tick(s, k*.01)
    tick(s, .3, measured_power_w=10000.)
    assert not s.bounds_valid
    assert "excess_cap_not_established" in s.bound_failures
    assert s.spent_upper_j > s.budget.excess_power_cap_w * .01


def test_average_power_does_not_certify_continuous_positive_part():
    # Jensen: max(mean(delta), 0) can be strictly below mean(max(delta, 0)).
    delta = np.array([10., -10.])
    discrete_cost = max(float(delta.mean()), 0.)
    continuous_cost = float(np.maximum(delta, 0.).mean())
    assert discrete_cost == 0 and continuous_cost == 5


def test_same_past_can_admit_opposite_future_flux_preferences():
    # Illustrative steady-state loss family, not a fitted AIR56B2 model.
    a, baseline, candidate = 100., .83, .65
    threshold = a*baseline**2*candidate**2
    def gain(b):
        return (baseline**2-candidate**2)*(a-b/(baseline**2*candidate**2))
    assert gain(threshold*.5) > 0
    assert abs(gain(threshold)) < 1e-12
    assert gain(threshold*2) < 0


def test_candidate_window_age_is_subtracted_from_gain_bound():
    from control.air56b2_dynamic_probe import DynamicProbeSample, SettledProbeWindow
    from control.air56b2_measured_loss_fit import ProbeMeasurement
    s = make_supervisor(power_error_bound_w=0, baseline_drift_w_per_s=0,
                        gain_deterioration_w_per_s=.5)
    def window(phase, current, power, times):
        samples = tuple(DynamicProbeSample(t,power,2.,140.) for t in times)
        return SettledProbeWindow(phase,samples,ProbeMeasurement(current,power,2.,140.),0.,0.,0.,2.)
    s._windows = [window("baseline",.83,100.,[.2,.3,.4,.5]),
                  window("baseline_repeat",.83,100.,[.6,.7,.8,.9])]
    s.phase = "candidateverify"
    s.candidate_id_a = .7
    s._accept_window(window("candidateverify",.7,97.97,[.88,.92,.96,1.]),1.)
    assert s.gain_lower_w <= 2.


def test_early_electrical_abort_invalidates_historical_payback_projection():
    s = make_supervisor()
    for k in range(300):
        tick(s,k*.01)
        if s.ever_committed:
            break
    assert s.ever_committed and s.net_gain_lower_j > 0
    tick(s,(k+1)*.01,measured_current_peak_a=20.)
    assert not s.bounds_valid
    assert s.summary()["payback_status"] == "invalidated_by_early_return"


def test_gap_while_holding_does_not_keep_unjustified_candidate():
    s = make_supervisor()
    for k in range(300):
        tick(s,k*.01)
        if s.ever_committed:
            break
    result = tick(s,k*.01+.2)
    assert result.rejected and not result.committed


def test_recovery_settling_starts_after_actual_reference_arrival():
    s = make_supervisor()
    for k in range(30):
        tick(s,k*.01)
    assert s.id_ref_a != .83
    # A late observation caps slew to one nominal tick, so actual return is late.
    result = tick(s,1.,measured_current_peak_a=20.)
    t = 1.
    while result.phase != "rejected":
        t += .1
        result = tick(s,t)
    assert not result.completed
    assert tick(s,t+.01).completed is False

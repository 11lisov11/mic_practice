import math

import pytest

from control.air56b2_active_probe import ActiveProbeConfig
from control.air56b2_dynamic_probe import DynamicProbeConfig
from control.air56b2_energy_value_probe import EnergyValueProbeSupervisor, candidate_value


def make(**kwargs):
    return EnergyValueProbeSupervisor(DynamicProbeConfig(dt_s=.01,start_after_s=.1,
        minimum_settle_s=.04,window_s=.06),ActiveProbeConfig(hold_until_s=4.),**kwargs)


def tick(s,t):
    x = (s.id_ref_a-.83)/.18
    return s.step(t,100+12*x+4*x*x,2.,100.,100.,100.)


def test_future_value_preserves_costs_horizon_and_payback():
    assert candidate_value(4,2,1,2,8,2) == 7
    assert candidate_value(4,0,1,2,8,2) == 0
    assert candidate_value(4,2,7,2,8,2) == 0
    assert candidate_value(4,2,7,0,8,2) == 1
    assert candidate_value(1,20,0,0,8,2) == 0
    assert candidate_value(4,2,1,8,20,2) == 0


@pytest.mark.parametrize("bad",[math.nan,math.inf,-math.inf])
def test_nonfinite_value_rejected(bad):
    with pytest.raises(ValueError):
        candidate_value(bad,2,1,2,8,2)


def test_query_with_no_future_value_is_declined():
    s = make()
    s.hypotheses = ((-1.,-1.,-1.,-1.),)
    for k in range(80):
        result = tick(s,k*.01)
    assert result.id_ref_a == .83 and result.completed
    assert not s.cycles


def test_query_information_not_useful_when_horizon_exhausted():
    s = make()
    assert s.expected_query_value(0,3.9,{}) is None


def test_lowering_gain_scale_reduces_energy_value_despite_same_best_label():
    s = make()
    s.hypotheses = ((20.,-20.,10.,-10.),)
    high = s.expected_query_value(0,.2,{})
    s.hypotheses = ((.2,-.2,.1,-.1),)
    low = s.expected_query_value(0,.2,{})
    assert high > 0 > low


@pytest.mark.parametrize("greedy",[False,True])
def test_measured_good_candidate_accepted_with_return_and_full_journal(greedy):
    s = make(greedy=greedy)
    for k in range(401):
        result = tick(s,k*.01)
    assert s.ever_committed
    assert s.cycles and s.episodes
    assert result.completed and result.id_ref_a == .83
    assert s.projection_status == "holding_ended_prediction_only"
    assert any(e["kind"]=="verification_hold_return" for e in s.episodes)


def test_controller_never_commits_an_unmeasured_candidate():
    s = make()
    for k in range(300):
        output = tick(s,k*.01)
        if output.committed:
            assert s.candidate_id_a in {c["id_a"] for c in s.cycles}


def test_greedy_starts_at_lower_probe():
    s = make(greedy=True)
    for k in range(30):
        tick(s,k*.01)
    assert s.decisions[0]["selected_index"] == 0

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location("budget_audit", ROOT / "tools/analyze_air56b2_probe_budget.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def sample(power=100., measured_error=.1):
    return dict(trace_columns=["time_s","true_interval_terminal_power_w"],
        trace=[[1.,power],[2.,power]], max_power_measurement_error_after_1p6s_w=measured_error,
        budget=dict(anchor_time_s=1.,anchor_power_w=100.,events=[],
                    config=dict(power_error_bound_w=1.,baseline_drift_w_per_s=.5,
                                excess_power_cap_w=10.,gain_deterioration_w_per_s=.5)))


def test_sampled_audit_can_falsify_unseen_baseline_drift():
    result = audit.audit_assumptions(sample(),sample(110.))
    assert result["baseline_band_violations"] == 2
    assert result["maximum_baseline_exceedance_w"] == 9.


def test_power_error_of_either_run_counts():
    assert audit.audit_assumptions(sample(),sample(measured_error=2.))["measurement_error_bound_falsified"]
    assert audit.audit_assumptions(sample(measured_error=2.),sample())["measurement_error_bound_falsified"]


def test_true_cap_exceedance_is_detected_independently_of_online_filter():
    result = audit.audit_assumptions(sample(120.),sample())
    assert result["positive_excess_cap_violations"] == 2


def test_gain_forecast_is_not_a_loss_forecast():
    row = sample(100.)
    row["budget"]["events"] = [dict(reason="payback_accept",time_s=1.,hold_s=1.,gain_lower_w=5.)]
    result = audit.audit_assumptions(row,sample(101.))
    assert result["gain_envelope_violations"] == 2
    assert result["minimum_gain_envelope_slack_w"] == -4.


def test_unmatched_traces_cannot_certify_assumptions():
    baseline = sample()
    baseline["trace"][-1][0] += .01
    assert audit.audit_assumptions(sample(),baseline) == {"status":"unmatched_time_grid"}

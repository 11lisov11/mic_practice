from __future__ import annotations

import pytest

from tools.plan_binomial_noninferiority_power import (
    acceptance_power,
    build_report,
    critical_successes,
    minimum_probe_count,
)


def test_locked_400_probe_design_has_less_than_half_acceptance_power() -> None:
    critical, power = acceptance_power(
        400,
        assumed_true_coverage=0.95,
        lower_bound_threshold=0.92,
        error_probability=0.01,
    )
    assert critical == 381
    assert power == pytest.approx(0.46796994929118646)


def test_aggregate_800_probe_design_has_more_than_80pct_power() -> None:
    critical, power = acceptance_power(
        800,
        assumed_true_coverage=0.95,
        lower_bound_threshold=0.92,
        error_probability=0.01,
    )
    assert critical == 754
    assert power == pytest.approx(0.8537831855439442)


def test_minimum_count_for_90pct_power_is_exact() -> None:
    total, critical, achieved = minimum_probe_count(
        assumed_true_coverage=0.95,
        lower_bound_threshold=0.92,
        error_probability=0.01,
        desired_power=0.90,
    )
    assert (total, critical) == (897, 844)
    assert achieved == pytest.approx(0.9049128297075686)


def test_report_exposes_joint_two_series_power_and_boundaries() -> None:
    report = build_report()
    assert report["joint_power_for_two_independent_400_probe_series"] == pytest.approx(
        0.46796994929118646**2
    )
    assert report["minimum_designs"][1]["minimum_probe_count"] == 897
    assert "does not repair a failed locked protocol" in report["interpretation_boundary"]


def test_power_planner_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        critical_successes(0, lower_bound_threshold=0.92, error_probability=0.01)
    with pytest.raises(ValueError):
        acceptance_power(
            400,
            assumed_true_coverage=1.0,
            lower_bound_threshold=0.92,
            error_probability=0.01,
        )
    with pytest.raises(ValueError):
        minimum_probe_count(
            assumed_true_coverage=0.95,
            lower_bound_threshold=0.92,
            error_probability=0.01,
            desired_power=0.90,
            minimum_total=10,
            maximum_total=9,
        )

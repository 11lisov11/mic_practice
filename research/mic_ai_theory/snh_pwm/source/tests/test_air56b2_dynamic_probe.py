import ast
from dataclasses import FrozenInstanceError, fields, replace
import inspect
import json
import math
import sys

import numpy as np
import pytest

from control import air56b2_dynamic_probe as dynamic_probe
from control.air56b2_dynamic_probe import DynamicProbeConfig, DynamicProbeSupervisor
from control.air56b2_measured_loss_fit import (
    MeasuredLossFitConfig,
    ProbeMeasurement,
    fit_measured_loss_reference,
)


def _config(**changes):
    return replace(DynamicProbeConfig(dt_s=0.01), **changes)


def _best_probe(probes):
    return min(probes, key=lambda probe: (probe.power_w, probe.id_a))


def _power(id_a):
    # An observable synthetic power channel, not a plant or an oracle argument.
    return 200.0 * id_a**2 + 48.02 / id_a**2 + 50.0


def _step(supervisor, time_s, **changes):
    observed = dict(
        measured_power_w=_power(supervisor.id_ref_a),
        measured_current_peak_a=2.0,
        measured_voltage_peak_v=140.0,
        measured_speed_rad_s=100.0,
        reference_speed_rad_s=100.0,
    )
    observed.update(changes)
    return supervisor.step(time_s, **observed)


def _run(supervisor, observations=None, *, until_completed=True, duration_s=8.0):
    outputs = []
    for index in range(round(duration_s / supervisor.config.dt_s) + 1):
        time_s = index * supervisor.config.dt_s
        values = {} if observations is None else observations(supervisor, time_s)
        outputs.append(_step(supervisor, time_s, **values))
        if until_completed and outputs[-1].completed:
            break
    return outputs


def _assert_slew(outputs, config):
    previous_id, previous_time = config.baseline_id_a, outputs[0].time_s
    for output in outputs:
        bound = config.slew_a_per_s * min(output.time_s - previous_time, config.dt_s)
        assert abs(output.id_ref_a - previous_id) <= bound + 1e-12
        assert config.low_id_a <= output.id_ref_a <= config.high_id_a
        previous_id, previous_time = output.id_ref_a, output.time_s


def test_defaults_and_frozen_records():
    config = DynamicProbeConfig(0.01)
    assert config == _config()
    assert tuple(getattr(config, field.name) for field in fields(config))[1:] == (
        0.83,
        0.65,
        1.0,
        1.5,
        0.8,
        0.15,
        0.12,
        1.2,
        3.0,
        0.03,
        2.0,
        3.1,
        170.0,
        4.0,
        2.0,
    )
    with pytest.raises(FrozenInstanceError):
        config.dt_s = 1.0
    supervisor = DynamicProbeSupervisor(config)
    output = _step(supervisor, 0.0)
    with pytest.raises(FrozenInstanceError):
        output.phase = "committed"


@pytest.mark.parametrize("selector,expected", [(None, 0.7), (_best_probe, 0.65)])
def test_complete_settled_sequence_commits_observed_improvement(selector, expected):
    supervisor = DynamicProbeSupervisor(_config(), selector)
    outputs = _run(supervisor)
    final = outputs[-1]
    assert final.completed and final.committed
    assert not final.rejected and not final.aborted and final.reason is None
    assert final.id_ref_a == pytest.approx(expected)
    assert final.improvement_w == pytest.approx(_power(0.83) - _power(expected))
    assert [window.phase for window in supervisor.windows] == [
        "baseline",
        "low",
        "high",
        "baseline_repeat",
        "candidateverify",
    ]
    assert [
        event["phase"]
        for event in supervisor.events
        if event["kind"] == "stage_started"
    ] == ["baseline", "low", "high", "baseline_repeat", "candidateverify", "committed"]
    for window in supervisor.windows:
        assert len(window.samples) >= 4
        assert window.samples[-1].time_s - window.samples[0].time_s >= 0.12 - 1e-12
        assert window.measurement.power_w == pytest.approx(
            _power(window.measurement.id_a)
        )
    if selector is None:
        assert supervisor.fit_result.accepted
    _assert_slew(outputs, supervisor.config)
    later = _step(supervisor, final.time_s + 0.01)
    assert later.committed and later.id_ref_a == final.id_ref_a
    assert len(supervisor.windows) == 5


def test_each_window_follows_previous_command_settling_and_full_minimum_wait():
    supervisor = DynamicProbeSupervisor(_config())
    commands = {}

    def observed(state, time_s):
        commands[round(time_s, 8)] = state.id_ref_a
        return {}

    _run(supervisor, observed)
    starts = {
        event["phase"]: event["time_s"]
        for event in supervisor.events
        if event["kind"] == "stage_started"
    }
    for window in supervisor.windows:
        target = window.measurement.id_a
        stage_commands = [
            (time, value)
            for time, value in commands.items()
            if time >= starts[window.phase]
        ]
        arrival = next(time for time, value in stage_commands if value == target)
        assert (
            window.samples[0].time_s
            >= arrival + supervisor.config.minimum_settle_s - 1e-12
        )
        assert all(
            commands[round(sample.time_s, 8)] == target for sample in window.samples
        )
    assert supervisor.windows[0].samples[0].time_s >= 0.95 - 1e-12
    assert supervisor.windows[0].samples[-1].time_s >= 1.07 - 1e-12


def test_speed_error_clears_partial_window_and_restarts_minimum_settle():
    supervisor = DynamicProbeSupervisor(_config(start_after_s=0.0))
    for index in range(21):
        _step(supervisor, index * 0.01)
    assert supervisor.window_samples
    _step(supervisor, 0.21, measured_speed_rad_s=103.01)
    assert not supervisor.window_samples and not supervisor.windows
    for index in range(22, 49):
        _step(supervisor, index * 0.01)
        assert not supervisor.windows
    _step(supervisor, 0.49)
    assert supervisor.windows[0].samples[0].time_s == pytest.approx(0.37)
    assert any(event["reason"] == "speed_error" for event in supervisor.events)


def test_sampling_gap_cannot_stand_in_for_a_complete_window():
    supervisor = DynamicProbeSupervisor(_config(start_after_s=0.0))
    for index in range(21):
        _step(supervisor, index * 0.01)
    _step(supervisor, 0.50)
    assert not supervisor.window_samples and not supervisor.windows
    for index in range(51, 77):
        _step(supervisor, index * 0.01)
        assert not supervisor.windows
    _step(supervisor, 0.77)
    assert supervisor.windows[0].samples[0].time_s == pytest.approx(0.65)
    assert any(event["reason"] == "sample_gap" for event in supervisor.events)


def test_command_ramps_and_initial_transient_power_are_not_measured():
    config = _config(start_after_s=0.0)
    supervisor = DynamicProbeSupervisor(config)
    reached = {}

    def observed(state, time_s):
        if state.id_ref_a != state.target_id_a:
            return {"measured_power_w": -10000.0}
        reached.setdefault(state.phase, time_s)
        if time_s - reached[state.phase] < config.minimum_settle_s - 1e-12:
            return {"measured_power_w": -10000.0}
        return {}

    outputs = _run(supervisor, observed)
    assert outputs[-1].committed
    assert all(
        sample.power_w > 0.0
        for window in supervisor.windows
        for sample in window.samples
    )
    _assert_slew(outputs, config)


@pytest.mark.parametrize("offset", [0.0, -100.0, 100.0])
def test_absolute_plus_relative_power_tolerance_handles_noise_and_zero_power(offset):
    supervisor = DynamicProbeSupervisor(_config(start_after_s=0.0), _best_probe)

    def observed(state, time_s):
        return {
            "measured_power_w": offset + (-0.5 if round(time_s / 0.01) % 2 else 0.5)
        }

    outputs = _run(supervisor, observed)
    assert len(supervisor.windows) == 5
    assert outputs[-1].reason == "insufficient_improvement"
    for window in supervisor.windows:
        assert window.power_tolerance_w == pytest.approx(
            2.0 + 0.03 * abs(window.measurement.power_w)
        )


def test_endpoint_drift_blocks_ramp_even_when_cv_and_half_means_pass():
    supervisor = DynamicProbeSupervisor(
        _config(
            start_after_s=0.0,
            minimum_settle_s=0.0,
            power_cv_tolerance=0.0,
            power_abs_tolerance_w=2.0,
            max_stage_s=0.5,
        )
    )
    outputs = _run(supervisor, lambda state, time: {"measured_power_w": 25.0 * time})
    assert outputs[-1].reason == "stage_timeout:baseline"
    assert not supervisor.windows
    assert outputs[-1].aborted and outputs[-1].completed


def test_high_variance_blocks_zero_endpoint_and_half_drift():
    supervisor = DynamicProbeSupervisor(
        _config(
            start_after_s=0.0,
            minimum_settle_s=0.0,
            power_cv_tolerance=0.0,
            power_abs_tolerance_w=2.0,
            max_stage_s=0.5,
        )
    )
    outputs = _run(
        supervisor,
        lambda state, time: {
            "measured_power_w": 30.0 * math.sin(round(time / 0.01) * math.pi / 2.0)
        },
    )
    assert outputs[-1].reason == "stage_timeout:baseline"
    assert not supervisor.windows


def test_unstable_power_can_settle_later_with_a_fresh_rolling_window():
    supervisor = DynamicProbeSupervisor(
        _config(start_after_s=0.0, minimum_settle_s=0.0)
    )
    for index in range(51):
        time_s = index * 0.01
        _step(
            supervisor, time_s, measured_power_w=100.0 * time_s if index < 30 else 100.0
        )
        if supervisor.windows:
            break
    assert supervisor.windows
    assert supervisor.windows[0].samples[0].time_s >= 0.30 - 1e-12


@pytest.mark.parametrize("selector", [None, _best_probe])
def test_baseline_repeat_load_drift_rejects_before_candidate(selector):
    supervisor = DynamicProbeSupervisor(_config(), selector)
    outputs = _run(
        supervisor,
        lambda state, time: {
            "measured_power_w": _power(state.id_ref_a)
            + (5.0 if state.phase == "baseline_repeat" else 0.0)
        },
    )
    assert outputs[-1].completed and outputs[-1].rejected and outputs[-1].aborted
    assert outputs[-1].reason == "baseline_repeat_drift"
    assert outputs[-1].candidate_id_a is None
    assert len(supervisor.windows) == 4


def test_selector_sees_only_three_averages_with_repeated_baseline_combined():
    captured = []

    def select(probes):
        captured.append(probes)
        return _best_probe(probes)

    supervisor = DynamicProbeSupervisor(_config(), select)
    outputs = _run(
        supervisor,
        lambda state, time: {
            "measured_power_w": _power(state.id_ref_a)
            + (2.0 if state.phase == "baseline_repeat" else 0.0),
            "measured_current_peak_a": 2.4 if state.phase == "baseline_repeat" else 2.0,
            "measured_voltage_peak_v": 144.0
            if state.phase == "baseline_repeat"
            else 140.0,
        },
    )
    assert outputs[-1].committed
    assert len(captured) == 1 and isinstance(captured[0], tuple)
    baseline, low, high = captured[0]
    assert all(isinstance(probe, ProbeMeasurement) for probe in captured[0])
    assert (baseline.id_a, low.id_a, high.id_a) == (0.83, 0.65, 1.0)
    assert baseline.power_w == pytest.approx(_power(0.83) + 1.0)
    assert baseline.current_peak_a == pytest.approx(2.2)
    assert baseline.voltage_peak_v == pytest.approx(142.0)


@pytest.mark.parametrize("selector", [None, _best_probe])
def test_candidate_must_deliver_fresh_measured_improvement_or_slew_back(selector):
    supervisor = DynamicProbeSupervisor(_config(), selector)
    outputs = _run(
        supervisor,
        lambda state, time: {
            "measured_power_w": _power(0.83)
            if state.phase == "candidateverify"
            else _power(state.id_ref_a)
        },
    )
    assert outputs[-1].reason == "insufficient_improvement"
    assert outputs[-1].rejected and not outputs[-1].aborted
    assert outputs[-1].completed and outputs[-1].id_ref_a == 0.83
    assert len(supervisor.windows) == 5
    assert any(
        output.phase == "rollback" and output.rejected and not output.completed
        for output in outputs
    )
    _assert_slew(outputs, supervisor.config)


def test_improvement_is_compared_with_both_baselines_not_only_their_mean():
    supervisor = DynamicProbeSupervisor(_config(), lambda probes: 0.7)

    def observed(state, time_s):
        power = {
            "baseline": 100.0,
            "baseline_repeat": 96.0,
            "candidateverify": 95.0,
        }.get(state.phase, 110.0)
        return {"measured_power_w": power}

    final = _run(supervisor, observed)[-1]
    assert final.reason == "insufficient_improvement" and final.improvement_w == 1.0


@pytest.mark.parametrize("selector", [None, _best_probe])
@pytest.mark.parametrize("stage", ["low", "high", "baseline_repeat", "candidateverify"])
@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("measured_current_peak_a", 3.1001, "current_limit"),
        ("measured_voltage_peak_v", 170.0001, "voltage_limit"),
        ("voltage_limit_v", 139.0, "voltage_limit"),
    ],
)
def test_single_sample_risk_stops_probing_and_latches_failure(
    selector, stage, field, value, reason
):
    supervisor = DynamicProbeSupervisor(_config(), selector)
    triggered = False

    def observed(state, time_s):
        nonlocal triggered
        if state.phase == stage and not triggered:
            triggered = True
            return {field: value}
        return {}

    outputs = _run(supervisor, observed)
    assert triggered
    assert outputs[-1].reason == reason
    assert outputs[-1].completed and outputs[-1].aborted
    assert outputs[-1].id_ref_a == 0.83
    assert stage not in supervisor.measurements
    _assert_slew(outputs, supervisor.config)
    count = len(supervisor.events)
    later = _step(supervisor, outputs[-1].time_s + 0.01)
    assert later.reason == reason and len(supervisor.events) == count


def test_limits_are_checked_even_while_waiting_and_after_commit():
    waiting = DynamicProbeSupervisor(_config())
    result = _step(waiting, 0.0, measured_current_peak_a=4.0)
    assert result.completed and result.reason == "current_limit"
    supervisor = DynamicProbeSupervisor(_config())
    final = _run(supervisor)[-1]
    result = _step(supervisor, final.time_s + 0.01, measured_voltage_peak_v=180.0)
    assert result.rejected and result.aborted and not result.committed
    assert result.phase == "rollback" and not result.completed


def test_equality_at_limits_is_feasible_and_observed_cap_cannot_loosen_config():
    supervisor = DynamicProbeSupervisor(_config())
    outputs = _run(
        supervisor,
        lambda state, time: {
            "measured_current_peak_a": 3.1,
            "measured_voltage_peak_v": 170.0,
            "voltage_limit_v": 200.0,
            "measured_speed_rad_s": 103.0,
        },
    )
    assert outputs[-1].committed
    tightened = DynamicProbeSupervisor(_config())
    assert _step(tightened, 0.0, voltage_limit_v=140.0).phase == "waiting"
    output = _step(
        tightened, 0.01, measured_voltage_peak_v=145.0, voltage_limit_v=200.0
    )
    assert output.reason == "voltage_limit"


@pytest.mark.parametrize("selector", [None, _best_probe])
def test_smaller_later_voltage_cap_checks_earlier_windows_for_both_selectors(selector):
    supervisor = DynamicProbeSupervisor(_config(), selector)
    outputs = _run(
        supervisor,
        lambda state, time: {
            "measured_voltage_peak_v": 140.0
            if state.phase == "baseline_repeat"
            else 160.0,
            "voltage_limit_v": 150.0 if state.phase == "baseline_repeat" else 170.0,
        },
    )
    assert outputs[-1].reason == "probe_limits"
    assert len(supervisor.windows) == 4


@pytest.mark.parametrize(
    "stage", ["baseline", "low", "high", "baseline_repeat", "candidateverify"]
)
def test_stage_timeout_is_not_extended_by_speed_error(stage):
    supervisor = DynamicProbeSupervisor(_config())
    outputs = _run(
        supervisor,
        lambda state, time: {
            "measured_speed_rad_s": 90.0 if state.phase == stage else 100.0
        },
    )
    final = outputs[-1]
    assert (
        final.reason == f"stage_timeout:{stage}" and final.aborted and final.completed
    )
    start = next(
        event["time_s"]
        for event in supervisor.events
        if event["phase"] == stage and event["kind"] == "stage_started"
    )
    failure = next(
        event["time_s"] for event in supervisor.events if event["kind"] == "rejected"
    )
    assert failure == pytest.approx(start + supervisor.config.max_stage_s)
    assert stage not in supervisor.measurements
    _assert_slew(outputs, supervisor.config)


def test_slew_transition_counts_toward_stage_timeout():
    supervisor = DynamicProbeSupervisor(
        _config(start_after_s=0.0, slew_a_per_s=0.05, max_stage_s=0.5)
    )
    outputs = _run(supervisor)
    assert outputs[-1].reason == "stage_timeout:low"
    assert len(supervisor.windows) == 1
    assert outputs[-1].completed and outputs[-1].id_ref_a == 0.83
    _assert_slew(outputs, supervisor.config)


@pytest.mark.parametrize(
    "candidate,reason",
    [
        (None, "no_candidate"),
        (math.nan, "invalid_candidate"),
        (math.inf, "invalid_candidate"),
        (True, "invalid_candidate"),
        ("0.7", "invalid_candidate"),
        (object(), "invalid_candidate"),
        (0.64, "candidate_out_of_bounds"),
        (1.01, "candidate_out_of_bounds"),
    ],
)
def test_invalid_selector_proposals_reject(candidate, reason):
    supervisor = DynamicProbeSupervisor(_config(), lambda probes: candidate)
    final = _run(supervisor)[-1]
    assert final.completed and final.rejected and final.reason == reason
    assert len(supervisor.windows) == 4


def test_selector_failure_rolls_back():
    def failing(probes):
        raise RuntimeError("synthetic selector failure")

    final = _run(DynamicProbeSupervisor(_config(), failing))[-1]
    assert final.reason == "selector_failed" and final.aborted and final.completed


def test_default_analytic_rejected_fit_can_verify_its_measured_fallback():
    supervisor = DynamicProbeSupervisor(_config())
    final = _run(
        supervisor, lambda state, time: {"measured_power_w": 100.0 * state.id_ref_a}
    )[-1]
    assert not supervisor.fit_result.accepted
    assert final.committed and final.id_ref_a == 0.65


@pytest.mark.parametrize("dt_s", [0.001, 0.02, 0.07, 0.1])
def test_fine_and_coarse_timesteps_keep_complete_windows_and_slew_bounds(dt_s):
    supervisor = DynamicProbeSupervisor(_config(dt_s=dt_s))
    outputs = _run(supervisor)
    assert outputs[-1].committed
    assert outputs[-1].id_ref_a == pytest.approx(0.7)
    for window in supervisor.windows:
        assert len(window.samples) >= 4
        assert window.samples[-1].time_s - window.samples[0].time_s >= 0.12 - 1e-12
    _assert_slew(outputs, supervisor.config)


def test_selector_can_return_existing_fit_result():
    def select(probes):
        return fit_measured_loss_reference(
            probes, MeasuredLossFitConfig(0.65, 1.0, 3.1, 170.0)
        )

    supervisor = DynamicProbeSupervisor(_config(), select)
    assert _run(supervisor)[-1].committed
    assert supervisor.fit_result.accepted


@pytest.mark.parametrize(
    "margin,power,committed", [(2.0, 98.0, True), (0.0, 100.0, False)]
)
def test_exact_improvement_margin_and_zero_margin_do_not_allow_no_change(
    margin, power, committed
):
    supervisor = DynamicProbeSupervisor(
        _config(improvement_margin_w=margin), lambda probes: 0.7
    )
    final = _run(
        supervisor,
        lambda state, time: {
            "measured_power_w": power if state.phase == "candidateverify" else 100.0
        },
    )[-1]
    assert final.committed is committed
    assert final.completed


def test_late_first_call_does_not_backfill_unobserved_settling():
    supervisor = DynamicProbeSupervisor(_config())
    output = _step(supervisor, 10.0)
    assert output.phase == "baseline" and not supervisor.windows
    assert not supervisor.window_samples
    for index in range(1, 27):
        _step(supervisor, 10.0 + index * 0.01)
        assert not supervisor.windows
    _step(supervisor, 10.27)
    assert len(supervisor.windows) == 1


def test_repeated_invalid_samples_during_rollback_preserve_first_failure_and_slew():
    supervisor = DynamicProbeSupervisor(_config())
    outputs = _run(supervisor)[-1:]
    time_s = outputs[-1].time_s
    outputs.append(_step(supervisor, time_s + 0.01, measured_power_w=math.nan))
    assert outputs[-1].phase == "rollback"
    for index in range(2, 30):
        outputs.append(
            _step(supervisor, time_s + index * 0.01, measured_current_peak_a=4.0)
        )
    assert outputs[-1].completed and outputs[-1].reason == "invalid_measurement"
    assert outputs[-1].id_ref_a == 0.83
    assert (
        len([event for event in supervisor.events if event["kind"] == "rejected"]) == 1
    )
    for before, after in zip(outputs, outputs[1:]):
        assert abs(after.id_ref_a - before.id_ref_a) <= 0.015 + 1e-12


def test_gap_at_active_reference_caps_rollback_movement_to_nominal_step():
    supervisor = DynamicProbeSupervisor(_config())
    for index in range(200):
        output = _step(supervisor, index * 0.01)
        if output.phase == "low" and output.id_ref_a == 0.65:
            break
    assert output.id_ref_a == 0.65
    later = _step(supervisor, output.time_s + 5.0)
    assert later.reason == "stage_timeout:low" and later.phase == "rollback"
    assert later.id_ref_a == pytest.approx(0.665)
    assert not later.completed


@pytest.mark.parametrize("field", [field.name for field in fields(DynamicProbeConfig)])
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "1", None, 1j])
def test_config_requires_finite_real_values(field, bad):
    with pytest.raises(ValueError):
        _config(**{field: bad})


@pytest.mark.parametrize(
    "changes",
    [
        {"dt_s": 0.0},
        {"slew_a_per_s": 0.0},
        {"window_s": 0.0},
        {"max_stage_s": 0.0},
        {"current_limit_a": 0.0},
        {"voltage_limit_v": 0.0},
        {"start_after_s": -1.0},
        {"minimum_settle_s": -1.0},
        {"speed_error_limit_rad_s": -1.0},
        {"power_cv_tolerance": -1.0},
        {"power_abs_tolerance_w": -1.0},
        {"repeat_drift_limit_w": -1.0},
        {"improvement_margin_w": -1.0},
        {"low_id_a": 0.0},
        {"low_id_a": 0.83},
        {"baseline_id_a": 1.0},
        {"high_id_a": 0.8},
    ],
)
def test_invalid_config_ranges(changes):
    with pytest.raises(ValueError):
        _config(**changes)


@pytest.mark.parametrize(
    "field",
    [
        "measured_power_w",
        "measured_current_peak_a",
        "measured_voltage_peak_v",
        "measured_speed_rad_s",
        "reference_speed_rad_s",
        "voltage_limit_v",
    ],
)
@pytest.mark.parametrize(
    "bad", [math.nan, math.inf, -math.inf, True, "1", 1j, 10**1000]
)
def test_invalid_observations_latch_abort(field, bad):
    supervisor = DynamicProbeSupervisor(_config())
    output = _step(supervisor, 0.0, **{field: bad})
    assert (
        output.reason == "invalid_measurement" and output.aborted and output.completed
    )
    assert output.id_ref_a == 0.83 and not supervisor.windows


@pytest.mark.parametrize(
    "field,value",
    [
        ("measured_current_peak_a", -0.1),
        ("measured_voltage_peak_v", -0.1),
        ("voltage_limit_v", 0.0),
        ("voltage_limit_v", -1.0),
    ],
)
def test_invalid_observation_ranges_abort(field, value):
    output = _step(DynamicProbeSupervisor(_config()), 0.0, **{field: value})
    assert output.reason == "invalid_measurement"


@pytest.mark.parametrize("bad", [-0.01, math.nan, math.inf, True, "1", None, 0.1, 0.0])
def test_bad_or_nonmonotonic_time_raises_without_mutation(bad):
    supervisor = DynamicProbeSupervisor(_config(start_after_s=0.0))
    _step(supervisor, 0.1)
    before = dict(supervisor.__dict__)
    with pytest.raises(ValueError):
        _step(supervisor, bad)
    assert supervisor.__dict__ == before


def test_numpy_scalars_negative_power_and_large_finite_offsets():
    config = _config(dt_s=np.float64(0.01), start_after_s=0.0)
    for power in (-100.0, 1e308):
        supervisor = DynamicProbeSupervisor(config, _best_probe)
        final = _run(
            supervisor,
            lambda state, time: {
                "measured_power_w": np.float64(power),
                "measured_speed_rad_s": -100.0,
                "reference_speed_rad_s": -100.0,
            },
        )[-1]
        assert final.reason == "insufficient_improvement"
        assert len(supervisor.windows) == 5


def test_history_snapshots_cannot_mutate_supervisor():
    supervisor = DynamicProbeSupervisor(_config())
    _run(supervisor)
    assert isinstance(supervisor.events, tuple) and isinstance(
        supervisor.windows, tuple
    )
    measurements = supervisor.measurements
    measurements.clear()
    assert len(supervisor.measurements) == 5
    with pytest.raises(FrozenInstanceError):
        supervisor.windows[0].measurement.power_w = -1.0
    event = supervisor.events[0]
    event["phase"] = "committed"
    assert supervisor.events[0]["phase"] == "baseline"
    decoded = json.loads(json.dumps(supervisor.events, allow_nan=False))
    assert decoded == list(supervisor.events)
    measured = next(event for event in decoded if event["kind"] == "measurement")
    assert (
        measured["measurement"]["power_w"]
        == supervisor.measurements["baseline"].power_w
    )


def test_standalone_source_and_observable_only_api():
    assert tuple(inspect.signature(DynamicProbeSupervisor.step).parameters) == (
        "self",
        "time_s",
        "measured_power_w",
        "measured_current_peak_a",
        "measured_voltage_peak_v",
        "measured_speed_rad_s",
        "reference_speed_rad_s",
        "voltage_limit_v",
    )
    tree = ast.parse(inspect.getsource(dynamic_probe))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".")[0] in sys.stdlib_module_names
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module.split(".")[0] in sys.stdlib_module_names or (
                node.module == "control.air56b2_measured_loss_fit"
            )
    for hidden in ("params", "torque_nm", "speed_truth_rad_s", "oracle_loss", "plant"):
        with pytest.raises(TypeError):
            DynamicProbeSupervisor(_config(), **{hidden: object()})
        with pytest.raises(TypeError):
            _step(DynamicProbeSupervisor(_config()), 0.0, **{hidden: object()})


def test_invalid_constructor_arguments():
    with pytest.raises(TypeError):
        DynamicProbeSupervisor(object())
    with pytest.raises(TypeError):
        DynamicProbeSupervisor(_config(), 1.0)

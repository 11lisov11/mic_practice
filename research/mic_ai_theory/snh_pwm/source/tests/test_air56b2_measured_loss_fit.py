import ast
from dataclasses import fields, is_dataclass, replace
import inspect
import math
import sys

import numpy as np
import pytest

from control import air56b2_measured_loss_fit as measured_fit
from control.air56b2_measured_loss_fit import (
    MeasuredLossFitConfig,
    MeasuredLossFitResult,
    ProbeMeasurement,
    fit_measured_loss_reference,
)


def _config(**changes: float) -> MeasuredLossFitConfig:
    return replace(MeasuredLossFitConfig(0.1, 4.0, 5.0, 200.0), **changes)


def _probes(
    ids: tuple[float, ...] = (0.5, 0.8, 1.2, 1.8, 2.5),
    *,
    a: float = 3.0,
    b: float = 12.0,
    c: float = 20.0,
) -> list[ProbeMeasurement]:
    return [
        ProbeMeasurement(id_a, a * id_a**2 + b / id_a**2 + c, 3.0, 150.0)
        for id_a in ids
    ]


@pytest.mark.parametrize("ids", [(0.5, 1.0, 2.0), (0.5, 0.8, 1.2, 1.8, 2.5)])
def test_known_analytic_optimum(ids: tuple[float, ...]) -> None:
    result = fit_measured_loss_reference(_probes(ids), _config())
    assert isinstance(result, MeasuredLossFitResult)
    assert result.accepted
    assert result.reason == "fit_accepted"
    assert result.id_a == pytest.approx(math.sqrt(2.0), rel=1e-12)
    assert result.coefficients == pytest.approx((3.0, 12.0, 20.0), rel=1e-12)
    assert result.condition is not None and 1.0 <= result.condition < 1e8
    assert result.infeasible_probe_indices == ()


def test_three_distinct_averaged_probes_from_baseline_repeat_sequence() -> None:
    center, low, high, repeated_center = _probes((1.4, 1.0, 1.8, 1.4))
    center = replace(center, power_w=center.power_w - 0.05)
    repeated_center = replace(repeated_center, power_w=repeated_center.power_w + 0.05)
    averaged_center = replace(
        center, power_w=(center.power_w + repeated_center.power_w) / 2.0
    )
    result = fit_measured_loss_reference([averaged_center, low, high], _config())
    assert result.accepted
    assert result.id_a == pytest.approx(math.sqrt(2.0), rel=1e-12)
    assert result.coefficients == pytest.approx((3.0, 12.0, 20.0), rel=1e-12)


@pytest.mark.parametrize("offset", [-1e6, -100.0, 0.0, 100.0, 1e6])
def test_constant_power_offset_invariance(offset: float) -> None:
    probes = _probes()
    base = fit_measured_loss_reference(probes, _config())
    shifted = fit_measured_loss_reference(
        [replace(probe, power_w=probe.power_w + offset) for probe in probes], _config()
    )
    assert shifted.accepted
    assert shifted.id_a == pytest.approx(base.id_a, rel=1e-10)
    assert shifted.coefficients[:2] == pytest.approx(base.coefficients[:2], rel=1e-10)
    assert shifted.coefficients[2] == pytest.approx(base.coefficients[2] + offset)
    assert shifted.condition == base.condition


@pytest.mark.parametrize("id_scale", [1e-100, 1e-6, 1.0, 1e6, 1e100])
@pytest.mark.parametrize("power_scale", [1e-9, 1.0, 1e9])
def test_scaled_units_preserve_reference(id_scale: float, power_scale: float) -> None:
    probes = [
        ProbeMeasurement(
            probe.id_a * id_scale,
            probe.power_w * power_scale,
            probe.current_peak_a * id_scale,
            probe.voltage_peak_v,
        )
        for probe in _probes()
    ]
    result = fit_measured_loss_reference(
        probes, MeasuredLossFitConfig(0.1 * id_scale, 4.0 * id_scale, 5.0 * id_scale, 200)
    )
    assert result.accepted
    assert result.id_a / id_scale == pytest.approx(math.sqrt(2.0), rel=1e-11)
    a, b, c = result.coefficients
    assert a / (power_scale / id_scale**2) == pytest.approx(3.0, rel=1e-11)
    assert b / (power_scale * id_scale**2) == pytest.approx(12.0, rel=1e-11)
    assert c / power_scale == pytest.approx(20.0, rel=1e-11)


@pytest.mark.parametrize("a,b", [(-3.0, 12.0), (3.0, -12.0), (-3.0, -12.0), (0.0, 0.0)])
def test_nonconvex_or_flat_fit_falls_back_to_measured_minimum(a: float, b: float) -> None:
    probes = _probes(a=a, b=b)
    result = fit_measured_loss_reference(probes, _config())
    assert not result.accepted
    assert result.reason == "nonconvex_fit"
    assert result.id_a == min(probes, key=lambda probe: (probe.power_w, probe.id_a)).id_a
    assert result.coefficients is not None


@pytest.mark.parametrize("offset,scale", [(0.0, 1.0), (1e6, 1.0), (-100.0, 1e-6)])
def test_noisy_positive_coefficient_fit_falls_back(offset: float, scale: float) -> None:
    probes = [
        replace(probe, power_w=(probe.power_w + noise) * scale + offset)
        for probe, noise in zip(_probes(), (0.0, 10.0, -10.0, 10.0, 0.0))
    ]
    result = fit_measured_loss_reference(probes, _config())
    assert not result.accepted
    assert result.reason == "poor_fit"
    assert result.coefficients[0] > 0 and result.coefficients[1] > 0
    assert result.id_a == min(probes, key=lambda probe: probe.power_w).id_a


def test_small_measurement_noise_can_still_be_accepted() -> None:
    probes = [
        replace(probe, power_w=probe.power_w + noise)
        for probe, noise in zip(_probes(), (0.01, -0.01, 0.01, -0.01, 0.0))
    ]
    result = fit_measured_loss_reference(probes, _config())
    assert result.accepted
    assert result.id_a == pytest.approx(math.sqrt(2.0), rel=0.002)


@pytest.mark.parametrize("ids", [(1.0,), (1.0, 2.0), (1.0, 1.0, 2.0, 2.0)])
def test_insufficient_distinct_probes_fall_back(ids: tuple[float, ...]) -> None:
    probes = _probes(ids)
    result = fit_measured_loss_reference(probes, _config())
    assert not result.accepted
    assert result.reason == "insufficient_distinct_probes"
    assert result.id_a == min(probes, key=lambda probe: (probe.power_w, probe.id_a)).id_a
    assert result.coefficients is None and result.condition is None


def test_repeats_with_three_distinct_probes_and_iterators_are_supported() -> None:
    probes = _probes((0.5, 0.5, 1.0, 2.0, 2.0))
    result = fit_measured_loss_reference(iter(probes), _config())
    assert result.accepted
    assert result.id_a == pytest.approx(math.sqrt(2.0))


@pytest.mark.parametrize("spacing", [1e-5, 1e-10, 1e-14])
def test_ill_conditioned_probes_fall_back(spacing: float) -> None:
    probes = _probes(tuple(1.0 + n * spacing for n in range(5)))
    result = fit_measured_loss_reference(probes, _config())
    assert not result.accepted
    assert result.reason == "ill_conditioned_probes"
    assert result.condition > 1e8
    assert result.coefficients is None
    assert result.id_a == min(probes, key=lambda probe: (probe.power_w, probe.id_a)).id_a


@pytest.mark.parametrize("a,b,expected", [(100.0, 1.0, 0.5), (1.0, 1000.0, 2.5)])
def test_never_extrapolates_beyond_measured_convex_hull(
    a: float, b: float, expected: float
) -> None:
    result = fit_measured_loss_reference(_probes(a=a, b=b), _config())
    assert result.accepted
    assert result.reason == "fit_accepted_bounded"
    assert result.id_a == expected


@pytest.mark.parametrize("lower,upper,expected", [(0.7, 1.1, 1.1), (1.6, 2.2, 1.6)])
def test_config_further_bounds_interpolation(lower: float, upper: float, expected: float) -> None:
    result = fit_measured_loss_reference(
        _probes(), _config(id_lower_a=lower, id_upper_a=upper)
    )
    assert result.accepted
    assert result.reason == "fit_accepted_bounded"
    assert result.id_a == expected


def test_hull_and_config_can_intersect_at_one_point() -> None:
    result = fit_measured_loss_reference(_probes(), _config(id_lower_a=2.5))
    assert result.accepted and result.id_a == 2.5


@pytest.mark.parametrize("lower,upper", [(0.1, 0.4), (2.6, 4.0)])
def test_disjoint_bounds_return_no_action(lower: float, upper: float) -> None:
    result = fit_measured_loss_reference(
        _probes(), _config(id_lower_a=lower, id_upper_a=upper)
    )
    assert not result.accepted
    assert result.id_a is None and result.reason == "no_feasible_probe"


@pytest.mark.parametrize("field,value", [("current_peak_a", 5.1), ("voltage_peak_v", 200.1)])
def test_infeasible_probe_flags_and_blocks_fitted_proposal(field: str, value: float) -> None:
    probes = _probes()
    probes[2] = replace(probes[2], power_w=-100.0, **{field: value})
    result = fit_measured_loss_reference(probes, _config())
    assert not result.accepted
    assert result.reason == "infeasible_measured_probes"
    assert result.infeasible_probe_indices == (2,)
    assert result.id_a == min(
        (probe for i, probe in enumerate(probes) if i != 2), key=lambda probe: probe.power_w
    ).id_a


def test_fallback_also_respects_config_bounds() -> None:
    probes = _probes(a=-3.0, b=-12.0)
    result = fit_measured_loss_reference(
        probes, _config(id_lower_a=0.8, id_upper_a=1.8)
    )
    assert not result.accepted
    assert result.id_a == min(
        (probe for probe in probes if 0.8 <= probe.id_a <= 1.8),
        key=lambda probe: probe.power_w,
    ).id_a


def test_limit_equality_is_feasible() -> None:
    probes = [replace(probe, current_peak_a=5.0, voltage_peak_v=200.0) for probe in _probes()]
    result = fit_measured_loss_reference(probes, _config())
    assert result.accepted and result.infeasible_probe_indices == ()


def test_all_electrically_infeasible_probes_return_no_action() -> None:
    probes = [
        replace(probe, current_peak_a=6.0) if i % 2 else replace(probe, voltage_peak_v=201.0)
        for i, probe in enumerate(_probes())
    ]
    result = fit_measured_loss_reference(probes, _config())
    assert not result.accepted
    assert result.id_a is None and result.reason == "no_feasible_probe"
    assert result.infeasible_probe_indices == tuple(range(len(probes)))


def test_empty_probes_return_no_action() -> None:
    result = fit_measured_loss_reference([], _config())
    assert not result.accepted
    assert result.id_a is None and result.reason == "no_feasible_probe"


def test_fallback_ties_and_probe_order_are_deterministic() -> None:
    probes = _probes(a=0.0, b=0.0)
    for ordering in (probes, probes[::-1]):
        result = fit_measured_loss_reference(ordering, _config())
        assert not result.accepted and result.id_a == 0.5
    result = fit_measured_loss_reference(_probes()[::-1], _config())
    assert result.accepted and result.id_a == pytest.approx(math.sqrt(2.0))


@pytest.mark.parametrize("field", [field.name for field in fields(ProbeMeasurement)])
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "1.0", 1.0j, None])
def test_invalid_probe_numbers_fail(field: str, bad: object) -> None:
    with pytest.raises(ValueError):
        replace(_probes()[0], **{field: bad})


@pytest.mark.parametrize(
    "field,value",
    [("id_a", 0.0), ("id_a", -1.0), ("current_peak_a", -0.1), ("voltage_peak_v", -0.1)],
)
def test_invalid_probe_ranges_fail(field: str, value: float) -> None:
    with pytest.raises(ValueError):
        replace(_probes()[0], **{field: value})


@pytest.mark.parametrize("field", [field.name for field in fields(MeasuredLossFitConfig)])
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, False, "1.0", 1.0j, None])
def test_invalid_config_numbers_fail(field: str, bad: object) -> None:
    with pytest.raises(ValueError):
        _config(**{field: bad})


@pytest.mark.parametrize(
    "changes",
    [
        {"id_lower_a": 0.0}, {"id_lower_a": -1.0}, {"id_upper_a": 0.0},
        {"id_upper_a": 0.1}, {"id_lower_a": 5.0},
        {"current_limit_a": 0.0}, {"current_limit_a": -1.0},
        {"voltage_limit_v": 0.0}, {"voltage_limit_v": -1.0},
    ],
)
def test_invalid_config_ranges_fail(changes: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        _config(**changes)


def test_numpy_real_scalars_are_supported() -> None:
    probe = ProbeMeasurement(np.float64(1.0), np.float32(2.0), np.int64(3), 0)
    result = fit_measured_loss_reference([probe], _config())
    assert result.id_a == 1.0


def test_numeric_conversion_overflow_is_invalid() -> None:
    with pytest.raises(ValueError):
        ProbeMeasurement(10**1000, 1.0, 1.0, 1.0)


def test_lstsq_failure_returns_measured_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise np.linalg.LinAlgError("solver failed")

    monkeypatch.setattr(np.linalg, "lstsq", fail)
    probes = _probes()
    result = fit_measured_loss_reference(probes, _config())
    assert not result.accepted and result.reason == "numerical_failure"
    assert result.id_a == min(probes, key=lambda probe: probe.power_w).id_a


def test_only_standard_library_and_numpy_source_imports() -> None:
    tree = ast.parse(inspect.getsource(measured_fit))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            roots = [node.module.split(".")[0]]
        else:
            continue
        assert all(root in sys.stdlib_module_names or root == "numpy" for root in roots)


def test_public_api_contains_only_measurements_and_limits() -> None:
    assert tuple(inspect.signature(fit_measured_loss_reference).parameters) == ("probes", "config")
    assert [field.name for field in fields(ProbeMeasurement)] == [
        "id_a", "power_w", "current_peak_a", "voltage_peak_v"
    ]
    assert [field.name for field in fields(MeasuredLossFitConfig)] == [
        "id_lower_a", "id_upper_a", "current_limit_a", "voltage_limit_v"
    ]
    assert is_dataclass(MeasuredLossFitResult)


@pytest.mark.parametrize("name", ["params", "torque_nm", "temperature_c", "oracle"])
def test_oracle_and_hidden_context_are_not_accepted(name: str) -> None:
    with pytest.raises(TypeError):
        fit_measured_loss_reference(_probes(), _config(), **{name: object()})


def test_callable_is_rejected_without_invocation() -> None:
    def oracle() -> None:
        pytest.fail("measurement fitting must never invoke a supplied oracle")

    with pytest.raises(TypeError):
        fit_measured_loss_reference(oracle, _config())
    with pytest.raises(TypeError):
        fit_measured_loss_reference([oracle], _config())
    with pytest.raises(TypeError):
        fit_measured_loss_reference(_probes(), oracle)


def test_nonmeasurement_entries_cannot_hide_behind_fallback() -> None:
    with pytest.raises(TypeError):
        fit_measured_loss_reference([_probes()[0], object()], _config())

"""Bounded reference proposals using only supplied electrical probe data."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
from numbers import Real

import numpy as np


_MAX_CONDITION = 1.0e8
_MAX_RELATIVE_RESIDUAL = 0.1


def _finite_real(name: str, value: float) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite real number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


@dataclass(frozen=True)
class ProbeMeasurement:
    """Caller-supplied data; power_w may be a simulated estimator proxy.

    This record does not imply bench-measured watts. Averaging, baseline-repeat
    drift gating, and validation of the power channel belong to the caller.
    """

    id_a: float
    power_w: float
    current_peak_a: float
    voltage_peak_v: float

    def __post_init__(self) -> None:
        for name in ("id_a", "power_w", "current_peak_a", "voltage_peak_v"):
            object.__setattr__(self, name, _finite_real(name, getattr(self, name)))
        if self.id_a <= 0.0:
            raise ValueError("probe id_a must be positive")
        if self.current_peak_a < 0.0 or self.voltage_peak_v < 0.0:
            raise ValueError("measured peaks must be nonnegative")


@dataclass(frozen=True)
class MeasuredLossFitConfig:
    id_lower_a: float
    id_upper_a: float
    current_limit_a: float
    voltage_limit_v: float

    def __post_init__(self) -> None:
        for name in ("id_lower_a", "id_upper_a", "current_limit_a", "voltage_limit_v"):
            object.__setattr__(self, name, _finite_real(name, getattr(self, name)))
        if not 0.0 < self.id_lower_a < self.id_upper_a:
            raise ValueError("id bounds must satisfy 0 < lower < upper")
        if self.current_limit_a <= 0.0 or self.voltage_limit_v <= 0.0:
            raise ValueError("current and voltage limits must be positive")


@dataclass(frozen=True)
class MeasuredLossFitResult:
    """A fit or measured fallback; ``accepted`` refers only to the fit.

    ``coefficients`` is (a, b, c) in P(i_d) = a*i_d**2 + b/i_d**2 + c,
    or None when unavailable. ``condition`` is the scaled design's 2-norm
    condition number, or None when no solve was attempted. Zero-based
    ``infeasible_probe_indices`` flag measured current/voltage violations.
    A rejected fit can have a measured fallback id_a; None means no action.
    """

    id_a: float | None
    accepted: bool
    reason: str
    coefficients: tuple[float, float, float] | None
    condition: float | None
    infeasible_probe_indices: tuple[int, ...] = ()


def fit_measured_loss_reference(
    probes: Iterable[ProbeMeasurement], config: MeasuredLossFitConfig
) -> MeasuredLossFitResult:
    """Fit positive a,b and bound (b/a)**0.25 to the probe hull and config.

    Repeated measurements are retained, but at least three distinct IDs are
    required. IDs outside the configured reference bounds may inform the fit;
    they cannot be fallback references. Any measured electrical violation
    blocks the fit. A scaled condition above 1e8 or residual norm above 10%
    of the centered power norm also blocks it. Three distinct probes cannot
    expose residual noise because there are three fitted coefficients.

    Rejections select the in-bounds, electrically feasible probe with minimum
    measured power (lower ID breaks ties), or return id_a=None if none exists.
    An interpolated proposal does not certify unmeasured electrical limits;
    the caller must retain online current/voltage protection and settling.
    Invalid numeric data/configuration raises ValueError, not a fallback.
    """
    if not isinstance(config, MeasuredLossFitConfig):
        raise TypeError("config must be a MeasuredLossFitConfig")
    measurements = tuple(probes)
    if not all(isinstance(probe, ProbeMeasurement) for probe in measurements):
        raise TypeError("probes must contain only ProbeMeasurement instances")

    infeasible = tuple(
        index
        for index, probe in enumerate(measurements)
        if probe.current_peak_a > config.current_limit_a
        or probe.voltage_peak_v > config.voltage_limit_v
    )
    feasible = [
        probe
        for probe in measurements
        if config.id_lower_a <= probe.id_a <= config.id_upper_a
        and probe.current_peak_a <= config.current_limit_a
        and probe.voltage_peak_v <= config.voltage_limit_v
    ]
    best = min(feasible, key=lambda probe: (probe.power_w, probe.id_a), default=None)
    coefficients = None
    condition = None

    def fallback(reason: str) -> MeasuredLossFitResult:
        return MeasuredLossFitResult(
            id_a=None if best is None else best.id_a,
            accepted=False,
            reason="no_feasible_probe" if best is None else reason,
            coefficients=coefficients,
            condition=condition,
            infeasible_probe_indices=infeasible,
        )

    if infeasible:
        return fallback("infeasible_measured_probes")
    if len({probe.id_a for probe in measurements}) < 3:
        return fallback("insufficient_distinct_probes")

    ids = np.array([probe.id_a for probe in measurements], dtype=float)
    lower = max(config.id_lower_a, float(ids.min()))
    upper = min(config.id_upper_a, float(ids.max()))
    if lower > upper:
        return fallback("no_interpolation_interval")

    powers = np.array([probe.power_w for probe in measurements], dtype=float)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        centered = powers - powers[0]
        # These are scaled i_d**2 and 1/i_d**2 without squaring large IDs.
        design = np.column_stack(
            ((ids / ids.max()) ** 2, (ids.min() / ids) ** 2, np.ones(ids.size))
        )
    if not np.all(np.isfinite(centered)):
        return fallback("numerical_failure")
    power_scale = float(np.max(np.abs(centered))) or 1.0
    target = centered / power_scale
    column_norms = np.linalg.norm(design, axis=0)
    scaled_design = design / column_norms
    try:
        fitted, _, rank, singular_values = np.linalg.lstsq(
            scaled_design, target, rcond=None
        )
    except np.linalg.LinAlgError:
        return fallback("numerical_failure")

    condition = (
        float(singular_values[0] / singular_values[-1])
        if singular_values[-1] > 0.0
        else math.inf
    )
    if rank < 3 or not math.isfinite(condition) or condition > _MAX_CONDITION:
        return fallback("ill_conditioned_probes")
    normalized = fitted / column_norms
    if not np.all(np.isfinite(normalized)):
        return fallback("numerical_failure")

    # Log rescaling avoids overflowing intermediate squares or products.
    def physical_coefficient(value: float, id_scale: float, exponent: int) -> float:
        if value == 0.0:
            return 0.0
        return math.copysign(
            math.exp(
                math.log(abs(value))
                + math.log(power_scale)
                + exponent * math.log(id_scale)
            ),
            value,
        )

    try:
        a = physical_coefficient(float(normalized[0]), float(ids.max()), -2)
        b = physical_coefficient(float(normalized[1]), float(ids.min()), 2)
        c = float(normalized[2]) * power_scale + float(powers[0])
    except OverflowError:
        return fallback("numerical_failure")
    if not all(math.isfinite(value) for value in (a, b, c)):
        return fallback("numerical_failure")
    coefficients = (a, b, c)
    if a <= 0.0 or b <= 0.0:
        return fallback("nonconvex_fit")

    variation = float(np.linalg.norm(target - target.mean()))
    residual = float(np.linalg.norm(scaled_design @ fitted - target))
    if variation == 0.0 or residual > _MAX_RELATIVE_RESIDUAL * variation:
        return fallback("poor_fit")

    optimum = math.exp((math.log(b) - math.log(a)) / 4.0)
    reference = min(max(optimum, lower), upper)
    return MeasuredLossFitResult(
        id_a=reference,
        accepted=True,
        reason="fit_accepted" if lower <= optimum <= upper else "fit_accepted_bounded",
        coefficients=coefficients,
        condition=condition,
        infeasible_probe_indices=infeasible,
    )

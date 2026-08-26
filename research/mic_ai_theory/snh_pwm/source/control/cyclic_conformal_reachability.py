from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Literal, Sequence

from control.cyclic_robust_viability_pwm import SECTOR_ANGLE, rotate_alpha_beta


DIMENSIONS = (
    "psi_s_alpha",
    "psi_s_beta",
    "psi_r_alpha",
    "psi_r_beta",
    "omega_m",
)
Method = Literal["raw_global", "sectorwise", "c6_canonical"]


@dataclass(frozen=True)
class ResidualSample:
    sector: int
    values: tuple[float, float, float, float, float]

    def __post_init__(self) -> None:
        if type(self.sector) is not int or not 0 <= self.sector < 6:
            raise ValueError("residual sample sector must be an integer in 0..5")
        if len(self.values) != len(DIMENSIONS):
            raise ValueError(f"residual sample must contain {len(DIMENSIONS)} dimensions")
        normalized = tuple(float(value) for value in self.values)
        if not all(math.isfinite(value) for value in normalized):
            raise ValueError("residual sample values must be finite")
        object.__setattr__(self, "values", normalized)


@dataclass(frozen=True)
class ResidualTrajectory:
    trajectory_id: int
    samples: tuple[ResidualSample, ...]

    def __post_init__(self) -> None:
        if type(self.trajectory_id) is not int:
            raise ValueError("trajectory_id must be an integer")
        if not self.samples:
            raise ValueError("residual trajectory must contain at least one sample")
        if not all(isinstance(sample, ResidualSample) for sample in self.samples):
            raise ValueError("trajectory samples must be ResidualSample instances")
        object.__setattr__(self, "samples", tuple(self.samples))


@dataclass(frozen=True)
class ConformalTube:
    method: Method
    alpha: float
    shape_quantile: float
    calibration_quantile: float
    finite_sample_rank: int
    training_trajectories: int
    calibration_trajectories: int
    scales_by_key: dict[int, tuple[float, float, float, float, float]]

    def key_for(self, sample: ResidualSample) -> int:
        return int(sample.sector) % 6 if self.method == "sectorwise" else 0

    def transformed_values(self, sample: ResidualSample) -> tuple[float, float, float, float, float]:
        if self.method != "c6_canonical":
            return sample.values
        angle = -(int(sample.sector) % 6) * SECTOR_ANGLE
        ss_a, ss_b = rotate_alpha_beta(sample.values[0], sample.values[1], angle)
        sr_a, sr_b = rotate_alpha_beta(sample.values[2], sample.values[3], angle)
        return ss_a, ss_b, sr_a, sr_b, sample.values[4]

    def half_widths(self, key: int = 0) -> tuple[float, float, float, float, float]:
        scales = self.scales_by_key[int(key)]
        return tuple(float(self.calibration_quantile) * value for value in scales)  # type: ignore[return-value]

    def trajectory_score(self, trajectory: ResidualTrajectory) -> float:
        score = 0.0
        for sample in trajectory.samples:
            values = self.transformed_values(sample)
            scales = self.scales_by_key[self.key_for(sample)]
            score = max(score, *(abs(value) / scale for value, scale in zip(values, scales)))
        return float(score)

    def covers(self, trajectory: ResidualTrajectory) -> bool:
        return self.trajectory_score(trajectory) <= self.calibration_quantile + 1.0e-15

    def log10_volume(self) -> float:
        logs: list[float] = []
        for key in sorted(self.scales_by_key):
            widths = self.half_widths(key)
            logs.append(sum(math.log10(max(2.0 * value, 1.0e-300)) for value in widths))
        return sum(logs) / max(len(logs), 1)


def _empirical_quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("at least one value is required")
    probability = max(0.0, min(1.0, float(probability)))
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, int(math.ceil(probability * len(ordered))) - 1))
    return ordered[index]


def split_conformal_quantile(scores: Sequence[float], alpha: float) -> tuple[float, int]:
    if not scores:
        raise ValueError("at least one calibration score is required")
    alpha = float(alpha)
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    ordered = sorted(float(score) for score in scores)
    if not all(math.isfinite(score) for score in ordered):
        raise ValueError("calibration scores must be finite")
    rank = int(math.ceil((len(ordered) + 1) * (1.0 - alpha)))
    if rank > len(ordered):
        return float("inf"), rank
    return ordered[rank - 1], rank


def _transform(method: Method, sample: ResidualSample) -> tuple[int, tuple[float, float, float, float, float]]:
    sector = int(sample.sector) % 6
    if method == "raw_global":
        return 0, sample.values
    if method == "sectorwise":
        return sector, sample.values
    angle = -sector * SECTOR_ANGLE
    ss_a, ss_b = rotate_alpha_beta(sample.values[0], sample.values[1], angle)
    sr_a, sr_b = rotate_alpha_beta(sample.values[2], sample.values[3], angle)
    return 0, (ss_a, ss_b, sr_a, sr_b, sample.values[4])


def fit_conformal_tube(
    training: Sequence[ResidualTrajectory],
    calibration: Sequence[ResidualTrajectory],
    *,
    method: Method,
    alpha: float = 0.05,
    shape_quantile: float = 0.80,
    scale_floor: float = 1.0e-12,
) -> ConformalTube:
    if not training or not calibration:
        raise ValueError("training and calibration trajectories must be non-empty")
    if method not in ("raw_global", "sectorwise", "c6_canonical"):
        raise ValueError(f"unsupported conformal method: {method!r}")
    if not math.isfinite(float(shape_quantile)) or not 0.0 < float(shape_quantile) <= 1.0:
        raise ValueError("shape_quantile must be finite and in (0, 1]")
    if not math.isfinite(float(scale_floor)) or float(scale_floor) <= 0.0:
        raise ValueError("scale_floor must be finite and positive")
    expected_keys = tuple(range(6)) if method == "sectorwise" else (0,)
    values_by_key: dict[int, list[tuple[float, float, float, float, float]]] = {
        key: [] for key in expected_keys
    }
    for trajectory in training:
        for sample in trajectory.samples:
            key, values = _transform(method, sample)
            values_by_key[key].append(values)

    scales: dict[int, tuple[float, float, float, float, float]] = {}
    for key, rows in values_by_key.items():
        if not rows:
            raise ValueError(f"training split has no samples for sector key {key}")
        dimension_scales = []
        for index in range(len(DIMENSIONS)):
            raw = [abs(row[index]) for row in rows]
            dimension_scales.append(max(float(scale_floor), _empirical_quantile(raw, shape_quantile)))
        scales[key] = tuple(dimension_scales)  # type: ignore[assignment]

    provisional = ConformalTube(
        method=method,
        alpha=float(alpha),
        shape_quantile=float(shape_quantile),
        calibration_quantile=1.0,
        finite_sample_rank=0,
        training_trajectories=len(training),
        calibration_trajectories=len(calibration),
        scales_by_key=scales,
    )
    scores = [provisional.trajectory_score(trajectory) for trajectory in calibration]
    quantile, rank = split_conformal_quantile(scores, alpha)
    return ConformalTube(
        method=method,
        alpha=float(alpha),
        shape_quantile=float(shape_quantile),
        calibration_quantile=float(quantile),
        finite_sample_rank=int(rank),
        training_trajectories=len(training),
        calibration_trajectories=len(calibration),
        scales_by_key=scales,
    )


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return float("nan"), float("nan")
    p = float(successes) / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    radius = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def binomial_lower_tail(successes: int, total: int, probability: float) -> float:
    if total <= 0:
        return float("nan")
    probability = max(0.0, min(1.0, float(probability)))
    if probability == 0.0:
        return 1.0
    if probability == 1.0:
        return 1.0 if successes >= total else 0.0
    successes = max(0, min(int(successes), int(total)))
    log_terms = [
        math.lgamma(total + 1)
        - math.lgamma(k + 1)
        - math.lgamma(total - k + 1)
        + k * math.log(probability)
        + (total - k) * math.log1p(-probability)
        for k in range(successes + 1)
    ]
    pivot = max(log_terms)
    cumulative = math.exp(pivot) * sum(math.exp(value - pivot) for value in log_terms)
    return max(0.0, min(1.0, cumulative))


def binomial_upper_tail(successes: int, total: int, probability: float) -> float:
    """Return P[X >= successes] for X ~ Binomial(total, probability)."""

    if total <= 0:
        return float("nan")
    successes = max(0, min(int(successes), int(total)))
    if successes <= 0:
        return 1.0
    return binomial_lower_tail(total - successes, total, 1.0 - float(probability))


def binomial_lower_confidence_bound(
    successes: int,
    total: int,
    *,
    error_probability: float = 0.01,
) -> float:
    """One-sided exact Clopper-Pearson lower confidence bound."""

    if total <= 0:
        return float("nan")
    successes = max(0, min(int(successes), int(total)))
    error_probability = float(error_probability)
    if not math.isfinite(error_probability) or not 0.0 < error_probability < 1.0:
        raise ValueError("error_probability must be finite and in (0, 1)")
    if successes == 0:
        return 0.0
    lo = 0.0
    hi = successes / total
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if binomial_upper_tail(successes, total, mid) < error_probability:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def evaluate_tube(tube: ConformalTube, trajectories: Iterable[ResidualTrajectory]) -> dict[str, float | int | bool]:
    rows = list(trajectories)
    covered = sum(1 for trajectory in rows if tube.covers(trajectory))
    total = len(rows)
    coverage = float(covered) / total if total else float("nan")
    low, high = wilson_interval(covered, total)
    target = 1.0 - tube.alpha
    undercoverage_p = binomial_lower_tail(covered, total, target)
    return {
        "covered_trajectories": covered,
        "total_trajectories": total,
        "empirical_coverage": coverage,
        "target_coverage": target,
        "wilson95_low": low,
        "wilson95_high": high,
        "undercoverage_p_value": undercoverage_p,
        "significant_undercoverage_1pct": bool(undercoverage_p < 0.01),
        "calibration_quantile": tube.calibration_quantile,
        "finite_sample_rank": tube.finite_sample_rank,
        "log10_volume": tube.log10_volume(),
    }


__all__ = [
    "ConformalTube",
    "DIMENSIONS",
    "Method",
    "ResidualSample",
    "ResidualTrajectory",
    "binomial_lower_confidence_bound",
    "binomial_lower_tail",
    "binomial_upper_tail",
    "evaluate_tube",
    "fit_conformal_tube",
    "split_conformal_quantile",
    "wilson_interval",
]

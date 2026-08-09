from __future__ import annotations

from dataclasses import dataclass, replace
import math
from random import Random
from typing import Literal, Sequence

import numpy as np

from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    AlphaBetaMotorState,
)
from models.two_level_inverter import TwoLevelInverterParams, alpha_beta_voltage

try:
    from scipy.optimize import least_squares
except Exception as exc:  # pragma: no cover - optional runtime dependency
    least_squares = None
    _SCIPY_IMPORT_ERROR = exc


PARAMETER_NAMES = ("Rs", "Rr", "Lm", "J", "B")
MOTOR_FIT_PARAMETER_NAMES = ("Rs", "Rr", "Lsigma", "Lm", "J", "B")
FIT_PARAMETER_NAMES = (*MOTOR_FIT_PARAMETER_NAMES, "Tload")
SEPARATE_LEAKAGE_PARAMETER_NAMES = ("Rs", "Rr", "Lls", "Llr", "Lm", "J", "B", "Tload")
LOAD_TORQUE_SCALE_NM = 0.01
ExcitationKind = Literal["fixed_sector", "random_prbs", "c6_multiscale"]


@dataclass(frozen=True)
class IdentificationExperiment:
    name: str
    dt: float
    v_alpha: tuple[float, ...]
    v_beta: tuple[float, ...]
    load_torque_nm: tuple[float, ...]
    rotor_locked: bool = False
    initial_omega_m: float = 0.0

    def __post_init__(self) -> None:
        lengths = {len(self.v_alpha), len(self.v_beta), len(self.load_torque_nm)}
        if lengths == {0} or len(lengths) != 1:
            raise ValueError("experiment input arrays must be non-empty and have equal length")
        if not math.isfinite(self.dt) or self.dt <= 0.0:
            raise ValueError("dt must be finite and positive")


@dataclass(frozen=True)
class IdentificationDataset:
    i_alpha: np.ndarray
    i_beta: np.ndarray
    omega_m: np.ndarray

    def stacked(self, noise_scales: tuple[float, float, float]) -> np.ndarray:
        if min(noise_scales) <= 0.0:
            raise ValueError("noise scales must be positive")
        return np.concatenate(
            (
                self.i_alpha / float(noise_scales[0]),
                self.i_beta / float(noise_scales[1]),
                self.omega_m / float(noise_scales[2]),
            )
        )


@dataclass(frozen=True)
class IdentifiabilityReport:
    parameter_names: tuple[str, ...]
    singular_values: tuple[float, ...]
    numerical_rank: int
    condition_number: float
    log10_fisher_determinant: float
    relative_column_norms: tuple[float, ...]
    max_abs_parameter_correlation: float
    identifiable: bool
    rank_tolerance: float
    condition_limit: float


@dataclass(frozen=True)
class ParameterEstimate:
    params: AlphaBetaMotorParams
    load_torque_nm: float
    normalized_rmse: float
    optimizer_cost: float
    successful_starts: int
    starts: int


def _active_vectors_by_angle(inverter: TwoLevelInverterParams) -> tuple[int, ...]:
    def angle(vector_id: int) -> float:
        alpha, beta = alpha_beta_voltage(vector_id, inverter)
        return math.atan2(beta, alpha)

    return tuple(sorted(range(1, 7), key=angle))


def _repeat_to_length(values: Sequence[int], length: int) -> list[int]:
    if not values:
        raise ValueError("values must be non-empty")
    return [int(values[index % len(values)]) for index in range(length)]


def _multiscale_locked_vectors(active: Sequence[int], length: int) -> list[int]:
    cycle: list[int] = []
    for dwell in (1, 2, 4, 8, 16):
        for vector_id in active:
            cycle.extend([int(vector_id)] * dwell)
            cycle.extend([0] * dwell)
    return _repeat_to_length(cycle, length)


def _rotating_vectors(active: Sequence[int], length: int, dwell: int = 4) -> list[int]:
    cycle: list[int] = []
    for vector_id in active:
        cycle.extend([int(vector_id)] * dwell)
    return _repeat_to_length(cycle, length)


def _c6_bidirectional_vectors(active: Sequence[int], length: int) -> list[int]:
    forward_length = int(0.40 * length)
    first_coast = int(0.10 * length)
    reverse_length = int(0.40 * length)
    final_coast = length - forward_length - first_coast - reverse_length
    return (
        _rotating_vectors(active, forward_length)
        + [0] * first_coast
        + _rotating_vectors(tuple(reversed(active)), reverse_length)
        + [0] * final_coast
    )


def make_excitation_suite(
    kind: ExcitationKind,
    *,
    steps_per_stage: int = 720,
    dt: float = 5.0e-4,
    vdc: float = 24.0,
    seed: int = 0,
) -> tuple[IdentificationExperiment, ...]:
    """Build standstill, driven, and measured-speed coast experiments.

    The C6 profile visits every active inverter-vector orbit at several dwell
    times, then applies a balanced rotating sequence. No motor parameter is used
    while constructing the profile.
    """

    if steps_per_stage < 48:
        raise ValueError("steps_per_stage must be at least 48")
    inverter = TwoLevelInverterParams(Vdc=float(vdc))
    active = _active_vectors_by_angle(inverter)

    if kind == "fixed_sector":
        pulse = [active[0]] * 12 + [0] * 12
        locked_vectors = _repeat_to_length(pulse, steps_per_stage)
        free_vectors = [active[0]] * steps_per_stage
    elif kind == "random_prbs":
        rng = Random(seed)
        candidates = (0, 0, *active)
        locked_vectors = [int(rng.choice(candidates)) for _ in range(steps_per_stage)]
        free_vectors = [int(rng.choice(candidates)) for _ in range(steps_per_stage)]
    elif kind == "c6_multiscale":
        locked_vectors = _multiscale_locked_vectors(active, steps_per_stage)
        free_vectors = _c6_bidirectional_vectors(active, steps_per_stage)
    else:  # pragma: no cover - protected by Literal for typed callers
        raise ValueError(f"unknown excitation kind: {kind}")

    def voltages(vector_ids: Sequence[int]) -> tuple[tuple[float, ...], tuple[float, ...]]:
        rows = [alpha_beta_voltage(vector_id, inverter) for vector_id in vector_ids]
        return tuple(row[0] for row in rows), tuple(row[1] for row in rows)

    locked_alpha, locked_beta = voltages(locked_vectors)
    free_alpha, free_beta = voltages(free_vectors)
    zero_load = (0.0,) * steps_per_stage
    coast_steps = 500
    coast_dt = 0.01
    return (
        IdentificationExperiment(
            name=f"{kind}_standstill",
            dt=float(dt),
            v_alpha=locked_alpha,
            v_beta=locked_beta,
            load_torque_nm=zero_load,
            rotor_locked=True,
        ),
        IdentificationExperiment(
            name=f"{kind}_free_run",
            dt=float(dt),
            v_alpha=free_alpha,
            v_beta=free_beta,
            load_torque_nm=zero_load,
            rotor_locked=False,
        ),
        IdentificationExperiment(
            name=f"{kind}_measured_speed_coast",
            dt=coast_dt,
            v_alpha=(0.0,) * coast_steps,
            v_beta=(0.0,) * coast_steps,
            load_torque_nm=(0.0,) * coast_steps,
            rotor_locked=False,
            initial_omega_m=20.0,
        ),
    )


def simulate_identification_experiments(
    params: AlphaBetaMotorParams,
    experiments: Sequence[IdentificationExperiment],
) -> IdentificationDataset:
    i_alpha: list[float] = []
    i_beta: list[float] = []
    omega_m: list[float] = []

    for experiment in experiments:
        model = AlphaBetaInductionMotorModel(
            params,
            AlphaBetaMotorState(omega_m=float(experiment.initial_omega_m)),
        )
        for v_alpha, v_beta, load_torque in zip(
            experiment.v_alpha,
            experiment.v_beta,
            experiment.load_torque_nm,
        ):
            result = model.step(v_alpha, v_beta, load_torque, experiment.dt)
            if experiment.rotor_locked:
                model.state = replace(result.state, omega_m=0.0, theta_m=0.0)
                currents = model.currents()
                i_alpha.append(float(currents.i_s_alpha))
                i_beta.append(float(currents.i_s_beta))
                omega_m.append(0.0)
            else:
                i_alpha.append(float(result.currents.i_s_alpha))
                i_beta.append(float(result.currents.i_s_beta))
                omega_m.append(float(result.state.omega_m))

    dataset = IdentificationDataset(
        i_alpha=np.asarray(i_alpha, dtype=float),
        i_beta=np.asarray(i_beta, dtype=float),
        omega_m=np.asarray(omega_m, dtype=float),
    )
    if not np.all(np.isfinite(dataset.stacked((1.0, 1.0, 1.0)))):
        raise FloatingPointError("motor simulation produced non-finite outputs")
    return dataset


def add_measurement_noise(
    dataset: IdentificationDataset,
    *,
    noise_scales: tuple[float, float, float],
    seed: int,
) -> IdentificationDataset:
    rng = np.random.default_rng(seed)
    return IdentificationDataset(
        i_alpha=dataset.i_alpha + rng.normal(0.0, noise_scales[0], dataset.i_alpha.shape),
        i_beta=dataset.i_beta + rng.normal(0.0, noise_scales[1], dataset.i_beta.shape),
        omega_m=dataset.omega_m + rng.normal(0.0, noise_scales[2], dataset.omega_m.shape),
    )


def _replace_identified_params(
    template: AlphaBetaMotorParams,
    values: Sequence[float],
) -> AlphaBetaMotorParams:
    if len(values) != len(MOTOR_FIT_PARAMETER_NAMES):
        raise ValueError("parameter vector length mismatch")
    updates = {name: float(value) for name, value in zip(MOTOR_FIT_PARAMETER_NAMES, values)}
    if min(updates.values()) <= 0.0:
        raise ValueError("identified parameters must be positive")
    leakage = updates.pop("Lsigma")
    return replace(template, Lls=leakage, Llr=leakage, **updates)


def parameter_vector(params: AlphaBetaMotorParams) -> np.ndarray:
    leakage = 0.5 * (float(params.Lls) + float(params.Llr))
    return np.asarray(
        [params.Rs, params.Rr, leakage, params.Lm, params.J, params.B],
        dtype=float,
    )


def with_free_run_load_bias(
    experiments: Sequence[IdentificationExperiment],
    load_torque_nm: float,
) -> tuple[IdentificationExperiment, ...]:
    bias = float(load_torque_nm)
    return tuple(
        experiment
        if experiment.rotor_locked
        else replace(
            experiment,
            load_torque_nm=tuple(float(value) + bias for value in experiment.load_torque_nm),
        )
        for experiment in experiments
    )


def sensitivity_matrix(
    nominal: AlphaBetaMotorParams,
    experiments: Sequence[IdentificationExperiment],
    *,
    noise_scales: tuple[float, float, float] = (0.01, 0.01, 0.05),
    relative_step: float = 1.0e-4,
) -> np.ndarray:
    """Finite-difference sensitivity with respect to log physical parameters."""

    if not 0.0 < relative_step < 0.1:
        raise ValueError("relative_step must be in (0, 0.1)")
    nominal_values = parameter_vector(nominal)
    columns: list[np.ndarray] = []
    for index in range(len(MOTOR_FIT_PARAMETER_NAMES)):
        plus = nominal_values.copy()
        minus = nominal_values.copy()
        plus[index] *= math.exp(relative_step)
        minus[index] *= math.exp(-relative_step)
        y_plus = simulate_identification_experiments(
            _replace_identified_params(nominal, plus), experiments
        ).stacked(noise_scales)
        y_minus = simulate_identification_experiments(
            _replace_identified_params(nominal, minus), experiments
        ).stacked(noise_scales)
        columns.append((y_plus - y_minus) / (2.0 * relative_step))
    plus_load = with_free_run_load_bias(experiments, LOAD_TORQUE_SCALE_NM * relative_step)
    minus_load = with_free_run_load_bias(experiments, -LOAD_TORQUE_SCALE_NM * relative_step)
    y_plus = simulate_identification_experiments(nominal, plus_load).stacked(noise_scales)
    y_minus = simulate_identification_experiments(nominal, minus_load).stacked(noise_scales)
    columns.append((y_plus - y_minus) / (2.0 * relative_step))
    return np.column_stack(columns)


def separate_leakage_sensitivity_matrix(
    nominal: AlphaBetaMotorParams,
    experiments: Sequence[IdentificationExperiment],
    *,
    noise_scales: tuple[float, float, float] = (0.01, 0.01, 0.05),
    relative_step: float = 1.0e-4,
) -> np.ndarray:
    """Audit whether stator and rotor leakage can be estimated separately."""

    if not 0.0 < relative_step < 0.1:
        raise ValueError("relative_step must be in (0, 0.1)")
    columns: list[np.ndarray] = []
    for name in SEPARATE_LEAKAGE_PARAMETER_NAMES:
        if name == "Tload":
            plus_load = with_free_run_load_bias(experiments, LOAD_TORQUE_SCALE_NM * relative_step)
            minus_load = with_free_run_load_bias(experiments, -LOAD_TORQUE_SCALE_NM * relative_step)
            y_plus = simulate_identification_experiments(nominal, plus_load).stacked(noise_scales)
            y_minus = simulate_identification_experiments(nominal, minus_load).stacked(noise_scales)
            columns.append((y_plus - y_minus) / (2.0 * relative_step))
            continue
        nominal_value = float(getattr(nominal, name))
        plus = replace(nominal, **{name: nominal_value * math.exp(relative_step)})
        minus = replace(nominal, **{name: nominal_value * math.exp(-relative_step)})
        y_plus = simulate_identification_experiments(plus, experiments).stacked(noise_scales)
        y_minus = simulate_identification_experiments(minus, experiments).stacked(noise_scales)
        columns.append((y_plus - y_minus) / (2.0 * relative_step))
    return np.column_stack(columns)


def analyze_identifiability(
    sensitivity: np.ndarray,
    *,
    parameter_names: Sequence[str] = FIT_PARAMETER_NAMES,
    rank_tolerance: float = 1.0e-7,
    condition_limit: float = 1.0e8,
) -> IdentifiabilityReport:
    matrix = np.asarray(sensitivity, dtype=float)
    names = tuple(str(name) for name in parameter_names)
    if not names or matrix.ndim != 2 or matrix.shape[1] != len(names):
        raise ValueError(f"sensitivity must have shape (n, {len(names)})")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("sensitivity contains non-finite values")

    singular_values = np.linalg.svd(matrix, compute_uv=False)
    threshold = float(rank_tolerance) * max(float(singular_values[0]), 1.0)
    rank = int(np.count_nonzero(singular_values > threshold))
    condition = (
        float(singular_values[0] / singular_values[-1])
        if singular_values[-1] > 0.0
        else float("inf")
    )
    column_norms = np.linalg.norm(matrix, axis=0)
    max_norm = max(float(np.max(column_norms)), 1.0e-300)
    relative_norms = column_norms / max_norm

    fisher = matrix.T @ matrix
    sign, logdet = np.linalg.slogdet(fisher)
    log10_det = float(logdet / math.log(10.0)) if sign > 0 else float("-inf")
    covariance = np.linalg.pinv(fisher, rcond=rank_tolerance)
    std = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    denom = np.outer(std, std)
    correlation = np.divide(covariance, denom, out=np.zeros_like(covariance), where=denom > 0.0)
    correlation = np.clip(correlation, -1.0, 1.0)
    off_diagonal = correlation - np.diag(np.diag(correlation))
    max_correlation = float(np.max(np.abs(off_diagonal)))

    return IdentifiabilityReport(
        parameter_names=names,
        singular_values=tuple(float(value) for value in singular_values),
        numerical_rank=rank,
        condition_number=condition,
        log10_fisher_determinant=log10_det,
        relative_column_norms=tuple(float(value) for value in relative_norms),
        max_abs_parameter_correlation=max_correlation,
        identifiable=rank == len(names) and condition <= float(condition_limit),
        rank_tolerance=float(rank_tolerance),
        condition_limit=float(condition_limit),
    )


def estimate_parameters(
    observed: IdentificationDataset,
    prior: AlphaBetaMotorParams,
    experiments: Sequence[IdentificationExperiment],
    *,
    noise_scales: tuple[float, float, float] = (0.01, 0.01, 0.05),
    starts: int = 5,
    seed: int = 0,
    bound_factor: float = 4.0,
    max_nfev: int = 160,
) -> ParameterEstimate:
    """Bounded multi-start prediction-error fit in log-parameter space."""

    if least_squares is None:  # pragma: no cover - dependency checked in CI
        raise ImportError(f"scipy is required for identification: {_SCIPY_IMPORT_ERROR}")
    if starts < 1:
        raise ValueError("starts must be positive")
    if bound_factor <= 1.0:
        raise ValueError("bound_factor must exceed one")

    target = observed.stacked(noise_scales)
    prior_log = np.log(parameter_vector(prior))
    delta = math.log(float(bound_factor))
    lower = np.concatenate((prior_log - delta, np.asarray([-2.0])))
    upper = np.concatenate((prior_log + delta, np.asarray([2.0])))
    prior_vector = np.concatenate((prior_log, np.asarray([0.0])))
    rng = np.random.default_rng(seed)

    def residual(fit_values: np.ndarray) -> np.ndarray:
        try:
            candidate = _replace_identified_params(prior, np.exp(fit_values[:-1]))
            candidate_experiments = with_free_run_load_bias(
                experiments,
                float(fit_values[-1]) * LOAD_TORQUE_SCALE_NM,
            )
            modeled = simulate_identification_experiments(candidate, candidate_experiments).stacked(noise_scales)
            if modeled.shape != target.shape or not np.all(np.isfinite(modeled)):
                raise FloatingPointError
            return modeled - target
        except (FloatingPointError, OverflowError, ValueError):
            return np.full_like(target, 1.0e12)

    best = None
    successful = 0
    for start_index in range(starts):
        if start_index == 0:
            x0 = prior_vector.copy()
        else:
            x0 = np.clip(prior_vector + rng.normal(0.0, 0.35, prior_vector.shape), lower, upper)
        result = least_squares(
            residual,
            x0=x0,
            bounds=(lower, upper),
            method="trf",
            max_nfev=int(max_nfev),
        )
        if result.success and np.all(np.isfinite(result.x)):
            successful += 1
        if best is None or float(result.cost) < float(best.cost):
            best = result

    if best is None:  # pragma: no cover - starts is checked above
        raise RuntimeError("parameter optimizer did not run")
    fitted = _replace_identified_params(prior, np.exp(best.x[:-1]))
    normalized_rmse = math.sqrt(2.0 * float(best.cost) / max(target.size, 1))
    return ParameterEstimate(
        params=fitted,
        load_torque_nm=float(best.x[-1]) * LOAD_TORQUE_SCALE_NM,
        normalized_rmse=float(normalized_rmse),
        optimizer_cost=float(best.cost),
        successful_starts=int(successful),
        starts=int(starts),
    )


def relative_parameter_errors(
    estimate: AlphaBetaMotorParams,
    truth: AlphaBetaMotorParams,
) -> dict[str, float]:
    return {
        name: abs(float(getattr(estimate, name)) - float(getattr(truth, name)))
        / abs(float(getattr(truth, name)))
        for name in PARAMETER_NAMES
    }


__all__ = [
    "ExcitationKind",
    "FIT_PARAMETER_NAMES",
    "LOAD_TORQUE_SCALE_NM",
    "MOTOR_FIT_PARAMETER_NAMES",
    "IdentificationDataset",
    "IdentificationExperiment",
    "IdentifiabilityReport",
    "PARAMETER_NAMES",
    "SEPARATE_LEAKAGE_PARAMETER_NAMES",
    "ParameterEstimate",
    "add_measurement_noise",
    "analyze_identifiability",
    "estimate_parameters",
    "make_excitation_suite",
    "parameter_vector",
    "relative_parameter_errors",
    "sensitivity_matrix",
    "separate_leakage_sensitivity_matrix",
    "simulate_identification_experiments",
    "with_free_run_load_bias",
]

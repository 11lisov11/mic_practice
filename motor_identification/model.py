from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping, Sequence

import numpy as np

try:
    from scipy.optimize import least_squares
except Exception as exc:  # pragma: no cover - reported by the CLI
    least_squares = None
    SCIPY_IMPORT_ERROR = exc


MOTOR_PARAMETER_NAMES = ("Rs", "Rr", "Lsigma", "Lm", "J", "B")
FIT_PARAMETER_NAMES = (*MOTOR_PARAMETER_NAMES, "Tload")


@dataclass(frozen=True)
class MotorParameters:
    Rs: float
    Rr: float
    Lsigma: float
    Lm: float
    J: float
    B: float
    pole_pairs: int
    i_limit: float
    load_torque_scale_nm: float

    def __post_init__(self) -> None:
        positive = (
            self.Rs,
            self.Rr,
            self.Lsigma,
            self.Lm,
            self.J,
            self.B,
            self.i_limit,
            self.load_torque_scale_nm,
        )
        if not all(math.isfinite(float(value)) and float(value) > 0.0 for value in positive):
            raise ValueError("all motor parameters, i_limit, and load_torque_scale_nm must be finite and positive")
        if int(self.pole_pairs) < 1:
            raise ValueError("pole_pairs must be positive")

    def as_dict(self) -> dict[str, float | int]:
        return {
            "Rs_ohm": float(self.Rs),
            "Rr_ohm": float(self.Rr),
            "Lsigma_h": float(self.Lsigma),
            "Lm_h": float(self.Lm),
            "J_kg_m2": float(self.J),
            "B_nm_s": float(self.B),
            "pole_pairs": int(self.pole_pairs),
            "i_limit_a": float(self.i_limit),
        }

    def as_mic_ai_estimated_dict(self) -> dict[str, float]:
        total_inductance = float(self.Lm + self.Lsigma)
        return {
            "Rs": float(self.Rs),
            "Rr": float(self.Rr),
            "Ls": total_inductance,
            "Lr": total_inductance,
            "Lm": float(self.Lm),
            "J": float(self.J),
            "B": float(self.B),
        }


@dataclass(frozen=True)
class MotorState:
    psi_s_alpha: float = 0.0
    psi_s_beta: float = 0.0
    psi_r_alpha: float = 0.0
    psi_r_beta: float = 0.0
    omega_m: float = 0.0


@dataclass(frozen=True)
class ExperimentInput:
    experiment_id: str
    kind: str
    rotor_locked: bool
    dt: float
    initial_omega_m: float
    v_alpha: np.ndarray
    v_beta: np.ndarray


@dataclass(frozen=True)
class Observations:
    i_alpha: np.ndarray
    i_beta: np.ndarray
    omega_m: np.ndarray

    def stacked(self, noise_scales: tuple[float, float, float]) -> np.ndarray:
        if not all(math.isfinite(value) and value > 0.0 for value in noise_scales):
            raise ValueError("noise scales must be finite and positive")
        return np.concatenate(
            (
                self.i_alpha / noise_scales[0],
                self.i_beta / noise_scales[1],
                self.omega_m / noise_scales[2],
            )
        )


@dataclass(frozen=True)
class RankReport:
    parameter_names: tuple[str, ...]
    singular_values: tuple[float, ...]
    numerical_rank: int
    condition_number: float
    log10_fisher_determinant: float
    max_abs_parameter_correlation: float
    identifiable: bool
    rank_tolerance: float
    condition_limit: float

    def as_dict(self) -> dict[str, object]:
        return {
            "parameter_names": list(self.parameter_names),
            "singular_values": list(self.singular_values),
            "numerical_rank": self.numerical_rank,
            "required_rank": len(self.parameter_names),
            "condition_number": self.condition_number,
            "log10_fisher_determinant": self.log10_fisher_determinant,
            "max_abs_parameter_correlation": self.max_abs_parameter_correlation,
            "identifiable": self.identifiable,
            "rank_tolerance": self.rank_tolerance,
            "condition_limit": self.condition_limit,
        }


@dataclass(frozen=True)
class Estimate:
    params: MotorParameters
    load_torque_nm: float
    normalized_rmse: float
    optimizer_cost: float
    successful_starts: int
    starts: int
    hit_bound: bool


def _currents(params: MotorParameters, state: MotorState) -> tuple[float, float, float, float]:
    ls = float(params.Lsigma + params.Lm)
    lr = float(params.Lsigma + params.Lm)
    lm = float(params.Lm)
    denominator = ls * lr - lm * lm
    if denominator <= 1.0e-15:
        raise FloatingPointError("invalid inductance matrix")
    i_s_alpha = (state.psi_s_alpha * lr - state.psi_r_alpha * lm) / denominator
    i_s_beta = (state.psi_s_beta * lr - state.psi_r_beta * lm) / denominator
    i_r_alpha = (state.psi_r_alpha * ls - state.psi_s_alpha * lm) / denominator
    i_r_beta = (state.psi_r_beta * ls - state.psi_s_beta * lm) / denominator
    return i_s_alpha, i_s_beta, i_r_alpha, i_r_beta


def _step(
    params: MotorParameters,
    state: MotorState,
    v_alpha: float,
    v_beta: float,
    load_torque_nm: float,
    dt: float,
    rotor_locked: bool,
) -> tuple[MotorState, float, float]:
    i_s_alpha, i_s_beta, i_r_alpha, i_r_beta = _currents(params, state)
    omega_e = float(params.pole_pairs) * state.omega_m
    dpsi_s_alpha = float(v_alpha) - params.Rs * i_s_alpha
    dpsi_s_beta = float(v_beta) - params.Rs * i_s_beta
    dpsi_r_alpha = -params.Rr * i_r_alpha - omega_e * state.psi_r_beta
    dpsi_r_beta = -params.Rr * i_r_beta + omega_e * state.psi_r_alpha
    torque = 1.5 * float(params.pole_pairs) * (
        state.psi_s_alpha * i_s_beta - state.psi_s_beta * i_s_alpha
    )
    omega_next = 0.0 if rotor_locked else state.omega_m + dt * (
        torque - load_torque_nm - params.B * state.omega_m
    ) / params.J
    next_state = MotorState(
        psi_s_alpha=state.psi_s_alpha + dt * dpsi_s_alpha,
        psi_s_beta=state.psi_s_beta + dt * dpsi_s_beta,
        psi_r_alpha=state.psi_r_alpha + dt * dpsi_r_alpha,
        psi_r_beta=state.psi_r_beta + dt * dpsi_r_beta,
        omega_m=omega_next,
    )
    next_i_alpha, next_i_beta, _, _ = _currents(params, next_state)
    return next_state, next_i_alpha, next_i_beta


def simulate(
    params: MotorParameters,
    experiments: Sequence[ExperimentInput],
    *,
    load_torque_nm: float = 0.0,
) -> Observations:
    i_alpha: list[float] = []
    i_beta: list[float] = []
    omega: list[float] = []
    for experiment in experiments:
        state = MotorState(omega_m=float(experiment.initial_omega_m))
        experiment_load = 0.0 if experiment.rotor_locked else float(load_torque_nm)
        for v_alpha, v_beta in zip(experiment.v_alpha, experiment.v_beta):
            state, current_alpha, current_beta = _step(
                params,
                state,
                float(v_alpha),
                float(v_beta),
                experiment_load,
                float(experiment.dt),
                bool(experiment.rotor_locked),
            )
            i_alpha.append(float(current_alpha))
            i_beta.append(float(current_beta))
            omega.append(float(state.omega_m))
    result = Observations(np.asarray(i_alpha), np.asarray(i_beta), np.asarray(omega))
    if not np.all(np.isfinite(result.stacked((1.0, 1.0, 1.0)))):
        raise FloatingPointError("motor simulation produced non-finite outputs")
    return result


def parameter_vector(params: MotorParameters) -> np.ndarray:
    return np.asarray([getattr(params, name) for name in MOTOR_PARAMETER_NAMES], dtype=float)


def replace_parameters(template: MotorParameters, values: Sequence[float]) -> MotorParameters:
    if len(values) != len(MOTOR_PARAMETER_NAMES):
        raise ValueError("parameter vector length mismatch")
    updates = {name: float(value) for name, value in zip(MOTOR_PARAMETER_NAMES, values)}
    if not all(math.isfinite(value) and value > 0.0 for value in updates.values()):
        raise ValueError("fitted parameters must be finite and positive")
    return replace(template, **updates)


def sensitivity_matrix(
    nominal: MotorParameters,
    experiments: Sequence[ExperimentInput],
    noise_scales: tuple[float, float, float],
    *,
    relative_step: float = 1.0e-4,
) -> np.ndarray:
    if not 0.0 < relative_step < 0.1:
        raise ValueError("relative_step must be in (0, 0.1)")
    nominal_values = parameter_vector(nominal)
    columns: list[np.ndarray] = []
    for index in range(len(MOTOR_PARAMETER_NAMES)):
        plus = nominal_values.copy()
        minus = nominal_values.copy()
        plus[index] *= math.exp(relative_step)
        minus[index] *= math.exp(-relative_step)
        y_plus = simulate(replace_parameters(nominal, plus), experiments).stacked(noise_scales)
        y_minus = simulate(replace_parameters(nominal, minus), experiments).stacked(noise_scales)
        columns.append((y_plus - y_minus) / (2.0 * relative_step))
    y_plus = simulate(
        nominal,
        experiments,
        load_torque_nm=nominal.load_torque_scale_nm * relative_step,
    ).stacked(noise_scales)
    y_minus = simulate(
        nominal,
        experiments,
        load_torque_nm=-nominal.load_torque_scale_nm * relative_step,
    ).stacked(noise_scales)
    columns.append((y_plus - y_minus) / (2.0 * relative_step))
    return np.column_stack(columns)


def analyze_rank(
    sensitivity: np.ndarray,
    *,
    rank_tolerance: float = 1.0e-7,
    condition_limit: float = 1.0e8,
) -> RankReport:
    matrix = np.asarray(sensitivity, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(FIT_PARAMETER_NAMES):
        raise ValueError(f"sensitivity must have {len(FIT_PARAMETER_NAMES)} columns")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("sensitivity contains non-finite values")
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    threshold = rank_tolerance * max(float(singular_values[0]), 1.0)
    rank = int(np.count_nonzero(singular_values > threshold))
    condition = (
        float(singular_values[0] / singular_values[-1])
        if singular_values[-1] > 0.0
        else float("inf")
    )
    fisher = matrix.T @ matrix
    sign, logdet = np.linalg.slogdet(fisher)
    log10_det = float(logdet / math.log(10.0)) if sign > 0 else float("-inf")
    covariance = np.linalg.pinv(fisher, rcond=rank_tolerance)
    std = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    denominator = np.outer(std, std)
    correlation = np.divide(
        covariance,
        denominator,
        out=np.zeros_like(covariance),
        where=denominator > 0.0,
    )
    off_diagonal = correlation - np.diag(np.diag(correlation))
    max_correlation = float(np.max(np.abs(off_diagonal)))
    return RankReport(
        parameter_names=FIT_PARAMETER_NAMES,
        singular_values=tuple(float(value) for value in singular_values),
        numerical_rank=rank,
        condition_number=condition,
        log10_fisher_determinant=log10_det,
        max_abs_parameter_correlation=max_correlation,
        identifiable=rank == len(FIT_PARAMETER_NAMES) and condition <= condition_limit,
        rank_tolerance=float(rank_tolerance),
        condition_limit=float(condition_limit),
    )


def fit_parameters(
    observed: Observations,
    prior: MotorParameters,
    experiments: Sequence[ExperimentInput],
    noise_scales: tuple[float, float, float],
    *,
    starts: int = 5,
    seed: int = 0,
    bound_factor: float = 4.0,
    max_nfev: int = 160,
) -> Estimate:
    if least_squares is None:  # pragma: no cover
        raise ImportError(f"scipy is required for identification: {SCIPY_IMPORT_ERROR}")
    if starts < 1:
        raise ValueError("starts must be positive")
    if bound_factor <= 1.0:
        raise ValueError("bound_factor must exceed one")
    target = observed.stacked(noise_scales)
    prior_log = np.log(parameter_vector(prior))
    delta = math.log(bound_factor)
    lower = np.concatenate((prior_log - delta, np.asarray([-2.0])))
    upper = np.concatenate((prior_log + delta, np.asarray([2.0])))
    initial = np.concatenate((prior_log, np.asarray([0.0])))
    rng = np.random.default_rng(seed)

    def residual(values: np.ndarray) -> np.ndarray:
        try:
            candidate = replace_parameters(prior, np.exp(values[:-1]))
            modeled = simulate(
                candidate,
                experiments,
                load_torque_nm=float(values[-1]) * prior.load_torque_scale_nm,
            ).stacked(noise_scales)
            if modeled.shape != target.shape or not np.all(np.isfinite(modeled)):
                raise FloatingPointError
            return modeled - target
        except (FloatingPointError, OverflowError, ValueError):
            return np.full_like(target, 1.0e12)

    best = None
    successful = 0
    for start_index in range(starts):
        x0 = initial.copy() if start_index == 0 else np.clip(
            initial + rng.normal(0.0, 0.35, initial.shape), lower, upper
        )
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
    if best is None:  # pragma: no cover
        raise RuntimeError("optimizer did not run")
    fitted = replace_parameters(prior, np.exp(best.x[:-1]))
    margin = 1.0e-5
    hit_bound = bool(np.any(best.x <= lower + margin) or np.any(best.x >= upper - margin))
    normalized_rmse = math.sqrt(2.0 * float(best.cost) / max(target.size, 1))
    return Estimate(
        params=fitted,
        load_torque_nm=float(best.x[-1]) * prior.load_torque_scale_nm,
        normalized_rmse=normalized_rmse,
        optimizer_cost=float(best.cost),
        successful_starts=successful,
        starts=starts,
        hit_bound=hit_bound,
    )


def metrics(
    observed: Observations,
    modeled: Observations,
    noise_scales: tuple[float, float, float],
) -> dict[str, float]:
    residuals = (
        modeled.i_alpha - observed.i_alpha,
        modeled.i_beta - observed.i_beta,
        modeled.omega_m - observed.omega_m,
    )
    names = ("i_alpha_a", "i_beta_a", "omega_rad_s")
    result: dict[str, float] = {}
    normalized_parts: list[np.ndarray] = []
    for name, residual, scale in zip(names, residuals, noise_scales):
        result[f"{name}_rmse"] = float(math.sqrt(float(np.mean(residual * residual))))
        normalized_parts.append(residual / scale)
    normalized = np.concatenate(normalized_parts)
    result["normalized_rmse"] = float(math.sqrt(float(np.mean(normalized * normalized))))
    result["max_abs_normalized_residual"] = float(np.max(np.abs(normalized)))
    return result


def approximate_confidence_intervals(
    estimate: Estimate,
    experiments: Sequence[ExperimentInput],
    noise_scales: tuple[float, float, float],
    residual_nrmse: float,
) -> dict[str, dict[str, float]]:
    sensitivity = sensitivity_matrix(estimate.params, experiments, noise_scales)
    covariance = np.linalg.pinv(sensitivity.T @ sensitivity, rcond=1.0e-7)
    covariance *= max(float(residual_nrmse) ** 2, 1.0e-12)
    std = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    intervals: dict[str, dict[str, float]] = {}
    for index, name in enumerate(MOTOR_PARAMETER_NAMES):
        point = float(getattr(estimate.params, name))
        intervals[name] = {
            "estimate": point,
            "lower_95": point * math.exp(-1.96 * float(std[index])),
            "upper_95": point * math.exp(1.96 * float(std[index])),
            "log_std": float(std[index]),
        }
    load_std = float(std[-1]) * estimate.params.load_torque_scale_nm
    intervals["Tload"] = {
        "estimate": float(estimate.load_torque_nm),
        "lower_95": float(estimate.load_torque_nm - 1.96 * load_std),
        "upper_95": float(estimate.load_torque_nm + 1.96 * load_std),
        "std": load_std,
    }
    return intervals


def prior_from_payload(payload: Mapping[str, object]) -> MotorParameters:
    aliases = {
        "Rs": "Rs_ohm",
        "Rr": "Rr_ohm",
        "Lsigma": "Lsigma_h",
        "Lm": "Lm_h",
        "J": "J_kg_m2",
        "B": "B_nm_s",
        "pole_pairs": "pole_pairs",
        "i_limit": "i_limit_a",
        "load_torque_scale_nm": "load_torque_scale_nm",
    }
    values: dict[str, float | int] = {}
    for target, source in aliases.items():
        if source not in payload:
            raise ValueError(f"prior is missing {source}")
        values[target] = int(payload[source]) if target == "pole_pairs" else float(payload[source])
    return MotorParameters(**values)  # type: ignore[arg-type]


__all__ = [
    "FIT_PARAMETER_NAMES",
    "MOTOR_PARAMETER_NAMES",
    "Estimate",
    "ExperimentInput",
    "MotorParameters",
    "Observations",
    "RankReport",
    "analyze_rank",
    "approximate_confidence_intervals",
    "fit_parameters",
    "metrics",
    "prior_from_payload",
    "sensitivity_matrix",
    "simulate",
]

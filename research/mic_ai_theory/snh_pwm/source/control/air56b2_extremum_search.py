from __future__ import annotations

from dataclasses import dataclass
import math

from models.air56b2_loss_thermal import (
    Air56B2LossModelParams,
    LossBreakdown,
    MotorThermalState,
    evaluate_operating_point,
)


@dataclass(frozen=True)
class BoundedExtremumSearchResult:
    optimum: LossBreakdown
    initial: LossBreakdown
    evaluated_points: int
    iterations: int
    final_step_a: float
    id_lower_a: float
    id_upper_a: float


def bounded_extremum_search(
    params: Air56B2LossModelParams,
    *,
    speed_rad_s: float,
    torque_nm: float,
    initial_id_a: float,
    id_lower_a: float,
    id_upper_a: float,
    thermal_state: MotorThermalState | None = None,
    initial_step_a: float = 0.24,
    minimum_step_a: float = 0.005,
    max_iterations: int = 24,
) -> BoundedExtremumSearchResult:
    """Minimize a measurable loss proxy without using motor-model derivatives.

    This deterministic bounded search is a simulation proxy for a future online
    extremum-seeking loop. The caller supplies the loss evaluation through the
    shared plant model here; hardware use still requires a validated electrical
    loss estimator, settling logic, and the normal current/voltage protections.
    """

    values = (
        initial_id_a,
        id_lower_a,
        id_upper_a,
        initial_step_a,
        minimum_step_a,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("search inputs must be finite")
    if id_lower_a <= 0.0 or id_upper_a <= id_lower_a:
        raise ValueError("id bounds must satisfy 0 < lower < upper")
    if initial_step_a <= 0.0 or minimum_step_a <= 0.0:
        raise ValueError("search steps must be positive")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be positive")

    initial_id = min(max(float(initial_id_a), float(id_lower_a)), float(id_upper_a))
    cache: dict[float, LossBreakdown] = {}

    def evaluate(id_a: float) -> LossBreakdown:
        bounded = min(max(float(id_a), float(id_lower_a)), float(id_upper_a))
        key = round(bounded, 12)
        if key not in cache:
            cache[key] = evaluate_operating_point(
                params,
                speed_rad_s=speed_rad_s,
                torque_nm=torque_nm,
                id_a=bounded,
                thermal_state=thermal_state,
            )
        return cache[key]

    initial = evaluate(initial_id)
    if not initial.feasible:
        raise ValueError("initial id reference must be feasible")

    best = initial
    step = min(float(initial_step_a), float(id_upper_a) - float(id_lower_a))
    iterations = 0
    while iterations < int(max_iterations) and step >= float(minimum_step_a):
        iterations += 1
        candidates = [best]
        for candidate_id in (best.id_a - step, best.id_a + step):
            bounded = min(max(candidate_id, id_lower_a), id_upper_a)
            candidate = evaluate(bounded)
            if candidate.feasible:
                candidates.append(candidate)
        candidate_best = min(
            candidates,
            key=lambda item: (item.total_loss_w, item.phase_current_peak_a, item.id_a),
        )
        if candidate_best.total_loss_w < best.total_loss_w - 1e-12:
            best = candidate_best
        else:
            step *= 0.5

    return BoundedExtremumSearchResult(
        optimum=best,
        initial=initial,
        evaluated_points=len(cache),
        iterations=iterations,
        final_step_a=step,
        id_lower_a=float(id_lower_a),
        id_upper_a=float(id_upper_a),
    )

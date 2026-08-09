from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Dict, Iterable, Sequence, Tuple

from control.safe_neural_horizon_pwm import ControllerStepResult
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    AlphaBetaMotorState,
)
from models.two_level_inverter import (
    TwoLevelInverterParams,
    alpha_beta_voltage,
    estimate_inverter_losses,
)
from safety.ai_pwm_gateway import AIPwmRequest, AIPwmSafetyGateway, GateDecision, nearest_zero_vector


TAU = 2.0 * math.pi
SECTOR_ANGLE = TAU / 6.0


def _wrap_angle(angle: float) -> float:
    return (float(angle) + math.pi) % TAU - math.pi


def _angular_distance(left: float, right: float) -> float:
    return abs(_wrap_angle(float(left) - float(right)))


def rotate_alpha_beta(alpha: float, beta: float, angle: float) -> tuple[float, float]:
    c = math.cos(float(angle))
    s = math.sin(float(angle))
    return c * float(alpha) - s * float(beta), s * float(alpha) + c * float(beta)


def rotate_state(state: AlphaBetaMotorState, sectors: int) -> AlphaBetaMotorState:
    angle = int(sectors) * SECTOR_ANGLE
    psi_s_alpha, psi_s_beta = rotate_alpha_beta(state.psi_s_alpha, state.psi_s_beta, angle)
    psi_r_alpha, psi_r_beta = rotate_alpha_beta(state.psi_r_alpha, state.psi_r_beta, angle)
    return replace(
        state,
        psi_s_alpha=psi_s_alpha,
        psi_s_beta=psi_s_beta,
        psi_r_alpha=psi_r_alpha,
        psi_r_beta=psi_r_beta,
    )


def cyclic_sector(angle: float) -> int:
    return int(math.floor((float(angle) + 0.5 * SECTOR_ANGLE) / SECTOR_ANGLE)) % 6


def _active_vector_angles() -> dict[int, float]:
    inverter = TwoLevelInverterParams(Vdc=1.0)
    out: dict[int, float] = {}
    for vector_id in range(1, 7):
        v_alpha, v_beta = alpha_beta_voltage(vector_id, inverter)
        out[vector_id] = math.atan2(v_beta, v_alpha)
    return out


ACTIVE_VECTOR_ANGLES = _active_vector_angles()


def rotate_vector_id(vector_id: int, sectors: int) -> int:
    vector_id = int(vector_id)
    if vector_id in (0, 7):
        return vector_id
    target = _wrap_angle(ACTIVE_VECTOR_ANGLES[vector_id] + int(sectors) * SECTOR_ANGLE)
    return min(ACTIVE_VECTOR_ANGLES, key=lambda item: (_angular_distance(ACTIVE_VECTOR_ANGLES[item], target), item))


@dataclass(frozen=True)
class CyclicRobustViabilityConfig:
    dt_s: float = 100.0e-6
    speed_kp: float = 0.04
    speed_ki: float = 1.2
    torque_limit_nm: float = 3.5
    flux_ref_wb: float | None = None
    active_candidates: int = 3
    use_cyclic_reduction: bool = True
    use_parameter_set: bool = True
    use_viability_predecessor: bool = True
    viability_trigger_ratio: float = 0.95
    rs_radius: float = 0.20
    rr_radius: float = 0.20
    lm_radius: float = 0.10
    j_radius: float = 0.30
    cvar_alpha: float = 0.75
    cvar_weight: float = 0.55
    worst_weight: float = 0.25
    speed_weight: float = 0.20
    torque_weight: float = 1.00
    flux_weight: float = 0.85
    current_weight: float = 0.18
    switching_weight: float = 0.030
    loss_weight: float = 0.002
    torque_ripple_weight: float = 0.05
    common_mode_weight: float = 1.0e-4
    zero_vector_flux_penalty: float = 0.40
    current_margin: float = 0.92
    current_barrier_weight: float = 500.0
    infeasible_penalty: float = 1.0e6
    feedback_error_threshold_rad_s: float = 5.0
    feedback_uncertainty_threshold: float = 0.35
    temp_trip_c: float = 125.0


class SetMembershipStateEstimator:
    """Physics state estimate with a residual radius, without learned weights."""

    def __init__(self, params: AlphaBetaMotorParams, state: AlphaBetaMotorState | None = None) -> None:
        self.params = params
        self.state_hat = state if state is not None else AlphaBetaMotorState()
        self.residual_norm = 0.0
        self.uncertainty = 0.15

    def correct(self, measured: AlphaBetaMotorState, alpha: float = 0.6) -> None:
        alpha = max(0.0, min(1.0, float(alpha)))
        previous = self.state_hat
        residual = math.sqrt(
            (measured.psi_s_alpha - previous.psi_s_alpha) ** 2
            + (measured.psi_s_beta - previous.psi_s_beta) ** 2
            + (measured.psi_r_alpha - previous.psi_r_alpha) ** 2
            + (measured.psi_r_beta - previous.psi_r_beta) ** 2
            + 0.01 * (measured.omega_m - previous.omega_m) ** 2
        )
        self.residual_norm = 0.85 * self.residual_norm + 0.15 * residual
        self.uncertainty = max(0.02, min(1.0, 0.8 * self.uncertainty + 0.2 * residual))
        self.state_hat = replace(
            previous,
            psi_s_alpha=(1.0 - alpha) * previous.psi_s_alpha + alpha * measured.psi_s_alpha,
            psi_s_beta=(1.0 - alpha) * previous.psi_s_beta + alpha * measured.psi_s_beta,
            psi_r_alpha=(1.0 - alpha) * previous.psi_r_alpha + alpha * measured.psi_r_alpha,
            psi_r_beta=(1.0 - alpha) * previous.psi_r_beta + alpha * measured.psi_r_beta,
            omega_m=(1.0 - alpha) * previous.omega_m + alpha * measured.omega_m,
            theta_m=(1.0 - alpha) * previous.theta_m + alpha * measured.theta_m,
            temp_s_c=measured.temp_s_c,
            temp_r_c=measured.temp_r_c,
        )

    def drift_without_feedback(self) -> None:
        self.uncertainty = min(1.0, self.uncertainty + 0.01)

    def confidence(self) -> float:
        return max(0.0, min(1.0, math.exp(-self.uncertainty - 0.35 * self.residual_norm)))


def parameter_sigma_points(
    base: AlphaBetaMotorParams,
    cfg: CyclicRobustViabilityConfig,
) -> tuple[AlphaBetaMotorParams, ...]:
    if not cfg.use_parameter_set:
        return (base,)
    points = [base]
    for field, radius in (
        ("Rs", cfg.rs_radius),
        ("Rr", cfg.rr_radius),
        ("Lm", cfg.lm_radius),
        ("J", cfg.j_radius),
    ):
        value = float(getattr(base, field))
        radius = max(0.0, min(0.95, float(radius)))
        points.append(replace(base, **{field: max(1.0e-12, value * (1.0 - radius))}))
        points.append(replace(base, **{field: max(1.0e-12, value * (1.0 + radius))}))
    return tuple(points)


def _cvar(values: Sequence[float], alpha: float) -> float:
    if not values:
        return 0.0
    ordered = sorted((float(value) for value in values), reverse=True)
    tail_count = max(1, int(math.ceil((1.0 - max(0.0, min(0.999999, float(alpha)))) * len(ordered))))
    return sum(ordered[:tail_count]) / tail_count


class CyclicRobustViabilityPwmController:
    """C6-reduced, scenario-robust FCS controller with a viability predecessor test.

    The controller is deliberately non-neural. Each candidate vector is evaluated
    on deterministic parameter sigma points. A candidate is robustly viable only
    if every predicted member has at least one next switching vector that remains
    inside the planning current set.
    """

    def __init__(
        self,
        motor_params: AlphaBetaMotorParams,
        inverter_params: TwoLevelInverterParams,
        gateway: AIPwmSafetyGateway,
        cfg: CyclicRobustViabilityConfig | None = None,
    ) -> None:
        self.motor_params = motor_params
        self.inverter_params = inverter_params
        self.gateway = gateway
        self.cfg = cfg if cfg is not None else CyclicRobustViabilityConfig(dt_s=inverter_params.t_pwm_s)
        self.twin = SetMembershipStateEstimator(motor_params)
        self.parameter_set = parameter_sigma_points(motor_params, self.cfg)
        self.speed_integral = 0.0
        self.last_torque = 0.0
        self.theta_probe = 0.0
        self.tj_c = float(inverter_params.ambient_c)

    def reset(self, state: AlphaBetaMotorState | None = None) -> None:
        self.gateway.reset(0)
        self.twin = SetMembershipStateEstimator(self.motor_params, state)
        self.speed_integral = 0.0
        self.last_torque = 0.0
        self.theta_probe = 0.0
        self.tj_c = float(self.inverter_params.ambient_c)

    def _flux_ref(self) -> float:
        if self.cfg.flux_ref_wb is not None and self.cfg.flux_ref_wb > 0.0:
            return float(self.cfg.flux_ref_wb)
        return max(0.02, min(0.45, 0.15 * float(self.motor_params.Lm) * max(self.motor_params.i_limit, 1e-3)))

    def _torque_ref(self, omega_ref: float, omega_hat: float) -> float:
        error = float(omega_ref) - float(omega_hat)
        self.speed_integral = max(-12.0, min(12.0, self.speed_integral + error * self.cfg.dt_s))
        raw = self.cfg.speed_kp * error + self.cfg.speed_ki * self.speed_integral
        return max(-self.cfg.torque_limit_nm, min(self.cfg.torque_limit_nm, raw))

    def _candidate_vectors(self, state: AlphaBetaMotorState, torque_ref: float) -> tuple[tuple[int, ...], int]:
        if not self.cfg.use_cyclic_reduction:
            return tuple(range(8)), 0
        flux_angle = math.atan2(state.psi_s_beta, state.psi_s_alpha)
        if math.hypot(state.psi_s_alpha, state.psi_s_beta) < 1.0e-9:
            flux_angle = self.theta_probe
        torque = AlphaBetaInductionMotorModel(self.motor_params, state).torque_nm()
        torque_error = float(torque_ref) - float(torque)
        desired_angle = flux_angle + math.copysign(0.5 * math.pi, torque_error if torque_error != 0.0 else 1.0)
        sector = cyclic_sector(flux_angle)
        canonical_desired = _wrap_angle(desired_angle - sector * SECTOR_ANGLE)
        ranked_canonical = sorted(
            ACTIVE_VECTOR_ANGLES,
            key=lambda vector_id: (_angular_distance(ACTIVE_VECTOR_ANGLES[vector_id], canonical_desired), vector_id),
        )
        count = max(1, min(6, int(self.cfg.active_candidates)))
        active = [rotate_vector_id(vector_id, sector) for vector_id in ranked_canonical[:count]]
        candidates = [self.gateway.current_vector_id, nearest_zero_vector(self.gateway.current_vector_id), *active]
        return tuple(dict.fromkeys(int(item) for item in candidates)), sector

    def _predict(
        self,
        *,
        state: AlphaBetaMotorState,
        params: AlphaBetaMotorParams,
        vector_id: int,
        inverter: TwoLevelInverterParams,
        load_torque_nm: float,
    ):
        model = AlphaBetaInductionMotorModel(params, state)
        currents = model.currents()
        voltage = alpha_beta_voltage(
            vector_id,
            inverter,
            i_alpha_beta=(currents.i_s_alpha, currents.i_s_beta),
        )
        return model.next_state(*voltage, load_torque_nm, self.cfg.dt_s, state=state, params=params)

    def _recovery_margin(
        self,
        *,
        state: AlphaBetaMotorState,
        params: AlphaBetaMotorParams,
        inverter: TwoLevelInverterParams,
        load_torque_nm: float,
        current_limit: float,
    ) -> tuple[float, int]:
        best_current = float("inf")
        evaluations = 0
        for vector_id in range(8):
            step = self._predict(
                state=state,
                params=params,
                vector_id=vector_id,
                inverter=inverter,
                load_torque_nm=load_torque_nm,
            )
            evaluations += 1
            best_current = min(best_current, step.currents.stator_abs)
        return float(current_limit - best_current), evaluations

    def _score_vector(
        self,
        *,
        vector_id: int,
        state: AlphaBetaMotorState,
        omega_ref: float,
        torque_ref: float,
        load_torque_nm: float,
        inverter: TwoLevelInverterParams,
    ) -> tuple[float, Dict[str, float]]:
        costs: list[float] = []
        currents: list[float] = []
        recovery_margins: list[float] = []
        predicted_members: list[tuple[AlphaBetaMotorState, AlphaBetaMotorParams]] = []
        evaluation_count = 0
        current_limit = float(self.gateway.limits.i_soft_a) * float(self.cfg.current_margin)
        nominal_currents = AlphaBetaInductionMotorModel(self.motor_params, state).currents()
        losses = estimate_inverter_losses(
            prev_vector_id=self.gateway.current_vector_id,
            next_vector_id=vector_id,
            params=inverter,
            i_alpha_beta=(nominal_currents.i_s_alpha, nominal_currents.i_s_beta),
        )
        flux_ref = self._flux_ref()

        for params in self.parameter_set:
            step = self._predict(
                state=state,
                params=params,
                vector_id=vector_id,
                inverter=inverter,
                load_torque_nm=load_torque_nm,
            )
            evaluation_count += 1
            current_abs = step.currents.stator_abs
            flux_abs = math.hypot(step.state.psi_s_alpha, step.state.psi_s_beta)
            flux_error = abs(flux_ref - flux_abs)
            if flux_abs < 0.8 * flux_ref and vector_id in (0, 7):
                flux_error += self.cfg.zero_vector_flux_penalty
            stage_cost = (
                self.cfg.speed_weight * abs(float(omega_ref) - step.state.omega_m)
                + self.cfg.torque_weight * abs(float(torque_ref) - step.torque_nm)
                + self.cfg.flux_weight * flux_error
                + self.cfg.current_weight * current_abs
                + self.cfg.switching_weight * losses.switch_events
                + self.cfg.loss_weight * losses.total_w
                + self.cfg.torque_ripple_weight * abs(step.torque_nm - self.last_torque)
                + self.cfg.common_mode_weight * abs(losses.common_mode_v)
            )
            costs.append(float(stage_cost))
            currents.append(float(current_abs))
            predicted_members.append((step.state, params))

        mean_cost = sum(costs) / max(len(costs), 1)
        worst_cost = max(costs) if costs else float("inf")
        cvar_cost = _cvar(costs, self.cfg.cvar_alpha)
        robust_current = max(currents) if currents else float("inf")
        trigger_ratio = max(0.0, min(1.0, float(self.cfg.viability_trigger_ratio)))
        viability_triggered = (
            self.cfg.use_viability_predecessor
            and robust_current >= trigger_ratio * current_limit
        )
        if viability_triggered:
            for predicted_state, params in predicted_members:
                margin, recovery_evaluations = self._recovery_margin(
                    state=predicted_state,
                    params=params,
                    inverter=inverter,
                    load_torque_nm=load_torque_nm,
                    current_limit=current_limit,
                )
                evaluation_count += recovery_evaluations
                recovery_margins.append(margin)
        current_excess = max(0.0, robust_current / max(current_limit, 1.0e-12) - 1.0)
        recovery_margin = min(recovery_margins) if recovery_margins else current_limit - robust_current
        viable = not viability_triggered or recovery_margin >= 0.0
        robust_cost = (
            mean_cost
            + self.cfg.cvar_weight * max(0.0, cvar_cost - mean_cost)
            + self.cfg.worst_weight * max(0.0, worst_cost - mean_cost)
            + self.cfg.current_barrier_weight * current_excess * current_excess
            + (0.0 if viable else self.cfg.infeasible_penalty + abs(recovery_margin) * 1000.0)
        )
        return float(robust_cost), {
            "cost": float(robust_cost),
            "nominal_mean_cost": float(mean_cost),
            "cvar_cost": float(cvar_cost),
            "worst_cost": float(worst_cost),
            "robust_max_current": float(robust_current),
            "planning_current_limit": float(current_limit),
            "recovery_margin": float(recovery_margin),
            "robust_viable": 1.0 if viable else 0.0,
            "viability_triggered": 1.0 if viability_triggered else 0.0,
            "model_evaluations": float(evaluation_count),
            "parameter_set_size": float(len(self.parameter_set)),
        }

    def _select_vector(
        self,
        *,
        state: AlphaBetaMotorState,
        omega_ref: float,
        torque_ref: float,
        load_torque_nm: float,
        inverter: TwoLevelInverterParams,
    ) -> tuple[int, Dict[str, float]]:
        candidates, sector = self._candidate_vectors(state, torque_ref)
        best_vector = self.gateway.current_vector_id
        best_cost = float("inf")
        best_metrics: Dict[str, float] = {}
        viability_rejections = 0
        viability_triggers = 0
        total_evaluations = 0.0
        for vector_id in candidates:
            cost, metrics = self._score_vector(
                vector_id=vector_id,
                state=state,
                omega_ref=omega_ref,
                torque_ref=torque_ref,
                load_torque_nm=load_torque_nm,
                inverter=inverter,
            )
            total_evaluations += metrics["model_evaluations"]
            if metrics["robust_viable"] == 0.0:
                viability_rejections += 1
            if metrics["viability_triggered"] > 0.0:
                viability_triggers += 1
            if cost < best_cost:
                best_cost = cost
                best_vector = vector_id
                best_metrics = metrics
        best_metrics = dict(best_metrics)
        best_metrics.update(
            {
                "candidate_count": float(len(candidates)),
                "c6_sector": float(sector),
                "viability_rejections": float(viability_rejections),
                "viability_triggers": float(viability_triggers),
                "total_model_evaluations": float(total_evaluations),
            }
        )
        return int(best_vector), best_metrics

    def step(
        self,
        *,
        omega_ref: float,
        load_torque_nm: float,
        measured_state: AlphaBetaMotorState | None = None,
        measured_i_abs: float = 0.0,
        vdc: float | None = None,
    ) -> ControllerStepResult:
        if measured_state is not None:
            self.twin.correct(measured_state)
        else:
            self.twin.drift_without_feedback()

        inverter = replace(self.inverter_params, Vdc=float(self.inverter_params.Vdc if vdc is None else vdc))
        state = self.twin.state_hat
        torque_ref = self._torque_ref(omega_ref, state.omega_m)
        self.theta_probe = (self.theta_probe + self.motor_params.p * float(omega_ref) * self.cfg.dt_s) % TAU
        vector_id, metrics = self._select_vector(
            state=state,
            omega_ref=omega_ref,
            torque_ref=torque_ref,
            load_torque_nm=load_torque_nm,
            inverter=inverter,
        )
        robust_current = float(metrics.get("robust_max_current", 0.0))
        confidence = max(0.55, min(0.99, self.twin.confidence()))
        predicted_risk = max(0.0, min(1.3, self.twin.uncertainty + max(0.0, -metrics.get("recovery_margin", 0.0))))
        previous_vector = self.gateway.current_vector_id
        decision: GateDecision = self.gateway.evaluate(
            AIPwmRequest(
                vector_id=vector_id,
                dwell_s=self.cfg.dt_s,
                confidence=confidence,
                predicted_i_abs=robust_current,
                measured_i_abs=measured_i_abs,
                vdc=inverter.Vdc,
                tj_c=self.tj_c,
                predicted_risk=predicted_risk,
            )
        )
        applied_vector = decision.vector_id if decision.pwm_enabled else 0
        nominal_model = AlphaBetaInductionMotorModel(self.motor_params, state)
        nominal_currents = nominal_model.currents()
        if decision.pwm_enabled:
            losses = estimate_inverter_losses(
                prev_vector_id=previous_vector,
                next_vector_id=applied_vector,
                params=inverter,
                i_alpha_beta=(nominal_currents.i_s_alpha, nominal_currents.i_s_beta),
            )
            applied_loss_w = float(losses.total_w)
            applied_switch_events = float(losses.switch_events)
        else:
            applied_loss_w = 0.0
            applied_switch_events = 0.0

        applied_step = self._predict(
            state=state,
            params=self.motor_params,
            vector_id=applied_vector,
            inverter=inverter,
            load_torque_nm=load_torque_nm,
        )
        self.twin.state_hat = applied_step.state
        self.last_torque = applied_step.torque_nm
        tau = max(inverter.thermal_rth_k_per_w * inverter.thermal_cth_j_per_k, 1.0e-9)
        target_temp = inverter.ambient_c + inverter.thermal_rth_k_per_w * applied_loss_w
        self.tj_c += (target_temp - self.tj_c) * min(1.0, self.cfg.dt_s / tau)

        metrics = dict(metrics)
        metrics.update(
            {
                "torque_ref": float(torque_ref),
                "applied_torque": float(applied_step.torque_nm),
                "loss_w": applied_loss_w,
                "switch_events": applied_switch_events,
                "accepted": 1.0 if decision.accepted else 0.0,
                "fault_flags": float(int(decision.fault_flags)),
                "tj_c": float(self.tj_c),
            }
        )
        return ControllerStepResult(
            decision=decision,
            vector_id=applied_vector,
            feedback_requested=measured_state is not None,
            confidence=confidence,
            predicted_i_abs=robust_current,
            predicted_risk=predicted_risk,
            metrics=metrics,
        )


__all__ = [
    "ACTIVE_VECTOR_ANGLES",
    "CyclicRobustViabilityConfig",
    "CyclicRobustViabilityPwmController",
    "SetMembershipStateEstimator",
    "cyclic_sector",
    "parameter_sigma_points",
    "rotate_alpha_beta",
    "rotate_state",
    "rotate_vector_id",
]

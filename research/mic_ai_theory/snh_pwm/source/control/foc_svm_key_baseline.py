from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Dict, Tuple

from control.safe_neural_horizon_pwm import ControllerStepResult, NeuralTwin
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    AlphaBetaMotorState,
)
from models.transformations import alpha_beta_to_dq, dq_to_alpha_beta
from models.two_level_inverter import (
    SpaceVectorDwell,
    TwoLevelInverterParams,
    estimate_inverter_losses,
    space_vector_schedule,
)
from safety.ai_pwm_gateway import AIPwmRequest, AIPwmSafetyGateway, GateDecision


@dataclass(frozen=True)
class FocSvmKeyBaselineConfig:
    dt_s: float = 100.0e-6
    speed_kp: float = 0.035
    speed_ki: float = 1.0
    current_kp: float = 22.0
    current_ki: float = 650.0
    torque_limit_nm: float = 3.0
    flux_ref_wb: float | None = None
    id_max_fraction: float = 0.45
    iq_max_fraction: float = 0.80
    voltage_limit_fraction: float = 0.92
    switching_tiebreak_weight: float = 0.015
    preflux_voltage_fraction: float = 0.12
    feedback_error_threshold_rad_s: float = 6.0
    feedback_uncertainty_threshold: float = 0.40
    temp_trip_c: float = 125.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(value)))


def _wrap_angle(theta: float) -> float:
    return math.atan2(math.sin(theta), math.cos(theta))


class FocSvmKeyBaselineController:
    """Host FOC-SVPWM baseline with PI loops and atomic gateway protection.

    Each PWM period is synthesized from two adjacent active vectors and a zero
    vector. The same accepted dwell schedule is propagated through the gateway,
    digital twin, loss estimate, and simulation plant.
    """

    def __init__(
        self,
        motor_params: AlphaBetaMotorParams,
        inverter_params: TwoLevelInverterParams,
        gateway: AIPwmSafetyGateway,
        cfg: FocSvmKeyBaselineConfig | None = None,
    ) -> None:
        self.motor_params = motor_params
        self.inverter_params = inverter_params
        self.gateway = gateway
        self.cfg = cfg if cfg is not None else FocSvmKeyBaselineConfig(dt_s=inverter_params.t_pwm_s)
        if not math.isclose(self.cfg.dt_s, inverter_params.t_pwm_s, rel_tol=0.0, abs_tol=1.0e-15):
            raise ValueError("FOC controller dt_s must match the inverter PWM period")
        if not math.isclose(gateway.limits.t_pwm_s, inverter_params.t_pwm_s, rel_tol=0.0, abs_tol=1.0e-15):
            raise ValueError("FOC gateway period must match the inverter PWM period")
        self.twin = NeuralTwin(motor_params)
        self.speed_integral = 0.0
        self.id_integral = 0.0
        self.iq_integral = 0.0
        self.theta_e = 0.0
        self.omega_slip = 0.0
        self.omega_e = 0.0
        self.last_torque_ref = 0.0
        self.tj_c = float(inverter_params.ambient_c)

    def reset(self, state: AlphaBetaMotorState | None = None) -> None:
        self.gateway.reset(0)
        self.twin = NeuralTwin(self.motor_params, state)
        self.speed_integral = 0.0
        self.id_integral = 0.0
        self.iq_integral = 0.0
        self.theta_e = 0.0
        self.omega_slip = 0.0
        self.omega_e = 0.0
        self.last_torque_ref = 0.0
        self.tj_c = float(self.inverter_params.ambient_c)

    def _flux_ref(self) -> float:
        if self.cfg.flux_ref_wb is not None and self.cfg.flux_ref_wb > 0.0:
            return float(self.cfg.flux_ref_wb)
        if float(self.motor_params.psi_sat) > 0.0:
            return max(0.02, min(0.50, 0.78 * float(self.motor_params.psi_sat)))
        return max(0.02, min(0.45, 0.15 * float(self.motor_params.Lm) * max(self.motor_params.i_limit, 1e-3)))

    def _torque_ref(self, omega_ref: float, omega_hat: float) -> float:
        err = float(omega_ref) - float(omega_hat)
        limit = max(float(self.cfg.torque_limit_nm), 1e-9)
        ki = float(self.cfg.speed_ki)
        integral_limit = limit / max(abs(ki), 1e-9)
        candidate_integral = _clamp(
            self.speed_integral + err * float(self.cfg.dt_s),
            -integral_limit,
            integral_limit,
        )
        candidate_raw = float(self.cfg.speed_kp) * err + ki * candidate_integral
        driving_further_into_saturation = (
            (candidate_raw > limit and err > 0.0)
            or (candidate_raw < -limit and err < 0.0)
        )
        if not driving_further_into_saturation:
            self.speed_integral = candidate_integral
        raw = float(self.cfg.speed_kp) * err + ki * self.speed_integral
        self.last_torque_ref = _clamp(raw, -limit, limit)
        return self.last_torque_ref

    def _update_angle(
        self,
        state: AlphaBetaMotorState,
        id_ref: float,
        iq_ref: float,
    ) -> float:
        flux_alpha, flux_beta = state.psi_r_alpha, state.psi_r_beta
        flux_abs = math.hypot(flux_alpha, flux_beta)
        if flux_abs < 1.0e-5:
            flux_alpha, flux_beta = state.psi_s_alpha, state.psi_s_beta
            flux_abs = math.hypot(flux_alpha, flux_beta)

        rotor_inductance = float(self.motor_params.Llr) + float(self.motor_params.Lm)
        rotor_inverse_time_constant = float(self.motor_params.Rr) / max(rotor_inductance, 1e-9)
        slip = rotor_inverse_time_constant * float(iq_ref) / max(abs(float(id_ref)), 1e-4)
        slip = _clamp(slip, -160.0, 160.0)
        omega_e = float(self.motor_params.p) * float(state.omega_m) + slip
        self.omega_slip = slip
        self.omega_e = omega_e
        self.theta_e = _wrap_angle(
            self.theta_e + omega_e * float(self.cfg.dt_s)
        )
        if flux_abs > 1.0e-4:
            self.theta_e = math.atan2(flux_beta, flux_alpha)
        return omega_e

    def _dq_references(self, torque_ref: float) -> Tuple[float, float]:
        flux_ref = self._flux_ref()
        id_limit = max(0.05, float(self.cfg.id_max_fraction) * max(self.motor_params.i_limit, 1e-6))
        iq_limit = max(0.05, float(self.cfg.iq_max_fraction) * max(self.motor_params.i_limit, 1e-6))
        id_ref = _clamp(flux_ref / max(float(self.motor_params.Lm), 1e-9), 0.0, id_limit)
        rotor_inductance = float(self.motor_params.Llr) + float(self.motor_params.Lm)
        torque_gain = (
            1.5
            * max(self.motor_params.p, 1)
            * float(self.motor_params.Lm)
            / max(rotor_inductance, 1e-9)
            * max(flux_ref, 1e-6)
        )
        iq_ref = _clamp(
            torque_ref / max(torque_gain, 1e-9),
            -iq_limit,
            iq_limit,
        )
        return id_ref, iq_ref

    def _voltage_reference(
        self,
        *,
        id_ref: float,
        iq_ref: float,
        i_d: float,
        i_q: float,
        omega_e: float,
        inverter: TwoLevelInverterParams,
        rotor_flux_abs: float,
        preflux_v: float = 0.0,
    ) -> Tuple[float, float]:
        err_d = float(id_ref) - float(i_d)
        err_q = float(iq_ref) - float(i_q)
        lm = float(self.motor_params.Lm)
        ls = float(self.motor_params.Lls) + lm
        lr = float(self.motor_params.Llr) + lm
        sigma_ls = max(ls - lm * lm / max(lr, 1e-9), 1e-9)
        limit = max(1.0, float(self.cfg.voltage_limit_fraction) * abs(float(inverter.Vdc)) / math.sqrt(3.0))
        kp = float(self.cfg.current_kp)
        ki = float(self.cfg.current_ki)
        integral_limit = limit / max(abs(ki), 1e-9)
        candidate_id_integral = _clamp(
            self.id_integral + err_d * float(self.cfg.dt_s),
            -integral_limit,
            integral_limit,
        )
        candidate_iq_integral = _clamp(
            self.iq_integral + err_q * float(self.cfg.dt_s),
            -integral_limit,
            integral_limit,
        )
        decouple_d = -float(omega_e) * sigma_ls * float(i_q) + float(preflux_v)
        decouple_q = float(omega_e) * (
            sigma_ls * float(i_d) + lm / max(lr, 1e-9) * float(rotor_flux_abs)
        )
        v_d = kp * err_d + ki * candidate_id_integral + decouple_d
        v_q = kp * err_q + ki * candidate_iq_integral + decouple_q
        mag = math.hypot(v_d, v_q)
        if mag > limit:
            scale = limit / mag
            v_d *= scale
            v_q *= scale
            if abs(ki) > 1e-9:
                self.id_integral = _clamp(
                    (v_d - kp * err_d - decouple_d) / ki,
                    -integral_limit,
                    integral_limit,
                )
                self.iq_integral = _clamp(
                    (v_q - kp * err_q - decouple_q) / ki,
                    -integral_limit,
                    integral_limit,
                )
        else:
            self.id_integral = candidate_id_integral
            self.iq_integral = candidate_iq_integral
        v_alpha, v_beta = dq_to_alpha_beta(v_d, v_q, self.theta_e)
        return float(v_alpha), float(v_beta)

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
            self.twin.correct(measured_state, alpha=1.0)
        else:
            self.twin.drift_without_feedback()

        inverter = replace(self.inverter_params, Vdc=float(self.inverter_params.Vdc if vdc is None else vdc))
        state = self.twin.state_hat
        model = AlphaBetaInductionMotorModel(self.motor_params, state)
        currents = model.currents()
        torque_ref = self._torque_ref(omega_ref, state.omega_m)
        id_ref, iq_ref = self._dq_references(torque_ref)
        omega_e = self._update_angle(state, id_ref, iq_ref)
        i_d, i_q = alpha_beta_to_dq(currents.i_s_alpha, currents.i_s_beta, self.theta_e)
        flux_ref = self._flux_ref()
        flux_abs = math.hypot(state.psi_s_alpha, state.psi_s_beta)
        preflux_v = 0.0
        if flux_abs < 0.65 * flux_ref:
            preflux_v = float(self.cfg.preflux_voltage_fraction) * abs(float(inverter.Vdc))
        v_alpha_ref, v_beta_ref = self._voltage_reference(
            id_ref=id_ref,
            iq_ref=iq_ref,
            i_d=i_d,
            i_q=i_q,
            omega_e=omega_e,
            inverter=inverter,
            rotor_flux_abs=math.hypot(state.psi_r_alpha, state.psi_r_beta),
            preflux_v=preflux_v,
        )
        requested_schedule = space_vector_schedule(
            v_alpha_ref,
            v_beta_ref,
            inverter,
            previous_vector_id=self.gateway.current_vector_id,
            min_pulse_s=self.gateway.limits.min_pulse_s,
        )
        _, predicted_torque, predicted_i_abs = self.twin.predict_schedule(
            requested_schedule.segments,
            inverter,
            load_torque_nm,
        )
        current_ratio = predicted_i_abs / max(self.motor_params.i_limit, 1e-9)
        predicted_risk = max(0.0, current_ratio - 0.85) + 0.25 * self.twin.uncertainty
        confidence = max(0.50, min(0.99, self.twin.confidence()))
        prev_vector_id = self.gateway.current_vector_id
        requests = tuple(
            AIPwmRequest(
                vector_id=segment.vector_id,
                dwell_s=segment.dwell_s,
                confidence=confidence,
                predicted_i_abs=predicted_i_abs,
                measured_i_abs=measured_i_abs,
                vdc=inverter.Vdc,
                tj_c=self.tj_c,
                predicted_risk=predicted_risk,
            )
            for segment in requested_schedule.segments
        )
        decisions = self.gateway.evaluate_sequence_atomic(requests)
        sequence_accepted = len(decisions) == len(requests) and all(item.accepted for item in decisions)
        decision: GateDecision = decisions[-1]
        if sequence_accepted:
            applied_schedule = requested_schedule.segments
        else:
            applied_schedule = (SpaceVectorDwell(decision.vector_id, self.cfg.dt_s),)
        applied_vector = applied_schedule[-1].vector_id

        if decision.pwm_enabled:
            applied_loss_w = 0.0
            applied_switch_events = 0.0
            loss_prev_vector = prev_vector_id
            for segment in applied_schedule:
                losses = estimate_inverter_losses(
                    prev_vector_id=loss_prev_vector,
                    next_vector_id=segment.vector_id,
                    params=inverter,
                    i_alpha_beta=(currents.i_s_alpha, currents.i_s_beta),
                )
                dwell_fraction = segment.dwell_s / max(self.cfg.dt_s, 1.0e-12)
                applied_loss_w += float(losses.conduction_w) * dwell_fraction + float(losses.switching_w)
                applied_switch_events += float(losses.switch_events)
                loss_prev_vector = segment.vector_id
        else:
            applied_loss_w = 0.0
            applied_switch_events = 0.0

        applied_state, applied_torque, _ = self.twin.predict_schedule(
            applied_schedule,
            inverter,
            load_torque_nm,
            pwm_enabled=decision.pwm_enabled,
        )
        self.twin.state_hat = applied_state
        tau = max(inverter.thermal_rth_k_per_w * inverter.thermal_cth_j_per_k, 1e-9)
        target_temp = inverter.ambient_c + inverter.thermal_rth_k_per_w * applied_loss_w
        self.tj_c += (target_temp - self.tj_c) * min(1.0, self.cfg.dt_s / tau)

        metrics: Dict[str, float] = {
            "id_ref": float(id_ref),
            "iq_ref": float(iq_ref),
            "i_d": float(i_d),
            "i_q": float(i_q),
            "torque_ref": float(torque_ref),
            "omega_slip_rad_s": float(self.omega_slip),
            "omega_e_rad_s": float(self.omega_e),
            "predicted_torque": float(predicted_torque),
            "applied_torque": float(applied_torque),
            "v_alpha_ref": float(v_alpha_ref),
            "v_beta_ref": float(v_beta_ref),
            "flux_abs": float(flux_abs),
            "loss_w": applied_loss_w,
            "switch_events": applied_switch_events,
            "accepted": 1.0 if decision.accepted else 0.0,
            "fault_flags": float(int(decision.fault_flags)),
            "tj_c": float(self.tj_c),
            "svm_segment_count": float(len(applied_schedule)),
            "svm_sector": float(requested_schedule.sector),
            "svm_saturated": 1.0 if requested_schedule.saturated else 0.0,
            "svm_pulse_adjusted": 1.0 if requested_schedule.pulse_adjusted else 0.0,
            "svm_voltage_error_v": float(
                math.hypot(
                    requested_schedule.synthesized_alpha_beta_v[0] - v_alpha_ref,
                    requested_schedule.synthesized_alpha_beta_v[1] - v_beta_ref,
                )
            ),
            "svm_sequence_accepted": 1.0 if sequence_accepted else 0.0,
            "svm_total_dwell_s": float(sum(segment.dwell_s for segment in applied_schedule)),
        }
        return ControllerStepResult(
            decision=decision,
            vector_id=applied_vector,
            feedback_requested=measured_state is not None,
            confidence=confidence,
            predicted_i_abs=float(predicted_i_abs),
            predicted_risk=float(predicted_risk),
            vector_schedule=tuple(applied_schedule),
            metrics=metrics,
        )


__all__ = [
    "FocSvmKeyBaselineConfig",
    "FocSvmKeyBaselineController",
]

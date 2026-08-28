from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Dict

from control.safe_neural_horizon_pwm import ControllerStepResult, NeuralTwin
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    AlphaBetaMotorState,
)
from models.two_level_inverter import (
    SpaceVectorDwell,
    TwoLevelInverterParams,
    estimate_inverter_losses,
    space_vector_schedule,
)
from safety.ai_pwm_gateway import AIPwmRequest, AIPwmSafetyGateway, GateDecision


HOST_SIMULATION_ONLY = True


@dataclass(frozen=True)
class ScalarVfBaselineConfig:
    """AIR56B2 host-only scalar V/f settings.

    The rated voltage is the physical line-to-line RMS value for the 220 V
    Delta connection. The alpha-beta plant uses the equivalent star phase
    voltage, whose peak is ``U_line_rms * sqrt(2/3)``.
    """

    dt_s: float = 100.0e-6
    rated_line_voltage_rms_v: float = 220.0
    base_frequency_hz: float = 50.0
    max_frequency_hz: float = 50.0
    ramp_hz_per_s: float = 20.0
    low_frequency_boost_fraction: float = 0.08
    boost_end_frequency_hz: float = 8.0
    voltage_limit_fraction: float = 1.0
    current_guard_start_fraction: float = 0.80
    current_guard_limit_a: float | None = None
    temp_trip_c: float = 125.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(value)))


def _require_finite(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


class Air56B2ScalarVfBaselineController:
    """Deterministic open-loop AIR56B2 V/f baseline for host simulation only.

    This controller is not MCU firmware and carries no hardware-validation
    claim. It produces only legal two-level inverter vectors: a requested
    rotating alpha-beta voltage is converted to an SVPWM dwell schedule and the
    complete schedule is accepted atomically by ``AIPwmSafetyGateway``.
    """

    host_simulation_only = True

    def __init__(
        self,
        motor_params: AlphaBetaMotorParams,
        inverter_params: TwoLevelInverterParams,
        gateway: AIPwmSafetyGateway,
        cfg: ScalarVfBaselineConfig | None = None,
    ) -> None:
        self.motor_params = motor_params
        self.inverter_params = inverter_params
        self.gateway = gateway
        self.cfg = cfg if cfg is not None else ScalarVfBaselineConfig(dt_s=inverter_params.t_pwm_s)
        self._validate_configuration()
        self.twin = NeuralTwin(motor_params)
        self.frequency_hz = 0.0
        self.electrical_angle_rad = 0.0
        self.tj_c = float(inverter_params.ambient_c)

    def _validate_configuration(self) -> None:
        values = {
            "dt_s": self.cfg.dt_s,
            "rated_line_voltage_rms_v": self.cfg.rated_line_voltage_rms_v,
            "base_frequency_hz": self.cfg.base_frequency_hz,
            "max_frequency_hz": self.cfg.max_frequency_hz,
            "ramp_hz_per_s": self.cfg.ramp_hz_per_s,
            "low_frequency_boost_fraction": self.cfg.low_frequency_boost_fraction,
            "boost_end_frequency_hz": self.cfg.boost_end_frequency_hz,
            "voltage_limit_fraction": self.cfg.voltage_limit_fraction,
            "current_guard_start_fraction": self.cfg.current_guard_start_fraction,
            "temp_trip_c": self.cfg.temp_trip_c,
        }
        if self.cfg.current_guard_limit_a is not None:
            values["current_guard_limit_a"] = self.cfg.current_guard_limit_a
        for name, value in values.items():
            _require_finite(name, value)
        if not math.isclose(self.cfg.dt_s, self.inverter_params.t_pwm_s, rel_tol=0.0, abs_tol=1.0e-15):
            raise ValueError("scalar V/f dt_s must match the inverter PWM period")
        if not math.isclose(self.gateway.limits.t_pwm_s, self.cfg.dt_s, rel_tol=0.0, abs_tol=1.0e-15):
            raise ValueError("scalar V/f gateway period must match the controller period")
        if self.cfg.rated_line_voltage_rms_v <= 0.0:
            raise ValueError("rated line voltage must be positive")
        if self.cfg.base_frequency_hz <= 0.0:
            raise ValueError("base frequency must be positive")
        if self.cfg.max_frequency_hz <= 0.0 or self.cfg.max_frequency_hz > self.cfg.base_frequency_hz:
            raise ValueError("max frequency must be in (0, base_frequency_hz]")
        if self.cfg.ramp_hz_per_s <= 0.0:
            raise ValueError("frequency ramp must be positive")
        if not 0.0 <= self.cfg.low_frequency_boost_fraction < 1.0:
            raise ValueError("low-frequency boost fraction must be in [0, 1)")
        if self.cfg.boost_end_frequency_hz <= 0.0:
            raise ValueError("boost end frequency must be positive")
        if not 0.0 < self.cfg.voltage_limit_fraction <= 1.0:
            raise ValueError("voltage limit fraction must be in (0, 1]")
        if not 0.0 < self.cfg.current_guard_start_fraction < 1.0:
            raise ValueError("current guard start fraction must be in (0, 1)")
        if self.cfg.current_guard_limit_a is not None and self.cfg.current_guard_limit_a <= 0.0:
            raise ValueError("current guard limit must be positive")

    @property
    def rated_phase_peak_v(self) -> float:
        return float(self.cfg.rated_line_voltage_rms_v) * math.sqrt(2.0 / 3.0)

    @property
    def current_guard_limit_a(self) -> float:
        requested = (
            float(self.motor_params.i_limit)
            if self.cfg.current_guard_limit_a is None
            else float(self.cfg.current_guard_limit_a)
        )
        gateway_soft_limit = math.nextafter(float(self.gateway.limits.i_soft_a), 0.0)
        return max(1.0e-6, min(requested, gateway_soft_limit))

    def reset(self, state: AlphaBetaMotorState | None = None) -> None:
        self.gateway.reset(0)
        self.twin = NeuralTwin(self.motor_params, state)
        self.frequency_hz = 0.0
        self.electrical_angle_rad = 0.0
        self.tj_c = float(self.inverter_params.ambient_c)

    def _ramp_frequency(self, command_hz: float) -> tuple[float, float]:
        target = _clamp(command_hz, 0.0, self.cfg.max_frequency_hz)
        previous = self.frequency_hz
        max_delta = float(self.cfg.ramp_hz_per_s) * float(self.cfg.dt_s)
        self.frequency_hz = previous + _clamp(target - previous, -max_delta, max_delta)
        return previous, target

    def _vf_voltage(self, frequency_hz: float, vdc: float) -> tuple[float, float]:
        frequency = _clamp(frequency_hz, 0.0, self.cfg.max_frequency_hz)
        if frequency <= 0.0:
            return 0.0, 0.0
        linear = self.rated_phase_peak_v * frequency / float(self.cfg.base_frequency_hz)
        boost_weight = max(
            0.0,
            1.0 - frequency / float(self.cfg.boost_end_frequency_hz),
        )
        boosted = linear + self.rated_phase_peak_v * float(self.cfg.low_frequency_boost_fraction) * boost_weight
        nameplate_limited = min(boosted, self.rated_phase_peak_v)
        dc_bus_limited = min(
            nameplate_limited,
            float(self.cfg.voltage_limit_fraction) * abs(float(vdc)) / math.sqrt(3.0),
        )
        return float(nameplate_limited), max(0.0, float(dc_bus_limited))

    def _current_guard_scale(self, current_a: float) -> float:
        limit = self.current_guard_limit_a
        start = float(self.cfg.current_guard_start_fraction) * limit
        current = abs(float(current_a))
        if current <= start:
            return 1.0
        if current >= limit:
            return 0.0
        return (limit - current) / max(limit - start, 1.0e-12)

    def step(
        self,
        *,
        frequency_command_hz: float,
        load_torque_nm: float,
        measured_state: AlphaBetaMotorState | None = None,
        measured_i_abs: float = 0.0,
        vdc: float | None = None,
    ) -> ControllerStepResult:
        command = _require_finite("frequency_command_hz", frequency_command_hz)
        load_torque = _require_finite("load_torque_nm", load_torque_nm)
        measured_current = abs(_require_finite("measured_i_abs", measured_i_abs))
        bus_voltage = _require_finite(
            "vdc",
            self.inverter_params.Vdc if vdc is None else vdc,
        )
        if bus_voltage <= 0.0:
            raise ValueError("vdc must be positive")

        if measured_state is not None:
            self.twin.correct(measured_state, alpha=1.0)
            state_current = AlphaBetaInductionMotorModel(
                self.motor_params,
                measured_state,
            ).currents().stator_abs
            measured_current = max(measured_current, float(state_current))
        else:
            self.twin.drift_without_feedback()

        previous_frequency, target_frequency = self._ramp_frequency(command)
        average_frequency = 0.5 * (previous_frequency + self.frequency_hz)
        self.electrical_angle_rad = (
            self.electrical_angle_rad
            + 2.0 * math.pi * average_frequency * float(self.cfg.dt_s)
        ) % (2.0 * math.pi)

        inverter = replace(self.inverter_params, Vdc=bus_voltage)
        vf_voltage_unlimited, requested_voltage = self._vf_voltage(self.frequency_hz, bus_voltage)
        measured_guard_scale = self._current_guard_scale(measured_current)
        guard_scale = measured_guard_scale

        def build_schedule(scale: float):
            magnitude = requested_voltage * _clamp(scale, 0.0, 1.0)
            v_alpha = magnitude * math.cos(self.electrical_angle_rad)
            v_beta = magnitude * math.sin(self.electrical_angle_rad)
            schedule = space_vector_schedule(
                v_alpha,
                v_beta,
                inverter,
                previous_vector_id=self.gateway.current_vector_id,
                min_pulse_s=self.gateway.limits.min_pulse_s,
            )
            return magnitude, v_alpha, v_beta, schedule

        applied_voltage_ref, v_alpha_ref, v_beta_ref, requested_schedule = build_schedule(guard_scale)
        _, predicted_torque, predicted_current = self.twin.predict_schedule(
            requested_schedule.segments,
            inverter,
            load_torque,
        )
        predicted_guard_scale = self._current_guard_scale(predicted_current)
        revised_scale = min(guard_scale, predicted_guard_scale)
        if revised_scale < guard_scale - 1.0e-15:
            guard_scale = revised_scale
            applied_voltage_ref, v_alpha_ref, v_beta_ref, requested_schedule = build_schedule(guard_scale)
            _, predicted_torque, predicted_current = self.twin.predict_schedule(
                requested_schedule.segments,
                inverter,
                load_torque,
            )

        confidence = 1.0
        requests = tuple(
            AIPwmRequest(
                vector_id=segment.vector_id,
                dwell_s=segment.dwell_s,
                confidence=confidence,
                predicted_i_abs=predicted_current,
                measured_i_abs=measured_current,
                vdc=bus_voltage,
                tj_c=self.tj_c,
                predicted_risk=0.0,
            )
            for segment in requested_schedule.segments
        )
        previous_vector_id = self.gateway.current_vector_id
        decisions = self.gateway.evaluate_sequence_atomic(requests)
        sequence_accepted = len(decisions) == len(requests) and all(item.accepted for item in decisions)
        decision: GateDecision = decisions[-1]
        if sequence_accepted:
            applied_schedule = requested_schedule.segments
        else:
            applied_schedule = (SpaceVectorDwell(decision.vector_id, float(self.cfg.dt_s)),)

        currents = AlphaBetaInductionMotorModel(
            self.motor_params,
            self.twin.state_hat,
        ).currents()
        loss_w = 0.0
        switch_event_count = 0
        if decision.pwm_enabled:
            loss_previous = previous_vector_id
            for segment in applied_schedule:
                loss = estimate_inverter_losses(
                    prev_vector_id=loss_previous,
                    next_vector_id=segment.vector_id,
                    params=inverter,
                    i_alpha_beta=(currents.i_s_alpha, currents.i_s_beta),
                )
                dwell_fraction = segment.dwell_s / max(float(self.cfg.dt_s), 1.0e-12)
                loss_w += float(loss.conduction_w) * dwell_fraction + float(loss.switching_w)
                switch_event_count += int(loss.switch_events)
                loss_previous = segment.vector_id

        applied_state, applied_torque, applied_current = self.twin.predict_schedule(
            applied_schedule,
            inverter,
            load_torque,
            pwm_enabled=decision.pwm_enabled,
        )
        self.twin.state_hat = applied_state
        thermal_tau_s = max(
            float(inverter.thermal_rth_k_per_w) * float(inverter.thermal_cth_j_per_k),
            1.0e-9,
        )
        target_tj_c = float(inverter.ambient_c) + float(inverter.thermal_rth_k_per_w) * loss_w
        self.tj_c += (target_tj_c - self.tj_c) * min(1.0, float(self.cfg.dt_s) / thermal_tau_s)

        metrics: Dict[str, float] = {
            "host_simulation_only": 1.0,
            "frequency_command_hz": float(command),
            "frequency_target_hz": float(target_frequency),
            "frequency_applied_hz": float(self.frequency_hz),
            "electrical_angle_rad": float(self.electrical_angle_rad),
            "rated_phase_peak_v": float(self.rated_phase_peak_v),
            "vf_voltage_unlimited_v": float(vf_voltage_unlimited),
            "voltage_ref_peak_v": float(applied_voltage_ref),
            "v_alpha_ref": float(v_alpha_ref),
            "v_beta_ref": float(v_beta_ref),
            "current_guard_limit_a": float(self.current_guard_limit_a),
            "current_guard_scale": float(guard_scale),
            "current_guard_active": 1.0 if guard_scale < 1.0 else 0.0,
            "measured_i_abs": float(measured_current),
            "predicted_i_abs_before_gateway": float(predicted_current),
            "applied_i_abs": float(applied_current),
            "predicted_torque": float(predicted_torque),
            "applied_torque": float(applied_torque),
            "accepted": 1.0 if decision.accepted else 0.0,
            "fault_flags": float(int(decision.fault_flags)),
            "svm_sector": float(requested_schedule.sector),
            "svm_saturated": 1.0 if requested_schedule.saturated else 0.0,
            "svm_pulse_adjusted": 1.0 if requested_schedule.pulse_adjusted else 0.0,
            "svm_segment_count": float(len(applied_schedule)),
            "svm_sequence_accepted": 1.0 if sequence_accepted else 0.0,
            "svm_total_dwell_s": float(sum(segment.dwell_s for segment in applied_schedule)),
            "loss_w": float(loss_w),
            "switch_events": float(switch_event_count),
            "tj_c": float(self.tj_c),
        }
        return ControllerStepResult(
            decision=decision,
            vector_id=applied_schedule[-1].vector_id,
            feedback_requested=measured_state is not None,
            confidence=confidence,
            predicted_i_abs=float(predicted_current),
            predicted_risk=0.0,
            vector_schedule=tuple(applied_schedule),
            metrics=metrics,
        )


__all__ = [
    "Air56B2ScalarVfBaselineController",
    "HOST_SIMULATION_ONLY",
    "ScalarVfBaselineConfig",
]

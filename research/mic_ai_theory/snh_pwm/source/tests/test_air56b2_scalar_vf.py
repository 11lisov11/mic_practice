from __future__ import annotations

import math

import pytest

from control.safe_neural_horizon_pwm import effective_vector_schedule
from control.scalar_vf_baseline import (
    Air56B2ScalarVfBaselineController,
    HOST_SIMULATION_ONLY,
    ScalarVfBaselineConfig,
)
from models.air56b2_nameplate_ensemble import generate_air56b2_ensemble
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    step_inverter_schedule,
)
from models.two_level_inverter import TwoLevelInverterParams, validate_vector_id
from safety.ai_pwm_gateway import AIPwmSafetyGateway, GatewayLimits, has_shoot_through


def _controller(
    motor: AlphaBetaMotorParams,
    *,
    ramp_hz_per_s: float = 20.0,
    current_guard_limit_a: float | None = None,
) -> tuple[Air56B2ScalarVfBaselineController, TwoLevelInverterParams]:
    inverter = TwoLevelInverterParams(Vdc=311.0, f_pwm=10_000.0)
    limits = GatewayLimits(
        t_pwm_s=inverter.t_pwm_s,
        dead_time_s=inverter.dead_time_s,
        min_pulse_s=inverter.min_pulse_s,
        i_soft_a=8.0,
        i_trip_a=12.0,
        max_switch_events_per_window=1000,
        switch_window_steps=8,
    )
    controller = Air56B2ScalarVfBaselineController(
        motor,
        inverter,
        AIPwmSafetyGateway(limits),
        ScalarVfBaselineConfig(
            dt_s=inverter.t_pwm_s,
            ramp_hz_per_s=ramp_hz_per_s,
            current_guard_limit_a=current_guard_limit_a,
        ),
    )
    return controller, inverter


def _nominal_motor() -> AlphaBetaMotorParams:
    sample = generate_air56b2_ensemble(1, seed=5602)[0]
    return AlphaBetaMotorParams.from_motor_params(sample.motor)


def test_zero_command_returns_protected_zero_schedule() -> None:
    controller, inverter = _controller(_nominal_motor())
    result = controller.step(frequency_command_hz=0.0, load_torque_nm=0.0)
    schedule = effective_vector_schedule(result, inverter.t_pwm_s)

    assert HOST_SIMULATION_ONLY is True
    assert controller.host_simulation_only is True
    assert controller.frequency_hz == 0.0
    assert result.metrics["voltage_ref_peak_v"] == 0.0
    assert len(schedule) == 1
    assert schedule[0].vector_id in {0, 7}
    assert schedule[0].dwell_s == pytest.approx(inverter.t_pwm_s)
    assert result.decision.accepted is True
    assert result.decision.pwm_enabled is True
    assert not has_shoot_through((result.decision.gates,))


def test_frequency_ramp_clamps_command_and_vf_range() -> None:
    motor = _nominal_motor()
    boost_controller, _ = _controller(motor, ramp_hz_per_s=10_000.0)
    boosted = boost_controller.step(frequency_command_hz=50.0, load_torque_nm=0.0)
    assert boosted.metrics["frequency_applied_hz"] == 1.0
    assert boosted.metrics["vf_voltage_unlimited_v"] > (
        boost_controller.rated_phase_peak_v / 50.0
    )

    controller, inverter = _controller(motor, ramp_hz_per_s=100_000.0)

    first = controller.step(frequency_command_hz=100.0, load_torque_nm=0.0)
    assert first.metrics["frequency_target_hz"] == 50.0
    assert first.metrics["frequency_applied_hz"] == 10.0
    assert 0.0 < first.metrics["voltage_ref_peak_v"] <= controller.rated_phase_peak_v

    for _ in range(8):
        result = controller.step(frequency_command_hz=100.0, load_torque_nm=0.0)
    assert controller.frequency_hz == 50.0
    assert result.metrics["frequency_applied_hz"] == 50.0
    assert result.metrics["vf_voltage_unlimited_v"] == pytest.approx(
        220.0 * math.sqrt(2.0 / 3.0)
    )
    assert result.metrics["voltage_ref_peak_v"] <= abs(inverter.Vdc) / math.sqrt(3.0)

    falling = controller.step(frequency_command_hz=-20.0, load_torque_nm=0.0)
    assert falling.metrics["frequency_target_hz"] == 0.0
    assert falling.metrics["frequency_applied_hz"] == 40.0


def test_current_guard_forces_zero_voltage_before_gateway_trip() -> None:
    controller, inverter = _controller(
        _nominal_motor(),
        ramp_hz_per_s=500_000.0,
        current_guard_limit_a=2.0,
    )
    result = controller.step(
        frequency_command_hz=25.0,
        load_torque_nm=0.0,
        measured_i_abs=2.0,
    )
    schedule = effective_vector_schedule(result, inverter.t_pwm_s)

    assert result.metrics["current_guard_active"] == 1.0
    assert result.metrics["current_guard_scale"] == 0.0
    assert result.metrics["voltage_ref_peak_v"] == 0.0
    assert len(schedule) == 1
    assert schedule[0].vector_id in {0, 7}
    assert result.decision.accepted is True
    assert result.decision.fault_latched is False


def test_reset_is_deterministic_and_schedule_is_legal() -> None:
    controller, inverter = _controller(_nominal_motor(), ramp_hz_per_s=200_000.0)

    first = controller.step(frequency_command_hz=20.0, load_torque_nm=0.05)
    first_signature = (
        first.vector_schedule,
        first.metrics["frequency_applied_hz"],
        first.metrics["electrical_angle_rad"],
        first.metrics["voltage_ref_peak_v"],
    )
    controller.reset()
    repeated = controller.step(frequency_command_hz=20.0, load_torque_nm=0.05)
    repeated_signature = (
        repeated.vector_schedule,
        repeated.metrics["frequency_applied_hz"],
        repeated.metrics["electrical_angle_rad"],
        repeated.metrics["voltage_ref_peak_v"],
    )
    assert repeated_signature == first_signature

    schedule = effective_vector_schedule(repeated, inverter.t_pwm_s)
    assert sum(segment.dwell_s for segment in schedule) == pytest.approx(inverter.t_pwm_s)
    assert all(validate_vector_id(segment.vector_id) == segment.vector_id for segment in schedule)
    assert all(segment.dwell_s >= inverter.min_pulse_s for segment in schedule)
    assert repeated.decision.accepted is True
    assert not has_shoot_through((repeated.decision.gates,))


def test_short_air56b2_ensemble_smoke() -> None:
    samples = generate_air56b2_ensemble(3, seed=43156)
    for sample in samples:
        motor_params = AlphaBetaMotorParams.from_motor_params(sample.motor)
        controller, inverter = _controller(motor_params, ramp_hz_per_s=50_000.0)
        plant = AlphaBetaInductionMotorModel(motor_params)

        for _ in range(20):
            measured_current = plant.currents().stator_abs
            result = controller.step(
                frequency_command_hz=5.0,
                load_torque_nm=0.0,
                measured_state=plant.state,
                measured_i_abs=measured_current,
            )
            schedule = effective_vector_schedule(result, inverter.t_pwm_s)
            plant_step = step_inverter_schedule(
                plant,
                schedule,
                inverter,
                0.0,
                pwm_enabled=result.decision.pwm_enabled,
            )
            assert all(math.isfinite(value) for value in (
                plant_step.state.omega_m,
                plant_step.currents.stator_abs,
                plant_step.torque_nm,
            ))
            assert all(0 <= segment.vector_id <= 7 for segment in schedule)
            assert sum(segment.dwell_s for segment in schedule) == pytest.approx(inverter.t_pwm_s)

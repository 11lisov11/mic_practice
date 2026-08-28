import math

import pytest

from models.air56b2_loss_thermal import (
    Air56B2LossModelParams,
    MotorThermalParams,
    MotorThermalState,
    evaluate_operating_point,
    optimize_id_reference,
    simulate_constant_thermal_load,
)


def _params() -> Air56B2LossModelParams:
    return Air56B2LossModelParams(
        rs_ref_ohm=5.39,
        rr_ref_ohm=14.22,
        lm_h=0.482,
        lls_h=0.00249,
        llr_h=0.00194,
        pole_pairs=1,
        rated_frequency_hz=50.0,
        rated_omega_rad_s=284.84,
        rated_flux_wb=0.386,
        rated_core_loss_w=53.8,
        viscous_b_nms=1.0e-4,
        coulomb_friction_nm=0.015,
        stator_temp_coeff_per_c=0.0039,
        rotor_temp_coeff_per_c=0.0039,
        reference_temp_c=20.0,
        saturation_knee_flux_wb=0.48,
        saturation_exponent=2.0,
        minimum_lm_scale=0.45,
        vdc_v=310.0,
        pwm_frequency_hz=10_000.0,
        switch_r_on_ohm=0.12,
        switch_voltage_drop_v=1.2,
        phase_voltage_limit_v=170.0,
        phase_current_peak_limit_a=3.5,
    )


def test_loss_components_are_finite_positive_and_sum_exactly() -> None:
    loss = evaluate_operating_point(_params(), speed_rad_s=200.0, torque_nm=0.5, id_a=0.8)
    assert loss.feasible
    for value in (
        loss.stator_copper_w,
        loss.rotor_copper_w,
        loss.core_w,
        loss.mechanical_w,
        loss.inverter_conduction_w,
        loss.inverter_switching_w,
    ):
        assert math.isfinite(value)
        assert value >= 0.0
    assert loss.motor_loss_w == pytest.approx(
        loss.stator_copper_w + loss.rotor_copper_w + loss.core_w + loss.mechanical_w
    )
    assert loss.total_loss_w == pytest.approx(loss.motor_loss_w + loss.inverter_loss_w)


def test_classical_optimizer_respects_constraints_and_does_not_increase_loss() -> None:
    params = _params()
    fixed = evaluate_operating_point(params, speed_rad_s=140.0, torque_nm=0.35, id_a=0.8)
    result = optimize_id_reference(
        params,
        speed_rad_s=140.0,
        torque_nm=0.35,
        id_lower_a=0.15,
        id_upper_a=1.4,
        grid_points=501,
        candidate_id_values=(0.8,),
    )
    assert result.optimum.feasible
    assert result.optimum.total_loss_w <= fixed.total_loss_w
    assert result.optimum.constraint_margin_current_a >= 0.0
    assert result.optimum.constraint_margin_voltage_v >= 0.0


def test_hot_windings_raise_copper_loss() -> None:
    params = _params()
    cold = evaluate_operating_point(
        params,
        speed_rad_s=180.0,
        torque_nm=0.4,
        id_a=0.8,
        thermal_state=MotorThermalState(20.0, 20.0),
    )
    hot = evaluate_operating_point(
        params,
        speed_rad_s=180.0,
        torque_nm=0.4,
        id_a=0.8,
        thermal_state=MotorThermalState(100.0, 120.0),
    )
    assert hot.stator_copper_w > cold.stator_copper_w
    assert hot.rotor_copper_w > cold.rotor_copper_w


def test_two_node_thermal_prior_heats_and_remains_bounded() -> None:
    params = _params()
    losses = evaluate_operating_point(params, speed_rad_s=200.0, torque_nm=0.5, id_a=0.8)
    thermal = MotorThermalParams()
    initial = MotorThermalState(25.0, 25.0)
    final = simulate_constant_thermal_load(initial, losses, thermal, duration_s=600.0, dt_s=0.1)
    assert 25.0 < final.stator_temp_c <= thermal.maximum_temperature_c
    assert 25.0 < final.rotor_temp_c <= thermal.maximum_temperature_c

from __future__ import annotations

import pytest

from control.air56b2_extremum_search import bounded_extremum_search
from models.air56b2_loss_thermal import Air56B2LossModelParams, evaluate_operating_point
from tools.run_air56b2_common_control_benchmark import interpolate_lut_id_a


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


def test_bounded_extremum_search_is_deterministic_and_never_worsens_start() -> None:
    params = _params()
    initial = evaluate_operating_point(
        params,
        speed_rad_s=160.0,
        torque_nm=0.45,
        id_a=0.8,
    )
    first = bounded_extremum_search(
        params,
        speed_rad_s=160.0,
        torque_nm=0.45,
        initial_id_a=0.8,
        id_lower_a=0.12,
        id_upper_a=1.86,
    )
    second = bounded_extremum_search(
        params,
        speed_rad_s=160.0,
        torque_nm=0.45,
        initial_id_a=0.8,
        id_lower_a=0.12,
        id_upper_a=1.86,
    )
    assert first == second
    assert first.optimum.feasible
    assert 0.12 <= first.optimum.id_a <= 1.86
    assert first.optimum.total_loss_w <= initial.total_loss_w
    assert first.evaluated_points <= 1 + 2 * first.iterations


def test_lut_interpolation_is_trilinear_and_clamped() -> None:
    lut = {
        "speed_permille": [200, 1000],
        "torque_permille": [0, 1000],
        "temperatures_c": [20, 120],
        "id_ref_ma": [
            [[200, 400], [600, 800]],
            [[400, 600], [800, 1000]],
        ],
    }
    center = interpolate_lut_id_a(
        lut,
        speed_pu=0.6,
        torque_pu=0.5,
        temperature_c=70.0,
    )
    lower_clamped = interpolate_lut_id_a(
        lut,
        speed_pu=0.0,
        torque_pu=-1.0,
        temperature_c=-20.0,
    )
    upper_clamped = interpolate_lut_id_a(
        lut,
        speed_pu=2.0,
        torque_pu=2.0,
        temperature_c=200.0,
    )
    assert center == pytest.approx(0.6)
    assert lower_clamped == pytest.approx(0.2)
    assert upper_clamped == pytest.approx(1.0)

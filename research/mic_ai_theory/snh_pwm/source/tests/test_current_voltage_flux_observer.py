from __future__ import annotations

import math

import pytest

from control.cyclic_robust_viability_pwm import rotate_alpha_beta, rotate_state
from estimation.current_voltage_flux_observer import (
    CurrentVoltageFluxObserver,
    CurrentVoltageFluxObserverConfig,
)
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    AlphaBetaMotorState,
)


def _params() -> AlphaBetaMotorParams:
    return AlphaBetaMotorParams(
        Rs=2.0,
        Rr=1.6,
        Lls=0.01,
        Llr=0.012,
        Lm=0.16,
        J=0.004,
        B=0.001,
        p=1,
        i_limit=8.0,
    )


def test_nominal_observer_tracks_flux_with_exact_current_voltage_and_speed() -> None:
    params = _params()
    plant = AlphaBetaInductionMotorModel(params)
    observer = CurrentVoltageFluxObserver(
        params,
        CurrentVoltageFluxObserverConfig(speed_filter_gain=1.0),
    )
    observer.reset()
    dt = 100.0e-6

    for index in range(120):
        angle = 0.13 * index
        v_alpha = 48.0 * math.cos(angle)
        v_beta = 48.0 * math.sin(angle)
        before = plant.currents()
        actual = plant.step(v_alpha, v_beta, 0.2, dt)
        update = observer.step(
            v_alpha=v_alpha,
            v_beta=v_beta,
            i_s_alpha_before=before.i_s_alpha,
            i_s_beta_before=before.i_s_beta,
            i_s_alpha_after=actual.currents.i_s_alpha,
            i_s_beta_after=actual.currents.i_s_beta,
            omega_m_measured=actual.state.omega_m,
            dt_s=dt,
        )

    assert update.stator_flux_clipped is False
    assert update.state.psi_s_alpha == pytest.approx(actual.state.psi_s_alpha, abs=1.0e-12)
    assert update.state.psi_s_beta == pytest.approx(actual.state.psi_s_beta, abs=1.0e-12)
    assert update.state.psi_r_alpha == pytest.approx(actual.state.psi_r_alpha, abs=1.0e-12)
    assert update.state.psi_r_beta == pytest.approx(actual.state.psi_r_beta, abs=1.0e-12)
    assert update.state.omega_m == pytest.approx(actual.state.omega_m, abs=1.0e-12)


def test_observer_is_equivariant_under_sixty_degree_rotation() -> None:
    params = _params()
    state = AlphaBetaMotorState(
        psi_s_alpha=0.11,
        psi_s_beta=-0.07,
        psi_r_alpha=0.08,
        psi_r_beta=-0.02,
        omega_m=18.0,
    )
    base = CurrentVoltageFluxObserver(params, state=state)
    rotated = CurrentVoltageFluxObserver(params, state=rotate_state(state, 1))
    angle = math.pi / 3.0
    voltage = (31.0, -17.0)
    current_before = (1.2, -0.4)
    current_after = (1.3, -0.35)
    voltage_rotated = rotate_alpha_beta(*voltage, angle)
    before_rotated = rotate_alpha_beta(*current_before, angle)
    after_rotated = rotate_alpha_beta(*current_after, angle)

    first = base.step(
        v_alpha=voltage[0],
        v_beta=voltage[1],
        i_s_alpha_before=current_before[0],
        i_s_beta_before=current_before[1],
        i_s_alpha_after=current_after[0],
        i_s_beta_after=current_after[1],
        omega_m_measured=19.0,
        dt_s=100.0e-6,
    ).state
    second = rotated.step(
        v_alpha=voltage_rotated[0],
        v_beta=voltage_rotated[1],
        i_s_alpha_before=before_rotated[0],
        i_s_beta_before=before_rotated[1],
        i_s_alpha_after=after_rotated[0],
        i_s_beta_after=after_rotated[1],
        omega_m_measured=19.0,
        dt_s=100.0e-6,
    ).state
    expected = rotate_state(first, 1)
    assert second.psi_s_alpha == pytest.approx(expected.psi_s_alpha, abs=1.0e-12)
    assert second.psi_s_beta == pytest.approx(expected.psi_s_beta, abs=1.0e-12)
    assert second.psi_r_alpha == pytest.approx(expected.psi_r_alpha, abs=1.0e-12)
    assert second.psi_r_beta == pytest.approx(expected.psi_r_beta, abs=1.0e-12)
    assert second.omega_m == pytest.approx(expected.omega_m, abs=1.0e-12)


def test_observer_rejects_nonfinite_measurement_and_nonpositive_dt() -> None:
    observer = CurrentVoltageFluxObserver(_params())
    kwargs = dict(
        v_alpha=0.0,
        v_beta=0.0,
        i_s_alpha_before=0.0,
        i_s_beta_before=0.0,
        i_s_alpha_after=0.0,
        i_s_beta_after=0.0,
        omega_m_measured=0.0,
        dt_s=100.0e-6,
    )
    with pytest.raises(ValueError, match="v_alpha"):
        observer.step(**{**kwargs, "v_alpha": float("nan")})
    with pytest.raises(ValueError, match="dt_s"):
        observer.step(**{**kwargs, "dt_s": 0.0})


def test_observer_clips_unphysical_stator_flux() -> None:
    observer = CurrentVoltageFluxObserver(
        _params(),
        CurrentVoltageFluxObserverConfig(max_stator_flux_wb=0.01),
    )
    update = observer.step(
        v_alpha=1000.0,
        v_beta=0.0,
        i_s_alpha_before=0.0,
        i_s_beta_before=0.0,
        i_s_alpha_after=0.0,
        i_s_beta_after=0.0,
        omega_m_measured=0.0,
        dt_s=1.0e-3,
    )
    assert update.stator_flux_clipped is True
    assert math.hypot(update.state.psi_s_alpha, update.state.psi_s_beta) == pytest.approx(0.01)


def test_observer_configuration_rejects_unsafe_limits() -> None:
    with pytest.raises(ValueError):
        CurrentVoltageFluxObserverConfig(speed_filter_gain=0.0)
    with pytest.raises(ValueError):
        CurrentVoltageFluxObserverConfig(max_stator_flux_wb=0.0)

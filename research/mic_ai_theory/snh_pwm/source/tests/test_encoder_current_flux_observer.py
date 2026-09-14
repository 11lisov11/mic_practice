import math

import pytest

from estimation.encoder_current_flux_observer import EncoderCurrentFluxObserver
from models.induction_motor_alpha_beta import AlphaBetaMotorParams, AlphaBetaInductionMotorModel


def observer():
    return EncoderCurrentFluxObserver(AlphaBetaMotorParams(7., 20., .007, .005, .49, .0001, .0001, 1))


def test_zero_speed_exact_flux_and_current_reconstruction():
    o = observer()
    for _ in range(100):
        state = o.step(i_alpha_a=1., i_beta_a=.5, speed_rad_s=0., dt_s=.001)
    expected = .49*(1-math.exp(-20/.495*.1))
    assert state.psi_r_alpha == pytest.approx(expected, abs=1e-12)
    assert state.psi_r_beta == pytest.approx(.5*expected, abs=1e-12)
    current = AlphaBetaInductionMotorModel(o.params, state).currents()
    assert current.i_s_alpha == pytest.approx(1., abs=1e-12)
    assert current.i_s_beta == pytest.approx(.5, abs=1e-12)


def test_rotating_free_flux_decays():
    o = observer()
    o.step(i_alpha_a=1., i_beta_a=0., speed_rad_s=0., dt_s=.1)
    before = math.hypot(o.state.psi_r_alpha, o.state.psi_r_beta)
    o.step(i_alpha_a=0., i_beta_a=0., speed_rad_s=100., dt_s=.01)
    assert math.hypot(o.state.psi_r_alpha, o.state.psi_r_beta) == pytest.approx(before*math.exp(-20/.495*.01))


def test_rejects_invalid_input_without_mutation():
    o = observer()
    state = o.state
    with pytest.raises(ValueError):
        o.step(i_alpha_a=float("nan"), i_beta_a=0, speed_rad_s=0, dt_s=.001)
    assert o.state == state

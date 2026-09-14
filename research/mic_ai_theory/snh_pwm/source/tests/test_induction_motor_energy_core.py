from dataclasses import replace

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from models.induction_motor_energy_core import EnergyCoreMotor, EnergyCoreParams


def params(**kwargs):
    return replace(EnergyCoreParams(7., 20., .007, .005, .49, 1200., .00012, .0001,
                                   coulomb_nm=.004), **kwargs)


@pytest.mark.parametrize("kappa", [0., .4, 2.])
def test_discrete_energy_with_load_and_saturation(kappa):
    m = EnergyCoreMotor(params(saturation_kappa=kappa))
    for n in range(300):
        t = n * 1e-4
        result = m.step([110 * np.cos(180*t), 110 * np.sin(180*t)], .1, 1e-4)
        assert abs(result.balance_error_j) < 1e-9
        assert min(result.core_j, result.stator_copper_j, result.rotor_copper_j, result.friction_j) >= 0


def test_continuous_energy_gradient_identity():
    p = params(saturation_kappa=.8)
    m = EnergyCoreMotor(p, [.3, .09, .29, .087, .295, .088, 70.])
    x, v, load = m.state, np.array([70., 50.]), .2
    mid, i_s, i_r, i_c, _, friction, _ = m._terms(x, x)
    im = mid[4:6] / p.lm_h * (1 + p.saturation_kappa * (mid[4:6] @ mid[4:6]) / p.saturation_knee_wb**2)
    gradient = np.concatenate((1.5*i_s, 1.5*i_r, 1.5*(im-i_s-i_r), [p.inertia_kg_m2*x[6]]))
    expected = 1.5 * (v@i_s - p.rs_ohm*(i_s@i_s) - p.rr_ohm*(i_r@i_r) - p.rc_ohm*(i_c@i_c)) - (friction+load)*x[6]
    assert gradient @ m.derivative(x, v, load) == pytest.approx(expected, abs=1e-9)


def test_zero_input_passivity_and_core_branch_carries_current():
    initial = [.3, .09, .29, .087, .295, .088, 70.]
    m = EnergyCoreMotor(params(saturation_kappa=.5), initial)
    energy = m.stored_energy_j()
    core_loss = 0.
    for _ in range(300):
        result = m.step([0., 0.], 0., 1e-4)
        current_energy = m.stored_energy_j()
        assert current_energy <= energy + 1e-10
        energy = current_energy
        core_loss += result.core_j
    assert core_loss > .001
    low = EnergyCoreMotor(params(rc_ohm=300.))
    high = EnergyCoreMotor(params(rc_ohm=30000.))
    for n in range(100):
        voltage = [80*np.cos(n*.03), 80*np.sin(n*.03)]
        low.step(voltage, 0., 1e-4)
        high.step(voltage, 0., 1e-4)
    assert np.linalg.norm(low.currents()[0] - high.currents()[0]) > .01


def test_newton_jacobian_matches_finite_difference():
    m = EnergyCoreMotor(params(saturation_kappa=.7))
    old = np.array([.3, .09, .29, .087, .295, .088, 70.])
    new = old + np.array([.001, .002, .003, .001, .002, .001, .1])
    dt, h = 1e-4, 1e-7
    def residual(x):
        return x-old-dt*m._rhs(old, x, np.array([50., 20.]), .1)
    finite = np.column_stack([(residual(new+np.eye(7)[i]*h)-residual(new-np.eye(7)[i]*h))/(2*h) for i in range(7)])
    np.testing.assert_allclose(m._jacobian(old, new, dt), finite, atol=1e-7, rtol=1e-7)


def test_convergence_to_independent_radau():
    p = params(saturation_kappa=.4)
    initial = np.array([.1, .02, .098, .019, .099, .0195, 30.])
    reference = EnergyCoreMotor(p, initial)
    def voltage(t):
        return np.array([50*np.cos(100*t), 50*np.sin(100*t)])
    sol = solve_ivp(lambda t, x: reference.derivative(x, voltage(t), .05),
                    (0., .01), initial, method="Radau", rtol=1e-10, atol=1e-12)
    assert sol.success
    errors = []
    for dt in [1e-4, 5e-5, 2.5e-5]:
        m = EnergyCoreMotor(p, initial)
        for n in range(round(.01/dt)):
            m.step(voltage((n+.5)*dt), .05, dt)
        errors.append(np.linalg.norm((m.state-sol.y[:, -1]) / [1, 1, 1, 1, 1, 1, 100]))
    assert errors[1] < errors[0]/2.5
    assert errors[2] < errors[1]/2.5
    assert errors[-1] < 2e-5


@pytest.mark.parametrize("field,value", [("rc_ohm", 0), ("lm_h", -1), ("saturation_kappa", -1),
                                        ("pole_pairs", 1.5), ("rs_ohm", float("nan"))])
def test_invalid_params(field, value):
    with pytest.raises(ValueError):
        params(**{field: value})


def test_invalid_step_does_not_mutate():
    m = EnergyCoreMotor(params())
    with pytest.raises(ValueError):
        m.step([float("nan"), 0], 0, .001)
    np.testing.assert_array_equal(m.state, np.zeros(7))


@pytest.mark.parametrize("rc", [1200., 4000.])
def test_prezero_state_full_trajectory_and_integrated_losses_against_radau(rc):
    # A pre-energized core branch excites fast modes hidden by endpoint-only QA.
    m = EnergyCoreMotor(params(rc_ohm=rc, saturation_kappa=.4),
                        [.1, .02, .098, .019, .099, .0195, 30.])
    initial = m.state.copy()
    voltage = np.array([50., 10.])
    def rhs(t, x):
        mid, i_s, i_r, i_c, _, friction, _ = m._terms(x[:7], x[:7])
        p = m.params
        power = [1.5*(voltage@i_s), 1.5*p.rs_ohm*(i_s@i_s),
                 1.5*p.rr_ohm*(i_r@i_r), 1.5*p.rc_ohm*(i_c@i_c), friction*mid[6]]
        return np.concatenate((m.derivative(x[:7], voltage, 0.), power))
    reference = solve_ivp(rhs, (0, .002), np.concatenate((initial, np.zeros(5))),
                          method="Radau", dense_output=True, rtol=1e-10, atol=1e-12)
    assert reference.success
    errors = []
    for dt in [1e-4, 2.5e-5, 5e-7]:
        plant = EnergyCoreMotor(m.params, initial)
        totals = np.zeros(5)
        maximum_error = 0.
        for n in range(round(.002/dt)):
            step = plant.step(voltage, 0., dt)
            exact = reference.sol((n+1)*dt)
            maximum_error = max(maximum_error, np.linalg.norm(plant.currents()[0]-m.currents(exact[:7])[0]))
            totals += [step.input_j, step.stator_copper_j, step.rotor_copper_j, step.core_j, step.friction_j]
        errors.append(maximum_error)
    assert errors[-1] < errors[0]/10
    assert errors[-1] < .005
    np.testing.assert_allclose(totals, reference.y[7:, -1], rtol=2e-3, atol=2e-7)
    assert plant.stored_energy_j() == pytest.approx(m.stored_energy_j(reference.y[:7, -1]), abs=2e-7)

"""Passive stationary-frame T circuit with a physical core-current branch.

Amplitude-invariant alpha/beta vectors are peak-valued. Currents into both
windings are positive into the T node. A discrete gradient preserves the
electrical/mechanical work balance, including nonlinear magnetizing energy.
This averaged research plant is NOT an identified AIR56B2 hardware model.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class EnergyCoreParams:
    rs_ohm: float
    rr_ohm: float
    lls_h: float
    llr_h: float
    lm_h: float
    rc_ohm: float
    inertia_kg_m2: float
    viscous_nm_s: float
    pole_pairs: int = 1
    coulomb_nm: float = 0.0
    friction_smoothing_rad_s: float = 0.5
    saturation_kappa: float = 0.0
    saturation_knee_wb: float = 0.5

    def __post_init__(self):
        for name, value in vars(self).items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        for name in ("rs_ohm", "rr_ohm", "lls_h", "llr_h", "lm_h", "rc_ohm",
                     "inertia_kg_m2", "friction_smoothing_rad_s", "saturation_knee_wb"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.pole_pairs < 1 or int(self.pole_pairs) != self.pole_pairs:
            raise ValueError("pole_pairs must be a positive integer")
        if min(self.viscous_nm_s, self.coulomb_nm, self.saturation_kappa) < 0:
            raise ValueError("dissipation and saturation coefficients must be nonnegative")


@dataclass(frozen=True)
class EnergyCoreStep:
    input_j: float
    stator_copper_j: float
    rotor_copper_j: float
    core_j: float
    friction_j: float
    shaft_work_j: float
    stored_change_j: float
    balance_error_j: float
    torque_nm: float
    current_mid_a: tuple[float, float]
    newton_iterations: int

    @property
    def loss_j(self):
        return self.stator_copper_j + self.rotor_copper_j + self.core_j + self.friction_j


_J2 = np.array([[0., -1.], [1., 0.]])
_I2 = np.eye(2)


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


class EnergyCoreMotor:
    def __init__(self, params: EnergyCoreParams, state=None):
        self.params = params
        self.state = np.zeros(7) if state is None else np.asarray(state, dtype=float).copy()
        if self.state.shape != (7,) or not np.isfinite(self.state).all():
            raise ValueError("state must contain seven finite values")
        self.angle_rad = 0.0

    def currents(self, state=None):
        x = self.state if state is None else np.asarray(state)
        p = self.params
        return (x[:2] - x[4:6]) / p.lls_h, (x[2:4] - x[4:6]) / p.llr_h

    def stored_energy_j(self, state=None):
        x = self.state if state is None else np.asarray(state)
        p = self.params
        i_s, i_r = self.currents(x)
        m2 = x[4:6] @ x[4:6]
        return float(.75 * (p.lls_h * (i_s @ i_s) + p.llr_h * (i_r @ i_r))
                     + 1.5 / p.lm_h * (m2 / 2 + p.saturation_kappa * m2**2
                                                       / (4 * p.saturation_knee_wb**2))
                     + .5 * p.inertia_kg_m2 * x[6]**2)

    def _terms(self, old, new):
        p = self.params
        mid = (new + old) / 2
        i_s, i_r = self.currents(mid)
        m0, m1 = old[4:6], new[4:6]
        a = 1 + p.saturation_kappa * (m1 @ m1 + m0 @ m0) / (2 * p.saturation_knee_wb**2)
        i_m = mid[4:6] * a / p.lm_h
        i_c = i_s + i_r - i_m
        torque = 1.5 * p.pole_pairs / p.llr_h * _cross(mid[2:4], mid[4:6])
        friction = p.viscous_nm_s * mid[6] + p.coulomb_nm * math.tanh(
            mid[6] / p.friction_smoothing_rad_s)
        return mid, i_s, i_r, i_c, torque, friction, a

    def _rhs(self, old, new, voltage, load):
        p = self.params
        mid, i_s, i_r, i_c, torque, friction, _ = self._terms(old, new)
        return np.concatenate((voltage - p.rs_ohm * i_s,
                               -p.rr_ohm * i_r + p.pole_pairs * mid[6] * (_J2 @ mid[2:4]),
                               p.rc_ohm * i_c,
                               [(torque - load - friction) / p.inertia_kg_m2]))

    def derivative(self, state, voltage, load_nm):
        """Continuous equations, also exposed for independent Radau validation."""
        return self._rhs(np.asarray(state), np.asarray(state), np.asarray(voltage), load_nm)

    def _jacobian(self, old, new, dt):
        p = self.params
        mid, _, _, _, _, _, a = self._terms(old, new)
        jac = np.eye(7)
        jac[:2, :2] += dt * p.rs_ohm / (2 * p.lls_h) * _I2
        jac[:2, 4:6] -= dt * p.rs_ohm / (2 * p.lls_h) * _I2
        jac[2:4, 2:4] += dt * p.rr_ohm / (2 * p.llr_h) * _I2 - dt * p.pole_pairs * mid[6] / 2 * _J2
        jac[2:4, 4:6] -= dt * p.rr_ohm / (2 * p.llr_h) * _I2
        jac[2:4, 6] -= dt * p.pole_pairs / 2 * (_J2 @ mid[2:4])
        d_im = a / (2 * p.lm_h) * _I2 + p.saturation_kappa / (2 * p.lm_h * p.saturation_knee_wb**2) * np.outer(
            new[4:6] + old[4:6], new[4:6])
        jac[4:6, :2] -= dt * p.rc_ohm / (2 * p.lls_h) * _I2
        jac[4:6, 2:4] -= dt * p.rc_ohm / (2 * p.llr_h) * _I2
        jac[4:6, 4:6] += dt * p.rc_ohm * ((1 / (2 * p.lls_h) + 1 / (2 * p.llr_h)) * _I2 + d_im)
        factor = -dt / p.inertia_kg_m2 * 1.5 * p.pole_pairs / (2 * p.llr_h)
        jac[6, 2:4] += factor * np.array([mid[5], -mid[4]])
        jac[6, 4:6] += factor * np.array([-mid[3], mid[2]])
        jac[6, 6] += dt / (2 * p.inertia_kg_m2) * (
            p.viscous_nm_s + p.coulomb_nm / p.friction_smoothing_rad_s
            * (1 - math.tanh(mid[6] / p.friction_smoothing_rad_s)**2))
        return jac

    def step(self, voltage, load_nm, dt_s):
        v = np.asarray(voltage, dtype=float)
        if v.shape != (2,) or not np.isfinite(v).all() or not math.isfinite(load_nm):
            raise ValueError("finite two-axis voltage and load required")
        if not math.isfinite(dt_s) or dt_s <= 0:
            raise ValueError("dt_s must be finite and positive")
        old = self.state.copy()
        new = old.copy()
        scale = np.array([1., 1., 1., 1., 1., 1., 100.])
        tolerance = 2e-12
        for iteration in range(20):
            residual = new - old - dt_s * self._rhs(old, new, v, load_nm)
            norm = np.max(np.abs(residual / scale))
            if norm < tolerance:
                break
            delta = np.linalg.solve(self._jacobian(old, new, dt_s), -residual)
            factor = 1.
            for _ in range(12):
                candidate = new + factor * delta
                trial = candidate - old - dt_s * self._rhs(old, candidate, v, load_nm)
                if np.isfinite(trial).all() and np.max(np.abs(trial / scale)) < norm:
                    new = candidate
                    break
                factor /= 2
            else:
                raise ArithmeticError("core model Newton line search failed; state not advanced")
        else:
            raise ArithmeticError("core model Newton failed to converge; state not advanced")
        p = self.params
        mid, i_s, i_r, i_c, torque, friction, _ = self._terms(old, new)
        pin = dt_s * 1.5 * float(v @ i_s)
        stator = dt_s * 1.5 * p.rs_ohm * float(i_s @ i_s)
        rotor = dt_s * 1.5 * p.rr_ohm * float(i_r @ i_r)
        core = dt_s * 1.5 * p.rc_ohm * float(i_c @ i_c)
        friction_work = dt_s * friction * mid[6]
        shaft = dt_s * load_nm * mid[6]
        stored = self.stored_energy_j(new) - self.stored_energy_j(old)
        balance = pin - stator - rotor - core - friction_work - shaft - stored
        if not np.isfinite(new).all() or abs(balance) > 1e-8 * (1 + abs(pin) + abs(stored)):
            raise ArithmeticError("core model energy audit failed; state not advanced")
        self.state = new
        self.angle_rad += dt_s * mid[6]
        return EnergyCoreStep(pin, stator, rotor, core, friction_work, shaft, stored,
                              balance, torque, tuple(i_s), iteration)

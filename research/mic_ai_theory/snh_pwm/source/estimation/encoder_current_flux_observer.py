"""Encoder-aided, linear current-model observer; not a sensorless observer.

Constant-current/constant-speed exact integration avoids voltage-integrator
DC drift. Rotor resistance, saturation and omitted core current remain model
errors; no true plant flux/torque/temperature is accepted by this interface.
"""
from __future__ import annotations

import cmath
from dataclasses import replace
import math

from models.induction_motor_alpha_beta import AlphaBetaMotorParams, AlphaBetaMotorState


class EncoderCurrentFluxObserver:
    def __init__(self, params: AlphaBetaMotorParams):
        self.params = params
        for name in ("Rr", "Lm", "Llr", "Lls", "p"):
            if not math.isfinite(getattr(params, name)) or getattr(params, name) <= 0:
                raise ValueError(f"{name} must be positive and finite")
        self.state = AlphaBetaMotorState()

    def step(self, *, i_alpha_a, i_beta_a, speed_rad_s, dt_s):
        if not all(math.isfinite(v) for v in (i_alpha_a, i_beta_a, speed_rad_s, dt_s)) or dt_s <= 0:
            raise ValueError("finite observations and positive timestep required")
        p = self.params
        lr = p.Lm+p.Llr
        inverse_tau = p.Rr/lr
        a = complex(-inverse_tau, p.p*speed_rad_s)
        z = a*dt_s
        gain = (z+z*z/2+z*z*z/6) if abs(z) < 1e-5 else cmath.exp(z)-1
        current = complex(i_alpha_a, i_beta_a)
        flux = complex(self.state.psi_r_alpha, self.state.psi_r_beta)
        flux = (1+gain)*flux + inverse_tau*p.Lm*gain/a*current
        sigma_ls = p.Lls+p.Lm-p.Lm*p.Lm/lr
        stator_flux = sigma_ls*current+p.Lm/lr*flux
        self.state = replace(self.state, psi_r_alpha=flux.real, psi_r_beta=flux.imag,
            psi_s_alpha=stator_flux.real, psi_s_beta=stator_flux.imag,
            omega_m=speed_rad_s, theta_m=self.state.theta_m+speed_rad_s*dt_s)
        return self.state

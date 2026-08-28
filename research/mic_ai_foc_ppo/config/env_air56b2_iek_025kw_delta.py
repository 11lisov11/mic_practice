from __future__ import annotations

import math
from dataclasses import replace

from config.env import create_default_env, estimate_motor_params_from_nameplate


"""Preliminary digital-twin profile for the user's IEK AIR56B2 motor.

Passport values are copied from the official IEK AIR56B2 catalogue entry:
0.25 kW, 220/380 V Delta/Y, 1.24/0.72 A Delta/Y, 50 Hz, 2720 rpm,
cos(phi)=0.78, eta=0.68, two poles (one pole pair).

The electrical Rs/Rr/Lm parameters and the inertia are not in the nameplate.
They remain explicit preliminary estimates and this profile must not be used to
approve an HV run, a firmware release, or an AI checkpoint without ID data.
"""

SOURCE_KIND = "official_catalog_nameplate_with_unmeasured_model_parameters"
PHYSICAL_CONNECTION = "D"
MODEL_CONNECTION = "Y_equivalent_of_delta"

# Physical passport data.  The motor terminal links must be Delta for the
# 220 V inverter output; this dictionary is deliberately not fed directly
# into the star-connected dq model.
NAMEPLATE_AIR56B2_025KW_DELTA = {
    "P_n": 250.0,
    "U_ll": 220.0,
    "I_n": 1.24,
    "cos_phi_n": 0.78,
    "eta_n": 0.68,
    "f_n": 50.0,
    "p": 1,
    "n_rated": 2720.0,
    "connection": "D",
    # Not a passport value.  Replace after coast-down / locked-rotor ID.
    "J": 1.5e-4,
}

# The motor equations use a star phase model.  Convert the 220 V Delta motor
# to its 220 V line-to-line star equivalent: 127.0 V phase and 1.24 A
# line/phase.  This preserves apparent power and fits the 325 V DC-link limit.
MODEL_INPUT_AIR56B2_STAR_EQUIVALENT = {
    **NAMEPLATE_AIR56B2_025KW_DELTA,
    "connection": "Y",
}

_base = create_default_env()
_motor_est = estimate_motor_params_from_nameplate(MODEL_INPUT_AIR56B2_STAR_EQUIVALENT)
_motor = replace(
    _motor_est,
    # Nameplate-derived leakage inductances are intentionally only a stable
    # starting point for identification, not measured motor constants.
    Ls_sigma=float(max(getattr(_motor_est, "Ls_sigma", 0.05), 0.05)),
    Lr_sigma=float(max(getattr(_motor_est, "Lr_sigma", 0.05), 0.05)),
    J=float(MODEL_INPUT_AIR56B2_STAR_EQUIVALENT["J"]),
)

_torque_nom = float(NAMEPLATE_AIR56B2_025KW_DELTA["P_n"]) / max(
    2.0 * math.pi * float(NAMEPLATE_AIR56B2_025KW_DELTA["n_rated"]) / 60.0,
    1e-6,
)
_sim = replace(
    _base.sim,
    t_end=2.0,
    dt=5e-4,
    save_prefix="air56b2_iek_025kw_delta_preliminary",
    # The generic model currently applies a constant load at standstill.  It
    # cannot validate a loaded start without an identified load model, so the
    # preliminary smoke case is an unloaded voltage/frequency ramp only.
    mode="scalar",
    scenario_name="ramp:1.0",
    load_torque=0.0,
)
_inverter = replace(
    _base.inverter,
    # 220 Vac rectified: nominal DC bus is about 311 V; 325 V is the MCSDK
    # reference setpoint.  It is below the 400 V input rating of STEVAL-IPM15B.
    Vdc=325.0,
    r_out=0.12,
    dead_time=2e-6,
    v_drop=1.2,
)
_scalar_vf = replace(
    _base.scalar_vf,
    k_vf=(220.0 / math.sqrt(3.0)) / 50.0,
    u_boost=12.0,
    f_min=1.0,
    f_max=50.0,
    u_phase_nom=220.0 / math.sqrt(3.0),
)
_foc = replace(
    _base.foc,
    id_ref=0.25,
    iq_limit=1.24,
    v_limit=325.0 / math.sqrt(3.0),
)

ENV = replace(
    _base,
    motor=_motor,
    inverter=_inverter,
    scalar_vf=_scalar_vf,
    foc=_foc,
    sim=_sim,
)

__all__ = [
    "ENV",
    "NAMEPLATE_AIR56B2_025KW_DELTA",
    "MODEL_INPUT_AIR56B2_STAR_EQUIVALENT",
    "PHYSICAL_CONNECTION",
    "MODEL_CONNECTION",
    "SOURCE_KIND",
]

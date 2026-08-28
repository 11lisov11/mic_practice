"""
Конфигурация проекта MIC AI.

Все настраиваемые параметры собраны сверху с русскими комментариями.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

# -------- Параметры симуляции ----------
SIM_T_END = 3.0            # время моделирования, с
SIM_DT = 1e-4              # дискретизация, с
SIM_MODE = "foc"           # "scalar" или "foc"
SIM_SCENARIO = "speed_step"  # сценарий: speed_step / ramp и т.д.
SIM_SAVE_PREFIX = "run"    # префикс для файла результатов
SIM_LOAD_TORQUE = 1.0      # постоянный момент нагрузки, Нм
# ---------------------------------------

# ------ Паспортные данные электродвигателя -------
NAMEPLATE_P_KW = 0.25       # номинальная мощность, кВт
NAMEPLATE_U_LL = 220.0      # AIR56B2: линейное напряжение при соединении D, В
NAMEPLATE_I_N = 1.24        # AIR56B2: линейный ток, А
NAMEPLATE_COSPHI = 0.78     # AIR56B2: коэффициент мощности по каталогу IEK
NAMEPLATE_ETA = 0.68        # AIR56B2: КПД по каталогу IEK
NAMEPLATE_F_N = 50.0        # частота сети, Гц
NAMEPLATE_POLE_PAIRS = 1    # AIR56B2: число пар полюсов
NAMEPLATE_N_RATED = 2720.0  # AIR56B2: номинальная скорость, об/мин
NAMEPLATE_CONNECTION = "D"  # AIR56B2: треугольник для 220 В line-to-line
# -------------------------------------------------

# ------ Параметры инвертора -------
INVERTER_VDC = 310.0       # расчетное звено после выпрямления 220 В, В
INVERTER_F_PWM = 10_000.0  # частота ШИМ, Гц
# ----------------------------------

NAMEPLATE_DEFAULT = {
    "P_n": NAMEPLATE_P_KW * 1000.0,
    "U_ll": NAMEPLATE_U_LL,
    "I_n": NAMEPLATE_I_N,
    "cos_phi_n": NAMEPLATE_COSPHI,
    "eta_n": NAMEPLATE_ETA,
    "f_n": NAMEPLATE_F_N,
    "p": NAMEPLATE_POLE_PAIRS,
    "n_rated": NAMEPLATE_N_RATED,
    "connection": NAMEPLATE_CONNECTION,
}

VF_K = NAMEPLATE_U_LL / (math.sqrt(3.0) * NAMEPLATE_F_N)


# --------- Структуры данных ------------
@dataclass(frozen=True)
class MotorParams:
    Rs: float
    Rr: float
    Ls_sigma: float
    Lr_sigma: float
    Lm: float
    J: float
    B: float
    p: int
    I_n: float = NAMEPLATE_I_N
    psi_sat: float = 0.0
    sat_exp: float = 2.0
    lm_min_scale: float = 0.2


@dataclass(frozen=True)
class InverterParams:
    Vdc: float
    f_pwm: float
    r_out: float = 0.0
    dead_time: float = 0.0
    v_drop: float = 0.0


@dataclass(frozen=True)
class ScalarVfParams:
    k_vf: float
    u_boost: float
    f_min: float
    f_max: float


@dataclass(frozen=True)
class FocParams:
    kp_id: float
    ki_id: float
    kp_iq: float
    ki_iq: float
    kp_speed: float
    ki_speed: float
    id_ref: float = 0.0
    iq_limit: float | None = None
    v_limit: float | None = None
    field_weakening_enable: bool = False
    field_weakening_id_min: float = 0.0
    field_weakening_trigger_ratio: float = 0.98
    field_weakening_relax_ratio: float = 0.92
    field_weakening_dec_step: float = 0.05
    field_weakening_relax_step: float = 0.02


@dataclass(frozen=True)
class SimulationParams:
    t_end: float
    dt: float
    mode: str
    scenario_name: str
    save_prefix: str
    load_torque: float = 0.0
    # Sensor noise (applied to controller inputs inside InductionMotorEnv; metrics use true states).
    sigma_omega: float = 0.0
    sigma_i_abc: float = 0.0


@dataclass(frozen=True)
class EnvConfig:
    motor: MotorParams
    inverter: InverterParams
    scalar_vf: ScalarVfParams
    foc: FocParams
    sim: SimulationParams
# ---------------------------------------


def _require_official_air56b2_nameplate(nameplate: dict) -> None:
    """Reject silent substitution of guessed or legacy motor data."""

    if set(nameplate) != set(NAMEPLATE_DEFAULT):
        raise ValueError("nameplate must contain only the official AIR56B2 fields")
    for key, expected in NAMEPLATE_DEFAULT.items():
        actual = nameplate[key]
        if isinstance(expected, str):
            matches = str(actual).upper() == expected.upper()
        else:
            matches = math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12)
        if not matches:
            raise ValueError(f"{key}={actual!r} does not match official AIR56B2 value {expected!r}")


@lru_cache(maxsize=1)
def _default_nameplate_constrained_estimate() -> tuple[MotorParams, float]:
    """Return a reproducible estimate; no value here is claimed as measured."""

    # Local import keeps the base dataclasses independent from the estimator.
    from models.air56b2_nameplate_ensemble import (
        generate_air56b2_ensemble,
        select_nominal_sample,
    )

    samples = generate_air56b2_ensemble(256, seed=560225)
    nominal = select_nominal_sample(samples)
    return nominal.motor, nominal.magnetizing_current_a


def estimate_motor_params_from_nameplate(nameplate: dict) -> MotorParams:
    """Select the canonical passport-constrained AIR56B2 simulation estimate.

    Rs, Rr, leakage, Lm, J and B are not uniquely calculable from one rounded
    nameplate operating point. The returned model is the deterministic central
    member of the constrained ensemble, not a hardware-identified parameter set.
    """

    _require_official_air56b2_nameplate(nameplate)
    motor, _ = _default_nameplate_constrained_estimate()
    return motor


def estimate_id_ref_from_nameplate(nameplate: dict) -> float:
    """Return the nominal model magnetizing current, marked as an estimate."""

    _require_official_air56b2_nameplate(nameplate)
    _, magnetizing_current_a = _default_nameplate_constrained_estimate()
    return magnetizing_current_a


# --------- Готовая конфигурация ENV ------------
def create_default_env() -> EnvConfig:
    motor = estimate_motor_params_from_nameplate(NAMEPLATE_DEFAULT)
    id_ref = estimate_id_ref_from_nameplate(NAMEPLATE_DEFAULT)
    return EnvConfig(
        motor=motor,
        inverter=InverterParams(
            Vdc=INVERTER_VDC,
            f_pwm=INVERTER_F_PWM,
        ),
        scalar_vf=ScalarVfParams(
            k_vf=VF_K,
            u_boost=25.0,
            f_min=1.0,
            f_max=50.0,
        ),
        foc=FocParams(
            kp_id=1.0,
            ki_id=100.0,
            kp_iq=1.0,
            ki_iq=100.0,
            kp_speed=0.5,
            ki_speed=2.5,
            id_ref=id_ref,
            iq_limit=2.0,
            v_limit=INVERTER_VDC / math.sqrt(3.0),
        ),
        sim=SimulationParams(
            t_end=SIM_T_END,
            dt=SIM_DT,
            mode=SIM_MODE,
            scenario_name=SIM_SCENARIO,
            save_prefix=SIM_SAVE_PREFIX,
            load_torque=SIM_LOAD_TORQUE,
        ),
    )

# No module-level ENV: call create_default_env() explicitly so that construction
# of the passport-constrained estimate is visible to the caller.
# -----------------------------------------------


__all__ = [
    "MotorParams",
    "InverterParams",
    "ScalarVfParams",
    "FocParams",
    "SimulationParams",
    "EnvConfig",
    "estimate_motor_params_from_nameplate",
    "estimate_id_ref_from_nameplate",
    "NAMEPLATE_DEFAULT",
    "SIM_T_END",
    "SIM_DT",
    "SIM_MODE",
    "SIM_SCENARIO",
    "SIM_SAVE_PREFIX",
    "SIM_LOAD_TORQUE",
    "INVERTER_VDC",
    "INVERTER_F_PWM",
    "create_default_env", 
]

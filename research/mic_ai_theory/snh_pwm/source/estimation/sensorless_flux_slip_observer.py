from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SensorlessFluxSlipConfig:
    rs_ohm: float
    rr_ohm: float
    ls_h: float
    lr_h: float
    lm_h: float
    pole_pairs: int
    flux_leak_per_s: float = 3.0
    speed_filter_tau_s: float = 0.03
    slip_gain: float = 1.0
    minimum_flux_wb: float = 0.025
    maximum_flux_wb: float = 1.2
    maximum_abs_speed_rad_s: float = 500.0
    maximum_abs_slip_rad_s: float = 250.0

    def __post_init__(self) -> None:
        for name in ("rs_ohm", "rr_ohm", "ls_h", "lr_h", "lm_h"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.lm_h**2 >= self.ls_h * self.lr_h:
            raise ValueError("observer inductance matrix must be positive definite")
        if self.pole_pairs <= 0:
            raise ValueError("pole_pairs must be positive")
        if self.flux_leak_per_s < 0.0 or self.speed_filter_tau_s <= 0.0:
            raise ValueError("observer leak must be non-negative and filter tau positive")
        if not 0.0 < self.minimum_flux_wb < self.maximum_flux_wb:
            raise ValueError("flux validity bounds are invalid")


@dataclass(frozen=True)
class SensorlessFluxSlipState:
    psi_s_alpha_wb: float = 0.0
    psi_s_beta_wb: float = 0.0
    rotor_flux_alpha_wb: float = 0.0
    rotor_flux_beta_wb: float = 0.0
    rotor_flux_angle_rad: float = 0.0
    omega_sync_e_rad_s: float = 0.0
    omega_slip_e_rad_s: float = 0.0
    omega_m_rad_s: float = 0.0
    valid: bool = False


@dataclass(frozen=True)
class SensorlessFluxSlipUpdate:
    state: SensorlessFluxSlipState
    input_contract: str = "applied_voltage_and_measured_stator_current_only"


def _angle_delta(current: float, previous: float) -> float:
    return math.atan2(math.sin(current - previous), math.cos(current - previous))


class SensorlessFluxSlipObserver:
    """Voltage/flux/slip observer with no encoder or true-state input."""

    def __init__(self, config: SensorlessFluxSlipConfig) -> None:
        self.config = config
        self.state = SensorlessFluxSlipState()

    def reset(self) -> SensorlessFluxSlipState:
        self.state = SensorlessFluxSlipState()
        return self.state

    def step(
        self,
        *,
        v_alpha_v: float,
        v_beta_v: float,
        i_s_alpha_a: float,
        i_s_beta_a: float,
        dt_s: float,
    ) -> SensorlessFluxSlipUpdate:
        values = (v_alpha_v, v_beta_v, i_s_alpha_a, i_s_beta_a, dt_s)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("observer inputs must be finite")
        dt = float(dt_s)
        if dt <= 0.0:
            raise ValueError("dt_s must be positive")
        cfg = self.config
        decay = max(0.0, 1.0 - cfg.flux_leak_per_s * dt)
        psi_s_a = decay * self.state.psi_s_alpha_wb + dt * (
            float(v_alpha_v) - cfg.rs_ohm * float(i_s_alpha_a)
        )
        psi_s_b = decay * self.state.psi_s_beta_wb + dt * (
            float(v_beta_v) - cfg.rs_ohm * float(i_s_beta_a)
        )
        psi_s_abs = math.hypot(psi_s_a, psi_s_b)
        if psi_s_abs > cfg.maximum_flux_wb:
            scale = cfg.maximum_flux_wb / psi_s_abs
            psi_s_a *= scale
            psi_s_b *= scale

        sigma = 1.0 - cfg.lm_h**2 / (cfg.ls_h * cfg.lr_h)
        leakage_flux_scale = sigma * cfg.ls_h
        rotor_scale = cfg.lr_h / cfg.lm_h
        psi_r_a = rotor_scale * (psi_s_a - leakage_flux_scale * float(i_s_alpha_a))
        psi_r_b = rotor_scale * (psi_s_b - leakage_flux_scale * float(i_s_beta_a))
        rotor_flux_abs = math.hypot(psi_r_a, psi_r_b)
        valid = rotor_flux_abs >= cfg.minimum_flux_wb
        angle = self.state.rotor_flux_angle_rad
        omega_sync = self.state.omega_sync_e_rad_s
        omega_slip = self.state.omega_slip_e_rad_s
        omega_mech_raw = self.state.omega_m_rad_s
        if valid:
            angle = math.atan2(psi_r_b, psi_r_a)
            if self.state.valid:
                omega_sync = _angle_delta(angle, self.state.rotor_flux_angle_rad) / dt
            unit_a = psi_r_a / rotor_flux_abs
            unit_b = psi_r_b / rotor_flux_abs
            iq = -unit_b * float(i_s_alpha_a) + unit_a * float(i_s_beta_a)
            omega_slip = cfg.slip_gain * (cfg.rr_ohm * cfg.lm_h / cfg.lr_h) * iq / rotor_flux_abs
            omega_slip = max(-cfg.maximum_abs_slip_rad_s, min(cfg.maximum_abs_slip_rad_s, omega_slip))
            omega_mech_raw = (omega_sync - omega_slip) / cfg.pole_pairs
            omega_mech_raw = max(
                -cfg.maximum_abs_speed_rad_s,
                min(cfg.maximum_abs_speed_rad_s, omega_mech_raw),
            )
        alpha = 1.0 - math.exp(-dt / cfg.speed_filter_tau_s)
        omega_mech = self.state.omega_m_rad_s + alpha * (omega_mech_raw - self.state.omega_m_rad_s)
        self.state = SensorlessFluxSlipState(
            psi_s_alpha_wb=psi_s_a,
            psi_s_beta_wb=psi_s_b,
            rotor_flux_alpha_wb=psi_r_a,
            rotor_flux_beta_wb=psi_r_b,
            rotor_flux_angle_rad=angle,
            omega_sync_e_rad_s=omega_sync,
            omega_slip_e_rad_s=omega_slip,
            omega_m_rad_s=omega_mech,
            valid=valid,
        )
        return SensorlessFluxSlipUpdate(state=self.state)


__all__ = [
    "SensorlessFluxSlipConfig",
    "SensorlessFluxSlipObserver",
    "SensorlessFluxSlipState",
    "SensorlessFluxSlipUpdate",
]

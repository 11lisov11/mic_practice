from __future__ import annotations

from dataclasses import dataclass, replace
import math

from models.induction_motor_alpha_beta import AlphaBetaMotorParams, AlphaBetaMotorState


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True)
class CurrentVoltageFluxObserverConfig:
    speed_filter_gain: float = 0.35
    flux_leak_per_s: float = 0.0
    max_stator_flux_wb: float = 2.0
    max_abs_speed_rad_s: float = 1000.0

    def __post_init__(self) -> None:
        gain = _finite(self.speed_filter_gain, "speed_filter_gain")
        leak = _finite(self.flux_leak_per_s, "flux_leak_per_s")
        max_flux = _finite(self.max_stator_flux_wb, "max_stator_flux_wb")
        max_speed = _finite(self.max_abs_speed_rad_s, "max_abs_speed_rad_s")
        if not 0.0 < gain <= 1.0:
            raise ValueError("speed_filter_gain must be in (0, 1]")
        if leak < 0.0:
            raise ValueError("flux_leak_per_s must be non-negative")
        if max_flux <= 0.0:
            raise ValueError("max_stator_flux_wb must be positive")
        if max_speed <= 0.0:
            raise ValueError("max_abs_speed_rad_s must be positive")


@dataclass(frozen=True)
class FluxObserverUpdate:
    state: AlphaBetaMotorState
    stator_flux_clipped: bool
    measured_current_abs: float


class CurrentVoltageFluxObserver:
    """Voltage-model stator flux observer with encoder-speed correction.

    Inputs are quantities available to a drive controller: reconstructed applied
    alpha-beta voltage, measured stator current before and after the PWM period,
    and processed mechanical speed from an encoder. No true motor flux is accepted.
    """

    def __init__(
        self,
        params: AlphaBetaMotorParams,
        config: CurrentVoltageFluxObserverConfig | None = None,
        state: AlphaBetaMotorState | None = None,
    ) -> None:
        self.params = params
        self.config = config if config is not None else CurrentVoltageFluxObserverConfig()
        self.state = state if state is not None else AlphaBetaMotorState()
        self._validate_params()

    def _validate_params(self) -> None:
        values = {
            "Rs": self.params.Rs,
            "Lls": self.params.Lls,
            "Llr": self.params.Llr,
            "Lm": self.params.Lm,
        }
        if not all(math.isfinite(float(value)) for value in values.values()):
            raise ValueError("observer motor parameters must be finite")
        if float(self.params.Rs) <= 0.0:
            raise ValueError("observer Rs must be positive")
        if float(self.params.Lls) < 0.0 or float(self.params.Llr) < 0.0:
            raise ValueError("observer leakage inductances must be non-negative")
        if float(self.params.Lm) <= 0.0:
            raise ValueError("observer Lm must be positive")

    def reset(self, *, omega_m: float = 0.0, theta_m: float = 0.0) -> AlphaBetaMotorState:
        omega = self._clamp_speed(_finite(omega_m, "omega_m"))
        self.state = AlphaBetaMotorState(
            omega_m=omega,
            theta_m=_finite(theta_m, "theta_m"),
            temp_s_c=float(self.params.temp_ref_c),
            temp_r_c=float(self.params.temp_ref_c),
        )
        return self.state

    def _clamp_speed(self, value: float) -> float:
        limit = float(self.config.max_abs_speed_rad_s)
        return max(-limit, min(limit, float(value)))

    def _rotor_flux_from_current(
        self,
        psi_s_alpha: float,
        psi_s_beta: float,
        i_s_alpha: float,
        i_s_beta: float,
    ) -> tuple[float, float]:
        lm = float(self.params.Lm)
        ls = float(self.params.Lls) + lm
        lr = float(self.params.Llr) + lm
        determinant = ls * lr - lm * lm
        return (
            (lr * psi_s_alpha - determinant * i_s_alpha) / lm,
            (lr * psi_s_beta - determinant * i_s_beta) / lm,
        )

    def step(
        self,
        *,
        v_alpha: float,
        v_beta: float,
        i_s_alpha_before: float,
        i_s_beta_before: float,
        i_s_alpha_after: float,
        i_s_beta_after: float,
        omega_m_measured: float,
        dt_s: float,
    ) -> FluxObserverUpdate:
        values = {
            "v_alpha": v_alpha,
            "v_beta": v_beta,
            "i_s_alpha_before": i_s_alpha_before,
            "i_s_beta_before": i_s_beta_before,
            "i_s_alpha_after": i_s_alpha_after,
            "i_s_beta_after": i_s_beta_after,
            "omega_m_measured": omega_m_measured,
            "dt_s": dt_s,
        }
        normalized = {name: _finite(value, name) for name, value in values.items()}
        dt = normalized["dt_s"]
        if dt <= 0.0:
            raise ValueError("dt_s must be positive")

        decay = max(0.0, 1.0 - float(self.config.flux_leak_per_s) * dt)
        psi_s_alpha = decay * self.state.psi_s_alpha + dt * (
            normalized["v_alpha"] - float(self.params.Rs) * normalized["i_s_alpha_before"]
        )
        psi_s_beta = decay * self.state.psi_s_beta + dt * (
            normalized["v_beta"] - float(self.params.Rs) * normalized["i_s_beta_before"]
        )
        flux_abs = math.hypot(psi_s_alpha, psi_s_beta)
        flux_clipped = flux_abs > float(self.config.max_stator_flux_wb)
        if flux_clipped:
            scale = float(self.config.max_stator_flux_wb) / max(flux_abs, 1.0e-15)
            psi_s_alpha *= scale
            psi_s_beta *= scale

        psi_r_alpha, psi_r_beta = self._rotor_flux_from_current(
            psi_s_alpha,
            psi_s_beta,
            normalized["i_s_alpha_after"],
            normalized["i_s_beta_after"],
        )
        measured_speed = self._clamp_speed(normalized["omega_m_measured"])
        gain = float(self.config.speed_filter_gain)
        omega_m = self._clamp_speed(self.state.omega_m + gain * (measured_speed - self.state.omega_m))
        theta_m = self.state.theta_m + 0.5 * dt * (self.state.omega_m + omega_m)
        self.state = replace(
            self.state,
            psi_s_alpha=psi_s_alpha,
            psi_s_beta=psi_s_beta,
            psi_r_alpha=psi_r_alpha,
            psi_r_beta=psi_r_beta,
            omega_m=omega_m,
            theta_m=theta_m,
        )
        return FluxObserverUpdate(
            state=self.state,
            stator_flux_clipped=flux_clipped,
            measured_current_abs=math.hypot(
                normalized["i_s_alpha_after"], normalized["i_s_beta_after"]
            ),
        )


__all__ = [
    "CurrentVoltageFluxObserver",
    "CurrentVoltageFluxObserverConfig",
    "FluxObserverUpdate",
]

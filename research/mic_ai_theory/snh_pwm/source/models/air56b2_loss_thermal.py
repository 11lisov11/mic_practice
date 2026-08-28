from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable


@dataclass(frozen=True)
class Air56B2LossModelParams:
    """Simulation-only loss model parameters with explicit provenance."""

    rs_ref_ohm: float
    rr_ref_ohm: float
    lm_h: float
    lls_h: float
    llr_h: float
    pole_pairs: int
    rated_frequency_hz: float
    rated_omega_rad_s: float
    rated_flux_wb: float
    rated_core_loss_w: float
    viscous_b_nms: float
    coulomb_friction_nm: float
    stator_temp_coeff_per_c: float
    rotor_temp_coeff_per_c: float
    reference_temp_c: float
    saturation_knee_flux_wb: float
    saturation_exponent: float
    minimum_lm_scale: float
    vdc_v: float
    pwm_frequency_hz: float
    switch_r_on_ohm: float
    switch_voltage_drop_v: float
    phase_voltage_limit_v: float
    phase_current_peak_limit_a: float
    switching_time_equivalent_s: float = 2.0e-8
    core_frequency_exponent: float = 1.5
    core_flux_exponent: float = 2.0
    source_kind: str = "F1_F2_F3_simulation_prior"
    hardware_identified: bool = False

    def __post_init__(self) -> None:
        if self.hardware_identified:
            raise ValueError("Simulation-prior loss model cannot claim hardware identification")
        positive = (
            "rs_ref_ohm",
            "rr_ref_ohm",
            "lm_h",
            "lls_h",
            "llr_h",
            "rated_frequency_hz",
            "rated_omega_rad_s",
            "rated_flux_wb",
            "rated_core_loss_w",
            "stator_temp_coeff_per_c",
            "rotor_temp_coeff_per_c",
            "saturation_knee_flux_wb",
            "saturation_exponent",
            "minimum_lm_scale",
            "vdc_v",
            "pwm_frequency_hz",
            "phase_voltage_limit_v",
            "phase_current_peak_limit_a",
        )
        for name in positive:
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.pole_pairs <= 0:
            raise ValueError("pole_pairs must be positive")
        if not 0.0 < self.minimum_lm_scale <= 1.0:
            raise ValueError("minimum_lm_scale must be within (0, 1]")


@dataclass(frozen=True)
class MotorThermalState:
    stator_temp_c: float = 25.0
    rotor_temp_c: float = 25.0


@dataclass(frozen=True)
class MotorThermalParams:
    """Lumped two-node thermal prior; constants require hardware fitting."""

    ambient_temp_c: float = 25.0
    stator_heat_capacity_j_per_k: float = 180.0
    rotor_heat_capacity_j_per_k: float = 95.0
    stator_to_ambient_k_per_w: float = 0.85
    rotor_to_ambient_k_per_w: float = 1.45
    stator_rotor_coupling_k_per_w: float = 0.65
    maximum_temperature_c: float = 180.0
    source_kind: str = "bounded_lumped_thermal_simulation_prior"
    hardware_identified: bool = False

    def __post_init__(self) -> None:
        if self.hardware_identified:
            raise ValueError("Thermal prior cannot claim hardware identification")
        for name in (
            "stator_heat_capacity_j_per_k",
            "rotor_heat_capacity_j_per_k",
            "stator_to_ambient_k_per_w",
            "rotor_to_ambient_k_per_w",
            "stator_rotor_coupling_k_per_w",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.maximum_temperature_c <= self.ambient_temp_c:
            raise ValueError("maximum temperature must exceed ambient")


@dataclass(frozen=True)
class LossBreakdown:
    id_a: float
    iq_a: float
    phase_current_peak_a: float
    flux_wb: float
    effective_lm_h: float
    slip_omega_rad_s: float
    electrical_frequency_hz: float
    phase_voltage_peak_v: float
    stator_copper_w: float
    rotor_copper_w: float
    core_w: float
    mechanical_w: float
    inverter_conduction_w: float
    inverter_switching_w: float
    motor_loss_w: float
    inverter_loss_w: float
    total_loss_w: float
    feasible: bool
    constraint_margin_current_a: float
    constraint_margin_voltage_v: float


@dataclass(frozen=True)
class IdOptimizationResult:
    optimum: LossBreakdown
    evaluated_points: int
    feasible_points: int
    id_lower_a: float
    id_upper_a: float


def _temperature_scaled_resistance(base: float, coeff: float, temperature: float, reference: float) -> float:
    return float(base) * (1.0 + float(coeff) * (float(temperature) - float(reference)))


def effective_magnetizing_inductance(params: Air56B2LossModelParams, id_a: float) -> tuple[float, float]:
    """Solve the static saturation relation by deterministic fixed-point iteration."""

    lm = float(params.lm_h)
    id_abs = abs(float(id_a))
    for _ in range(32):
        flux = lm * id_abs
        raw_scale = 1.0 / (
            1.0
            + (flux / max(params.saturation_knee_flux_wb, 1e-12))
            ** max(params.saturation_exponent, 1.0)
        )
        target = params.lm_h * max(params.minimum_lm_scale, min(1.0, raw_scale))
        updated = 0.5 * lm + 0.5 * target
        if abs(updated - lm) <= 1e-12:
            lm = updated
            break
        lm = updated
    return float(lm), float(lm * id_abs)


def evaluate_operating_point(
    params: Air56B2LossModelParams,
    *,
    speed_rad_s: float,
    torque_nm: float,
    id_a: float,
    thermal_state: MotorThermalState | None = None,
) -> LossBreakdown:
    speed = abs(float(speed_rad_s))
    torque = max(0.0, float(torque_nm))
    id_value = max(float(id_a), 1e-6)
    thermal = thermal_state or MotorThermalState(params.reference_temp_c, params.reference_temp_c)

    rs = _temperature_scaled_resistance(
        params.rs_ref_ohm,
        params.stator_temp_coeff_per_c,
        thermal.stator_temp_c,
        params.reference_temp_c,
    )
    rr = _temperature_scaled_resistance(
        params.rr_ref_ohm,
        params.rotor_temp_coeff_per_c,
        thermal.rotor_temp_c,
        params.reference_temp_c,
    )
    lm_eff, flux = effective_magnetizing_inductance(params, id_value)
    lr = lm_eff + params.llr_h
    torque_per_iq = 1.5 * params.pole_pairs * (lm_eff / lr) * flux
    iq = 0.0 if torque <= 0.0 else torque / max(torque_per_iq, 1e-12)
    current_peak = math.hypot(id_value, iq)
    rotor_iq = (lm_eff / lr) * iq
    slip_omega = 0.0 if torque <= 0.0 else (rr / lr) * iq / max(id_value, 1e-9)
    electrical_omega = params.pole_pairs * speed + abs(slip_omega)
    electrical_frequency = electrical_omega / (2.0 * math.pi)

    vd = rs * id_value - electrical_omega * params.lls_h * iq
    vq = rs * iq + electrical_omega * (flux + params.lls_h * id_value)
    voltage_peak = math.hypot(vd, vq)

    stator_copper = 1.5 * rs * current_peak**2
    rotor_copper = 1.5 * rr * rotor_iq**2
    core_frequency_ratio = max(electrical_frequency / params.rated_frequency_hz, 0.0)
    core_flux_ratio = max(flux / params.rated_flux_wb, 0.0)
    core = params.rated_core_loss_w * core_frequency_ratio ** params.core_frequency_exponent
    core *= core_flux_ratio ** params.core_flux_exponent
    mechanical = params.viscous_b_nms * speed**2 + params.coulomb_friction_nm * speed

    phase_rms = current_peak / math.sqrt(2.0)
    phase_average_abs = 2.0 * current_peak / math.pi
    conduction = 3.0 * (
        params.switch_r_on_ohm * phase_rms**2
        + params.switch_voltage_drop_v * phase_average_abs
    )
    switching = (
        6.0
        * params.switching_time_equivalent_s
        * params.vdc_v
        * current_peak
        * params.pwm_frequency_hz
    )
    motor_loss = stator_copper + rotor_copper + core + mechanical
    inverter_loss = conduction + switching
    current_margin = params.phase_current_peak_limit_a - current_peak
    voltage_margin = params.phase_voltage_limit_v - voltage_peak
    feasible = current_margin >= 0.0 and voltage_margin >= 0.0 and all(
        math.isfinite(value)
        for value in (motor_loss, inverter_loss, current_peak, voltage_peak)
    )
    return LossBreakdown(
        id_a=id_value,
        iq_a=iq,
        phase_current_peak_a=current_peak,
        flux_wb=flux,
        effective_lm_h=lm_eff,
        slip_omega_rad_s=slip_omega,
        electrical_frequency_hz=electrical_frequency,
        phase_voltage_peak_v=voltage_peak,
        stator_copper_w=stator_copper,
        rotor_copper_w=rotor_copper,
        core_w=core,
        mechanical_w=mechanical,
        inverter_conduction_w=conduction,
        inverter_switching_w=switching,
        motor_loss_w=motor_loss,
        inverter_loss_w=inverter_loss,
        total_loss_w=motor_loss + inverter_loss,
        feasible=feasible,
        constraint_margin_current_a=current_margin,
        constraint_margin_voltage_v=voltage_margin,
    )


def optimize_id_reference(
    params: Air56B2LossModelParams,
    *,
    speed_rad_s: float,
    torque_nm: float,
    id_lower_a: float,
    id_upper_a: float,
    thermal_state: MotorThermalState | None = None,
    grid_points: int = 1001,
    candidate_id_values: Iterable[float] = (),
) -> IdOptimizationResult:
    if not math.isfinite(id_lower_a) or not math.isfinite(id_upper_a):
        raise ValueError("id bounds must be finite")
    if id_lower_a <= 0.0 or id_upper_a <= id_lower_a:
        raise ValueError("id bounds must satisfy 0 < lower < upper")
    if grid_points < 3:
        raise ValueError("grid_points must be at least three")

    candidates: list[LossBreakdown] = []
    for index in range(int(grid_points)):
        fraction = index / (grid_points - 1)
        id_value = id_lower_a + fraction * (id_upper_a - id_lower_a)
        candidates.append(
            evaluate_operating_point(
                params,
                speed_rad_s=speed_rad_s,
                torque_nm=torque_nm,
                id_a=id_value,
                thermal_state=thermal_state,
            )
        )
    for raw_value in candidate_id_values:
        value = float(raw_value)
        if not math.isfinite(value) or value < id_lower_a or value > id_upper_a:
            continue
        candidates.append(
            evaluate_operating_point(
                params,
                speed_rad_s=speed_rad_s,
                torque_nm=torque_nm,
                id_a=value,
                thermal_state=thermal_state,
            )
        )
    feasible = [item for item in candidates if item.feasible]
    if not feasible:
        raise ValueError("No feasible id reference satisfies current and voltage constraints")
    optimum = min(feasible, key=lambda item: (item.total_loss_w, item.phase_current_peak_a, item.id_a))
    return IdOptimizationResult(
        optimum=optimum,
        evaluated_points=len(candidates),
        feasible_points=len(feasible),
        id_lower_a=float(id_lower_a),
        id_upper_a=float(id_upper_a),
    )


def step_thermal_state(
    state: MotorThermalState,
    losses: LossBreakdown,
    params: MotorThermalParams,
    dt_s: float,
) -> MotorThermalState:
    dt = float(dt_s)
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError("dt_s must be finite and positive")
    stator_heat = losses.stator_copper_w + 0.70 * losses.core_w
    rotor_heat = losses.rotor_copper_w + 0.30 * losses.core_w
    coupling_w = (state.rotor_temp_c - state.stator_temp_c) / params.stator_rotor_coupling_k_per_w
    stator_to_ambient = (state.stator_temp_c - params.ambient_temp_c) / params.stator_to_ambient_k_per_w
    rotor_to_ambient = (state.rotor_temp_c - params.ambient_temp_c) / params.rotor_to_ambient_k_per_w
    stator_rate = (stator_heat + coupling_w - stator_to_ambient) / params.stator_heat_capacity_j_per_k
    rotor_rate = (rotor_heat - coupling_w - rotor_to_ambient) / params.rotor_heat_capacity_j_per_k
    return MotorThermalState(
        stator_temp_c=min(params.maximum_temperature_c, state.stator_temp_c + dt * stator_rate),
        rotor_temp_c=min(params.maximum_temperature_c, state.rotor_temp_c + dt * rotor_rate),
    )


def simulate_constant_thermal_load(
    initial_state: MotorThermalState,
    losses: LossBreakdown,
    params: MotorThermalParams,
    *,
    duration_s: float,
    dt_s: float = 0.1,
) -> MotorThermalState:
    if duration_s < 0.0:
        raise ValueError("duration_s must be non-negative")
    state = initial_state
    full_steps = int(duration_s // dt_s)
    for _ in range(full_steps):
        state = step_thermal_state(state, losses, params, dt_s)
    remainder = duration_s - full_steps * dt_s
    if remainder > 1e-12:
        state = step_thermal_state(state, losses, params, remainder)
    return state


def losses_to_dict(losses: LossBreakdown) -> dict[str, float | bool]:
    return asdict(losses)


def loss_params_from_fidelity_bundle(
    bundle: dict[str, Any],
    sample_index: int,
) -> tuple[Air56B2LossModelParams, float]:
    """Build one loss prior and its fixed rated-flux id reference."""

    fidelity = bundle.get("fidelity", bundle)
    f2_samples = fidelity.get("f2_samples", [])
    f3_samples = fidelity.get("f3_samples", [])
    if not 0 <= int(sample_index) < min(len(f2_samples), len(f3_samples)):
        raise IndexError(f"AIR56B2 fidelity sample out of range: {sample_index}")
    f2 = f2_samples[int(sample_index)]
    f3 = f3_samples[int(sample_index)]
    motor = f2["transformed_motor"]
    inverter = f3["inverter"]
    derived = fidelity["derived_nameplate"]
    nameplate = fidelity["nameplate"]
    rs_ref = float(motor["Rs"]) / float(f2["stator_resistance_scale"])
    rr_ref = float(motor["Rr"]) / float(f2["rotor_resistance_scale"])
    rated_flux = float(f2["saturation_knee_flux_wb"]) / float(
        f2["saturation_knee_flux_scale"]
    )
    params = Air56B2LossModelParams(
        rs_ref_ohm=rs_ref,
        rr_ref_ohm=rr_ref,
        lm_h=float(motor["Lm"]),
        lls_h=float(motor["Ls_sigma"]),
        llr_h=float(motor["Lr_sigma"]),
        pole_pairs=int(motor["p"]),
        rated_frequency_hz=float(nameplate["frequency_hz"]),
        rated_omega_rad_s=float(derived["rated_omega_rad_s"]),
        rated_flux_wb=rated_flux,
        rated_core_loss_w=float(f2["effective_core_loss_w"]),
        viscous_b_nms=float(f2["effective_viscous_coefficient_nms"]),
        coulomb_friction_nm=float(f2["effective_coulomb_friction_torque_nm"]),
        stator_temp_coeff_per_c=float(f2["stator_copper_alpha_per_c"]),
        rotor_temp_coeff_per_c=float(f2["rotor_copper_alpha_per_c"]),
        reference_temp_c=20.0,
        saturation_knee_flux_wb=float(f2["saturation_knee_flux_wb"]),
        saturation_exponent=float(f2["saturation_exponent"]),
        minimum_lm_scale=float(f2["minimum_magnetizing_inductance_scale"]),
        vdc_v=float(inverter["nominal_vdc_v"]),
        pwm_frequency_hz=float(inverter["pwm_frequency_hz"]),
        switch_r_on_ohm=float(inverter["switch_r_on_ohm"]),
        switch_voltage_drop_v=float(inverter["switch_voltage_drop_v"]),
        phase_voltage_limit_v=0.95 * float(inverter["nominal_vdc_v"]) / math.sqrt(3.0),
        phase_current_peak_limit_a=2.5 * float(nameplate["line_current_a"]),
    )
    fixed_id = rated_flux / max(float(motor["Lm"]), 1e-12)
    return params, fixed_id


__all__ = [
    "Air56B2LossModelParams",
    "IdOptimizationResult",
    "LossBreakdown",
    "MotorThermalParams",
    "MotorThermalState",
    "effective_magnetizing_inductance",
    "evaluate_operating_point",
    "losses_to_dict",
    "loss_params_from_fidelity_bundle",
    "optimize_id_reference",
    "simulate_constant_thermal_load",
    "step_thermal_state",
]

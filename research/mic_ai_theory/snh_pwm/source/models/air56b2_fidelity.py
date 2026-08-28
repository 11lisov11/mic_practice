from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from random import Random
from typing import Any, Sequence

from config.env import MotorParams
from models.air56b2_nameplate_ensemble import (
    Air56B2EnsembleSample,
    Air56B2Nameplate,
    derive_nameplate,
)


@dataclass(frozen=True)
class FloatBounds:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.lower)) or not math.isfinite(float(self.upper)):
            raise ValueError("float bounds must be finite")
        if float(self.lower) > float(self.upper):
            raise ValueError("float bounds must satisfy lower <= upper")

    def sample(self, rng: Random) -> float:
        return rng.uniform(float(self.lower), float(self.upper))

    def contains(self, value: float) -> bool:
        return float(self.lower) <= float(value) <= float(self.upper)


@dataclass(frozen=True)
class IntBounds:
    lower: int
    upper: int

    def __post_init__(self) -> None:
        if isinstance(self.lower, bool) or isinstance(self.upper, bool):
            raise ValueError("integer bounds must not be boolean")
        if not isinstance(self.lower, int) or not isinstance(self.upper, int):
            raise ValueError("integer bounds must contain integers")
        if self.lower > self.upper:
            raise ValueError("integer bounds must satisfy lower <= upper")

    def sample(self, rng: Random) -> int:
        return rng.randint(self.lower, self.upper)

    def contains(self, value: int) -> bool:
        return self.lower <= int(value) <= self.upper


def _require_positive_bounds(name: str, bounds: FloatBounds, *, allow_zero: bool = False) -> None:
    minimum = 0.0 if allow_zero else math.nextafter(0.0, 1.0)
    if bounds.lower < minimum:
        relation = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} bounds must be {relation}")


def _require_fraction_bounds(name: str, bounds: FloatBounds) -> None:
    if bounds.lower < 0.0 or bounds.upper > 1.0:
        raise ValueError(f"{name} bounds must be within [0, 1]")


def _require_finite_positive(name: str, value: float, *, allow_zero: bool = False) -> None:
    value = float(value)
    if not math.isfinite(value) or value < 0.0 or (not allow_zero and value == 0.0):
        relation = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be finite and {relation}")


@dataclass(frozen=True)
class F2Priors:
    """Bounded simulation priors absent from the AIR56B2 nameplate."""

    reference_temperature_c: float = 20.0
    stator_temperature_c: FloatBounds = FloatBounds(20.0, 140.0)
    rotor_temperature_c: FloatBounds = FloatBounds(20.0, 160.0)
    stator_copper_alpha_per_c: FloatBounds = FloatBounds(0.0037, 0.0041)
    rotor_copper_alpha_per_c: FloatBounds = FloatBounds(0.0037, 0.0041)
    saturation_knee_flux_scale: FloatBounds = FloatBounds(0.75, 1.25)
    saturation_exponent: FloatBounds = FloatBounds(1.5, 4.0)
    minimum_magnetizing_inductance_scale: FloatBounds = FloatBounds(0.35, 0.75)
    core_loss_scale: FloatBounds = FloatBounds(0.80, 1.25)
    rotational_loss_scale: FloatBounds = FloatBounds(0.70, 1.40)
    viscous_loss_fraction: FloatBounds = FloatBounds(0.30, 0.85)

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.reference_temperature_c)):
            raise ValueError("reference_temperature_c must be finite")
        if self.stator_temperature_c.lower < self.reference_temperature_c:
            raise ValueError("stator temperature bounds must not be below the reference")
        if self.rotor_temperature_c.lower < self.reference_temperature_c:
            raise ValueError("rotor temperature bounds must not be below the reference")
        _require_positive_bounds("stator_copper_alpha_per_c", self.stator_copper_alpha_per_c)
        _require_positive_bounds("rotor_copper_alpha_per_c", self.rotor_copper_alpha_per_c)
        _require_positive_bounds("saturation_knee_flux_scale", self.saturation_knee_flux_scale)
        _require_positive_bounds("saturation_exponent", self.saturation_exponent)
        if self.saturation_exponent.lower < 1.0:
            raise ValueError("saturation_exponent lower bound must be at least one")
        _require_fraction_bounds(
            "minimum_magnetizing_inductance_scale",
            self.minimum_magnetizing_inductance_scale,
        )
        if self.minimum_magnetizing_inductance_scale.lower <= 0.0:
            raise ValueError("minimum magnetizing inductance scale must be positive")
        _require_positive_bounds("core_loss_scale", self.core_loss_scale)
        _require_positive_bounds("rotational_loss_scale", self.rotational_loss_scale)
        _require_fraction_bounds("viscous_loss_fraction", self.viscous_loss_fraction)


@dataclass(frozen=True)
class F2Sample:
    index: int
    seed: int
    f1_index: int
    f1_seed: int
    stator_temperature_c: float
    rotor_temperature_c: float
    stator_copper_alpha_per_c: float
    rotor_copper_alpha_per_c: float
    stator_resistance_scale: float
    rotor_resistance_scale: float
    saturation_knee_flux_scale: float
    saturation_knee_flux_wb: float
    saturation_exponent: float
    minimum_magnetizing_inductance_scale: float
    core_loss_scale: float
    effective_core_loss_w: float
    rotational_loss_scale: float
    effective_rotational_loss_w: float
    viscous_loss_fraction: float
    effective_viscous_coefficient_nms: float
    effective_coulomb_friction_torque_nm: float
    transformed_motor: MotorParams
    source_kind: str = "bounded_simulation_prior"
    parameters_measured: bool = False
    hardware_identified: bool = False

    def __post_init__(self) -> None:
        if self.index < 0 or self.f1_index < 0 or self.seed < 0 or self.f1_seed < 0:
            raise ValueError("sample indexes and seeds must be non-negative")
        if self.parameters_measured or self.hardware_identified:
            raise ValueError("F2 samples cannot claim measurement or hardware identification")
        for name in (
            "stator_resistance_scale",
            "rotor_resistance_scale",
            "saturation_knee_flux_scale",
            "saturation_knee_flux_wb",
            "saturation_exponent",
            "minimum_magnetizing_inductance_scale",
            "core_loss_scale",
            "effective_core_loss_w",
            "rotational_loss_scale",
            "effective_rotational_loss_w",
            "viscous_loss_fraction",
            "effective_viscous_coefficient_nms",
        ):
            _require_finite_positive(name, getattr(self, name))
        _require_finite_positive(
            "effective_coulomb_friction_torque_nm",
            self.effective_coulomb_friction_torque_nm,
            allow_zero=True,
        )
        if not (0.0 < self.viscous_loss_fraction <= 1.0):
            raise ValueError("viscous_loss_fraction must be within (0, 1]")
        if not (0.0 < self.minimum_magnetizing_inductance_scale <= 1.0):
            raise ValueError("minimum magnetizing inductance scale must be within (0, 1]")
        for name in ("Rs", "Rr", "Ls_sigma", "Lr_sigma", "Lm", "J", "B"):
            _require_finite_positive(f"transformed_motor.{name}", getattr(self.transformed_motor, name))
        if self.transformed_motor.psi_sat <= 0.0:
            raise ValueError("F2 transformed motor must enable bounded saturation")


@dataclass(frozen=True)
class F3Priors:
    """Bounded nonideal inverter and sensor-chain simulation priors."""

    nominal_vdc_v: float = 310.0
    pwm_frequency_hz: float = 10_000.0
    vdc_ripple_fraction_peak: FloatBounds = FloatBounds(0.00, 0.08)
    vdc_ripple_frequency_hz: FloatBounds = FloatBounds(90.0, 110.0)
    dead_time_s: FloatBounds = FloatBounds(0.2e-6, 2.0e-6)
    switch_r_on_ohm: FloatBounds = FloatBounds(0.02, 0.50)
    switch_voltage_drop_v: FloatBounds = FloatBounds(0.20, 2.00)
    adc_bits: IntBounds = IntBounds(10, 14)
    adc_current_full_scale_a: FloatBounds = FloatBounds(10.0, 16.0)
    adc_voltage_full_scale_v: FloatBounds = FloatBounds(360.0, 500.0)
    adc_current_offset_fraction_fs: FloatBounds = FloatBounds(-0.01, 0.01)
    adc_voltage_offset_fraction_fs: FloatBounds = FloatBounds(-0.005, 0.005)
    adc_current_gain_scale: FloatBounds = FloatBounds(0.98, 1.02)
    adc_voltage_gain_scale: FloatBounds = FloatBounds(0.98, 1.02)
    adc_sample_delay_pwm_periods: FloatBounds = FloatBounds(0.0, 2.0)
    as5600_bits: IntBounds = IntBounds(12, 12)
    as5600_delay_s: FloatBounds = FloatBounds(0.0, 0.002)

    def __post_init__(self) -> None:
        _require_finite_positive("nominal_vdc_v", self.nominal_vdc_v)
        _require_finite_positive("pwm_frequency_hz", self.pwm_frequency_hz)
        _require_fraction_bounds("vdc_ripple_fraction_peak", self.vdc_ripple_fraction_peak)
        if self.vdc_ripple_fraction_peak.upper >= 1.0:
            raise ValueError("Vdc ripple must remain below nominal Vdc")
        _require_positive_bounds("vdc_ripple_frequency_hz", self.vdc_ripple_frequency_hz)
        _require_positive_bounds("dead_time_s", self.dead_time_s, allow_zero=True)
        if self.dead_time_s.upper >= 0.5 / self.pwm_frequency_hz:
            raise ValueError("dead time must remain below half a PWM period")
        _require_positive_bounds("switch_r_on_ohm", self.switch_r_on_ohm, allow_zero=True)
        _require_positive_bounds(
            "switch_voltage_drop_v", self.switch_voltage_drop_v, allow_zero=True
        )
        if self.adc_bits.lower < 2 or self.adc_bits.upper > 24:
            raise ValueError("ADC resolution must be within [2, 24] bits")
        _require_positive_bounds("adc_current_full_scale_a", self.adc_current_full_scale_a)
        nameplate = Air56B2Nameplate()
        nameplate_start_peak_a = (
            math.sqrt(2.0) * nameplate.line_current_a * nameplate.start_current_ratio
        )
        if self.adc_current_full_scale_a.lower < nameplate_start_peak_a:
            raise ValueError(
                "ADC current full scale must cover the AIR56B2 nameplate start-current peak"
            )
        _require_positive_bounds("adc_voltage_full_scale_v", self.adc_voltage_full_scale_v)
        maximum_vdc = self.nominal_vdc_v * (
            1.0 + self.vdc_ripple_fraction_peak.upper
        )
        if self.adc_voltage_full_scale_v.lower < maximum_vdc:
            raise ValueError(
                "ADC voltage full scale must cover nominal Vdc plus the F3 ripple envelope"
            )
        for name, bounds in (
            ("adc_current_offset_fraction_fs", self.adc_current_offset_fraction_fs),
            ("adc_voltage_offset_fraction_fs", self.adc_voltage_offset_fraction_fs),
        ):
            if bounds.lower < -0.25 or bounds.upper > 0.25:
                raise ValueError(f"{name} must remain within +/-25% full scale")
        _require_positive_bounds("adc_current_gain_scale", self.adc_current_gain_scale)
        _require_positive_bounds("adc_voltage_gain_scale", self.adc_voltage_gain_scale)
        _require_positive_bounds(
            "adc_sample_delay_pwm_periods",
            self.adc_sample_delay_pwm_periods,
            allow_zero=True,
        )
        if self.as5600_bits.lower < 1 or self.as5600_bits.upper > 24:
            raise ValueError("AS5600 resolution must be within [1, 24] bits")
        _require_positive_bounds("as5600_delay_s", self.as5600_delay_s, allow_zero=True)


@dataclass(frozen=True)
class InverterNonidealities:
    nominal_vdc_v: float
    ripple_peak_v: float
    ripple_fraction_peak: float
    ripple_frequency_hz: float
    ripple_phase_rad: float
    pwm_frequency_hz: float
    dead_time_s: float
    switch_r_on_ohm: float
    switch_voltage_drop_v: float

    def __post_init__(self) -> None:
        _require_finite_positive("nominal_vdc_v", self.nominal_vdc_v)
        _require_finite_positive("ripple_peak_v", self.ripple_peak_v, allow_zero=True)
        if not (0.0 <= self.ripple_fraction_peak < 1.0):
            raise ValueError("ripple_fraction_peak must be within [0, 1)")
        _require_finite_positive("ripple_frequency_hz", self.ripple_frequency_hz)
        _require_finite_positive("pwm_frequency_hz", self.pwm_frequency_hz)
        _require_finite_positive("dead_time_s", self.dead_time_s, allow_zero=True)
        if self.dead_time_s >= 0.5 / self.pwm_frequency_hz:
            raise ValueError("dead time must remain below half a PWM period")
        _require_finite_positive("switch_r_on_ohm", self.switch_r_on_ohm, allow_zero=True)
        _require_finite_positive(
            "switch_voltage_drop_v", self.switch_voltage_drop_v, allow_zero=True
        )
        if not (0.0 <= self.ripple_phase_rad < 2.0 * math.pi):
            raise ValueError("ripple phase must be within [0, 2*pi)")
        if not math.isclose(
            self.ripple_peak_v,
            self.nominal_vdc_v * self.ripple_fraction_peak,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("ripple peak must match nominal Vdc and ripple fraction")

    def vdc_at(self, time_s: float) -> float:
        if not math.isfinite(float(time_s)):
            raise ValueError("time_s must be finite")
        return self.nominal_vdc_v + self.ripple_peak_v * math.sin(
            2.0 * math.pi * self.ripple_frequency_hz * float(time_s)
            + self.ripple_phase_rad
        )

    def conduction_drop_v(self, phase_current_a: float) -> float:
        if not math.isfinite(float(phase_current_a)):
            raise ValueError("phase_current_a must be finite")
        return math.copysign(
            self.switch_voltage_drop_v + self.switch_r_on_ohm * abs(float(phase_current_a)),
            float(phase_current_a),
        ) if phase_current_a != 0.0 else 0.0


@dataclass(frozen=True)
class AdcNonidealities:
    bits: int
    current_full_scale_a: float
    voltage_full_scale_v: float
    current_lsb_a: float
    voltage_lsb_v: float
    current_offset_a: float
    voltage_offset_v: float
    current_gain_scale: float
    voltage_gain_scale: float
    sample_delay_s: float

    def __post_init__(self) -> None:
        if self.bits < 2 or self.bits > 24:
            raise ValueError("ADC bits must be within [2, 24]")
        for name in (
            "current_full_scale_a",
            "voltage_full_scale_v",
            "current_lsb_a",
            "voltage_lsb_v",
            "current_gain_scale",
            "voltage_gain_scale",
        ):
            _require_finite_positive(name, getattr(self, name))
        _require_finite_positive("sample_delay_s", self.sample_delay_s, allow_zero=True)
        if not math.isfinite(self.current_offset_a) or not math.isfinite(self.voltage_offset_v):
            raise ValueError("ADC offsets must be finite")
        levels = (1 << self.bits) - 1
        if not math.isclose(
            self.current_lsb_a,
            2.0 * self.current_full_scale_a / levels,
            rel_tol=1e-12,
        ):
            raise ValueError("current ADC LSB is inconsistent with resolution and range")
        if not math.isclose(
            self.voltage_lsb_v,
            self.voltage_full_scale_v / levels,
            rel_tol=1e-12,
        ):
            raise ValueError("voltage ADC LSB is inconsistent with resolution and range")

    def quantize_current(self, current_a: float) -> float:
        measured = float(current_a) * self.current_gain_scale + self.current_offset_a
        clipped = min(self.current_full_scale_a, max(-self.current_full_scale_a, measured))
        quantized = round(clipped / self.current_lsb_a) * self.current_lsb_a
        return min(self.current_full_scale_a, max(-self.current_full_scale_a, quantized))

    def quantize_voltage(self, voltage_v: float) -> float:
        measured = float(voltage_v) * self.voltage_gain_scale + self.voltage_offset_v
        clipped = min(self.voltage_full_scale_v, max(0.0, measured))
        quantized = round(clipped / self.voltage_lsb_v) * self.voltage_lsb_v
        return min(self.voltage_full_scale_v, max(0.0, quantized))


@dataclass(frozen=True)
class As5600Nonidealities:
    bits: int
    angle_lsb_rad: float
    sample_delay_s: float

    def __post_init__(self) -> None:
        if self.bits < 1 or self.bits > 24:
            raise ValueError("AS5600 bits must be within [1, 24]")
        _require_finite_positive("angle_lsb_rad", self.angle_lsb_rad)
        _require_finite_positive("sample_delay_s", self.sample_delay_s, allow_zero=True)
        if not math.isclose(
            self.angle_lsb_rad,
            2.0 * math.pi / (1 << self.bits),
            rel_tol=1e-12,
        ):
            raise ValueError("AS5600 angle LSB is inconsistent with resolution")

    def quantize_angle(self, angle_rad: float) -> float:
        wrapped = float(angle_rad) % (2.0 * math.pi)
        return (round(wrapped / self.angle_lsb_rad) * self.angle_lsb_rad) % (
            2.0 * math.pi
        )


@dataclass(frozen=True)
class F3Sample:
    index: int
    seed: int
    f1_index: int
    f1_seed: int
    inverter: InverterNonidealities
    adc: AdcNonidealities
    as5600: As5600Nonidealities
    source_kind: str = "bounded_simulation_prior"
    parameters_measured: bool = False
    hardware_identified: bool = False

    def __post_init__(self) -> None:
        if self.index < 0 or self.f1_index < 0 or self.seed < 0 or self.f1_seed < 0:
            raise ValueError("sample indexes and seeds must be non-negative")
        if self.parameters_measured or self.hardware_identified:
            raise ValueError("F3 samples cannot claim measurement or hardware identification")


def _validate_f1_sample(sample: Air56B2EnsembleSample) -> None:
    nameplate = Air56B2Nameplate()
    if sample.index < 0 or sample.seed < 0:
        raise ValueError("F1 sample index and seed must be non-negative")
    if sample.hardware_identified:
        raise ValueError("F1 hardware-identified samples are outside this simulation transform")
    if sample.motor.p != nameplate.pole_pairs:
        raise ValueError("F1 pole-pair count does not match the AIR56B2 nameplate")
    if not math.isclose(sample.motor.I_n, nameplate.line_current_a, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("F1 rated current does not match the AIR56B2 nameplate")


def generate_f2_samples(
    f1_samples: Sequence[Air56B2EnsembleSample],
    *,
    seed: int,
    priors: F2Priors = F2Priors(),
) -> list[F2Sample]:
    """Apply seeded F2 operating-condition priors without mutating F1 samples."""

    if seed < 0:
        raise ValueError("seed must be non-negative")
    if not f1_samples:
        raise ValueError("f1_samples must be non-empty")
    nameplate = Air56B2Nameplate()
    derived = derive_nameplate(nameplate)
    rated_flux_wb = derived.model_phase_voltage_v / (
        2.0 * math.pi * nameplate.frequency_hz
    )
    master_rng = Random(seed)
    result: list[F2Sample] = []
    for index, f1 in enumerate(f1_samples):
        _validate_f1_sample(f1)
        sample_seed = master_rng.randrange(0, 2**63)
        rng = Random(sample_seed)
        stator_temperature = priors.stator_temperature_c.sample(rng)
        rotor_temperature = priors.rotor_temperature_c.sample(rng)
        stator_alpha = priors.stator_copper_alpha_per_c.sample(rng)
        rotor_alpha = priors.rotor_copper_alpha_per_c.sample(rng)
        stator_scale = 1.0 + stator_alpha * (
            stator_temperature - priors.reference_temperature_c
        )
        rotor_scale = 1.0 + rotor_alpha * (
            rotor_temperature - priors.reference_temperature_c
        )
        saturation_scale = priors.saturation_knee_flux_scale.sample(rng)
        saturation_exponent = priors.saturation_exponent.sample(rng)
        lm_min_scale = priors.minimum_magnetizing_inductance_scale.sample(rng)
        core_loss_scale = priors.core_loss_scale.sample(rng)
        rotational_loss_scale = priors.rotational_loss_scale.sample(rng)
        viscous_fraction = priors.viscous_loss_fraction.sample(rng)
        effective_rotational_loss = f1.rotational_loss_w * rotational_loss_scale
        effective_viscous_loss = effective_rotational_loss * viscous_fraction
        effective_coulomb_loss = effective_rotational_loss - effective_viscous_loss
        effective_b = effective_viscous_loss / derived.rated_omega_rad_s**2
        transformed_motor = replace(
            f1.motor,
            Rs=f1.motor.Rs * stator_scale,
            Rr=f1.motor.Rr * rotor_scale,
            B=effective_b,
            psi_sat=rated_flux_wb * saturation_scale,
            sat_exp=saturation_exponent,
            lm_min_scale=lm_min_scale,
        )
        result.append(
            F2Sample(
                index=index,
                seed=sample_seed,
                f1_index=f1.index,
                f1_seed=f1.seed,
                stator_temperature_c=stator_temperature,
                rotor_temperature_c=rotor_temperature,
                stator_copper_alpha_per_c=stator_alpha,
                rotor_copper_alpha_per_c=rotor_alpha,
                stator_resistance_scale=stator_scale,
                rotor_resistance_scale=rotor_scale,
                saturation_knee_flux_scale=saturation_scale,
                saturation_knee_flux_wb=rated_flux_wb * saturation_scale,
                saturation_exponent=saturation_exponent,
                minimum_magnetizing_inductance_scale=lm_min_scale,
                core_loss_scale=core_loss_scale,
                effective_core_loss_w=f1.core_loss_w * core_loss_scale,
                rotational_loss_scale=rotational_loss_scale,
                effective_rotational_loss_w=effective_rotational_loss,
                viscous_loss_fraction=viscous_fraction,
                effective_viscous_coefficient_nms=effective_b,
                effective_coulomb_friction_torque_nm=(
                    effective_coulomb_loss / derived.rated_omega_rad_s
                ),
                transformed_motor=transformed_motor,
            )
        )
    return result


def generate_f3_samples(
    f1_samples: Sequence[Air56B2EnsembleSample],
    *,
    seed: int,
    priors: F3Priors = F3Priors(),
) -> list[F3Sample]:
    """Attach seeded F3 inverter/measurement-chain priors to F1 samples."""

    if seed < 0:
        raise ValueError("seed must be non-negative")
    if not f1_samples:
        raise ValueError("f1_samples must be non-empty")
    master_rng = Random(seed)
    result: list[F3Sample] = []
    for index, f1 in enumerate(f1_samples):
        _validate_f1_sample(f1)
        sample_seed = master_rng.randrange(0, 2**63)
        rng = Random(sample_seed)
        ripple_fraction = priors.vdc_ripple_fraction_peak.sample(rng)
        adc_bits = priors.adc_bits.sample(rng)
        current_full_scale = priors.adc_current_full_scale_a.sample(rng)
        voltage_full_scale = priors.adc_voltage_full_scale_v.sample(rng)
        adc_levels = (1 << adc_bits) - 1
        as5600_bits = priors.as5600_bits.sample(rng)
        result.append(
            F3Sample(
                index=index,
                seed=sample_seed,
                f1_index=f1.index,
                f1_seed=f1.seed,
                inverter=InverterNonidealities(
                    nominal_vdc_v=priors.nominal_vdc_v,
                    ripple_peak_v=priors.nominal_vdc_v * ripple_fraction,
                    ripple_fraction_peak=ripple_fraction,
                    ripple_frequency_hz=priors.vdc_ripple_frequency_hz.sample(rng),
                    ripple_phase_rad=rng.uniform(0.0, 2.0 * math.pi),
                    pwm_frequency_hz=priors.pwm_frequency_hz,
                    dead_time_s=priors.dead_time_s.sample(rng),
                    switch_r_on_ohm=priors.switch_r_on_ohm.sample(rng),
                    switch_voltage_drop_v=priors.switch_voltage_drop_v.sample(rng),
                ),
                adc=AdcNonidealities(
                    bits=adc_bits,
                    current_full_scale_a=current_full_scale,
                    voltage_full_scale_v=voltage_full_scale,
                    current_lsb_a=2.0 * current_full_scale / adc_levels,
                    voltage_lsb_v=voltage_full_scale / adc_levels,
                    current_offset_a=(
                        priors.adc_current_offset_fraction_fs.sample(rng)
                        * current_full_scale
                    ),
                    voltage_offset_v=(
                        priors.adc_voltage_offset_fraction_fs.sample(rng)
                        * voltage_full_scale
                    ),
                    current_gain_scale=priors.adc_current_gain_scale.sample(rng),
                    voltage_gain_scale=priors.adc_voltage_gain_scale.sample(rng),
                    sample_delay_s=(
                        priors.adc_sample_delay_pwm_periods.sample(rng)
                        / priors.pwm_frequency_hz
                    ),
                ),
                as5600=As5600Nonidealities(
                    bits=as5600_bits,
                    angle_lsb_rad=2.0 * math.pi / (1 << as5600_bits),
                    sample_delay_s=priors.as5600_delay_s.sample(rng),
                ),
            )
        )
    return result


def fidelity_manifest(
    f1_samples: Sequence[Air56B2EnsembleSample],
    f2_samples: Sequence[F2Sample],
    f3_samples: Sequence[F3Sample],
    *,
    f2_seed: int,
    f3_seed: int,
    f2_priors: F2Priors = F2Priors(),
    f3_priors: F3Priors = F3Priors(),
) -> dict[str, Any]:
    """Build a JSON-safe F1/F2/F3 provenance manifest with no hardware claim."""

    if not f1_samples:
        raise ValueError("f1_samples must be non-empty")
    if len(f1_samples) != len(f2_samples) or len(f1_samples) != len(f3_samples):
        raise ValueError("F1, F2 and F3 sample counts must match")
    expected_refs = [(sample.index, sample.seed) for sample in f1_samples]
    if [(sample.f1_index, sample.f1_seed) for sample in f2_samples] != expected_refs:
        raise ValueError("F2 references do not match F1 samples in order")
    if [(sample.f1_index, sample.f1_seed) for sample in f3_samples] != expected_refs:
        raise ValueError("F3 references do not match F1 samples in order")
    for sample in f1_samples:
        _validate_f1_sample(sample)
    if any(sample.parameters_measured or sample.hardware_identified for sample in f2_samples):
        raise ValueError("F2 manifest contains an invalid hardware claim")
    if any(sample.parameters_measured or sample.hardware_identified for sample in f3_samples):
        raise ValueError("F3 manifest contains an invalid hardware claim")

    nameplate = Air56B2Nameplate()
    return {
        "schema": "air56b2-fidelity-uncertainty-v1",
        "status": "simulation_prior_only",
        "hardware_claim": False,
        "hardware_identified": False,
        "parameters_measured": False,
        "nameplate_unchanged": True,
        "nameplate": asdict(nameplate),
        "derived_nameplate": asdict(derive_nameplate(nameplate)),
        "levels": {
            "F1": "linear_nameplate_constrained_equivalent_circuit",
            "F2": "bounded_saturation_temperature_and_loss_mechanical_priors",
            "F3": "bounded_nonideal_inverter_and_sensor_chain_priors",
        },
        "seeds": {"F2": int(f2_seed), "F3": int(f3_seed)},
        "f2_priors": asdict(f2_priors),
        "f3_priors": asdict(f3_priors),
        "sample_count": len(f1_samples),
        "f1_references": [
            {
                "index": sample.index,
                "seed": sample.seed,
                "source_kind": sample.source_kind,
                "hardware_identified": sample.hardware_identified,
                "motor": asdict(sample.motor),
            }
            for sample in f1_samples
        ],
        "f2_samples": [asdict(sample) for sample in f2_samples],
        "f3_samples": [asdict(sample) for sample in f3_samples],
    }


__all__ = [
    "AdcNonidealities",
    "As5600Nonidealities",
    "F2Priors",
    "F2Sample",
    "F3Priors",
    "F3Sample",
    "FloatBounds",
    "IntBounds",
    "InverterNonidealities",
    "fidelity_manifest",
    "generate_f2_samples",
    "generate_f3_samples",
]

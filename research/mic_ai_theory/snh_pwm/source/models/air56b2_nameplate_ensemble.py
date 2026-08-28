from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from random import Random
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from config.env import MotorParams


OFFICIAL_IEK_SOURCE_URL = (
    "https://cdn-01.iek.ru/media/original/"
    "78c31060549010eaa9a1bb1f4f6d2d8cb3155062b138bfd13478f55521c38a47.pdf"
)


@dataclass(frozen=True)
class Air56B2Nameplate:
    """Official rounded catalogue values for IEK AIR56B2, 220 V Delta."""

    output_power_w: float = 250.0
    line_voltage_v: float = 220.0
    line_current_a: float = 1.24
    power_factor: float = 0.78
    efficiency: float = 0.68
    frequency_hz: float = 50.0
    rated_speed_rpm: float = 2720.0
    pole_pairs: int = 1
    connection: str = "D"
    start_current_ratio: float = 5.3
    start_torque_ratio: float = 2.2
    max_torque_ratio: float = 2.2
    source_url: str = OFFICIAL_IEK_SOURCE_URL

    def __post_init__(self) -> None:
        if self.connection.upper() != "D":
            raise ValueError("AIR56B2 220 V profile must use physical Delta connection")
        positive = (
            self.output_power_w,
            self.line_voltage_v,
            self.line_current_a,
            self.power_factor,
            self.efficiency,
            self.frequency_hz,
            self.rated_speed_rpm,
            self.start_current_ratio,
        )
        if any(value <= 0.0 for value in positive):
            raise ValueError("nameplate values must be positive")
        if self.power_factor > 1.0 or self.efficiency > 1.0:
            raise ValueError("power factor and efficiency must not exceed one")
        if self.pole_pairs < 1:
            raise ValueError("pole_pairs must be positive")


@dataclass(frozen=True)
class NameplateDerived:
    synchronous_speed_rpm: float
    rated_slip: float
    rated_omega_rad_s: float
    rated_torque_nm: float
    apparent_power_va: float
    input_power_from_ui_w: float
    input_power_from_eta_w: float
    reactive_power_var: float
    total_loss_w: float
    power_balance_relative_mismatch: float
    physical_phase_voltage_v: float
    physical_phase_current_a: float
    model_phase_voltage_v: float
    model_phase_current_a: float


@dataclass(frozen=True)
class EnsembleAssumptions:
    """Explicit priors for quantities that are absent from the nameplate."""

    rotational_loss_fraction: tuple[float, float] = (0.05, 0.18)
    leakage_total_h: tuple[float, float] = (0.004, 0.015)
    leakage_split: tuple[float, float] = (0.35, 0.65)
    inertia_kg_m2: tuple[float, float] = (0.7e-4, 4.0e-4)
    fit_relative_tolerance: float = 0.01

    def __post_init__(self) -> None:
        for name in (
            "rotational_loss_fraction",
            "leakage_total_h",
            "leakage_split",
            "inertia_kg_m2",
        ):
            low, high = getattr(self, name)
            if not (0.0 < low <= high):
                raise ValueError(f"invalid range for {name}")
        if not (0.0 < self.fit_relative_tolerance < 0.10):
            raise ValueError("fit_relative_tolerance must be in (0, 0.10)")


@dataclass(frozen=True)
class EquivalentCircuitPrediction:
    line_current_a: float
    power_factor: float
    input_power_w: float
    output_power_w: float
    efficiency: float
    output_torque_nm: float
    stator_copper_loss_w: float
    rotor_copper_loss_w: float
    core_loss_w: float
    rotational_loss_w: float
    parallel_voltage_v: float
    magnetizing_current_a: float
    rotor_branch_current_a: float
    start_current_ratio: float
    start_torque_ratio: float
    max_torque_ratio: float
    max_torque_slip: float


@dataclass(frozen=True)
class Air56B2EnsembleSample:
    index: int
    seed: int
    motor: MotorParams
    core_resistance_ohm: float
    rated_prediction: EquivalentCircuitPrediction
    stator_copper_loss_w: float
    rotor_copper_loss_w: float
    core_loss_w: float
    rotational_loss_w: float
    magnetizing_current_a: float
    rotor_branch_current_a: float
    predicted_start_current_ratio: float
    leakage_split: float
    source_kind: str = "partial_nameplate_constrained_single_cage_estimate"
    hardware_identified: bool = False


def derive_nameplate(nameplate: Air56B2Nameplate = Air56B2Nameplate()) -> NameplateDerived:
    n_sync = 60.0 * nameplate.frequency_hz / nameplate.pole_pairs
    slip = (n_sync - nameplate.rated_speed_rpm) / n_sync
    if not (0.0 < slip < 1.0):
        raise ValueError("rated speed is inconsistent with an induction motor")

    omega = 2.0 * math.pi * nameplate.rated_speed_rpm / 60.0
    apparent = math.sqrt(3.0) * nameplate.line_voltage_v * nameplate.line_current_a
    p_ui = apparent * nameplate.power_factor
    p_eta = nameplate.output_power_w / nameplate.efficiency
    q = math.sqrt(max(apparent * apparent - p_ui * p_ui, 0.0))

    # A Delta winding has U_phase=U_line and I_phase=I_line/sqrt(3).
    # The alpha-beta plant uses the power-invariant star equivalent.
    physical_i_phase = nameplate.line_current_a / math.sqrt(3.0)
    model_u_phase = nameplate.line_voltage_v / math.sqrt(3.0)
    mismatch = abs(p_ui - p_eta) / max(p_eta, 1e-12)
    return NameplateDerived(
        synchronous_speed_rpm=n_sync,
        rated_slip=slip,
        rated_omega_rad_s=omega,
        rated_torque_nm=nameplate.output_power_w / omega,
        apparent_power_va=apparent,
        input_power_from_ui_w=p_ui,
        input_power_from_eta_w=p_eta,
        reactive_power_var=q,
        total_loss_w=p_eta - nameplate.output_power_w,
        power_balance_relative_mismatch=mismatch,
        physical_phase_voltage_v=nameplate.line_voltage_v,
        physical_phase_current_a=physical_i_phase,
        model_phase_voltage_v=model_u_phase,
        model_phase_current_a=nameplate.line_current_a,
    )


def _uniform(rng: Random, bounds: tuple[float, float]) -> float:
    return rng.uniform(float(bounds[0]), float(bounds[1]))


def _log_uniform(rng: Random, bounds: tuple[float, float]) -> float:
    low, high = map(float, bounds)
    return math.exp(rng.uniform(math.log(low), math.log(high)))


def equivalent_circuit_electromagnetic_torque(
    motor: MotorParams,
    *,
    core_resistance_ohm: float,
    slip: float,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    derived: NameplateDerived | None = None,
) -> float:
    """Return Thevenin electromagnetic torque for a positive motoring slip."""

    if not (0.0 < float(slip) <= 1.0):
        raise ValueError("motoring slip must be in (0, 1]")
    derived = derived if derived is not None else derive_nameplate(nameplate)
    omega_e = 2.0 * math.pi * nameplate.frequency_hz
    voltage = derived.model_phase_voltage_v
    rc = max(float(core_resistance_ohm), 1e-12)
    z_stator = complex(float(motor.Rs), omega_e * float(motor.Ls_sigma))
    z_magnetizing = 1.0 / (
        1.0 / complex(0.0, omega_e * float(motor.Lm)) + 1.0 / rc
    )
    z_thevenin = z_stator * z_magnetizing / (z_stator + z_magnetizing)
    v_thevenin = voltage * z_magnetizing / (z_stator + z_magnetizing)
    rotor_effective_r = float(motor.Rr) / float(slip)
    x_total = z_thevenin.imag + omega_e * float(motor.Lr_sigma)
    omega_sync_mech = omega_e / float(nameplate.pole_pairs)
    denominator = omega_sync_mech * (
        (z_thevenin.real + rotor_effective_r) ** 2 + x_total**2
    )
    return 3.0 * abs(v_thevenin) ** 2 * rotor_effective_r / max(denominator, 1e-12)


def equivalent_circuit_max_torque(
    motor: MotorParams,
    *,
    core_resistance_ohm: float,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    derived: NameplateDerived | None = None,
) -> tuple[float, float]:
    """Return analytical maximum motoring torque and its slip in (0, 1]."""

    derived = derived if derived is not None else derive_nameplate(nameplate)
    omega_e = 2.0 * math.pi * nameplate.frequency_hz
    rc = max(float(core_resistance_ohm), 1e-12)
    z_stator = complex(float(motor.Rs), omega_e * float(motor.Ls_sigma))
    z_magnetizing = 1.0 / (
        1.0 / complex(0.0, omega_e * float(motor.Lm)) + 1.0 / rc
    )
    z_thevenin = z_stator * z_magnetizing / (z_stator + z_magnetizing)
    x_total = z_thevenin.imag + omega_e * float(motor.Lr_sigma)
    optimum_rotor_effective_r = math.hypot(z_thevenin.real, x_total)
    unconstrained_slip = float(motor.Rr) / max(optimum_rotor_effective_r, 1.0e-12)
    max_slip = min(1.0, max(unconstrained_slip, 1.0e-9))
    return (
        equivalent_circuit_electromagnetic_torque(
            motor,
            core_resistance_ohm=rc,
            slip=max_slip,
            nameplate=nameplate,
            derived=derived,
        ),
        max_slip,
    )


def evaluate_equivalent_circuit(
    motor: MotorParams,
    *,
    core_resistance_ohm: float,
    rotational_loss_w: float,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    derived: NameplateDerived | None = None,
) -> EquivalentCircuitPrediction:
    """Evaluate the per-phase star-equivalent circuit at rated slip."""

    derived = derived if derived is not None else derive_nameplate(nameplate)
    omega_e = 2.0 * math.pi * nameplate.frequency_hz
    voltage = derived.model_phase_voltage_v
    rc = max(float(core_resistance_ohm), 1e-12)

    def electrical(slip: float) -> tuple[complex, complex, complex, float]:
        slip = max(float(slip), 1e-9)
        z_stator = complex(float(motor.Rs), omega_e * float(motor.Ls_sigma))
        z_magnetizing = 1.0 / (
            1.0 / complex(0.0, omega_e * float(motor.Lm)) + 1.0 / rc
        )
        z_rotor = complex(
            float(motor.Rr) / slip,
            omega_e * float(motor.Lr_sigma),
        )
        z_parallel = z_magnetizing * z_rotor / (z_magnetizing + z_rotor)
        i_stator = voltage / (z_stator + z_parallel)
        parallel_voltage = voltage - i_stator * z_stator
        i_rotor = parallel_voltage / z_rotor
        input_power = 3.0 * (voltage * i_stator.conjugate()).real
        return i_stator, i_rotor, parallel_voltage, input_power

    i_stator, i_rotor, parallel_voltage, input_power = electrical(derived.rated_slip)
    start_i_stator, _, _, _ = electrical(1.0)
    air_gap_power = 3.0 * abs(i_rotor) ** 2 * float(motor.Rr) / derived.rated_slip
    developed_power = air_gap_power * (1.0 - derived.rated_slip)
    output_power = developed_power - float(rotational_loss_w)
    apparent = 3.0 * voltage * abs(i_stator)
    power_factor = input_power / max(apparent, 1e-12)
    stator_copper = 3.0 * abs(i_stator) ** 2 * float(motor.Rs)
    rotor_copper = 3.0 * abs(i_rotor) ** 2 * float(motor.Rr)
    core_loss = 3.0 * abs(parallel_voltage) ** 2 / rc

    # Starting and maximum torque are electromagnetic torques; the catalogue
    # ratios use rated shaft torque as their denominator.
    start_torque = equivalent_circuit_electromagnetic_torque(
        motor,
        core_resistance_ohm=rc,
        slip=1.0,
        nameplate=nameplate,
        derived=derived,
    )
    max_torque, max_torque_slip = equivalent_circuit_max_torque(
        motor,
        core_resistance_ohm=rc,
        nameplate=nameplate,
        derived=derived,
    )
    rated_shaft_torque = nameplate.output_power_w / derived.rated_omega_rad_s
    start_torque_ratio = start_torque / rated_shaft_torque
    max_torque_ratio = max_torque / rated_shaft_torque
    return EquivalentCircuitPrediction(
        line_current_a=abs(i_stator),
        power_factor=power_factor,
        input_power_w=input_power,
        output_power_w=output_power,
        efficiency=output_power / max(input_power, 1e-12),
        output_torque_nm=output_power / max(derived.rated_omega_rad_s, 1e-12),
        stator_copper_loss_w=stator_copper,
        rotor_copper_loss_w=rotor_copper,
        core_loss_w=core_loss,
        rotational_loss_w=float(rotational_loss_w),
        parallel_voltage_v=abs(parallel_voltage),
        magnetizing_current_a=abs(parallel_voltage) / max(omega_e * float(motor.Lm), 1e-12),
        rotor_branch_current_a=abs(i_rotor),
        start_current_ratio=abs(start_i_stator) / max(nameplate.line_current_a, 1e-12),
        start_torque_ratio=start_torque_ratio,
        max_torque_ratio=max_torque_ratio,
        max_torque_slip=max_torque_slip,
    )


def _candidate(
    index: int,
    seed: int,
    rng: Random,
    nameplate: Air56B2Nameplate,
    derived: NameplateDerived,
    assumptions: EnsembleAssumptions,
) -> Air56B2EnsembleSample | None:
    total_loss = derived.total_loss_w
    p_rot = total_loss * _uniform(rng, assumptions.rotational_loss_fraction)
    split = _uniform(rng, assumptions.leakage_split)
    j = _log_uniform(rng, assumptions.inertia_kg_m2)
    b = p_rot / (derived.rated_omega_rad_s**2)

    def build_motor(values: np.ndarray) -> tuple[MotorParams, float]:
        rs, rr, lm, leakage_total, rc = (float(value) for value in np.exp(values))
        return (
            MotorParams(
                Rs=rs,
                Rr=rr,
                Ls_sigma=leakage_total * split,
                Lr_sigma=leakage_total * (1.0 - split),
                Lm=lm,
                J=j,
                B=b,
                p=nameplate.pole_pairs,
                I_n=nameplate.line_current_a,
                psi_sat=0.0,
                sat_exp=2.0,
                lm_min_scale=0.45,
            ),
            rc,
        )

    def residuals(values: np.ndarray) -> list[float]:
        motor, rc = build_motor(values)
        prediction = evaluate_equivalent_circuit(
            motor,
            core_resistance_ohm=rc,
            rotational_loss_w=p_rot,
            nameplate=nameplate,
            derived=derived,
        )
        return [
            prediction.line_current_a / nameplate.line_current_a - 1.0,
            prediction.power_factor / nameplate.power_factor - 1.0,
            prediction.output_power_w / nameplate.output_power_w - 1.0,
            prediction.efficiency / nameplate.efficiency - 1.0,
            prediction.start_current_ratio / nameplate.start_current_ratio - 1.0,
        ]

    initial = np.log(
        [
            rng.uniform(4.0, 8.0),
            rng.uniform(10.0, 18.0),
            rng.uniform(0.35, 0.70),
            _uniform(rng, assumptions.leakage_total_h),
            rng.uniform(500.0, 1400.0),
        ]
    )
    lower = np.log([1.0, 1.0, 0.05, assumptions.leakage_total_h[0], 50.0])
    upper = np.log([40.0, 50.0, 2.0, assumptions.leakage_total_h[1], 10_000.0])
    fit = least_squares(
        residuals,
        initial,
        bounds=(lower, upper),
        max_nfev=1200,
        ftol=1.0e-11,
        xtol=1.0e-11,
        gtol=1.0e-11,
    )
    if not fit.success:
        return None
    motor, core_resistance = build_motor(fit.x)
    prediction = evaluate_equivalent_circuit(
        motor,
        core_resistance_ohm=core_resistance,
        rotational_loss_w=p_rot,
        nameplate=nameplate,
        derived=derived,
    )
    fit_errors = residuals(fit.x)
    if max(abs(error) for error in fit_errors) > assumptions.fit_relative_tolerance:
        return None
    # F1 is deliberately linear. Saturation parameters are not identifiable
    # from this nameplate and belong to a separate F2 uncertainty family.
    inductance_determinant = (motor.Lm + motor.Ls_sigma) * (
        motor.Lm + motor.Lr_sigma
    ) - motor.Lm**2
    if inductance_determinant <= 0.0:
        return None

    return Air56B2EnsembleSample(
        index=index,
        seed=seed,
        motor=motor,
        core_resistance_ohm=core_resistance,
        rated_prediction=prediction,
        stator_copper_loss_w=prediction.stator_copper_loss_w,
        rotor_copper_loss_w=prediction.rotor_copper_loss_w,
        core_loss_w=prediction.core_loss_w,
        rotational_loss_w=p_rot,
        magnetizing_current_a=prediction.magnetizing_current_a,
        rotor_branch_current_a=prediction.rotor_branch_current_a,
        predicted_start_current_ratio=prediction.start_current_ratio,
        leakage_split=split,
    )


def generate_air56b2_ensemble(
    count: int,
    *,
    seed: int,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    assumptions: EnsembleAssumptions = EnsembleAssumptions(),
) -> list[Air56B2EnsembleSample]:
    """Generate deterministic candidates constrained by rounded nameplate data."""

    if count < 1:
        raise ValueError("count must be positive")
    derived = derive_nameplate(nameplate)
    if derived.power_balance_relative_mismatch > 0.03:
        raise ValueError("nameplate power balance mismatch exceeds catalogue rounding tolerance")

    rng = Random(seed)
    samples: list[Air56B2EnsembleSample] = []
    attempts = 0
    max_attempts = max(1000, count * 500)
    while len(samples) < count and attempts < max_attempts:
        attempts += 1
        sample_seed = rng.randrange(0, 2**63)
        sample_rng = Random(sample_seed)
        sample = _candidate(
            len(samples), sample_seed, sample_rng, nameplate, derived, assumptions
        )
        if sample is not None:
            samples.append(sample)
    if len(samples) != count:
        raise RuntimeError(
            f"generated only {len(samples)} of {count} candidates after {attempts} attempts"
        )
    return samples


def select_nominal_sample(
    samples: list[Air56B2EnsembleSample],
) -> Air56B2EnsembleSample:
    """Return the observed sample nearest to the component-wise log median."""

    if not samples:
        raise ValueError("samples must be non-empty")
    fields = ("Rs", "Rr", "Ls_sigma", "Lr_sigma", "Lm", "J", "B")
    centers: dict[str, float] = {}
    for field in fields:
        values = sorted(math.log(float(getattr(sample.motor, field))) for sample in samples)
        middle = len(values) // 2
        centers[field] = (
            values[middle]
            if len(values) % 2
            else 0.5 * (values[middle - 1] + values[middle])
        )

    def distance(sample: Air56B2EnsembleSample) -> float:
        return sum(
            (math.log(float(getattr(sample.motor, field))) - centers[field]) ** 2
            for field in fields
        )

    return min(samples, key=lambda sample: (distance(sample), sample.index))


def ensemble_manifest(
    samples: list[Air56B2EnsembleSample],
    *,
    master_seed: int,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    assumptions: EnsembleAssumptions = EnsembleAssumptions(),
) -> dict[str, Any]:
    motor_fields = ("Rs", "Rr", "Ls_sigma", "Lr_sigma", "Lm", "J", "B", "psi_sat")
    ranges = {
        field: {
            "min": min(float(getattr(sample.motor, field)) for sample in samples),
            "max": max(float(getattr(sample.motor, field)) for sample in samples),
        }
        for field in motor_fields
    } if samples else {}
    prediction_fields = (
        "line_current_a",
        "power_factor",
        "output_power_w",
        "efficiency",
        "start_current_ratio",
        "start_torque_ratio",
        "max_torque_ratio",
        "max_torque_slip",
    )
    prediction_ranges = {
        field: {
            "min": min(float(getattr(sample.rated_prediction, field)) for sample in samples),
            "max": max(float(getattr(sample.rated_prediction, field)) for sample in samples),
        }
        for field in prediction_fields
    } if samples else {}
    torque_targets = {
        "start_torque_ratio": nameplate.start_torque_ratio,
        "max_torque_ratio": nameplate.max_torque_ratio,
    }
    torque_discrepancy = {
        field: {
            "official_target": target,
            "minimum_relative_error": min(
                abs(float(getattr(sample.rated_prediction, field)) / target - 1.0)
                for sample in samples
            ),
            "maximum_relative_error": max(
                abs(float(getattr(sample.rated_prediction, field)) / target - 1.0)
                for sample in samples
            ),
        }
        for field, target in torque_targets.items()
    } if samples else {}
    nominal = select_nominal_sample(samples) if samples else None
    return {
        "schema": "air56b2-nameplate-ensemble-v2",
        "status": "simulation_prior_only",
        "model_fidelity": "F1_linear_partial_nameplate_constrained_single_cage",
        "hardware_identified": False,
        "physical_connection": "Delta_220V",
        "model_connection": "power_invariant_star_equivalent",
        "saturation_model_enabled": False,
        "master_seed": int(master_seed),
        "nameplate": asdict(nameplate),
        "derived": asdict(derive_nameplate(nameplate)),
        "assumptions": asdict(assumptions),
        "parameter_provenance": {
            "official_nameplate": {
                "source_url": nameplate.source_url,
                "fields": [
                    "output_power_w",
                    "line_voltage_v",
                    "line_current_a",
                    "power_factor",
                    "efficiency",
                    "frequency_hz",
                    "rated_speed_rpm",
                    "pole_pairs",
                    "connection",
                    "start_current_ratio",
                    "start_torque_ratio",
                    "max_torque_ratio",
                ],
            },
            "deterministically_derived": {
                "fields": list(asdict(derive_nameplate(nameplate))),
                "depends_only_on_official_nameplate": True,
            },
            "constrained_estimates": {
                "fields": [
                    "Rs",
                    "Rr",
                    "Ls_sigma",
                    "Lr_sigma",
                    "Lm",
                    "core_resistance_ohm",
                    "J",
                    "B",
                ],
                "unique_from_nameplate": False,
                "depends_on_explicit_priors": True,
                "hardware_identified": False,
            },
        },
        "f1_constraint_policy": {
            "fitted_within_relative_tolerance": [
                "line_current_a",
                "power_factor",
                "output_power_w",
                "efficiency",
                "start_current_ratio",
            ],
            "validation_only_not_forced": [
                "start_torque_ratio",
                "max_torque_ratio",
            ],
            "reason": (
                "The linear single-cage F1 equivalent circuit does not uniquely "
                "reproduce every rounded catalogue ratio. Official torque ratios "
                "remain unchanged and are validation targets for higher-fidelity models."
            ),
        },
        "sample_count": len(samples),
        "motor_parameter_ranges": ranges,
        "rated_prediction_ranges": prediction_ranges,
        "f1_torque_ratio_discrepancy": torque_discrepancy,
        "f1_all_torque_ratios_within_fit_tolerance": bool(samples) and all(
            details["maximum_relative_error"] <= assumptions.fit_relative_tolerance
            for details in torque_discrepancy.values()
        ),
        "f1_full_nameplate_fit_pass": bool(samples) and all(
            details["maximum_relative_error"] <= assumptions.fit_relative_tolerance
            for details in torque_discrepancy.values()
        ),
        "nominal_estimate": (
            {
                "sample_index": nominal.index,
                "sample_seed": nominal.seed,
                "motor": asdict(nominal.motor),
                "core_resistance_ohm": nominal.core_resistance_ohm,
                "rated_prediction": asdict(nominal.rated_prediction),
                "hardware_identified": False,
            }
            if nominal is not None
            else None
        ),
        "samples": [
            {
                **{key: value for key, value in asdict(sample).items() if key != "motor"},
                "motor": asdict(sample.motor),
            }
            for sample in samples
        ],
    }


__all__ = [
    "Air56B2EnsembleSample",
    "Air56B2Nameplate",
    "EnsembleAssumptions",
    "EquivalentCircuitPrediction",
    "NameplateDerived",
    "OFFICIAL_IEK_SOURCE_URL",
    "derive_nameplate",
    "ensemble_manifest",
    "equivalent_circuit_electromagnetic_torque",
    "equivalent_circuit_max_torque",
    "evaluate_equivalent_circuit",
    "generate_air56b2_ensemble",
    "select_nominal_sample",
]

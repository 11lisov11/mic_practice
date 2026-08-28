from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Sequence

from models.air56b2_nameplate_ensemble import (
    Air56B2EnsembleSample,
    Air56B2Nameplate,
    derive_nameplate,
)


@dataclass(frozen=True)
class StartingRegimeAssumptions:
    """Explicit phenomenological assumptions used only above rated slip.

    The exponent is not a nameplate value. It shapes a smooth additional-loss
    term between the rated point and locked rotor. The fixed value was selected
    conservatively so the corrected F1 ensemble does not exceed the rounded
    catalogue maximum-torque ratio.
    """

    transition_exponent: float = 0.15
    slip_grid_points: int = 2048
    maximum_torque_relative_tolerance: float = 0.002

    def __post_init__(self) -> None:
        if not (0.0 < float(self.transition_exponent) <= 1.0):
            raise ValueError("transition_exponent must be in (0, 1]")
        if int(self.slip_grid_points) < 128:
            raise ValueError("slip_grid_points must be at least 128")
        if not (0.0 <= float(self.maximum_torque_relative_tolerance) <= 0.05):
            raise ValueError("maximum_torque_relative_tolerance must be in [0, 0.05]")


@dataclass(frozen=True)
class StartingRegimePoint:
    slip: float
    mechanical_speed_rpm: float
    line_current_a: float
    current_ratio: float
    input_power_w: float
    power_factor: float
    base_air_gap_power_w: float
    corrected_air_gap_power_w: float
    additional_high_slip_loss_w: float
    base_electromagnetic_torque_nm: float
    corrected_electromagnetic_torque_nm: float
    base_torque_ratio: float
    corrected_torque_ratio: float
    torque_scale: float


@dataclass(frozen=True)
class StartingRegimeCalibration:
    index: int
    seed: int
    f1_index: int
    f1_seed: int
    transition_exponent: float
    start_torque_scale: float
    base_start_current_ratio: float
    corrected_start_current_ratio: float
    base_start_torque_ratio: float
    corrected_start_torque_ratio: float
    base_max_torque_ratio: float
    corrected_max_torque_ratio: float
    corrected_max_torque_slip: float
    rated_torque_scale: float
    start_additional_high_slip_loss_w: float
    source_kind: str = "official_nameplate_calibrated_phenomenological_high_slip_loss"
    parameters_measured: bool = False
    hardware_identified: bool = False

    def __post_init__(self) -> None:
        if min(self.index, self.seed, self.f1_index, self.f1_seed) < 0:
            raise ValueError("sample indexes and seeds must be non-negative")
        if self.parameters_measured or self.hardware_identified:
            raise ValueError("starting-regime calibration cannot claim hardware identification")
        if not (0.0 < self.start_torque_scale <= 1.0):
            raise ValueError("start_torque_scale must be in (0, 1]")
        if not math.isclose(self.rated_torque_scale, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("starting-regime correction must preserve the rated point")
        if self.start_additional_high_slip_loss_w < 0.0:
            raise ValueError("additional high-slip loss must be non-negative")


def _base_operating_point(
    sample: Air56B2EnsembleSample,
    *,
    slip: float,
    nameplate: Air56B2Nameplate,
) -> tuple[float, float, float, float, float]:
    slip = float(slip)
    if not (0.0 < slip <= 1.0):
        raise ValueError("motoring slip must be in (0, 1]")
    derived = derive_nameplate(nameplate)
    motor = sample.motor
    omega_e = 2.0 * math.pi * nameplate.frequency_hz
    voltage = derived.model_phase_voltage_v
    core_resistance = max(float(sample.core_resistance_ohm), 1e-12)
    z_stator = complex(float(motor.Rs), omega_e * float(motor.Ls_sigma))
    z_magnetizing = 1.0 / (
        1.0 / complex(0.0, omega_e * float(motor.Lm)) + 1.0 / core_resistance
    )
    z_rotor = complex(
        float(motor.Rr) / slip,
        omega_e * float(motor.Lr_sigma),
    )
    z_parallel = z_magnetizing * z_rotor / (z_magnetizing + z_rotor)
    stator_current = voltage / (z_stator + z_parallel)
    parallel_voltage = voltage - stator_current * z_stator
    rotor_current = parallel_voltage / z_rotor
    input_power = 3.0 * (voltage * stator_current.conjugate()).real
    apparent_power = 3.0 * voltage * abs(stator_current)
    air_gap_power = 3.0 * abs(rotor_current) ** 2 * float(motor.Rr) / slip
    omega_sync_mechanical = omega_e / float(nameplate.pole_pairs)
    torque = air_gap_power / omega_sync_mechanical
    return (
        abs(stator_current),
        input_power,
        input_power / max(apparent_power, 1e-12),
        air_gap_power,
        torque,
    )


def starting_torque_scale(
    sample: Air56B2EnsembleSample,
    *,
    slip: float,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    assumptions: StartingRegimeAssumptions = StartingRegimeAssumptions(),
) -> float:
    """Return the F1S torque scale while preserving the rated F1 point."""

    derived = derive_nameplate(nameplate)
    slip = float(slip)
    if not math.isfinite(slip) or slip <= 0.0:
        raise ValueError("motoring slip must be finite and positive")
    if slip <= derived.rated_slip:
        return 1.0
    base_start_ratio = float(sample.rated_prediction.start_torque_ratio)
    if base_start_ratio <= 0.0:
        raise ValueError("F1 start torque ratio must be positive")
    start_scale = float(nameplate.start_torque_ratio) / base_start_ratio
    if not (0.0 < start_scale <= 1.0):
        raise ValueError("F1S supports loss-only correction; F1 start torque must exceed target")
    normalized_slip = min(
        1.0,
        max(0.0, (min(slip, 1.0) - derived.rated_slip) / (1.0 - derived.rated_slip)),
    )
    scale = 1.0 - (1.0 - start_scale) * (
        normalized_slip ** float(assumptions.transition_exponent)
    )
    return min(1.0, max(start_scale, scale))


def starting_torque_scale_for_speed(
    sample: Air56B2EnsembleSample,
    *,
    electrical_frequency_hz: float,
    mechanical_speed_rad_s: float,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    assumptions: StartingRegimeAssumptions = StartingRegimeAssumptions(),
) -> float:
    """Map instantaneous speed and stator frequency to the F1S slip correction."""

    frequency = float(electrical_frequency_hz)
    speed = float(mechanical_speed_rad_s)
    if not math.isfinite(frequency) or not math.isfinite(speed):
        raise ValueError("frequency and speed must be finite")
    if frequency <= 0.0:
        return 1.0
    synchronous_speed = 2.0 * math.pi * frequency / float(nameplate.pole_pairs)
    slip = (synchronous_speed - speed) / max(synchronous_speed, 1e-12)
    if slip <= 0.0:
        return 1.0
    return starting_torque_scale(
        sample,
        slip=min(slip, 1.0),
        nameplate=nameplate,
        assumptions=assumptions,
    )


def evaluate_starting_regime(
    sample: Air56B2EnsembleSample,
    *,
    slip: float,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    assumptions: StartingRegimeAssumptions = StartingRegimeAssumptions(),
) -> StartingRegimePoint:
    derived = derive_nameplate(nameplate)
    current, input_power, power_factor, base_air_gap_power, base_torque = (
        _base_operating_point(sample, slip=slip, nameplate=nameplate)
    )
    torque_scale = starting_torque_scale(
        sample,
        slip=slip,
        nameplate=nameplate,
        assumptions=assumptions,
    )
    corrected_air_gap_power = base_air_gap_power * torque_scale
    additional_loss = base_air_gap_power - corrected_air_gap_power
    corrected_torque = base_torque * torque_scale
    rated_torque = derived.rated_torque_nm
    return StartingRegimePoint(
        slip=float(slip),
        mechanical_speed_rpm=derived.synchronous_speed_rpm * (1.0 - float(slip)),
        line_current_a=current,
        current_ratio=current / nameplate.line_current_a,
        input_power_w=input_power,
        power_factor=power_factor,
        base_air_gap_power_w=base_air_gap_power,
        corrected_air_gap_power_w=corrected_air_gap_power,
        additional_high_slip_loss_w=max(0.0, additional_loss),
        base_electromagnetic_torque_nm=base_torque,
        corrected_electromagnetic_torque_nm=corrected_torque,
        base_torque_ratio=base_torque / rated_torque,
        corrected_torque_ratio=corrected_torque / rated_torque,
        torque_scale=torque_scale,
    )


def calibrate_starting_regime(
    sample: Air56B2EnsembleSample,
    *,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    assumptions: StartingRegimeAssumptions = StartingRegimeAssumptions(),
) -> StartingRegimeCalibration:
    derived = derive_nameplate(nameplate)
    rated = evaluate_starting_regime(
        sample,
        slip=derived.rated_slip,
        nameplate=nameplate,
        assumptions=assumptions,
    )
    start = evaluate_starting_regime(
        sample,
        slip=1.0,
        nameplate=nameplate,
        assumptions=assumptions,
    )
    points: list[StartingRegimePoint] = []
    ratio = 1.0 / derived.rated_slip
    for index in range(int(assumptions.slip_grid_points)):
        fraction = index / float(assumptions.slip_grid_points - 1)
        slip = derived.rated_slip * ratio**fraction
        points.append(
            evaluate_starting_regime(
                sample,
                slip=slip,
                nameplate=nameplate,
                assumptions=assumptions,
            )
        )
    maximum = max(points, key=lambda point: (point.corrected_torque_ratio, point.slip))
    allowed_maximum = nameplate.max_torque_ratio * (
        1.0 + assumptions.maximum_torque_relative_tolerance
    )
    if maximum.corrected_torque_ratio > allowed_maximum:
        raise ValueError(
            "F1S transition assumption exceeds the official maximum-torque envelope"
        )
    return StartingRegimeCalibration(
        index=sample.index,
        seed=sample.seed,
        f1_index=sample.index,
        f1_seed=sample.seed,
        transition_exponent=assumptions.transition_exponent,
        start_torque_scale=start.torque_scale,
        base_start_current_ratio=start.current_ratio,
        corrected_start_current_ratio=start.current_ratio,
        base_start_torque_ratio=start.base_torque_ratio,
        corrected_start_torque_ratio=start.corrected_torque_ratio,
        base_max_torque_ratio=sample.rated_prediction.max_torque_ratio,
        corrected_max_torque_ratio=maximum.corrected_torque_ratio,
        corrected_max_torque_slip=maximum.slip,
        rated_torque_scale=rated.torque_scale,
        start_additional_high_slip_loss_w=start.additional_high_slip_loss_w,
    )


def generate_starting_regime_calibrations(
    samples: Sequence[Air56B2EnsembleSample],
    *,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    assumptions: StartingRegimeAssumptions = StartingRegimeAssumptions(),
) -> list[StartingRegimeCalibration]:
    if not samples:
        raise ValueError("samples must be non-empty")
    return [
        calibrate_starting_regime(
            sample,
            nameplate=nameplate,
            assumptions=assumptions,
        )
        for sample in samples
    ]


def starting_regime_manifest(
    samples: Sequence[Air56B2EnsembleSample],
    calibrations: Sequence[StartingRegimeCalibration],
    *,
    master_seed: int,
    nameplate: Air56B2Nameplate = Air56B2Nameplate(),
    assumptions: StartingRegimeAssumptions = StartingRegimeAssumptions(),
) -> dict[str, Any]:
    if not samples or len(samples) != len(calibrations):
        raise ValueError("F1 samples and F1S calibrations must be non-empty and aligned")
    expected = [(sample.index, sample.seed) for sample in samples]
    observed = [(item.f1_index, item.f1_seed) for item in calibrations]
    if observed != expected:
        raise ValueError("F1S references do not match F1 samples in order")
    current_errors = [
        abs(item.corrected_start_current_ratio / nameplate.start_current_ratio - 1.0)
        for item in calibrations
    ]
    start_torque_errors = [
        abs(item.corrected_start_torque_ratio / nameplate.start_torque_ratio - 1.0)
        for item in calibrations
    ]
    maximum_torque_errors = [
        abs(item.corrected_max_torque_ratio / nameplate.max_torque_ratio - 1.0)
        for item in calibrations
    ]
    gates = {
        "start_current_within_f1_fit_tolerance": max(current_errors) <= 0.01,
        "start_torque_matches_rounded_nameplate": max(start_torque_errors) <= 1e-9,
        "maximum_torque_within_declared_tolerance": max(maximum_torque_errors)
        <= assumptions.maximum_torque_relative_tolerance,
        "rated_operating_point_preserved": all(
            math.isclose(item.rated_torque_scale, 1.0, rel_tol=0.0, abs_tol=1e-12)
            for item in calibrations
        ),
        "no_hardware_claim": all(
            not item.parameters_measured and not item.hardware_identified
            for item in calibrations
        ),
    }
    return {
        "schema": "air56b2-starting-regime-f1s-v1",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "model_fidelity": "F1S_nameplate_calibrated_high_slip_loss_extension",
        "hardware_claim": False,
        "hardware_identified": False,
        "parameters_measured": False,
        "master_seed": int(master_seed),
        "sample_count": len(samples),
        "nameplate": asdict(nameplate),
        "assumptions": asdict(assumptions),
        "parameter_provenance": {
            "official_nameplate_targets": [
                "start_current_ratio",
                "start_torque_ratio",
                "max_torque_ratio",
            ],
            "modeling_assumptions_not_on_nameplate": [
                "transition_exponent",
                "slip_grid_points",
                "phenomenological_additional_high_slip_loss",
            ],
            "unique_physical_identification_claimed": False,
        },
        "gates": gates,
        "error_summary": {
            "start_current_max_relative_error": max(current_errors),
            "start_torque_max_relative_error": max(start_torque_errors),
            "maximum_torque_max_relative_error": max(maximum_torque_errors),
        },
        "corrected_ranges": {
            "start_torque_scale": {
                "min": min(item.start_torque_scale for item in calibrations),
                "max": max(item.start_torque_scale for item in calibrations),
            },
            "start_additional_high_slip_loss_w": {
                "min": min(item.start_additional_high_slip_loss_w for item in calibrations),
                "max": max(item.start_additional_high_slip_loss_w for item in calibrations),
            },
            "corrected_start_torque_ratio": {
                "min": min(item.corrected_start_torque_ratio for item in calibrations),
                "max": max(item.corrected_start_torque_ratio for item in calibrations),
            },
            "corrected_max_torque_ratio": {
                "min": min(item.corrected_max_torque_ratio for item in calibrations),
                "max": max(item.corrected_max_torque_ratio for item in calibrations),
            },
        },
        "calibrations": [asdict(item) for item in calibrations],
        "limitations": [
            "F1S is a phenomenological loss correction, not a uniquely identified double-cage circuit.",
            "The transition exponent is an explicit simulation assumption and must be replaced or narrowed after locked-rotor measurements.",
            "The correction is intended for positive motoring slip between the rated point and locked rotor.",
        ],
    }


__all__ = [
    "StartingRegimeAssumptions",
    "StartingRegimeCalibration",
    "StartingRegimePoint",
    "calibrate_starting_regime",
    "evaluate_starting_regime",
    "generate_starting_regime_calibrations",
    "starting_regime_manifest",
    "starting_torque_scale",
    "starting_torque_scale_for_speed",
]

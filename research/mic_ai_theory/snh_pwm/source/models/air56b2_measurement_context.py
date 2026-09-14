from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
import torch
from torch import nn

from control.air56b2_measured_loss_fit import ProbeMeasurement


FEATURE_KEYS = (
    "measured_speed_pu",
    "center_current_peak_pu",
    "center_voltage_peak_pu",
    "low_minus_center_power_100w",
    "high_minus_center_power_100w",
    "low_current_peak_pu",
    "high_current_peak_pu",
    "low_voltage_peak_pu",
    "high_voltage_peak_pu",
)


@dataclass(frozen=True)
class MeasurementProtocol:
    center_id_a: float = 0.83
    low_id_a: float = 0.55
    high_id_a: float = 1.11
    current_limit_a: float = 3.10
    voltage_limit_v: float = 170.0
    rated_speed_rad_s: float = 284.8377339254746
    repeat_power_tolerance_w: float = 4.0
    verification_margin_w: float = 2.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) and v > 0 for v in vars(self).values()):
            raise ValueError("protocol values must be finite and positive")
        if not self.low_id_a < self.center_id_a < self.high_id_a:
            raise ValueError("probe currents must be strictly ordered")

    @property
    def sequence(self) -> tuple[float, ...]:
        return (self.center_id_a, self.low_id_a, self.high_id_a, self.center_id_a)


def context_features(
    probes: Sequence[ProbeMeasurement],
    measured_speed_rad_s: float,
    protocol: MeasurementProtocol,
) -> np.ndarray:
    """Observable-only boundary: no plant parameters, torque or temperatures."""
    if len(probes) != 4 or not math.isfinite(measured_speed_rad_s):
        raise ValueError("four ordered probes and finite measured speed are required")
    for probe, expected_id in zip(probes, protocol.sequence):
        if not all(math.isfinite(v) for v in vars(probe).values()):
            raise ValueError("measurements must be finite")
        if not math.isclose(probe.id_a, expected_id, abs_tol=1e-9):
            raise ValueError("measurement sequence does not match the frozen protocol")
    first, low, high, last = probes
    power_center = 0.5 * (first.power_w + last.power_w)
    return np.asarray([
        measured_speed_rad_s / protocol.rated_speed_rad_s,
        0.5 * (first.current_peak_a + last.current_peak_a) / protocol.current_limit_a,
        0.5 * (first.voltage_peak_v + last.voltage_peak_v) / protocol.voltage_limit_v,
        (low.power_w - power_center) / 100.0,
        (high.power_w - power_center) / 100.0,
        low.current_peak_a / protocol.current_limit_a,
        high.current_peak_a / protocol.current_limit_a,
        low.voltage_peak_v / protocol.voltage_limit_v,
        high.voltage_peak_v / protocol.voltage_limit_v,
    ], dtype=np.float32)


def window_rejection_reason(
    probes: Sequence[ProbeMeasurement], protocol: MeasurementProtocol
) -> str | None:
    context_features(probes, 0.0, protocol)
    if any(p.current_peak_a < 0.0 or p.voltage_peak_v < 0.0 for p in probes):
        return "invalid_amplitude"
    if any(p.current_peak_a > protocol.current_limit_a for p in probes):
        return "measured_probe_overcurrent"
    if any(p.voltage_peak_v > protocol.voltage_limit_v for p in probes):
        return "measured_probe_overvoltage"
    if abs(probes[-1].power_w - probes[0].power_w) > protocol.repeat_power_tolerance_w:
        return "repeat_probe_drift"
    return None


def accept_verification(
    baseline: ProbeMeasurement,
    candidate: ProbeMeasurement,
    protocol: MeasurementProtocol,
) -> bool:
    values = (*vars(baseline).values(), *vars(candidate).values())
    if not all(math.isfinite(v) for v in values):
        return False
    return (
        protocol.low_id_a <= candidate.id_a <= protocol.high_id_a
        and 0.0 <= candidate.current_peak_a <= protocol.current_limit_a
        and 0.0 <= candidate.voltage_peak_v <= protocol.voltage_limit_v
        and candidate.power_w < baseline.power_w - protocol.verification_margin_w
    )


class MeasurementContextPolicy(nn.Module):
    """Distilled steady-state flux recommendation, not a direct PWM controller."""

    def __init__(self, *, single_probe: bool = False) -> None:
        super().__init__()
        self.single_probe = single_probe
        self.network = nn.Sequential(
            nn.Linear(3 if single_probe else len(FEATURE_KEYS), 48),
            nn.Tanh(),
            nn.Linear(48, 48),
            nn.Tanh(),
            nn.Linear(48, 1),
            nn.Sigmoid(),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        values = inputs[..., :3] if self.single_probe else inputs
        return self.network(values).squeeze(-1)

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
from torch import nn


FEATURE_KEYS = (
    "speed_pu",
    "torque_command_pu",
    "stator_temperature_norm",
    "rotor_temperature_norm",
)


@dataclass(frozen=True)
class IdPolicyScaling:
    id_lower_a: float = 0.12
    id_upper_a: float = 1.86
    temperature_reference_c: float = 20.0
    temperature_span_c: float = 140.0

    def normalize_temperature(self, temperature_c: float) -> float:
        value = (float(temperature_c) - self.temperature_reference_c) / self.temperature_span_c
        return max(0.0, min(1.0, value))

    def normalize_id(self, id_a: float) -> float:
        value = (float(id_a) - self.id_lower_a) / (self.id_upper_a - self.id_lower_a)
        return max(0.0, min(1.0, value))

    def denormalize_id(self, normalized: float) -> float:
        return self.id_lower_a + max(0.0, min(1.0, float(normalized))) * (
            self.id_upper_a - self.id_lower_a
        )


class Air56B2IdPolicy(nn.Module):
    """Small actor that approximates the constrained classical id optimum."""

    def __init__(self, hidden_sizes: Sequence[int] = (48, 48)) -> None:
        super().__init__()
        sizes = tuple(int(value) for value in hidden_sizes)
        if not sizes or any(value <= 0 for value in sizes):
            raise ValueError("hidden_sizes must contain positive values")
        layers: list[nn.Module] = []
        previous = len(FEATURE_KEYS)
        for size in sizes:
            layers.append(nn.Linear(previous, size))
            layers.append(nn.Tanh())
            previous = size
        layers.append(nn.Linear(previous, 1))
        layers.append(nn.Sigmoid())
        self.network = nn.Sequential(*layers)
        self.hidden_sizes = sizes

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.network(inputs).squeeze(-1)


__all__ = ["Air56B2IdPolicy", "FEATURE_KEYS", "IdPolicyScaling"]

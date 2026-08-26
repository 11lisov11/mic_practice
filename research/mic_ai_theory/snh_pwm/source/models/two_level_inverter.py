from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Tuple

from models.transformations import abc_to_alpha_beta, alpha_beta_to_abc


VectorBits = Tuple[int, int, int]


@dataclass(frozen=True)
class TwoLevelInverterParams:
    Vdc: float
    f_pwm: float = 10_000.0
    dead_time_s: float = 1.0e-6
    min_pulse_s: float = 2.0e-6
    r_on_ohm: float = 0.05
    v_drop_v: float = 0.8
    e_sw_j_per_a: float = 2.0e-6
    thermal_rth_k_per_w: float = 1.5
    thermal_cth_j_per_k: float = 10.0
    ambient_c: float = 25.0

    @property
    def t_pwm_s(self) -> float:
        return 1.0 / max(float(self.f_pwm), 1e-12)


@dataclass(frozen=True)
class InverterLossEstimate:
    conduction_w: float
    switching_w: float
    total_w: float
    switch_events: int
    common_mode_v: float


@dataclass(frozen=True)
class SpaceVectorDwell:
    vector_id: int
    dwell_s: float


@dataclass(frozen=True)
class SpaceVectorSchedule:
    sector: int
    segments: Tuple[SpaceVectorDwell, ...]
    requested_alpha_beta_v: Tuple[float, float]
    synthesized_alpha_beta_v: Tuple[float, float]
    saturated: bool

    @property
    def total_dwell_s(self) -> float:
        return sum(segment.dwell_s for segment in self.segments)


def validate_vector_id(vector_id: int) -> int:
    if not isinstance(vector_id, int):
        raise ValueError(f"vector_id must be int, got {vector_id!r}")
    if vector_id < 0 or vector_id > 7:
        raise ValueError(f"vector_id must be in 0..7, got {vector_id!r}")
    return vector_id


def vector_bits(vector_id: int) -> VectorBits:
    vector_id = validate_vector_id(vector_id)
    return ((vector_id >> 2) & 1, (vector_id >> 1) & 1, vector_id & 1)


def vector_id_from_bits(bits: Iterable[int]) -> int:
    a, b, c = tuple(int(x) for x in bits)
    for value in (a, b, c):
        if value not in (0, 1):
            raise ValueError(f"vector bit must be 0 or 1, got {value!r}")
    return (a << 2) | (b << 1) | c


def phase_voltages(vector_id: int, vdc: float) -> Tuple[float, float, float]:
    """Return motor phase voltages after common-mode removal."""

    sa, sb, sc = vector_bits(vector_id)
    mean_s = (sa + sb + sc) / 3.0
    return (
        (sa - mean_s) * float(vdc),
        (sb - mean_s) * float(vdc),
        (sc - mean_s) * float(vdc),
    )


def alpha_beta_voltage(
    vector_id: int,
    params: TwoLevelInverterParams,
    *,
    i_alpha_beta: Tuple[float, float] | None = None,
) -> Tuple[float, float]:
    v_a, v_b, v_c = phase_voltages(vector_id, params.Vdc)
    if i_alpha_beta is not None:
        i_a, i_b, i_c = alpha_beta_to_abc(float(i_alpha_beta[0]), float(i_alpha_beta[1]))
        dt_drop = abs(float(params.Vdc)) * max(float(params.dead_time_s), 0.0) / max(params.t_pwm_s, 1e-12)

        def sign(value: float) -> float:
            return 1.0 if value > 0.0 else (-1.0 if value < 0.0 else 0.0)

        v_a -= (dt_drop + float(params.v_drop_v)) * sign(i_a) + float(params.r_on_ohm) * i_a
        v_b -= (dt_drop + float(params.v_drop_v)) * sign(i_b) + float(params.r_on_ohm) * i_b
        v_c -= (dt_drop + float(params.v_drop_v)) * sign(i_c) + float(params.r_on_ohm) * i_c
    return abc_to_alpha_beta(v_a, v_b, v_c)


def common_mode_voltage(vector_id: int, vdc: float) -> float:
    sa, sb, sc = vector_bits(vector_id)
    return ((sa - 0.5) + (sb - 0.5) + (sc - 0.5)) * float(vdc) / 3.0


def switch_events(prev_vector_id: int, next_vector_id: int) -> int:
    prev = vector_bits(prev_vector_id)
    nxt = vector_bits(next_vector_id)
    return sum(1 for a, b in zip(prev, nxt) if a != b)


def space_vector_schedule(
    v_alpha_ref: float,
    v_beta_ref: float,
    params: TwoLevelInverterParams,
    *,
    previous_vector_id: int = 0,
) -> SpaceVectorSchedule:
    """Synthesize one ideal linear-region SVPWM period.

    The returned schedule contains the two adjacent active vectors and one zero
    vector. If the requested reference is outside the linear hexagon, active
    dwell times are scaled so their sum equals one PWM period. Pulse suppression
    and dead-time distortion deliberately remain downstream safety concerns.
    """

    alpha = float(v_alpha_ref)
    beta = float(v_beta_ref)
    vdc = abs(float(params.Vdc))
    period = float(params.t_pwm_s)
    if not all(math.isfinite(value) for value in (alpha, beta, vdc, period)):
        raise ValueError("SVPWM inputs must be finite")
    if vdc <= 0.0 or period <= 0.0:
        raise ValueError("SVPWM requires positive Vdc and PWM period")
    previous = validate_vector_id(previous_vector_id)

    magnitude = math.hypot(alpha, beta)
    if magnitude <= 1.0e-15:
        zero = min((0, 7), key=lambda candidate: (switch_events(previous, candidate), candidate))
        return SpaceVectorSchedule(
            sector=0,
            segments=(SpaceVectorDwell(zero, period),),
            requested_alpha_beta_v=(alpha, beta),
            synthesized_alpha_beta_v=(0.0, 0.0),
            saturated=False,
        )

    theta = math.atan2(beta, alpha) % (2.0 * math.pi)
    sector = min(int(theta / (math.pi / 3.0)), 5)
    angle_in_sector = theta - sector * (math.pi / 3.0)
    active_vectors = (4, 6, 2, 3, 1, 5)
    first = active_vectors[sector]
    second = active_vectors[(sector + 1) % 6]
    modulation = math.sqrt(3.0) * magnitude / vdc
    t_first = period * modulation * math.sin(math.pi / 3.0 - angle_in_sector)
    t_second = period * modulation * math.sin(angle_in_sector)
    active_total = max(0.0, t_first) + max(0.0, t_second)
    saturated = active_total > period
    if saturated:
        scale = period / active_total
        t_first *= scale
        t_second *= scale
    t_zero = max(0.0, period - t_first - t_second)

    candidates: list[tuple[int, tuple[int, int, int]]] = []
    for zero in (0, 7):
        for ordered in ((first, second, zero), (second, first, zero)):
            events = switch_events(previous, ordered[0])
            events += switch_events(ordered[0], ordered[1])
            events += switch_events(ordered[1], ordered[2])
            candidates.append((events, ordered))
    _, ordered_vectors = min(candidates, key=lambda item: (item[0], item[1]))
    dwell_by_vector = {first: t_first, second: t_second, ordered_vectors[2]: t_zero}
    segments = tuple(
        SpaceVectorDwell(vector_id, dwell_by_vector[vector_id])
        for vector_id in ordered_vectors
        if dwell_by_vector[vector_id] > 1.0e-15
    )

    synth_alpha = 0.0
    synth_beta = 0.0
    for segment in segments:
        vector_alpha, vector_beta = alpha_beta_voltage(segment.vector_id, params)
        weight = segment.dwell_s / period
        synth_alpha += weight * vector_alpha
        synth_beta += weight * vector_beta
    return SpaceVectorSchedule(
        sector=sector,
        segments=segments,
        requested_alpha_beta_v=(alpha, beta),
        synthesized_alpha_beta_v=(float(synth_alpha), float(synth_beta)),
        saturated=saturated,
    )


def estimate_inverter_losses(
    *,
    prev_vector_id: int,
    next_vector_id: int,
    params: TwoLevelInverterParams,
    i_alpha_beta: Tuple[float, float],
) -> InverterLossEstimate:
    i_a, i_b, i_c = alpha_beta_to_abc(float(i_alpha_beta[0]), float(i_alpha_beta[1]))
    i_rms_sq_sum = i_a * i_a + i_b * i_b + i_c * i_c
    conduction_w = max(float(params.r_on_ohm), 0.0) * i_rms_sq_sum
    events = switch_events(prev_vector_id, next_vector_id)
    i_abs = math.sqrt(max(i_rms_sq_sum / 3.0, 0.0))
    switching_w = events * max(float(params.e_sw_j_per_a), 0.0) * i_abs * max(float(params.f_pwm), 0.0)
    cmv = common_mode_voltage(next_vector_id, params.Vdc)
    return InverterLossEstimate(
        conduction_w=float(conduction_w),
        switching_w=float(switching_w),
        total_w=float(conduction_w + switching_w),
        switch_events=int(events),
        common_mode_v=float(cmv),
    )


__all__ = [
    "InverterLossEstimate",
    "SpaceVectorDwell",
    "SpaceVectorSchedule",
    "TwoLevelInverterParams",
    "VectorBits",
    "alpha_beta_voltage",
    "common_mode_voltage",
    "estimate_inverter_losses",
    "phase_voltages",
    "space_vector_schedule",
    "switch_events",
    "validate_vector_id",
    "vector_bits",
    "vector_id_from_bits",
]

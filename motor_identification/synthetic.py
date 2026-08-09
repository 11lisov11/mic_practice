from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math
from typing import Sequence

import numpy as np

from .model import ExperimentInput, MotorParameters, simulate
from .schema import CAPTURE_SCHEMA, PRIOR_SCHEMA


def _phase_voltages(vector_id: int, vdc: float) -> tuple[float, float, float]:
    sa = (int(vector_id) >> 2) & 1
    sb = (int(vector_id) >> 1) & 1
    sc = int(vector_id) & 1
    mean = (sa + sb + sc) / 3.0
    return ((sa - mean) * vdc, (sb - mean) * vdc, (sc - mean) * vdc)


def _alpha_beta_voltage(vector_id: int, vdc: float) -> tuple[float, float]:
    va, vb, vc = _phase_voltages(vector_id, vdc)
    return (
        (2.0 / 3.0) * (va - 0.5 * vb - 0.5 * vc),
        (2.0 / 3.0) * (math.sqrt(3.0) * 0.5 * (vb - vc)),
    )


def _active_vectors() -> tuple[int, ...]:
    return tuple(sorted(range(1, 7), key=lambda item: math.atan2(*reversed(_alpha_beta_voltage(item, 1.0)))))


def _repeat(values: Sequence[int], length: int) -> list[int]:
    return [int(values[index % len(values)]) for index in range(length)]


def _standstill_vectors(active: Sequence[int], length: int) -> list[int]:
    cycle: list[int] = []
    for dwell in (1, 2, 4, 8, 16):
        for vector_id in active:
            cycle.extend([int(vector_id)] * dwell)
            cycle.extend([0] * dwell)
    return _repeat(cycle, length)


def _free_run_vectors(active: Sequence[int], length: int) -> list[int]:
    def rotate(vectors: Sequence[int], count: int, dwell: int = 4) -> list[int]:
        return _repeat([item for vector in vectors for item in [int(vector)] * dwell], count)

    first = int(length * 0.4)
    coast = int(length * 0.1)
    reverse = int(length * 0.4)
    final = length - first - coast - reverse
    return rotate(active, first) + [0] * coast + rotate(tuple(reversed(active)), reverse) + [0] * final


def _experiment(
    experiment_id: str,
    kind: str,
    role: str,
    run_id: str,
    vector_ids: Sequence[int],
    *,
    vdc: float,
    dt: float,
    initial_omega: float = 0.0,
) -> tuple[dict[str, object], ExperimentInput]:
    voltages = [_alpha_beta_voltage(vector_id, vdc) for vector_id in vector_ids]
    input_data = ExperimentInput(
        experiment_id=experiment_id,
        kind=kind,
        rotor_locked=kind == "standstill",
        dt=dt,
        initial_omega_m=initial_omega,
        v_alpha=np.asarray([row[0] for row in voltages], dtype=float),
        v_beta=np.asarray([row[1] for row in voltages], dtype=float),
    )
    descriptor: dict[str, object] = {
        "id": experiment_id,
        "run_id": run_id,
        "role": role,
        "kind": kind,
        "rotor_locked": kind == "standstill",
        "initial_state": "deenergized",
        "initial_omega_rad_s": float(initial_omega),
        "voltage_source": "measured_alpha_beta",
        "captured_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "load_condition_id": "no-external-load" if kind != "standstill" else "rotor-lock-fixture",
        "motor_temperature_c": 20.0,
    }
    return descriptor, input_data


def make_synthetic_bundle(
    *,
    seed: int = 20260809,
    steps_per_electrical_experiment: int = 360,
) -> tuple[dict[str, object], dict[str, object]]:
    if steps_per_electrical_experiment < 96:
        raise ValueError("steps_per_electrical_experiment must be at least 96")
    base = MotorParameters(
        Rs=17.006802721088434,
        Rr=42.17957024079473,
        Lsigma=0.05,
        Lm=2.850407894697701,
        J=0.01,
        B=0.001084293285114197,
        pole_pairs=2,
        i_limit=1.75,
        load_torque_scale_nm=0.01,
    )
    truth = replace(
        base,
        Rs=base.Rs * 1.08,
        Rr=base.Rr * 0.92,
        Lsigma=base.Lsigma * 1.06,
        Lm=base.Lm * 1.04,
        J=base.J * 1.12,
        B=base.B * 0.90,
    )
    prior = {
        "schema": PRIOR_SCHEMA,
        "motor_id": "synthetic-reference-motor",
        **base.as_dict(),
        "load_torque_scale_nm": base.load_torque_scale_nm,
        "provenance": "nameplate_and_cold_resistance_prior",
    }
    active = _active_vectors()
    all_descriptors: list[dict[str, object]] = []
    all_inputs: list[ExperimentInput] = []
    for role, run_id, vdc, shifted in (
        ("fit", f"fit-{seed}", 24.0, active),
        ("validation", f"validation-{seed + 1}", 22.0, active[1:] + active[:1]),
    ):
        n = steps_per_electrical_experiment
        descriptors_and_inputs = (
            _experiment(
                f"{role}-standstill",
                "standstill",
                role,
                run_id,
                _standstill_vectors(shifted, n),
                vdc=vdc,
                dt=5.0e-4,
            ),
            _experiment(
                f"{role}-free-run",
                "free_run",
                role,
                run_id,
                _free_run_vectors(shifted, n),
                vdc=vdc,
                dt=5.0e-4,
            ),
            _experiment(
                f"{role}-coast",
                "coast",
                role,
                run_id,
                [0] * 500,
                vdc=0.0,
                dt=0.01,
                initial_omega=20.0,
            ),
        )
        for descriptor, input_data in descriptors_and_inputs:
            all_descriptors.append(descriptor)
            all_inputs.append(input_data)

    noise_scales = (0.001, 0.001, 0.005)
    rng = np.random.default_rng(seed)
    true_load_torque = 0.003
    experiments: list[dict[str, object]] = []
    for descriptor, input_data in zip(all_descriptors, all_inputs):
        exact = simulate(truth, (input_data,), load_torque_nm=true_load_torque)
        count = input_data.v_alpha.size
        item = dict(descriptor)
        item["samples"] = {
            "t_s": (np.arange(1, count + 1, dtype=float) * input_data.dt).tolist(),
            "v_alpha_v": input_data.v_alpha.tolist(),
            "v_beta_v": input_data.v_beta.tolist(),
            "i_alpha_a": (exact.i_alpha + rng.normal(0.0, noise_scales[0], count)).tolist(),
            "i_beta_a": (exact.i_beta + rng.normal(0.0, noise_scales[1], count)).tolist(),
            "omega_rad_s": (exact.omega_m + rng.normal(0.0, noise_scales[2], count)).tolist(),
        }
        experiments.append(item)

    capture: dict[str, object] = {
        "schema": CAPTURE_SCHEMA,
        "motor_id": "synthetic-reference-motor",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "kind": "synthetic",
            "device_id": "alpha-beta-reference-model",
            "firmware_sha256": "not-applicable",
            "clock": "deterministic-model-time",
            "calibration": {"current": "exact", "voltage": "exact", "speed": "exact"},
        },
        "noise_std": {
            "i_alpha_a": noise_scales[0],
            "i_beta_a": noise_scales[1],
            "omega_rad_s": noise_scales[2],
        },
        "limits": {
            "max_abs_voltage_v": 30.0,
            "max_abs_current_a": truth.i_limit,
            "max_abs_speed_rad_s": 50.0,
        },
        "true_params": {**truth.as_dict(), "load_torque_nm": true_load_torque},
        "experiments": experiments,
    }
    return capture, prior


__all__ = ["make_synthetic_bundle"]

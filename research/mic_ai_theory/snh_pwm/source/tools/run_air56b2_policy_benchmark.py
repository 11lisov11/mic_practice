from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from random import Random
import statistics
import sys
from typing import Any, Iterable

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.air56b2_id_policy import Air56B2IdPolicy, FEATURE_KEYS, IdPolicyScaling
from models.air56b2_loss_thermal import (
    MotorThermalState,
    evaluate_operating_point,
    loss_params_from_fidelity_bundle,
    optimize_id_reference,
)


DEFAULT_INPUT = REPOSITORY_ROOT / "artifacts" / "air56b2_fidelity_bundle.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts" / "air56b2_policy_benchmark.json"
DEFAULT_CHECKPOINT = REPOSITORY_ROOT / "artifacts" / "air56b2_id_policy_actor.pt"
DEFAULT_BUNDLE = REPOSITORY_ROOT / "artifacts" / "air56b2_id_policy_bundle.json"
DEFAULT_LUT_JSON = REPOSITORY_ROOT / "artifacts" / "air56b2_id_ref_lut.json"
DEFAULT_LUT_HEADER = REPOSITORY_ROOT / "artifacts" / "air56b2_id_ref_lut.h"
MASTER_SEED = 560225
SPEED_FRACTIONS = (0.20, 0.40, 0.60, 0.80, 1.00)
TORQUE_FRACTIONS = (0.15, 0.35, 0.55, 0.75, 0.95)
THERMAL_CASES_C = ((30.0, 30.0), (90.0, 110.0))


@dataclass(frozen=True)
class PolicyCase:
    sample_index: int
    speed_pu: float
    torque_pu: float
    stator_temp_c: float
    rotor_temp_c: float
    fixed_id_a: float
    optimum_id_a: float
    optimum_loss_w: float
    fixed_loss_w: float


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _split_indices() -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    indices = list(range(256))
    Random(MASTER_SEED).shuffle(indices)
    return tuple(sorted(indices[:32])), tuple(sorted(indices[32:44])), tuple(sorted(indices[44:56]))


def _build_cases(bundle: dict[str, Any], sample_indices: Iterable[int]) -> list[PolicyCase]:
    derived = bundle["fidelity"]["derived_nameplate"]
    rated_speed = float(derived["rated_omega_rad_s"])
    rated_torque = float(derived["rated_torque_nm"])
    cases: list[PolicyCase] = []
    for sample_index in sample_indices:
        params, fixed_id = loss_params_from_fidelity_bundle(bundle, sample_index)
        for speed_pu in SPEED_FRACTIONS:
            for torque_pu in TORQUE_FRACTIONS:
                for stator_temp, rotor_temp in THERMAL_CASES_C:
                    thermal = MotorThermalState(stator_temp, rotor_temp)
                    speed = rated_speed * speed_pu
                    torque = rated_torque * torque_pu
                    fixed = evaluate_operating_point(
                        params,
                        speed_rad_s=speed,
                        torque_nm=torque,
                        id_a=fixed_id,
                        thermal_state=thermal,
                    )
                    optimum = optimize_id_reference(
                        params,
                        speed_rad_s=speed,
                        torque_nm=torque,
                        id_lower_a=0.12,
                        id_upper_a=1.86,
                        thermal_state=thermal,
                        grid_points=301,
                        candidate_id_values=(fixed_id,),
                    ).optimum
                    if not fixed.feasible or not optimum.feasible:
                        continue
                    cases.append(
                        PolicyCase(
                            sample_index=int(sample_index),
                            speed_pu=float(speed_pu),
                            torque_pu=float(torque_pu),
                            stator_temp_c=stator_temp,
                            rotor_temp_c=rotor_temp,
                            fixed_id_a=fixed_id,
                            optimum_id_a=optimum.id_a,
                            optimum_loss_w=optimum.total_loss_w,
                            fixed_loss_w=fixed.total_loss_w,
                        )
                    )
    return cases


def _features(cases: list[PolicyCase], scaling: IdPolicyScaling) -> np.ndarray:
    return np.asarray(
        [
            [
                case.speed_pu,
                case.torque_pu,
                scaling.normalize_temperature(case.stator_temp_c),
                scaling.normalize_temperature(case.rotor_temp_c),
            ]
            for case in cases
        ],
        dtype=np.float32,
    )


def _targets(cases: list[PolicyCase], scaling: IdPolicyScaling) -> np.ndarray:
    return np.asarray([scaling.normalize_id(case.optimum_id_a) for case in cases], dtype=np.float32)


def _seed_all(seed: int) -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True


def _train_policy(
    train_cases: list[PolicyCase],
    validation_cases: list[PolicyCase],
    scaling: IdPolicyScaling,
    *,
    device: str,
    seed: int,
    epochs: int = 800,
) -> tuple[dict[str, torch.Tensor], dict[str, Any]]:
    _seed_all(seed)
    model = Air56B2IdPolicy((48, 48)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2.0e-3, weight_decay=1.0e-5)
    x_train = torch.as_tensor(_features(train_cases, scaling), device=device)
    y_train = torch.as_tensor(_targets(train_cases, scaling), device=device)
    x_validation = torch.as_tensor(_features(validation_cases, scaling), device=device)
    y_validation = torch.as_tensor(_targets(validation_cases, scaling), device=device)
    best_loss = float("inf")
    best_epoch = -1
    best_state: dict[str, torch.Tensor] | None = None
    history: list[dict[str, float | int]] = []
    for epoch in range(int(epochs)):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        prediction = model(x_train)
        train_loss = torch.mean((prediction - y_train) ** 2)
        train_loss.backward()
        optimizer.step()
        model.eval()
        with torch.no_grad():
            validation_loss = torch.mean((model(x_validation) - y_validation) ** 2)
        value = float(validation_loss.item())
        if value < best_loss:
            best_loss = value
            best_epoch = epoch
            best_state = {key: tensor.detach().cpu().clone() for key, tensor in model.state_dict().items()}
        if epoch % 50 == 0 or epoch == epochs - 1:
            history.append(
                {
                    "epoch": epoch,
                    "train_mse": float(train_loss.item()),
                    "validation_mse": value,
                }
            )
    if best_state is None:
        raise RuntimeError("policy training did not produce a checkpoint")
    return best_state, {"best_epoch": best_epoch, "best_validation_mse": best_loss, "history": history}


def _state_sha256(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for key in sorted(state):
        tensor = state[key].detach().cpu().contiguous()
        digest.update(key.encode("utf-8"))
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(np.asarray(tensor.shape, dtype=np.int64).tobytes())
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def _evaluate_policy(
    state: dict[str, torch.Tensor],
    cases: list[PolicyCase],
    bundle: dict[str, Any],
    scaling: IdPolicyScaling,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    model = Air56B2IdPolicy((48, 48))
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        normalized = model(torch.as_tensor(_features(cases, scaling))).cpu().numpy()
    derived = bundle["fidelity"]["derived_nameplate"]
    rated_speed = float(derived["rated_omega_rad_s"])
    rated_torque = float(derived["rated_torque_nm"])
    rows: list[dict[str, Any]] = []
    id_errors: list[float] = []
    savings: list[float] = []
    gaps: list[float] = []
    constraint_violations = 0
    for case, prediction in zip(cases, normalized):
        id_ref = scaling.denormalize_id(float(prediction))
        params, _ = loss_params_from_fidelity_bundle(bundle, case.sample_index)
        result = evaluate_operating_point(
            params,
            speed_rad_s=rated_speed * case.speed_pu,
            torque_nm=rated_torque * case.torque_pu,
            id_a=id_ref,
            thermal_state=MotorThermalState(case.stator_temp_c, case.rotor_temp_c),
        )
        id_error = abs(id_ref - case.optimum_id_a)
        id_errors.append(id_error)
        if not result.feasible:
            constraint_violations += 1
        saving = 100.0 * (case.fixed_loss_w - result.total_loss_w) / max(case.fixed_loss_w, 1e-12)
        gap = 100.0 * (result.total_loss_w - case.optimum_loss_w) / max(case.optimum_loss_w, 1e-12)
        savings.append(saving)
        gaps.append(gap)
        rows.append(
            {
                **asdict(case),
                "policy_id_a": id_ref,
                "id_abs_error_a": id_error,
                "policy_loss_w": result.total_loss_w,
                "policy_feasible": result.feasible,
                "loss_saving_vs_fixed_pct": saving,
                "optimality_gap_pct": gap,
            }
        )
    summary = {
        "case_count": len(rows),
        "id_mae_a": statistics.fmean(id_errors),
        "id_max_error_a": max(id_errors),
        "loss_saving_vs_fixed_pct_mean": statistics.fmean(savings),
        "loss_saving_vs_fixed_pct_median": statistics.median(savings),
        "optimality_gap_pct_mean": statistics.fmean(gaps),
        "optimality_gap_pct_median": statistics.median(gaps),
        "optimality_gap_pct_max": max(gaps),
        "constraint_violation_count": constraint_violations,
    }
    return summary, rows


def _build_lut(bundle: dict[str, Any], scaling: IdPolicyScaling) -> dict[str, Any]:
    speed_permille = tuple(range(200, 1001, 100))
    torque_permille = tuple(range(0, 1001, 100))
    temperatures_c = (30, 80, 120)
    derived = bundle["fidelity"]["derived_nameplate"]
    rated_speed = float(derived["rated_omega_rad_s"])
    rated_torque = float(derived["rated_torque_nm"])
    params, fixed_id = loss_params_from_fidelity_bundle(bundle, 128)
    values: list[list[list[int]]] = []
    for temperature in temperatures_c:
        temperature_plane: list[list[int]] = []
        for speed_value in speed_permille:
            speed_row: list[int] = []
            for torque_value in torque_permille:
                optimum = optimize_id_reference(
                    params,
                    speed_rad_s=rated_speed * speed_value / 1000.0,
                    torque_nm=rated_torque * torque_value / 1000.0,
                    id_lower_a=scaling.id_lower_a,
                    id_upper_a=scaling.id_upper_a,
                    thermal_state=MotorThermalState(float(temperature), float(temperature)),
                    grid_points=501,
                    candidate_id_values=(fixed_id,),
                ).optimum
                speed_row.append(int(round(1000.0 * optimum.id_a)))
            temperature_plane.append(speed_row)
        values.append(temperature_plane)
    return {
        "schema": "air56b2-id-ref-lut-v1",
        "status": "simulation_only",
        "hardware_release_ready": False,
        "units": {"speed": "permille_rated", "torque": "permille_rated", "temperature": "degC", "id_ref": "mA_peak"},
        "speed_permille": list(speed_permille),
        "torque_permille": list(torque_permille),
        "temperatures_c": list(temperatures_c),
        "id_ref_ma": values,
    }


def _lut_header(lut: dict[str, Any]) -> str:
    def c_array(values: list[int]) -> str:
        return "{" + ", ".join(str(int(value)) for value in values) + "}"

    planes = []
    for plane in lut["id_ref_ma"]:
        planes.append("  {\n" + ",\n".join("    " + c_array(row) for row in plane) + "\n  }")
    return f"""#ifndef AIR56B2_ID_REF_LUT_H
#define AIR56B2_ID_REF_LUT_H

#include <stdint.h>

/* Simulation-only classical optimum. Hardware release is intentionally disabled. */
#define AIR56B2_ID_LUT_HARDWARE_RELEASE_READY 0
#define AIR56B2_ID_LUT_TEMP_COUNT {len(lut['temperatures_c'])}
#define AIR56B2_ID_LUT_SPEED_COUNT {len(lut['speed_permille'])}
#define AIR56B2_ID_LUT_TORQUE_COUNT {len(lut['torque_permille'])}

static const uint16_t air56b2_id_lut_temperature_c[AIR56B2_ID_LUT_TEMP_COUNT] = {c_array(lut['temperatures_c'])};
static const uint16_t air56b2_id_lut_speed_permille[AIR56B2_ID_LUT_SPEED_COUNT] = {c_array(lut['speed_permille'])};
static const uint16_t air56b2_id_lut_torque_permille[AIR56B2_ID_LUT_TORQUE_COUNT] = {c_array(lut['torque_permille'])};
static const uint16_t air56b2_id_ref_ma[AIR56B2_ID_LUT_TEMP_COUNT][AIR56B2_ID_LUT_SPEED_COUNT][AIR56B2_ID_LUT_TORQUE_COUNT] = {{
{',\n'.join(planes)}
}};

#endif
"""


def run_benchmark(
    input_path: Path,
    output_path: Path,
    checkpoint_path: Path,
    bundle_path: Path,
    lut_json_path: Path,
    lut_header_path: Path,
    *,
    device: str,
) -> dict[str, Any]:
    source_bundle = json.loads(input_path.read_text(encoding="utf-8"))
    if source_bundle.get("status") != "PASS" or bool(source_bundle.get("hardware_claim", True)):
        raise ValueError("AIR56B2 policy input must be a simulation-only PASS bundle")
    train_indices, validation_indices, holdout_indices = _split_indices()
    if set(train_indices) & set(validation_indices) or set(train_indices) & set(holdout_indices) or set(validation_indices) & set(holdout_indices):
        raise AssertionError("policy splits must be pairwise disjoint")
    scaling = IdPolicyScaling()
    train_cases = _build_cases(source_bundle, train_indices)
    validation_cases = _build_cases(source_bundle, validation_indices)
    holdout_cases = _build_cases(source_bundle, holdout_indices)
    resolved_device = "cuda" if device == "auto" and torch.cuda.is_available() else ("cpu" if device == "auto" else device)
    if resolved_device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    state_a, training = _train_policy(
        train_cases,
        validation_cases,
        scaling,
        device=resolved_device,
        seed=MASTER_SEED,
    )
    state_b, _ = _train_policy(
        train_cases,
        validation_cases,
        scaling,
        device=resolved_device,
        seed=MASTER_SEED,
    )
    state_hash_a = _state_sha256(state_a)
    state_hash_b = _state_sha256(state_b)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(state_a, checkpoint_path)
    holdout_summary, holdout_rows = _evaluate_policy(
        state_a,
        holdout_cases,
        source_bundle,
        scaling,
    )
    lut = _build_lut(source_bundle, scaling)
    lut_json_path.write_text(json.dumps(lut, indent=2), encoding="utf-8")
    lut_header_path.write_text(_lut_header(lut), encoding="ascii")
    gates = {
        "source_bundle_passed": True,
        "splits_pairwise_disjoint": True,
        "checkpoint_replay_bitwise_identical": state_hash_a == state_hash_b,
        "holdout_constraint_violations_zero": holdout_summary["constraint_violation_count"] == 0,
        "holdout_id_mae_below_0_08_a": holdout_summary["id_mae_a"] < 0.08,
        "holdout_median_loss_saving_positive": holdout_summary["loss_saving_vs_fixed_pct_median"] > 0.0,
        "holdout_median_optimality_gap_below_5pct": holdout_summary["optimality_gap_pct_median"] < 5.0,
        "lut_hardware_release_disabled": lut["hardware_release_ready"] is False,
        "no_hardware_claim": True,
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    result = {
        "schema": "air56b2-id-policy-benchmark-v1",
        "status": status,
        "hardware_claim": False,
        "hardware_identified": False,
        "hardware_release_ready": False,
        "input": {"path": str(input_path.resolve()), "sha256": _sha256(input_path)},
        "master_seed": MASTER_SEED,
        "device": resolved_device,
        "torch_version": str(torch.__version__),
        "feature_keys": list(FEATURE_KEYS),
        "scaling": asdict(scaling),
        "splits": {
            "train_sample_indices": list(train_indices),
            "validation_sample_indices": list(validation_indices),
            "holdout_sample_indices": list(holdout_indices),
            "train_case_count": len(train_cases),
            "validation_case_count": len(validation_cases),
            "holdout_case_count": len(holdout_cases),
        },
        "training": training,
        "checkpoint": {
            "path": str(checkpoint_path.resolve()),
            "state_sha256": state_hash_a,
            "replay_state_sha256": state_hash_b,
            "architecture": {"type": "MLP_tanh_sigmoid", "hidden_sizes": [48, 48]},
        },
        "holdout_summary": holdout_summary,
        "gates": gates,
        "lut": {
            "json": str(lut_json_path.resolve()),
            "json_sha256": _sha256(lut_json_path),
            "header": str(lut_header_path.resolve()),
            "header_sha256": _sha256(lut_header_path),
        },
        "limitations": [
            "The actor is supervised distillation of a simulation-only classical loss optimum, not a hardware-trained policy.",
            "Holdout separation proves software generalization across prior samples, not generalization to the physical motor.",
            "Torque command and winding temperatures are assumed available or estimated; hardware observers are still required.",
            "The generated LUT is not enabled for hardware release and must pass current, voltage, thermal, and fallback supervision on the bench.",
        ],
        "holdout_rows": holdout_rows,
    }
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    checkpoint_bundle = {
        "schema": "air56b2-id-policy-checkpoint-bundle-v1",
        "status": "simulation_only",
        "hardware_release_ready": False,
        "checkpoint": result["checkpoint"],
        "feature_keys": result["feature_keys"],
        "scaling": result["scaling"],
        "splits": result["splits"],
        "benchmark": {"path": str(output_path.resolve()), "sha256": _sha256(output_path)},
        "source": result["input"],
        "gates": gates,
    }
    bundle_path.write_text(json.dumps(checkpoint_bundle, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and holdout-test AIR56B2 id policy")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--lut-json", type=Path, default=DEFAULT_LUT_JSON)
    parser.add_argument("--lut-header", type=Path, default=DEFAULT_LUT_HEADER)
    parser.add_argument("--device", type=str, default="auto")
    args = parser.parse_args()
    result = run_benchmark(
        args.input.resolve(),
        args.output.resolve(),
        args.checkpoint.resolve(),
        args.bundle.resolve(),
        args.lut_json.resolve(),
        args.lut_header.resolve(),
        device=args.device,
    )
    print(json.dumps({"status": result["status"], **result["holdout_summary"]}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

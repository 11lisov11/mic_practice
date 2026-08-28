from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from random import Random
import statistics
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.air56b2_extremum_search import bounded_extremum_search
from models.air56b2_loss_thermal import (
    MotorThermalState,
    evaluate_operating_point,
    loss_params_from_fidelity_bundle,
)


DEFAULT_FIDELITY = REPOSITORY_ROOT / "artifacts" / "air56b2_fidelity_bundle.json"
DEFAULT_POLICY = REPOSITORY_ROOT / "artifacts" / "air56b2_policy_benchmark.json"
DEFAULT_LUT = REPOSITORY_ROOT / "artifacts" / "air56b2_id_ref_lut.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts" / "air56b2_common_control_benchmark.json"
MASTER_SEED = 560225
BOOTSTRAP_REPLICATES = 2000


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _bracket(grid: list[float], value: float) -> tuple[int, int, float]:
    if not grid:
        raise ValueError("interpolation grid cannot be empty")
    if value <= grid[0]:
        return 0, 0, 0.0
    if value >= grid[-1]:
        last = len(grid) - 1
        return last, last, 0.0
    for upper in range(1, len(grid)):
        if value <= grid[upper]:
            lower = upper - 1
            fraction = (value - grid[lower]) / (grid[upper] - grid[lower])
            return lower, upper, fraction
    raise AssertionError("unreachable interpolation bracket")


def interpolate_lut_id_a(
    lut: dict[str, Any],
    *,
    speed_pu: float,
    torque_pu: float,
    temperature_c: float,
) -> float:
    speeds = [float(value) / 1000.0 for value in lut["speed_permille"]]
    torques = [float(value) / 1000.0 for value in lut["torque_permille"]]
    temperatures = [float(value) for value in lut["temperatures_c"]]
    values = lut["id_ref_ma"]
    s0, s1, sf = _bracket(speeds, float(speed_pu))
    q0, q1, qf = _bracket(torques, float(torque_pu))
    t0, t1, tf = _bracket(temperatures, float(temperature_c))

    def at(t_index: int, s_index: int, q_index: int) -> float:
        return float(values[t_index][s_index][q_index]) / 1000.0

    def blend(a: float, b: float, fraction: float) -> float:
        return a + fraction * (b - a)

    planes: list[float] = []
    for t_index in (t0, t1):
        lower_speed = blend(at(t_index, s0, q0), at(t_index, s0, q1), qf)
        upper_speed = blend(at(t_index, s1, q0), at(t_index, s1, q1), qf)
        planes.append(blend(lower_speed, upper_speed, sf))
    return blend(planes[0], planes[1], tf)


def _percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("cannot calculate percentile of empty data")
    position = (len(sorted_values) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(sorted_values[lower])
    fraction = position - lower
    return float(sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower]))


def _cluster_bootstrap_ci(
    rows: list[dict[str, Any]],
    value_key: str,
    statistic: Callable[[list[float]], float],
    *,
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> list[float]:
    clusters: dict[int, list[float]] = {}
    for row in rows:
        clusters.setdefault(int(row["sample_index"]), []).append(float(row[value_key]))
    cluster_ids = sorted(clusters)
    if len(cluster_ids) < 2:
        raise ValueError("cluster bootstrap needs at least two independent parameter samples")
    rng = Random(seed)
    values: list[float] = []
    for _ in range(int(replicates)):
        sample: list[float] = []
        for _ in cluster_ids:
            sample.extend(clusters[rng.choice(cluster_ids)])
        values.append(float(statistic(sample)))
    values.sort()
    return [_percentile(values, 0.025), _percentile(values, 0.975)]


def _method_summary(
    rows: list[dict[str, Any]],
    *,
    method_key: str,
    seed_offset: int,
) -> dict[str, Any]:
    loss_key = f"{method_key}_loss_w"
    feasible_key = f"{method_key}_feasible"
    savings: list[float] = []
    gaps: list[float] = []
    method_rows: list[dict[str, Any]] = []
    for row in rows:
        fixed_loss = float(row["fixed_loss_w"])
        optimum_loss = float(row["classical_optimum_loss_w"])
        method_loss = float(row[loss_key])
        saving = 100.0 * (fixed_loss - method_loss) / max(fixed_loss, 1e-12)
        gap = 100.0 * (method_loss - optimum_loss) / max(optimum_loss, 1e-12)
        savings.append(saving)
        gaps.append(gap)
        method_rows.append(
            {
                "sample_index": int(row["sample_index"]),
                "saving_pct": saving,
                "gap_pct": gap,
            }
        )
    mean = lambda values: statistics.fmean(values)
    median = lambda values: statistics.median(values)
    return {
        "case_count": len(rows),
        "constraint_violation_count": sum(not bool(row[feasible_key]) for row in rows),
        "worse_than_fixed_count": sum(value < -1e-9 for value in savings),
        "saving_vs_fixed_pct": {
            "mean": mean(savings),
            "mean_cluster_bootstrap_95_ci": _cluster_bootstrap_ci(
                method_rows, "saving_pct", mean, seed=MASTER_SEED + seed_offset
            ),
            "median": median(savings),
            "median_cluster_bootstrap_95_ci": _cluster_bootstrap_ci(
                method_rows, "saving_pct", median, seed=MASTER_SEED + 100 + seed_offset
            ),
            "minimum": min(savings),
            "maximum": max(savings),
        },
        "optimality_gap_pct": {
            "mean": mean(gaps),
            "mean_cluster_bootstrap_95_ci": _cluster_bootstrap_ci(
                method_rows, "gap_pct", mean, seed=MASTER_SEED + 200 + seed_offset
            ),
            "median": median(gaps),
            "median_cluster_bootstrap_95_ci": _cluster_bootstrap_ci(
                method_rows, "gap_pct", median, seed=MASTER_SEED + 300 + seed_offset
            ),
            "minimum": min(gaps),
            "maximum": max(gaps),
        },
    }


def run_benchmark(
    fidelity_path: Path,
    policy_path: Path,
    lut_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    fidelity = _read(fidelity_path)
    policy = _read(policy_path)
    lut = _read(lut_path)
    if fidelity.get("status") != "PASS" or fidelity.get("hardware_claim") is not False:
        raise ValueError("fidelity bundle must be a simulation-only PASS artifact")
    if policy.get("status") != "PASS" or policy.get("hardware_claim") is not False:
        raise ValueError("policy benchmark must be a simulation-only PASS artifact")
    if lut.get("status") != "simulation_only" or lut.get("hardware_release_ready") is not False:
        raise ValueError("LUT must remain disabled for hardware release")

    source_rows = policy.get("holdout_rows", [])
    if len(source_rows) != int(policy.get("splits", {}).get("holdout_case_count", -1)):
        raise ValueError("policy holdout row count is inconsistent")
    derived = fidelity["fidelity"]["derived_nameplate"]
    rated_speed = float(derived["rated_omega_rad_s"])
    rated_torque = float(derived["rated_torque_nm"])
    rows: list[dict[str, Any]] = []
    search_evaluations: list[int] = []

    for source in source_rows:
        sample_index = int(source["sample_index"])
        params, fixed_id = loss_params_from_fidelity_bundle(fidelity, sample_index)
        speed = rated_speed * float(source["speed_pu"])
        torque = rated_torque * float(source["torque_pu"])
        thermal = MotorThermalState(
            float(source["stator_temp_c"]),
            float(source["rotor_temp_c"]),
        )
        fixed = evaluate_operating_point(
            params,
            speed_rad_s=speed,
            torque_nm=torque,
            id_a=fixed_id,
            thermal_state=thermal,
        )
        classical = evaluate_operating_point(
            params,
            speed_rad_s=speed,
            torque_nm=torque,
            id_a=float(source["optimum_id_a"]),
            thermal_state=thermal,
        )
        policy_result = evaluate_operating_point(
            params,
            speed_rad_s=speed,
            torque_nm=torque,
            id_a=float(source["policy_id_a"]),
            thermal_state=thermal,
        )
        search = bounded_extremum_search(
            params,
            speed_rad_s=speed,
            torque_nm=torque,
            initial_id_a=fixed_id,
            id_lower_a=0.12,
            id_upper_a=1.86,
            thermal_state=thermal,
        )
        raw_lut_id = interpolate_lut_id_a(
            lut,
            speed_pu=float(source["speed_pu"]),
            torque_pu=float(source["torque_pu"]),
            temperature_c=0.5 * (thermal.stator_temp_c + thermal.rotor_temp_c),
        )
        raw_lut = evaluate_operating_point(
            params,
            speed_rad_s=speed,
            torque_nm=torque,
            id_a=raw_lut_id,
            thermal_state=thermal,
        )
        guarded_lut = raw_lut if raw_lut.feasible and raw_lut.total_loss_w <= fixed.total_loss_w else fixed
        search_evaluations.append(search.evaluated_points)
        rows.append(
            {
                "sample_index": sample_index,
                "speed_pu": float(source["speed_pu"]),
                "torque_pu": float(source["torque_pu"]),
                "stator_temp_c": thermal.stator_temp_c,
                "rotor_temp_c": thermal.rotor_temp_c,
                "fixed_id_a": fixed.id_a,
                "fixed_loss_w": fixed.total_loss_w,
                "fixed_feasible": fixed.feasible,
                "classical_optimum_id_a": classical.id_a,
                "classical_optimum_loss_w": classical.total_loss_w,
                "classical_optimum_feasible": classical.feasible,
                "neural_policy_id_a": policy_result.id_a,
                "neural_policy_loss_w": policy_result.total_loss_w,
                "neural_policy_feasible": policy_result.feasible,
                "extremum_search_id_a": search.optimum.id_a,
                "extremum_search_loss_w": search.optimum.total_loss_w,
                "extremum_search_feasible": search.optimum.feasible,
                "extremum_search_evaluations": search.evaluated_points,
                "guarded_lut_raw_id_a": raw_lut.id_a,
                "guarded_lut_fallback_used": guarded_lut is fixed,
                "guarded_lut_id_a": guarded_lut.id_a,
                "guarded_lut_loss_w": guarded_lut.total_loss_w,
                "guarded_lut_feasible": guarded_lut.feasible,
            }
        )

    methods = {
        "fixed": _method_summary(rows, method_key="fixed", seed_offset=1),
        "classical_optimum": _method_summary(rows, method_key="classical_optimum", seed_offset=2),
        "neural_policy": _method_summary(rows, method_key="neural_policy", seed_offset=3),
        "extremum_search": _method_summary(rows, method_key="extremum_search", seed_offset=4),
        "guarded_lut": _method_summary(rows, method_key="guarded_lut", seed_offset=5),
    }
    policy_reference = policy["holdout_summary"]
    reproduced_policy_median = methods["neural_policy"]["saving_vs_fixed_pct"]["median"]
    reproduced_policy_gap = methods["neural_policy"]["optimality_gap_pct"]["median"]
    unique_samples = sorted({int(row["sample_index"]) for row in rows})
    gates = {
        "exact_policy_holdout_reused": len(rows) == 600 and len(unique_samples) == 12,
        "policy_median_saving_reproduced": math.isclose(
            reproduced_policy_median,
            float(policy_reference["loss_saving_vs_fixed_pct_median"]),
            rel_tol=0.0,
            abs_tol=1e-9,
        ),
        "policy_median_gap_reproduced": math.isclose(
            reproduced_policy_gap,
            float(policy_reference["optimality_gap_pct_median"]),
            rel_tol=0.0,
            abs_tol=1e-9,
        ),
        "all_methods_have_zero_constraint_violations": all(
            summary["constraint_violation_count"] == 0 for summary in methods.values()
        ),
        "extremum_search_never_worse_than_fixed": all(
            float(row["extremum_search_loss_w"]) <= float(row["fixed_loss_w"]) + 1e-9
            for row in rows
        ),
        "guarded_lut_never_worse_than_fixed": all(
            float(row["guarded_lut_loss_w"]) <= float(row["fixed_loss_w"]) + 1e-9
            for row in rows
        ),
        "classical_optimum_not_beaten_beyond_grid_tolerance": all(
            float(row["classical_optimum_loss_w"])
            <= float(row[method + "_loss_w"]) * 1.0005 + 1e-9
            for row in rows
            for method in ("neural_policy", "extremum_search", "guarded_lut")
        ),
        "hardware_release_disabled": True,
        "no_hardware_claim": True,
    }
    payload = {
        "schema": "air56b2-common-control-benchmark-v1",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "hardware_claim": False,
        "hardware_identified": False,
        "hardware_release_ready": False,
        "master_seed": MASTER_SEED,
        "bootstrap": {
            "method": "paired_cluster_bootstrap_by_f1_parameter_sample",
            "replicates": BOOTSTRAP_REPLICATES,
            "confidence_level": 0.95,
            "cluster_count": len(unique_samples),
        },
        "inputs": {
            "fidelity_bundle": {"path": str(fidelity_path.resolve()), "sha256": _sha256(fidelity_path)},
            "policy_benchmark": {"path": str(policy_path.resolve()), "sha256": _sha256(policy_path)},
            "id_ref_lut": {"path": str(lut_path.resolve()), "sha256": _sha256(lut_path)},
        },
        "case_count": len(rows),
        "sample_indices": unique_samples,
        "methods": methods,
        "extremum_search": {
            "mean_loss_evaluations": statistics.fmean(search_evaluations),
            "maximum_loss_evaluations": max(search_evaluations),
            "contract": "bounded_derivative_free_search_over_measurable_loss_proxy",
        },
        "guarded_lut": {
            "fallback_count": sum(bool(row["guarded_lut_fallback_used"]) for row in rows),
            "fallback_contract": "use_fixed_flux_when_lut_candidate_is_infeasible_or_worse",
        },
        "gates": gates,
        "interpretation": (
            "All methods are paired on the exact same disjoint 600-case holdout. "
            "The classical optimum is the simulation reference; the neural policy distils it "
            "and is not claimed to outperform it. The extremum-search result assumes an "
            "observable settled loss proxy and therefore is not yet a hardware result."
        ),
        "limitations": [
            "All confidence intervals quantify variation across the 12 simulated parameter samples, not physical motors.",
            "The bounded extremum search uses the simulated total-loss value as an oracle measurement proxy.",
            "The guarded LUT is generated from one central prior sample and falls back to fixed flux when needed.",
            "No result authorizes energizing the inverter before staged hardware identification and protection tests.",
        ],
        "rows": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare AIR56B2 control strategies on one holdout")
    parser.add_argument("--fidelity", type=Path, default=DEFAULT_FIDELITY)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--lut", type=Path, default=DEFAULT_LUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_benchmark(
        args.fidelity.resolve(),
        args.policy.resolve(),
        args.lut.resolve(),
        args.output.resolve(),
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "case_count": result["case_count"],
                "methods": result["methods"],
            },
            indent=2,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

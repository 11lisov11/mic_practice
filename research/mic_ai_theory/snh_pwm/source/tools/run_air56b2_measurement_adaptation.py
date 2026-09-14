from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
import hashlib
import gzip
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE_FILES = [Path(__file__), ROOT / "models/air56b2_measurement_context.py",
                ROOT / "control/air56b2_measured_loss_fit.py", ROOT / "models/air56b2_loss_thermal.py"]
SOURCE_HASHES = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in SOURCE_FILES}

from control.air56b2_measured_loss_fit import (
    MeasuredLossFitConfig, ProbeMeasurement, fit_measured_loss_reference,
)
from models.air56b2_loss_thermal import (
    Air56B2LossModelParams, LossBreakdown, MotorThermalState,
    evaluate_operating_point, loss_params_from_fidelity_bundle,
)
from models.air56b2_measurement_context import (
    FEATURE_KEYS, MeasurementContextPolicy, MeasurementProtocol,
    accept_verification, context_features, window_rejection_reason,
)


SPLIT_SEED = 560908
TRAINING_SEEDS = (560909, 560910, 560911)
EVALUATION_REALIZATIONS = (10, 11)
SPEEDS_PU = (0.25, 0.60, 0.95)
TORQUES_PU = (0.20, 0.45, 0.70, 0.95)
THERMAL_CASES = ((30.0, 35.0), (85.0, 105.0))


@dataclass(frozen=True)
class Condition:
    name: str
    power_noise_w: float = 0.0
    current_noise_a: float = 0.0
    voltage_noise_v: float = 0.0
    speed_noise_rad_s: float = 0.0
    power_gain_error: float = 0.0
    power_offset_w: float = 0.0
    excitation_bias_w_per_a: float = 0.0
    load_drift_fraction: float = 0.0
    ood: bool = False


CONDITIONS = (
    Condition("clean"),
    Condition("measurement_noise", 0.75, 0.01, 0.3, 0.5),
    Condition("systematic_power_bias", 0.75, 0.01, 0.3, 0.5, 0.03, 10.0, 12.0),
    Condition("load_drift", 0.75, 0.01, 0.3, 0.5, load_drift_fraction=0.30),
    Condition("ood_parameters", 0.75, 0.01, 0.3, 0.5, ood=True),
)


@dataclass
class Case:
    sample_index: int
    case_index: int
    speed_rad_s: float
    shaft_torque_nm: float
    thermal: MotorThermalState
    params: Air56B2LossModelParams
    probes_true: list[LossBreakdown]
    probe_power_w: list[float]
    fixed: LossBreakdown
    optimum: LossBreakdown | None


def split_indices(count: int, train: int, validation: int, holdout: int, ood: int) -> dict[str, list[int]]:
    sizes = (train, validation, holdout, ood)
    if min(sizes) < 2 or sum(sizes) > count:
        raise ValueError("four disjoint splits of at least two motors are required")
    indices = np.random.default_rng(SPLIT_SEED).permutation(count).tolist()
    result = {}
    offset = 0
    for name, size in zip(("train", "validation", "holdout", "ood"), sizes):
        result[name] = sorted(indices[offset:offset + size])
        offset += size
    return result


def evaluate_shaft_point(
    params: Air56B2LossModelParams, speed: float, shaft_torque: float,
    id_a: float, thermal: MotorThermalState,
) -> LossBreakdown:
    if not all(math.isfinite(v) for v in (speed, shaft_torque, id_a)) or speed < 0 or shaft_torque < 0 or id_a <= 0:
        raise ValueError("this steady-state study covers positive motoring only")
    # Legacy evaluate_operating_point uses electromagnetic torque in its iq equation.
    friction_torque = params.viscous_b_nms * speed + params.coulomb_friction_nm
    point = evaluate_operating_point(
        params, speed_rad_s=speed, torque_nm=shaft_torque + friction_torque,
        id_a=id_a, thermal_state=thermal,
    )
    lm, lr = point.effective_lm_h, point.effective_lm_h + params.llr_h
    rs = params.rs_ref_ohm * (1.0 + params.stator_temp_coeff_per_c *
                             (thermal.stator_temp_c - params.reference_temp_c))
    leakage = params.lls_h + lm * params.llr_h / lr
    omega_e = 2.0 * math.pi * point.electrical_frequency_hz
    vd = rs * id_a - omega_e * leakage * point.iq_a
    vq = rs * point.iq_a + omega_e * (leakage * id_a + lm / lr * point.flux_wb)
    voltage = math.hypot(vd, vq)
    return replace(point, phase_voltage_peak_v=voltage,
                   constraint_margin_voltage_v=params.phase_voltage_limit_v - voltage,
                   feasible=point.constraint_margin_current_a >= 0 and voltage <= params.phase_voltage_limit_v)


def _case_params(bundle: dict, index: int, ood: bool) -> Air56B2LossModelParams:
    params, _ = loss_params_from_fidelity_bundle(bundle, index)
    if ood:
        params = replace(
            params, rs_ref_ohm=1.5 * params.rs_ref_ohm,
            rr_ref_ohm=1.5 * params.rr_ref_ohm,
            saturation_knee_flux_wb=0.8 * params.saturation_knee_flux_wb,
            rated_core_loss_w=1.4 * params.rated_core_loss_w,
            vdc_v=0.85 * params.vdc_v,
            phase_voltage_limit_v=0.85 * params.phase_voltage_limit_v,
        )
    return params


def build_cases(bundle: dict, indices: list[int], protocol: MeasurementProtocol,
                condition: Condition, *, grid_points: int) -> list[Case]:
    derived = bundle["fidelity"]["derived_nameplate"]
    cases = []
    id_grid = np.unique(np.r_[np.linspace(protocol.low_id_a, protocol.high_id_a, grid_points),
                              protocol.center_id_a])
    for index in indices:
        params = _case_params(bundle, index, condition.ood)
        for speed_pu in SPEEDS_PU:
            for torque_pu in TORQUES_PU:
                for temperatures in THERMAL_CASES:
                    speed = float(derived["rated_omega_rad_s"]) * speed_pu
                    torque = float(derived["rated_torque_nm"]) * torque_pu
                    thermal = MotorThermalState(*temperatures)
                    points, powers = [], []
                    for probe_index, id_a in enumerate(protocol.sequence):
                        # End at the scored load; earlier probes see a gradual ramp.
                        probe_torque = torque * (1.0 - condition.load_drift_fraction * (1.0 - probe_index / 3.0))
                        point = evaluate_shaft_point(params, speed, probe_torque, id_a, thermal)
                        points.append(point)
                        powers.append(speed * probe_torque + point.total_loss_w)
                    fixed = evaluate_shaft_point(params, speed, torque, protocol.center_id_a, thermal)
                    candidates = [evaluate_shaft_point(params, speed, torque, float(x), thermal) for x in id_grid]
                    feasible = [point for point in candidates if point.feasible]
                    optimum = min(feasible, key=lambda p: p.total_loss_w) if feasible else None
                    cases.append(Case(index, len(cases), speed, torque, thermal,
                                      params, points, powers, fixed, optimum))
    return cases


def _rng(case: Case, realization: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([SPLIT_SEED, case.sample_index,
                                                        case.case_index, realization]))


def measure(point: LossBreakdown, input_power_w: float, condition: Condition,
            protocol: MeasurementProtocol, noise: np.ndarray) -> ProbeMeasurement:
    return ProbeMeasurement(
        id_a=point.id_a,
        power_w=(input_power_w * (1.0 + condition.power_gain_error)
                 + condition.power_offset_w
                 + condition.excitation_bias_w_per_a * (point.id_a - protocol.center_id_a)
                 + condition.power_noise_w * float(noise[0])),
        current_peak_a=max(0.0, point.phase_current_peak_a + condition.current_noise_a * float(noise[1])),
        voltage_peak_v=max(0.0, point.phase_voltage_peak_v + condition.voltage_noise_v * float(noise[2])),
    )


def observe(case: Case, condition: Condition, protocol: MeasurementProtocol, realization: int
            ) -> tuple[list[ProbeMeasurement], np.ndarray, np.ndarray, MeasurementProtocol]:
    noise = _rng(case, realization).normal(size=(6, 3))
    measured_bus_v = case.params.vdc_v + condition.voltage_noise_v * float(noise[5, 1])
    measured_protocol = replace(protocol, voltage_limit_v=min(
        protocol.voltage_limit_v, 0.95 * measured_bus_v / math.sqrt(3.0)))
    probes = [measure(point, power, condition, protocol, noise[i])
              for i, (point, power) in enumerate(zip(case.probes_true, case.probe_power_w))]
    speed = case.speed_rad_s + condition.speed_noise_rad_s * noise[5, 0]
    return probes, context_features(probes, float(speed), measured_protocol), noise[4], measured_protocol


def training_arrays(cases: list[Case], protocol: MeasurementProtocol) -> tuple[np.ndarray, np.ndarray, dict]:
    xs, ys = [], []
    exclusions = Counter()
    for case in cases:
        if case.optimum is None or not case.fixed.feasible:
            exclusions["no_feasible_reference"] += 1
            continue
        if any(not point.feasible for point in case.probes_true):
            exclusions["infeasible_training_probe"] += 1
            continue
        for realization, condition in enumerate(CONDITIONS[:2]):
            probes, features, _, measured_protocol = observe(case, condition, protocol, realization)
            if window_rejection_reason(probes, measured_protocol):
                exclusions["measurement_gate"] += 1
                continue
            xs.append(features)
            ys.append((case.optimum.id_a - protocol.low_id_a) / (protocol.high_id_a - protocol.low_id_a))
    if not xs:
        raise ValueError("no trainable measurement windows")
    return np.asarray(xs), np.asarray(ys, dtype=np.float32), dict(exclusions)


def train_policy(x_train: np.ndarray, y_train: np.ndarray, x_validation: np.ndarray,
                 y_validation: np.ndarray, *, seed: int, epochs: int, device: str,
                 single_probe: bool = False) -> tuple[dict, dict]:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    model = MeasurementContextPolicy(single_probe=single_probe).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.002, weight_decay=1e-5)
    xt, yt = torch.as_tensor(x_train, device=device), torch.as_tensor(y_train, device=device)
    xv, yv = torch.as_tensor(x_validation, device=device), torch.as_tensor(y_validation, device=device)
    best, best_loss, best_epoch = None, float("inf"), -1
    for epoch in range(epochs):
        optimizer.zero_grad(set_to_none=True)
        loss = ((model(xt) - yt) ** 2).mean()
        loss.backward()
        optimizer.step()
        with torch.no_grad():
            val = float(((model(xv) - yv) ** 2).mean().item())
        if val < best_loss:
            best_loss, best_epoch = val, epoch
            best = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    if best is None:
        raise ValueError("epochs must be positive")
    return best, {"seed": seed, "best_epoch": best_epoch, "validation_mse": best_loss,
                  "epochs": epochs, "single_probe": single_probe}


def state_digest(state: dict) -> str:
    digest = hashlib.sha256()
    for key, tensor in sorted(state.items()):
        digest.update(key.encode("utf-8"))
        digest.update(str((str(tensor.dtype), tuple(tensor.shape))).encode("ascii"))
        digest.update(tensor.contiguous().numpy().tobytes())
    return digest.hexdigest()


def _predict(state: dict, features: np.ndarray, protocol: MeasurementProtocol, *, single_probe: bool) -> np.ndarray:
    model = MeasurementContextPolicy(single_probe=single_probe)
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        out = model(torch.as_tensor(features, dtype=torch.float32)).numpy()
    return protocol.low_id_a + out * (protocol.high_id_a - protocol.low_id_a)


def score_cases(cases: list[Case], condition: Condition, protocol: MeasurementProtocol,
                states: dict[str, dict], *, realization: int, seed: int) -> list[dict]:
    observed = [observe(case, condition, protocol, realization) for case in cases]
    features = np.asarray([item[1] for item in observed])
    predictions = {
        "neural_context": _predict(states["context"], features, protocol, single_probe=False),
        "neural_single": _predict(states["single"], features, protocol, single_probe=True),
    }
    rows = []
    for case, (probes, _, verification_noise, measured_protocol) in zip(cases, observed):
        fit_config = MeasuredLossFitConfig(
            id_lower_a=protocol.low_id_a, id_upper_a=protocol.high_id_a,
            current_limit_a=protocol.current_limit_a, voltage_limit_v=measured_protocol.voltage_limit_v,
        )
        first, low, high, last = probes
        center = ProbeMeasurement(protocol.center_id_a, 0.5 * (first.power_w + last.power_w),
                                  0.5 * (first.current_peak_a + last.current_peak_a),
                                  0.5 * (first.voltage_peak_v + last.voltage_peak_v))
        fit = fit_measured_loss_reference([low, center, high], fit_config)
        sampled = min((low, center, high), key=lambda p: p.power_w)
        reason = window_rejection_reason(probes, measured_protocol)
        baseline_stop = (last.current_peak_a > measured_protocol.current_limit_a
                         or last.voltage_peak_v > measured_protocol.voltage_limit_v)
        proposed = {
            "fixed": protocol.center_id_a,
            "best_probe": sampled.id_a,
            "analytic_fit": fit.id_a if fit.id_a is not None else protocol.center_id_a,
            **{key: float(values[case.case_index]) for key, values in predictions.items()},
        }
        for method, raw_id in proposed.items():
            raw = evaluate_shaft_point(case.params, case.speed_rad_s, case.shaft_torque_nm,
                                       raw_id, case.thermal)
            candidate_measured = measure(raw, case.speed_rad_s * case.shaft_torque_nm + raw.total_loss_w,
                                         condition, protocol, verification_noise)
            accepted = (method != "fixed" and reason is None
                        and accept_verification(last, candidate_measured, measured_protocol))
            final = raw if accepted else case.fixed
            probe_violations = sum(not p.feasible for p in case.probes_true) if method != "fixed" else 0
            trial_executed = method != "fixed" and reason is None
            base_loss = case.fixed.total_loss_w
            gap = None if case.optimum is None or baseline_stop else 100.0 * (final.total_loss_w - case.optimum.total_loss_w) / case.optimum.total_loss_w
            rows.append({
                "condition": condition.name, "seed": seed, "measurement_realization": realization,
                "sample_index": case.sample_index,
                "case_index": case.case_index, "method": method,
                "speed_rad_s": case.speed_rad_s, "shaft_torque_nm": case.shaft_torque_nm,
                "stator_temp_c": case.thermal.stator_temp_c, "rotor_temp_c": case.thermal.rotor_temp_c,
                "fixed_feasible": case.fixed.feasible, "fixed_loss_w": base_loss,
                "oracle_trust_region_id_a": None if case.optimum is None else case.optimum.id_a,
                "oracle_trust_region_loss_w": None if case.optimum is None else case.optimum.total_loss_w,
                "raw_id_a": raw_id, "raw_loss_w": raw.total_loss_w, "raw_feasible": raw.feasible,
                "selected_id_a": None if baseline_stop else final.id_a,
                "selected_loss_w": None if baseline_stop else final.total_loss_w,
                "selected_feasible": None if baseline_stop else final.feasible,
                "stop_requested": baseline_stop, "accepted": accepted and not baseline_stop,
                "observed_voltage_limit_v": measured_protocol.voltage_limit_v,
                "window_rejection": reason, "fit_reason": fit.reason,
                "probe_constraint_violation_count": probe_violations,
                "verification_trial_constraint_violation": trial_executed and not raw.feasible,
                "measurement_window_budget": 0 if method == "fixed" else (5 if trial_executed else 4),
                "loss_saving_pct": None if baseline_stop or not final.feasible else 100.0 * (base_loss - final.total_loss_w) / base_loss,
                "input_power_saving_pct": None if baseline_stop or not final.feasible else 100.0 * (base_loss - final.total_loss_w) / (case.speed_rad_s * case.shaft_torque_nm + base_loss),
                "raw_loss_saving_pct": 100.0 * (base_loss - raw.total_loss_w) / base_loss,
                "optimality_gap_pct": gap,
            })
    return rows


def annotate_common_cases(rows: list[dict]) -> None:
    """Offline scoring only; truth never changes the online action or fallback."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["condition"], row["seed"], row["measurement_realization"],
               row["sample_index"], row["case_index"])
        groups.setdefault(key, []).append(row)
    for grouped in groups.values():
        if len(grouped) != 5 or len({r["method"] for r in grouped}) != 5:
            raise ValueError("every comparison requires all five methods")
        eligible = all(r["fixed_feasible"] and r["selected_feasible"] is True
                       and not r["stop_requested"] for r in grouped)
        for row in grouped:
            row["common_comparison_eligible"] = eligible


def _cluster_ci(rows: list[dict], key: str, *, replicates: int = 2000) -> list[float]:
    clusters: dict[int, list[float]] = {}
    for row in rows:
        if row[key] is not None:
            clusters.setdefault(row["sample_index"], []).append(row[key])
    if len(clusters) < 2:
        raise ValueError("CI requires at least two independent motor clusters")
    sums = np.asarray([np.sum(v) for _, v in sorted(clusters.items())])
    counts = np.asarray([len(v) for _, v in sorted(clusters.items())])
    rng = np.random.default_rng(SPLIT_SEED)
    draws = rng.integers(0, len(sums), (replicates, len(sums)))
    return np.quantile(sums[draws].sum(axis=1) / counts[draws].sum(axis=1), [0.025, 0.975]).tolist()


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for condition in sorted({r["condition"] for r in rows}):
        summary[condition] = {}
        for method in sorted({r["method"] for r in rows}):
            selected = [r for r in rows if r["condition"] == condition and r["method"] == method]
            comparable = [r for r in selected if r["common_comparison_eligible"]]
            gaps = [r["optimality_gap_pct"] for r in comparable if r["optimality_gap_pct"] is not None]
            summary[condition][method] = {
                "all_rows": len(selected), "comparable_rows": len(comparable),
                "baseline_infeasible_rows": sum(not r["fixed_feasible"] for r in selected),
                "stop_requested_rows": sum(r["stop_requested"] for r in selected),
                "common_excluded_rows": len(selected) - len(comparable),
                "energy_denominator": "common complete cases: all methods served and feasible; failures separately reported, never credited as savings",
                "motor_clusters": len({r["sample_index"] for r in selected}),
                "training_seeds": sorted({r["seed"] for r in selected}),
                "mean_loss_saving_pct": float(np.mean([r["loss_saving_pct"] for r in comparable])),
                "mean_loss_saving_motor_bootstrap_95ci": _cluster_ci(comparable, "loss_saving_pct"),
                "median_loss_saving_pct": float(np.median([r["loss_saving_pct"] for r in comparable])),
                "mean_input_power_saving_pct": float(np.mean([r["input_power_saving_pct"] for r in comparable])),
                "median_optimality_gap_pct": float(np.median(gaps)),
                "worst_loss_saving_pct": min(r["loss_saving_pct"] for r in comparable),
                "worse_than_fixed_rows": sum(r["loss_saving_pct"] < -1e-9 for r in comparable),
                "raw_worse_than_fixed_rows": sum(r["raw_loss_saving_pct"] < -1e-9 for r in comparable),
                "final_constraint_violation_rows": sum(r["selected_feasible"] is False for r in selected),
                "probe_constraint_violation_rows": sum(r["probe_constraint_violation_count"] > 0 for r in selected),
                "trial_constraint_violation_rows": sum(r["verification_trial_constraint_violation"] for r in selected),
                "acceptance_fraction": float(np.mean([r["accepted"] for r in comparable])),
                "window_rejections": dict(Counter(r["window_rejection"] for r in selected if r["window_rejection"])),
                "probe_budget_max": max(r["measurement_window_budget"] for r in selected),
            }
    return summary


def paired_comparison(rows: list[dict], first: str, second: str, condition: str) -> dict:
    def select(method):
        return {(r["seed"], r["sample_index"], r["case_index"], r["measurement_realization"]): r for r in rows
                if r["method"] == method and r["condition"] == condition and r["common_comparison_eligible"]}
    a, b = select(first), select(second)
    if set(a) != set(b):
        raise ValueError("paired comparisons must contain identical cases")
    differences = [{"sample_index": key[1], "difference_w": b[key]["selected_loss_w"] - a[key]["selected_loss_w"]}
                   for key in sorted(a)]
    ci = _cluster_ci(differences, "difference_w")
    return {"first": first, "second": second, "condition": condition,
            "positive_means_first_reduces_loss": True,
            "mean_difference_w": float(np.mean([r["difference_w"] for r in differences])),
            "motor_cluster_bootstrap_95ci_w": ci,
            "positive_ci": ci[0] > 0, "paired_rows": len(differences)}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="AIR56B2 observable-context flux adaptation, simulation only")
    parser.add_argument("--input", type=Path, default=REPO / "artifacts/air56b2_fidelity_bundle.json")
    parser.add_argument("--output-dir", type=Path, default=REPO / "artifacts/measurement_adaptation_20260908_v2")
    parser.add_argument("--train-count", type=int, default=96)
    parser.add_argument("--validation-count", type=int, default=32)
    parser.add_argument("--holdout-count", type=int, default=32)
    parser.add_argument("--ood-count", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=800)
    parser.add_argument("--grid-points", type=int, default=161)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(TRAINING_SEEDS))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    if args.epochs < 1 or args.grid_points < 3 or len(set(args.seeds)) != len(args.seeds):
        raise ValueError("invalid epochs, grid resolution or repeated training seeds")
    input_raw = args.input.read_bytes()
    input_sha256 = hashlib.sha256(input_raw).hexdigest()
    bundle = json.loads(input_raw.decode("utf-8"))
    if bundle.get("status") != "PASS" or bundle.get("hardware_claim") is not False:
        raise ValueError("input must be simulation-only PASS fidelity bundle")
    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    torch.set_num_threads(2)
    protocol = MeasurementProtocol(rated_speed_rad_s=float(bundle["fidelity"]["derived_nameplate"]["rated_omega_rad_s"]))
    splits = split_indices(len(bundle["fidelity"]["f2_samples"]), args.train_count,
                           args.validation_count, args.holdout_count, args.ood_count)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").unlink(missing_ok=True)
    protocol_record = {
        "schema": "air56b2-measurement-adaptation-protocol-v2", "split_seed": SPLIT_SEED,
        "splits": splits, "training_seeds": args.seeds, "protocol": asdict(protocol),
        "evaluation_realizations": EVALUATION_REALIZATIONS,
        "conditions": [asdict(c) for c in CONDITIONS], "feature_keys": list(FEATURE_KEYS),
        "speeds_pu": SPEEDS_PU, "torques_pu": TORQUES_PU, "thermal_cases_c": THERMAL_CASES,
        "epochs": args.epochs, "oracle_grid_points": args.grid_points,
        "primary_comparison": "neural_context vs analytic_fit, measurement_noise, paired mean loss W",
        "secondary_comparison": "neural_context vs neural_single, same windows and guard",
        "inference": "exploratory; bootstrap conditional on sampled priors and fixed training seeds",
        "power_observation": "virtual input wattmeter P_shaft + modeled_total_loss; no bench estimator implemented",
        "time_contract": "four settled windows plus one verification; settling time is NOT simulated",
        "mechanics_contract": "torque input denotes shaft torque; electromagnetic torque adds B*omega + Coulomb friction",
        "voltage_guard": "min(170 V, 0.95 * measured_DC_bus / sqrt(3)); invalid measured baseline requests STOP",
        "revision_history": "v2: measured bus guard; no savings for STOP/infeasible actions; common complete-case comparisons and matched clustered estimand; crossed fixed measurement realizations; original fixed-voltage diagnostic retained separately",
        "hardware_release_ready": False,
    }
    protocol_path = args.output_dir / "protocol.json"
    protocol_path.write_text(json.dumps(protocol_record, indent=2, allow_nan=False), encoding="utf-8")
    print("Protocol frozen; building training and validation cases", flush=True)
    train_cases = build_cases(bundle, splits["train"], protocol, CONDITIONS[0], grid_points=args.grid_points)
    val_cases = build_cases(bundle, splits["validation"], protocol, CONDITIONS[0], grid_points=args.grid_points)
    xt, yt, train_exclusions = training_arrays(train_cases, protocol)
    xv, yv, val_exclusions = training_arrays(val_cases, protocol)
    print(f"Training arrays: {len(xt)} train, {len(xv)} validation; device={device}", flush=True)
    trained, records = {}, []
    for seed in args.seeds:
        trained[seed] = {}
        for key in ("context", "single"):
            state, record = train_policy(xt, yt, xv, yv, seed=seed, epochs=args.epochs,
                                         device=device, single_probe=key == "single")
            checkpoint = args.output_dir / f"{key}_{seed}.pt"
            torch.save({"state_dict": state, "protocol": asdict(protocol), "feature_keys": FEATURE_KEYS,
                        "single_probe": key == "single", "hardware_release_ready": False}, checkpoint)
            trained[seed][key] = state
            records.append({**record, "kind": key, "checkpoint": checkpoint.name,
                            "sha256": _sha(checkpoint), "state_sha256": state_digest(state)})
            print(f"Trained {key} seed={seed} val_mse={record['validation_mse']:.6f}", flush=True)
    replay, _ = train_policy(xt, yt, xv, yv, seed=args.seeds[0], epochs=args.epochs, device=device)
    replay_equal = state_digest(replay) == state_digest(trained[args.seeds[0]]["context"])
    print(f"Bitwise training replay={replay_equal}; opening holdout only after training", flush=True)
    all_rows = []
    for condition in CONDITIONS:
        indices = splits["ood"] if condition.ood else splits["holdout"]
        cases = build_cases(bundle, indices, protocol, condition, grid_points=args.grid_points)
        for seed in args.seeds:
            for realization in EVALUATION_REALIZATIONS:
                all_rows.extend(score_cases(cases, condition, protocol, trained[seed], realization=realization, seed=seed))
        print(f"Scored {condition.name}: {len(cases)} cases per seed", flush=True)
    annotate_common_cases(all_rows)
    summary = summarize(all_rows)
    comparisons = [paired_comparison(all_rows, "neural_context", baseline, condition.name)
                   for condition in CONDITIONS for baseline in ("analytic_fit", "neural_single")]
    expected = (args.holdout_count * 24 * len(args.seeds) * 5 * 4 + args.ood_count * 24 * len(args.seeds) * 5) * len(EVALUATION_REALIZATIONS)
    gates = {
        "all_planned_rows_present": len(all_rows) == expected,
        "training_replay_bitwise_identical": replay_equal,
        "all_results_finite": all(r["stop_requested"] or math.isfinite(r["selected_loss_w"]) for r in all_rows),
        "stops_not_credited_as_savings": all(r["loss_saving_pct"] is None for r in all_rows if r["stop_requested"]),
        "infeasible_actions_not_credited_as_savings": all(r["loss_saving_pct"] is None for r in all_rows if r["selected_feasible"] is False),
        "disjoint_motor_splits": len(set(sum(splits.values(), []))) == sum(map(len, splits.values())),
        "negative_results_retained": True,
        "hardware_release_disabled": True,
    }
    result = {
        "schema": "air56b2-measurement-adaptation-study-v2",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "status_meaning": "experimental execution and integrity, NOT acceptance of scientific hypotheses",
        "hardware_release_ready": False, "hardware_claim": False,
        "device": device, "torch_version": str(torch.__version__),
        "protocol": {"file": protocol_path.name, "sha256": _sha(protocol_path)},
        "input": {"file": str(args.input.resolve()), "sha256": input_sha256},
        "training_records": records, "train_rows": len(xt), "validation_rows": len(xv),
        "training_exclusions": train_exclusions, "validation_exclusions": val_exclusions,
        "gates": gates, "summary": summary, "paired_comparisons": comparisons,
        "limitations": [
            "Virtual wattmeter is a modeled observation; it is not a validated phase-power or DC-power estimator.",
            "Legacy loss model lacks a current-carrying iron-loss branch; voltage/current amplitudes are approximate proxies.",
            "No flux settling, controller dynamics, transient probe energy, observer errors or torque ripple is simulated.",
            "Probe and verification constraint violations are counted, not prevented by an oracle.",
            "Training excludes infeasible probe windows; test includes and reports every planned window.",
            "New random motor splits share a previously explored prior family; this is exploratory evidence, not confirmatory evidence.",
            "Bootstrap resamples motor clusters including all seeds and regimes; intervals do not quantify simulator structural uncertainty.",
            "An excitation-dependent power-estimator bias is confounded with the true loss slope.",
        ],
        "row_count": len(all_rows),
    }
    row_path = args.output_dir / "rows.jsonl.gz"
    raw_rows = "\n".join(json.dumps(row, allow_nan=False, separators=(",", ":")) for row in all_rows).encode("utf-8")
    row_path.write_bytes(gzip.compress(raw_rows, mtime=0))
    result["row_data"] = {"file": row_path.name, "sha256": _sha(row_path), "format": "gzip_json_lines"}
    out = args.output_dir / "study.json"
    if _sha(args.input) != input_sha256 or any(_sha(REPO / p) != digest for p, digest in SOURCE_HASHES.items()):
        raise RuntimeError("research sources or input changed during execution; no manifest will be published")
    out.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    manifest = {"schema": "air56b2-measurement-adaptation-manifest-v1",
                "status": result["status"], "hardware_release_ready": False,
                "files": {p.name: _sha(p) for p in [protocol_path, out, row_path,
                          *(args.output_dir / record["checkpoint"] for record in records)]},
                "sources": SOURCE_HASHES}
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "rows": len(all_rows),
                      "primary": [r for r in comparisons if r["condition"] == "measurement_noise"]}, indent=2), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

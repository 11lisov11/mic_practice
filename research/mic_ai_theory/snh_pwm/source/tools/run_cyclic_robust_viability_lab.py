from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from random import Random
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.cyclic_robust_viability_pwm import rotate_state, rotate_vector_id
from models.induction_motor_alpha_beta import AlphaBetaInductionMotorModel, AlphaBetaMotorState
from models.two_level_inverter import alpha_beta_voltage
from tools.run_safe_neural_horizon_pwm_study import (
    DEFAULT_SCENARIOS,
    _make_base_params,
    _paired_effects,
    _paired_trial_seeds,
    _run_controller_trials,
    _safety_thresholds,
    _study_metadata,
    _summarize_rows,
    pareto_front,
    run_trial,
)


PROPOSED = "cyclic_robust_viability_pwm"
BASELINE = "foc_svm_key_baseline"
CONTROLLER_SPECS = [
    (BASELINE, 1, 1),
    ("fcs_mpc_one_step_baseline", 1, 1),
    ("safe_neural_horizon_pwm_h2", 2, 10),
    (PROPOSED, 1, 1),
]
ABLATION_SPECS = [
    (PROPOSED, 1, 1),
    ("cyclic_robust_viability_pwm_nominal_only", 1, 1),
    ("cyclic_robust_viability_pwm_no_viability", 1, 1),
    ("cyclic_robust_viability_pwm_full_vectors", 1, 1),
    ("cyclic_robust_viability_pwm_mean_only", 1, 1),
    ("cyclic_robust_viability_pwm_tight_margin", 1, 1),
    ("cyclic_robust_viability_pwm_eager_viability", 1, 1),
]
FALSIFICATION_SCENARIOS = [
    "reverse",
    "braking",
    "regeneration",
    "overload",
    "dc_sag",
    "shock_load",
    "sensor_delay",
    "sensor_dropout",
    "ood",
]


def run_equivariance_audit(*, samples: int, seed: int) -> dict[str, Any]:
    motor, inverter = _make_base_params()
    rng = Random(int(seed))
    residuals: list[float] = []
    torque_residuals: list[float] = []
    current_residuals: list[float] = []
    for _ in range(max(1, int(samples))):
        state = AlphaBetaMotorState(
            psi_s_alpha=rng.uniform(-0.25, 0.25),
            psi_s_beta=rng.uniform(-0.25, 0.25),
            psi_r_alpha=rng.uniform(-0.20, 0.20),
            psi_r_beta=rng.uniform(-0.20, 0.20),
            omega_m=rng.uniform(-150.0, 150.0),
            theta_m=rng.uniform(-math.pi, math.pi),
            temp_s_c=rng.uniform(20.0, 100.0),
            temp_r_c=rng.uniform(20.0, 110.0),
        )
        vector_id = rng.randrange(0, 8)
        sectors = rng.randrange(0, 6)
        load = rng.uniform(-1.0, 1.0)

        model = AlphaBetaInductionMotorModel(motor, state)
        currents = model.currents()
        voltage = alpha_beta_voltage(
            vector_id,
            inverter,
            i_alpha_beta=(currents.i_s_alpha, currents.i_s_beta),
        )
        nominal = model.next_state(*voltage, load, inverter.t_pwm_s)

        rotated_initial = rotate_state(state, sectors)
        rotated_model = AlphaBetaInductionMotorModel(motor, rotated_initial)
        rotated_currents = rotated_model.currents()
        rotated_voltage = alpha_beta_voltage(
            rotate_vector_id(vector_id, sectors),
            inverter,
            i_alpha_beta=(rotated_currents.i_s_alpha, rotated_currents.i_s_beta),
        )
        rotated = rotated_model.next_state(*rotated_voltage, load, inverter.t_pwm_s)
        expected_state = rotate_state(nominal.state, sectors)
        residuals.append(
            max(
                abs(rotated.state.psi_s_alpha - expected_state.psi_s_alpha),
                abs(rotated.state.psi_s_beta - expected_state.psi_s_beta),
                abs(rotated.state.psi_r_alpha - expected_state.psi_r_alpha),
                abs(rotated.state.psi_r_beta - expected_state.psi_r_beta),
                abs(rotated.state.omega_m - expected_state.omega_m),
            )
        )
        torque_residuals.append(abs(rotated.torque_nm - nominal.torque_nm))
        current_residuals.append(abs(rotated.currents.stator_abs - nominal.currents.stator_abs))

    maximum = max(residuals + torque_residuals + current_residuals)
    return {
        "status": "c6_equivariance_numeric_audit",
        "samples": max(1, int(samples)),
        "max_state_residual": max(residuals),
        "max_torque_residual": max(torque_residuals),
        "max_current_norm_residual": max(current_residuals),
        "tolerance": 1.0e-9,
        "pass": maximum <= 1.0e-9,
    }


def _matrix_for_specs(
    *,
    specs: list[tuple[str, int, int]],
    scenarios: Sequence[str],
    mc: int,
    steps: int,
    seed: int,
    workers: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    motor, inverter = _make_base_params()
    matrix: dict[str, Any] = {}
    paired: dict[str, Any] = {}
    for scenario in scenarios:
        trial_seeds = _paired_trial_seeds(seed=seed, scenario=scenario, trials=mc, stream="c6_rv_lab")
        rows = _run_controller_trials(
            controller_specs=specs,
            trial_seeds=trial_seeds,
            base_motor=motor,
            inverter=inverter,
            steps=steps,
            scenario=scenario,
            workers=workers,
        )
        scenario_payload = {label: _summarize_rows(rows[label]) for label, _, _ in specs}
        scenario_payload["pareto_front"] = pareto_front(scenario_payload)
        matrix[scenario] = scenario_payload
        if BASELINE in rows:
            paired[scenario] = {
                label: _paired_effects(controller_rows, rows[BASELINE])
                for label, controller_rows in rows.items()
                if label != BASELINE
            }
    return matrix, paired


def run_comparison(
    *,
    scenarios: Sequence[str],
    mc: int,
    steps: int,
    seed: int,
    workers: int,
) -> dict[str, Any]:
    motor, inverter = _make_base_params()
    matrix, paired = _matrix_for_specs(
        specs=CONTROLLER_SPECS,
        scenarios=scenarios,
        mc=mc,
        steps=steps,
        seed=seed,
        workers=workers,
    )
    ablation_matrix, _ = _matrix_for_specs(
        specs=ABLATION_SPECS,
        scenarios=["load_step", "dc_sag", "ood"],
        mc=mc,
        steps=steps,
        seed=seed,
        workers=workers,
    )
    return {
        "status": "host_mathematical_experiment_only",
        "hardware_claim": False,
        "controllers": [label for label, _, _ in CONTROLLER_SPECS],
        "scenarios": list(scenarios),
        "mc_trials": int(mc),
        "steps_per_trial": int(steps),
        "workers": max(1, int(workers)),
        "safety_thresholds": _safety_thresholds(motor),
        **_study_metadata(inverter=inverter, steps=steps),
        "matrix": matrix,
        "paired_effects_vs_foc_svm": paired,
        "ablation_matrix": ablation_matrix,
    }


def _genome_problem(unit: Sequence[float]):
    motor, inverter = _make_base_params()
    scenario = FALSIFICATION_SCENARIOS[min(len(FALSIFICATION_SCENARIOS) - 1, int(unit[0] * len(FALSIFICATION_SCENARIOS)))]
    rs_scale = 0.45 + 2.10 * unit[1]
    rr_scale = 0.45 + 2.10 * unit[2]
    lm_scale = 0.55 + 0.90 * unit[3]
    j_scale = 0.40 + 2.60 * unit[4]
    vdc_scale = 0.55 + 0.65 * unit[5]
    scaled_motor = replace(
        motor,
        Rs=max(1.0e-9, motor.Rs * rs_scale),
        Rr=max(1.0e-9, motor.Rr * rr_scale),
        Lm=max(1.0e-9, motor.Lm * lm_scale),
        J=max(1.0e-9, motor.J * j_scale),
    )
    scaled_inverter = replace(inverter, Vdc=inverter.Vdc * vdc_scale)
    seed_material = json.dumps([round(float(value), 12) for value in unit], separators=(",", ":"))
    trial_seed = int.from_bytes(hashlib.sha256(seed_material.encode("ascii")).digest()[:8], "big")
    return scaled_motor, scaled_inverter, scenario, trial_seed, {
        "rs_scale": rs_scale,
        "rr_scale": rr_scale,
        "lm_scale": lm_scale,
        "j_scale": j_scale,
        "vdc_scale": vdc_scale,
    }


def _evaluate_genome(unit: Sequence[float], *, steps: int) -> dict[str, Any]:
    motor, inverter, scenario, trial_seed, scales = _genome_problem(unit)
    proposed = run_trial(
        label=PROPOSED,
        base_motor=motor,
        inverter=inverter,
        rng=Random(trial_seed),
        steps=steps,
        horizon=1,
        feedback_period=1,
        scenario=scenario,
    )
    baseline = run_trial(
        label=BASELINE,
        base_motor=motor,
        inverter=inverter,
        rng=Random(trial_seed),
        steps=steps,
        horizon=1,
        feedback_period=1,
        scenario=scenario,
    )
    trip = max(3.5 * motor.i_limit, 5.0)
    omega_nom = 2.0 * math.pi * 50.0 / max(motor.p, 1)
    speed_regret = (proposed["mean_abs_speed_error"] - baseline["mean_abs_speed_error"]) / max(omega_nom, 1.0e-9)
    unsafe = proposed["safety_violations"] + proposed["fault_latch_events"]
    current_ratio = proposed["max_current_abs"] / max(trip, 1.0e-9)
    fallback_ratio = proposed["fallback_count"] / max(int(steps), 1)
    objective = 100.0 * unsafe + current_ratio + 2.0 * max(0.0, speed_regret) + 0.2 * fallback_ratio
    return {
        "objective": float(objective),
        "scenario": scenario,
        "trial_seed": int(trial_seed),
        "genome": [float(value) for value in unit],
        **scales,
        "speed_regret_normalized": float(speed_regret),
        "current_trip_ratio": float(current_ratio),
        "unsafe_events": float(unsafe),
        "fallback_ratio": float(fallback_ratio),
        "proposed": proposed,
        "baseline": baseline,
    }


def run_counterexample_search(
    *,
    seed: int,
    population: int,
    generations: int,
    steps: int,
) -> dict[str, Any]:
    rng = Random(int(seed))
    dimension = 6
    mean = [0.5] * dimension
    std = [0.30] * dimension
    all_rows: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    for generation in range(max(1, int(generations))):
        units = [list(mean)]
        while len(units) < max(4, int(population)):
            units.append([max(0.0, min(0.999999, rng.gauss(mu, sigma))) for mu, sigma in zip(mean, std)])
        rows = [_evaluate_genome(unit, steps=steps) for unit in units]
        rows.sort(key=lambda row: float(row["objective"]), reverse=True)
        all_rows.extend(rows)
        elite_count = max(2, int(math.ceil(0.25 * len(rows))))
        elites = rows[:elite_count]
        for index in range(dimension):
            values = [float(row["genome"][index]) for row in elites]
            mean[index] = sum(values) / len(values)
            variance = sum((value - mean[index]) ** 2 for value in values) / len(values)
            std[index] = max(0.03, math.sqrt(variance))
        history.append(
            {
                "generation": generation,
                "best_objective": float(rows[0]["objective"]),
                "elite_mean": list(mean),
                "elite_std": list(std),
            }
        )
    all_rows.sort(key=lambda row: float(row["objective"]), reverse=True)
    top = all_rows[: min(10, len(all_rows))]
    return {
        "status": "simulation_falsification_not_proof",
        "sound_if_counterexample_found": True,
        "complete_search": False,
        "seed": int(seed),
        "population": max(4, int(population)),
        "generations": max(1, int(generations)),
        "steps_per_evaluation": max(1, int(steps)),
        "history": history,
        "top_counterexamples": top,
        "unsafe_counterexample_found": any(float(row["unsafe_events"]) > 0.0 for row in top),
        "performance_counterexample_found": any(float(row["speed_regret_normalized"]) > 0.0 for row in top),
    }


def _hypothesis_audit(comparison: dict[str, Any], equivariance: dict[str, Any], falsification: dict[str, Any]) -> dict[str, Any]:
    proposed_rows = [comparison["matrix"][scenario][PROPOSED] for scenario in comparison["scenarios"]]
    no_observed_safety_violation = all(float(row["safety_violations"]["worst"]) == 0.0 for row in proposed_rows)
    reduced_candidates = all(float(row["planner_mean_candidate_count"]["mean"]) < 8.0 for row in proposed_rows)
    viability_predecessor_active = any(
        float(row["planner_mean_viability_rejections"]["worst"]) > 0.0 for row in proposed_rows
    )
    viability_predecessor_triggered = any(
        float(row["planner_mean_viability_triggers"]["worst"]) > 0.0 for row in proposed_rows
    )
    better = worse = inconclusive = 0
    for scenario in comparison["scenarios"]:
        metric = comparison["paired_effects_vs_foc_svm"][scenario][PROPOSED]["metrics"]["mean_abs_speed_error"]
        low = float(metric["ci95_normal_low"])
        high = float(metric["ci95_normal_high"])
        if high < 0.0:
            better += 1
        elif low > 0.0:
            worse += 1
        else:
            inconclusive += 1
    return {
        "h1_c6_numeric_equivariance": bool(equivariance["pass"]),
        "h2_candidate_set_reduced_below_full_eight": reduced_candidates,
        "h3_no_observed_software_safety_violation": no_observed_safety_violation,
        "h4_lazy_viability_predecessor_triggered": viability_predecessor_triggered,
        "h5_viability_predecessor_changed_candidate_set": viability_predecessor_active,
        "speed_error_vs_foc_svm": {"better": better, "worse": worse, "inconclusive": inconclusive},
        "counterexample_search_found_unsafe": bool(falsification["unsafe_counterexample_found"]),
        "counterexample_search_found_performance_regret": bool(falsification["performance_counterexample_found"]),
        "novelty_established": False,
        "hardware_ready": False,
    }


def run_lab(
    *,
    scenarios: Sequence[str],
    mc: int,
    steps: int,
    seed: int,
    workers: int,
    equivariance_samples: int,
    falsification_population: int,
    falsification_generations: int,
    falsification_steps: int,
) -> dict[str, Any]:
    comparison = run_comparison(
        scenarios=scenarios,
        mc=mc,
        steps=steps,
        seed=seed,
        workers=workers,
    )
    equivariance = run_equivariance_audit(samples=equivariance_samples, seed=seed + 1)
    falsification = run_counterexample_search(
        seed=seed + 2,
        population=falsification_population,
        generations=falsification_generations,
        steps=falsification_steps,
    )
    return {
        "study": "C6 Robust Viability PWM Mathematical Lab",
        "status": "host_research_candidate",
        "hardware_claim": False,
        "novelty_claim": False,
        "proposed_controller": PROPOSED,
        "hypothesis": (
            "C6-equivariant candidate reduction plus parameter-set CVaR scoring and a robust "
            "one-step viability predecessor can improve the safety/performance Pareto frontier."
        ),
        "comparison": comparison,
        "equivariance_audit": equivariance,
        "counterexample_search": falsification,
        "hypothesis_audit": _hypothesis_audit(comparison, equivariance, falsification),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the C6 robust viability PWM mathematical research lab.")
    parser.add_argument("--scenarios", default="start_no_load,load_step,reverse,braking,dc_sag,ood")
    parser.add_argument("--mc", type=int, default=3)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--seed", type=int, default=431)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--equivariance-samples", type=int, default=100)
    parser.add_argument("--falsification-population", type=int, default=12)
    parser.add_argument("--falsification-generations", type=int, default=4)
    parser.add_argument("--falsification-steps", type=int, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    unknown = sorted(set(scenarios) - set(DEFAULT_SCENARIOS))
    if unknown:
        parser.error(f"unknown scenarios: {', '.join(unknown)}")
    payload = run_lab(
        scenarios=scenarios,
        mc=max(1, args.mc),
        steps=max(1, args.steps),
        seed=args.seed,
        workers=max(1, args.workers),
        equivariance_samples=max(1, args.equivariance_samples),
        falsification_population=max(4, args.falsification_population),
        falsification_generations=max(1, args.falsification_generations),
        falsification_steps=max(1, args.falsification_steps),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "hypothesis_audit": payload["hypothesis_audit"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

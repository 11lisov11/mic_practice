from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
from random import Random
import statistics
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mic_ai.ident.model_based import (  # noqa: E402
    FIT_PARAMETER_NAMES,
    PARAMETER_NAMES,
    SEPARATE_LEAKAGE_PARAMETER_NAMES,
    add_measurement_noise,
    analyze_identifiability,
    estimate_parameters,
    make_excitation_suite,
    relative_parameter_errors,
    separate_leakage_sensitivity_matrix,
    sensitivity_matrix,
    simulate_identification_experiments,
    with_free_run_load_bias,
)
from models.induction_motor_alpha_beta import randomized_motor_params  # noqa: E402
from tools.run_safe_neural_horizon_pwm_study import _make_base_params  # noqa: E402


METHODS = ("fixed_sector", "random_prbs", "c6_multiscale")


def _finite(value: float) -> float | None:
    value = float(value)
    return value if math.isfinite(value) else None


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _sign_test_upper_tail(wins: int, trials: int) -> float:
    if trials <= 0:
        return 1.0
    return float(sum(math.comb(trials, k) for k in range(wins, trials + 1)) / (2**trials))


def _params_payload(params) -> dict[str, float]:
    result = {name: float(getattr(params, name)) for name in PARAMETER_NAMES}
    result["Lls"] = float(params.Lls)
    result["Llr"] = float(params.Llr)
    result["Lsigma"] = 0.5 * (float(params.Lls) + float(params.Llr))
    return result


def run_study(
    *,
    seed: int,
    motors: int = 12,
    steps_per_stage: int = 1920,
    dt: float = 5.0e-4,
    vdc: float = 48.0,
    starts: int = 2,
    max_nfev: int = 100,
    noise_scales: tuple[float, float, float] = (0.005, 0.005, 0.01),
    leakage_span: float = 0.20,
    design_repetitions: int = 32,
) -> dict[str, Any]:
    if motors < 1:
        raise ValueError("motors must be positive")
    base_motor, _ = _make_base_params()
    profile_seed = int(seed) * 1_000 + 10_000

    experiments = {
        method: make_excitation_suite(
            method,
            steps_per_stage=steps_per_stage,
            dt=dt,
            vdc=vdc,
            seed=profile_seed,
        )
        for method in METHODS
    }
    reports = {
        method: analyze_identifiability(sensitivity_matrix(base_motor, experiments[method]))
        for method in METHODS
    }
    if design_repetitions < 4:
        raise ValueError("design_repetitions must be at least four")
    prbs_design_reports = []
    for design_index in range(design_repetitions):
        design_experiments = make_excitation_suite(
            "random_prbs",
            steps_per_stage=steps_per_stage,
            dt=dt,
            vdc=vdc,
            seed=profile_seed + design_index,
        )
        prbs_design_reports.append(
            analyze_identifiability(sensitivity_matrix(base_motor, design_experiments))
        )
    c6_logdet = reports["c6_multiscale"].log10_fisher_determinant
    prbs_logdets = [report.log10_fisher_determinant for report in prbs_design_reports]
    c6_information_wins = sum(c6_logdet > value for value in prbs_logdets)
    design_robustness = {
        "prbs_designs": design_repetitions,
        "c6_log10_fisher_determinant": c6_logdet,
        "prbs_log10_fisher_median": float(statistics.median(prbs_logdets)),
        "prbs_log10_fisher_min": min(prbs_logdets),
        "prbs_log10_fisher_max": max(prbs_logdets),
        "c6_information_wins": c6_information_wins,
        "c6_information_win_rate": c6_information_wins / design_repetitions,
        "c6_information_sign_test_p_value_one_sided": _sign_test_upper_tail(
            c6_information_wins,
            design_repetitions,
        ),
        "c6_condition_number": reports["c6_multiscale"].condition_number,
        "prbs_condition_median": float(
            statistics.median(report.condition_number for report in prbs_design_reports)
        ),
    }
    separate_leakage_report = analyze_identifiability(
        separate_leakage_sensitivity_matrix(base_motor, experiments["c6_multiscale"]),
        parameter_names=SEPARATE_LEAKAGE_PARAMETER_NAMES,
    )

    rows: list[dict[str, Any]] = []
    for motor_index in range(motors):
        truth_seed = int(seed) * 100_003 + motor_index * 97 + 17
        truth_rng = Random(truth_seed)
        truth = randomized_motor_params(
            base_motor,
            truth_rng,
            rs_span=0.30,
            rr_span=0.30,
            lm_span=0.15,
            j_span=0.50,
            b_span=0.50,
        )
        truth = replace(
            truth,
            Lls=base_motor.Lls * (1.0 + truth_rng.uniform(-leakage_span, leakage_span)),
            Llr=base_motor.Llr * (1.0 + truth_rng.uniform(-leakage_span, leakage_span)),
        )
        true_load_torque_nm = truth_rng.uniform(-0.005, 0.005)
        measurement_seed = int(seed) * 1_000_003 + motor_index * 193 + 29
        for method_index, method in enumerate(METHODS):
            report = reports[method]
            row: dict[str, Any] = {
                "motor_index": motor_index,
                "method": method,
                "truth_seed": truth_seed,
                "measurement_seed": measurement_seed,
                "truth": _params_payload(truth),
                "true_load_torque_nm": true_load_torque_nm,
                "identifiability_gate_pass": report.identifiable,
            }
            truth_experiments = with_free_run_load_bias(experiments[method], true_load_torque_nm)
            exact = simulate_identification_experiments(truth, truth_experiments)
            max_current = float(np.max(np.hypot(exact.i_alpha, exact.i_beta)))
            row["max_stator_current"] = max_current
            row["current_limit"] = float(truth.i_limit)
            row["current_limit_exceeded"] = max_current > float(truth.i_limit)
            if not report.identifiable:
                row.update(
                    {
                        "estimate_status": "blocked_unidentifiable",
                        "estimate": None,
                        "relative_errors": None,
                        "max_relative_error": None,
                    }
                )
                rows.append(row)
                continue

            observed = add_measurement_noise(
                exact,
                noise_scales=noise_scales,
                seed=measurement_seed,
            )
            fitted = estimate_parameters(
                observed,
                base_motor,
                experiments[method],
                noise_scales=noise_scales,
                starts=starts,
                seed=int(seed) * 10_007 + motor_index * 31 + method_index,
                max_nfev=max_nfev,
            )
            errors = relative_parameter_errors(fitted.params, truth)
            row.update(
                {
                    "estimate_status": "ok",
                    "estimate": _params_payload(fitted.params),
                    "estimated_load_torque_nm": fitted.load_torque_nm,
                    "load_torque_abs_error_nm": abs(fitted.load_torque_nm - true_load_torque_nm),
                    "relative_errors": errors,
                    "max_relative_error": max(errors.values()),
                    "normalized_rmse": fitted.normalized_rmse,
                    "successful_starts": fitted.successful_starts,
                }
            )
            rows.append(row)

    summary: dict[str, Any] = {}
    for method in METHODS:
        method_rows = [row for row in rows if row["method"] == method]
        valid = [row for row in method_rows if row["estimate_status"] == "ok"]
        report = reports[method]
        summary[method] = {
            "identifiability": {
                "rank": report.numerical_rank,
                "parameter_count": len(FIT_PARAMETER_NAMES),
                "condition_number": _finite(report.condition_number),
                "log10_fisher_determinant": _finite(report.log10_fisher_determinant),
                "relative_column_norms": dict(zip(FIT_PARAMETER_NAMES, report.relative_column_norms)),
                "max_abs_parameter_correlation": report.max_abs_parameter_correlation,
                "gate_pass": report.identifiable,
            },
            "estimated_motors": len(valid),
            "blocked_motors": len(method_rows) - len(valid),
            "max_stator_current": max(float(row["max_stator_current"]) for row in method_rows),
            "current_limit_exceedances": sum(bool(row["current_limit_exceeded"]) for row in method_rows),
            "median_max_relative_error": _median([float(row["max_relative_error"]) for row in valid]),
            "median_relative_error_by_parameter": {
                name: _median([float(row["relative_errors"][name]) for row in valid])
                for name in PARAMETER_NAMES
            },
        }

    random_by_motor = {
        int(row["motor_index"]): row
        for row in rows
        if row["method"] == "random_prbs" and row["estimate_status"] == "ok"
    }
    c6_by_motor = {
        int(row["motor_index"]): row
        for row in rows
        if row["method"] == "c6_multiscale" and row["estimate_status"] == "ok"
    }
    paired_indices = sorted(set(random_by_motor) & set(c6_by_motor))
    c6_wins = sum(
        float(c6_by_motor[index]["max_relative_error"])
        < float(random_by_motor[index]["max_relative_error"])
        for index in paired_indices
    )
    error_ratios = [
        float(c6_by_motor[index]["max_relative_error"])
        / max(float(random_by_motor[index]["max_relative_error"]), 1.0e-15)
        for index in paired_indices
    ]
    random_condition = reports["random_prbs"].condition_number
    c6_condition = reports["c6_multiscale"].condition_number
    paired = {
        "trials": len(paired_indices),
        "c6_wins": c6_wins,
        "c6_win_rate": c6_wins / max(len(paired_indices), 1),
        "c6_win_sign_test_p_value_one_sided": _sign_test_upper_tail(c6_wins, len(paired_indices)),
        "median_c6_to_random_max_error_ratio": _median(error_ratios),
        "c6_to_random_condition_ratio": c6_condition / max(random_condition, 1.0e-300),
    }

    payload = {
        "schema": "mic-ai-model-based-identification-study-v1",
        "seed": int(seed),
        "protocol": {
            "motors": int(motors),
            "steps_per_stage": int(steps_per_stage),
            "dt": float(dt),
            "vdc": float(vdc),
            "starts": int(starts),
            "max_nfev": int(max_nfev),
            "noise_scales": list(noise_scales),
            "leakage_span": float(leakage_span),
            "unmodeled_load_torque_range_nm": [-0.005, 0.005],
            "profile_seed": profile_seed,
            "design_repetitions": int(design_repetitions),
            "truth_used_for": "post-fit synthetic error audit only",
            "available_outputs": ["i_s_alpha", "i_s_beta", "omega_m"],
            "known_inputs": ["v_alpha", "v_beta", "rotor_lock_state"],
            "fitted_nuisance_parameters": ["Lsigma", "Tload"],
        },
        "base_prior": _params_payload(base_motor),
        "design_robustness": design_robustness,
        "model_structure_audit": {
            "separate_leakage_parameter_names": list(SEPARATE_LEAKAGE_PARAMETER_NAMES),
            "separate_leakage_rank": separate_leakage_report.numerical_rank,
            "separate_leakage_parameter_count": len(SEPARATE_LEAKAGE_PARAMETER_NAMES),
            "separate_leakage_identifiable": separate_leakage_report.identifiable,
            "fitted_nuisance_parameter": "Lsigma=(Lls+Llr)/2",
        },
        "summary": summary,
        "paired_c6_vs_random": paired,
        "rows": rows,
        "claims": {
            "simulation_evidence": True,
            "hardware_validated": False,
            "world_novelty_established": False,
            "defensible_candidate": (
                reports["fixed_sector"].numerical_rank < len(FIT_PARAMETER_NAMES)
                and reports["c6_multiscale"].identifiable
                and c6_information_wins >= math.ceil(0.90 * design_repetitions)
                and design_robustness["c6_information_sign_test_p_value_one_sided"] <= 0.01
                and int(summary["c6_multiscale"]["current_limit_exceedances"]) == 0
            ),
            "candidate_statement": (
                "Identifiability-gated C6 multiscale inverter-vector excitation with leakage "
                "and load nuisance parameters is a testable D-informative candidate for joint "
                "electrical/mechanical induction-motor identification."
            ),
        },
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the model-based induction-motor identification study")
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--motors", type=int, default=12)
    parser.add_argument("--steps-per-stage", type=int, default=1920)
    parser.add_argument("--starts", type=int, default=2)
    parser.add_argument("--max-nfev", type=int, default=100)
    parser.add_argument("--design-repetitions", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run_study(
        seed=args.seed,
        motors=args.motors,
        steps_per_stage=args.steps_per_stage,
        starts=args.starts,
        max_nfev=args.max_nfev,
        design_repetitions=args.design_repetitions,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "claims": payload["claims"], "paired": payload["paired_c6_vs_random"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

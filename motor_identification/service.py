from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from statistics import median
from typing import Any, Mapping

import numpy as np

from .model import (
    ExperimentInput,
    MotorParameters,
    Observations,
    analyze_rank,
    approximate_confidence_intervals,
    fit_parameters,
    metrics,
    prior_from_payload,
    sensitivity_matrix,
    simulate,
)
from .schema import PRIOR_SCHEMA, RESULT_SCHEMA, normalized_samples, validate_capture


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite_json(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _finite_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_json(item) for item in value]
    return value


def validate_prior_payload(payload: Mapping[str, Any], motor_id: str) -> tuple[MotorParameters | None, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    if payload.get("schema") != PRIOR_SCHEMA:
        errors.append({"code": "prior_schema", "detail": f"expected {PRIOR_SCHEMA}"})
    if str(payload.get("motor_id", "")).strip() != str(motor_id).strip():
        errors.append({"code": "prior_motor_id", "detail": "prior motor_id does not match capture motor_id"})
    try:
        prior = prior_from_payload(payload)
    except (TypeError, ValueError) as exc:
        errors.append({"code": "prior_parameters", "detail": str(exc)})
        prior = None
    return prior, errors


def _role_data(
    payload: Mapping[str, Any], role: str
) -> tuple[tuple[ExperimentInput, ...], Observations]:
    inputs: list[ExperimentInput] = []
    i_alpha: list[float] = []
    i_beta: list[float] = []
    omega: list[float] = []
    experiments = payload.get("experiments", [])
    for experiment in experiments:
        if not isinstance(experiment, Mapping) or experiment.get("role") != role:
            continue
        samples = normalized_samples(experiment)
        times = samples["t_s"]
        dt = float(median(right - left for left, right in zip(times, times[1:])))
        initial_omega = float(experiment.get("initial_omega_rad_s", 0.0))
        inputs.append(
            ExperimentInput(
                experiment_id=str(experiment["id"]),
                kind=str(experiment["kind"]),
                rotor_locked=bool(experiment["rotor_locked"]),
                dt=dt,
                initial_omega_m=initial_omega,
                v_alpha=np.asarray(samples["v_alpha_v"], dtype=float),
                v_beta=np.asarray(samples["v_beta_v"], dtype=float),
            )
        )
        i_alpha.extend(samples["i_alpha_a"])
        i_beta.extend(samples["i_beta_a"])
        omega.extend(samples["omega_rad_s"])
    return tuple(inputs), Observations(np.asarray(i_alpha), np.asarray(i_beta), np.asarray(omega))


def _noise_scales(payload: Mapping[str, Any]) -> tuple[float, float, float]:
    noise = payload["noise_std"]
    return (
        float(noise["i_alpha_a"]),
        float(noise["i_beta_a"]),
        float(noise["omega_rad_s"]),
    )


def validate_capture_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    report = validate_capture(payload)
    return {
        "schema": "mic_ai.motor_identification.contract_report.v1",
        "capture_schema": payload.get("schema"),
        "capture_sha256": _canonical_sha256(payload),
        "contract": report.as_dict(),
        "identification_eligible": report.passed,
        "note": (
            "Contract valid; rank-gate still must pass with a motor prior."
            if report.passed
            else "Contract invalid; no parameter estimate may be produced."
        ),
    }


def _base_result(capture: Mapping[str, Any], prior: Mapping[str, Any]) -> dict[str, Any]:
    source = capture.get("source") if isinstance(capture.get("source"), Mapping) else {}
    return {
        "schema": RESULT_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "motor_id": capture.get("motor_id"),
        "source_kind": source.get("kind"),
        "capture_sha256": _canonical_sha256(capture),
        "prior_sha256": _canonical_sha256(prior),
        "accepted": False,
        "decision": "rejected",
        "blockers": [],
        "claims": {
            "synthetic_validation": False,
            "hardware_dataset_accepted": False,
            "automatic_pwm_used": False,
        },
    }


def identify_motor(
    capture: Mapping[str, Any],
    prior_payload: Mapping[str, Any],
    *,
    starts: int = 5,
    seed: int = 0,
    bound_factor: float = 4.0,
    max_nfev: int = 160,
    rank_tolerance: float = 1.0e-7,
    condition_limit: float = 1.0e8,
    max_fit_nrmse: float = 3.0,
    max_validation_nrmse: float = 3.0,
    max_relative_ci_half_width: float = 0.5,
) -> dict[str, Any]:
    result = _base_result(capture, prior_payload)
    contract = validate_capture(capture)
    result["contract"] = contract.as_dict()
    if not contract.passed:
        result["blockers"].append("capture_contract_failed")
        return _finite_json(result)

    prior, prior_errors = validate_prior_payload(prior_payload, str(capture.get("motor_id", "")))
    result["prior_validation"] = {"pass": not prior_errors, "errors": prior_errors}
    if prior is None or prior_errors:
        result["blockers"].append("prior_validation_failed")
        return _finite_json(result)

    noise_scales = _noise_scales(capture)
    fit_inputs, fit_observed = _role_data(capture, "fit")
    validation_inputs, validation_observed = _role_data(capture, "validation")
    experiment_provenance = [
        {
            "id": experiment.get("id"),
            "run_id": experiment.get("run_id"),
            "role": experiment.get("role"),
            "kind": experiment.get("kind"),
            "captured_utc": experiment.get("captured_utc"),
            "load_condition_id": experiment.get("load_condition_id"),
            "motor_temperature_c": experiment.get("motor_temperature_c"),
            "voltage_source": experiment.get("voltage_source"),
        }
        for experiment in capture.get("experiments", [])
        if isinstance(experiment, Mapping)
    ]
    fit_run_ids = sorted(
        {str(item["run_id"]) for item in experiment_provenance if item["role"] == "fit"}
    )
    validation_run_ids = sorted(
        {str(item["run_id"]) for item in experiment_provenance if item["role"] == "validation"}
    )
    result["dataset"] = {
        "fit_experiments": [experiment.experiment_id for experiment in fit_inputs],
        "validation_experiments": [experiment.experiment_id for experiment in validation_inputs],
        "fit_samples": int(fit_observed.i_alpha.size),
        "validation_samples": int(validation_observed.i_alpha.size),
        "fit_run_ids": fit_run_ids,
        "validation_run_ids": validation_run_ids,
        "experiment_provenance": experiment_provenance,
        "noise_std": {
            "i_alpha_a": noise_scales[0],
            "i_beta_a": noise_scales[1],
            "omega_rad_s": noise_scales[2],
        },
    }

    prior_rank = analyze_rank(
        sensitivity_matrix(prior, fit_inputs, noise_scales),
        rank_tolerance=rank_tolerance,
        condition_limit=condition_limit,
    )
    result["rank_gate_prior"] = prior_rank.as_dict()
    if not prior_rank.identifiable:
        result["blockers"].append("rank_gate_failed")
        return _finite_json(result)

    estimate = fit_parameters(
        fit_observed,
        prior,
        fit_inputs,
        noise_scales,
        starts=starts,
        seed=seed,
        bound_factor=bound_factor,
        max_nfev=max_nfev,
    )
    fit_modeled = simulate(estimate.params, fit_inputs, load_torque_nm=estimate.load_torque_nm)
    validation_modeled = simulate(
        estimate.params,
        validation_inputs,
        load_torque_nm=estimate.load_torque_nm,
    )
    fit_metrics = metrics(fit_observed, fit_modeled, noise_scales)
    validation_metrics = metrics(validation_observed, validation_modeled, noise_scales)
    fitted_rank = analyze_rank(
        sensitivity_matrix(estimate.params, fit_inputs, noise_scales),
        rank_tolerance=rank_tolerance,
        condition_limit=condition_limit,
    )
    intervals = approximate_confidence_intervals(
        estimate,
        fit_inputs,
        noise_scales,
        fit_metrics["normalized_rmse"],
    )
    relative_ci_half_widths = {
        name: (float(values["upper_95"]) - float(values["lower_95"]))
        / (2.0 * max(abs(float(values["estimate"])), 1.0e-15))
        for name, values in intervals.items()
        if name != "Tload"
    }
    max_ci_half_width = max(relative_ci_half_widths.values(), default=float("inf"))

    measured_peak_current = float(
        max(
            np.max(np.hypot(fit_observed.i_alpha, fit_observed.i_beta)),
            np.max(np.hypot(validation_observed.i_alpha, validation_observed.i_beta)),
        )
    )
    modeled_peak_current = float(
        max(
            np.max(np.hypot(fit_modeled.i_alpha, fit_modeled.i_beta)),
            np.max(np.hypot(validation_modeled.i_alpha, validation_modeled.i_beta)),
        )
    )
    minimum_successful_starts = max(1, math.ceil(starts / 2.0))
    acceptance_checks = {
        "rank_gate_fitted": fitted_rank.identifiable,
        "optimizer_starts": estimate.successful_starts >= minimum_successful_starts,
        "optimizer_not_on_bound": not estimate.hit_bound,
        "fit_residual": fit_metrics["normalized_rmse"] <= float(max_fit_nrmse),
        "independent_validation_residual": validation_metrics["normalized_rmse"] <= float(max_validation_nrmse),
        "confidence_interval_width": max_ci_half_width <= float(max_relative_ci_half_width),
        "measured_current_within_prior_limit": measured_peak_current <= prior.i_limit,
        "modeled_current_within_prior_limit": modeled_peak_current <= prior.i_limit,
    }
    for name, passed in acceptance_checks.items():
        if not passed:
            result["blockers"].append(name)

    accepted = all(acceptance_checks.values())
    source_kind = str(result.get("source_kind", ""))
    result.update(
        {
            "accepted": accepted,
            "decision": "accepted" if accepted else "rejected",
            # Keep the historical MIC AI loader contract while retaining explicit
            # SI-unit field names in the canonical result block.
            "estimated_params": estimate.params.as_mic_ai_estimated_dict(),
            "estimated_params_si": estimate.params.as_dict(),
            "nuisance_params": {
                "load_torque_nm": estimate.load_torque_nm,
                "load_torque_scale_nm": prior.load_torque_scale_nm,
                "load_torque_bounds_nm": [
                    -2.0 * prior.load_torque_scale_nm,
                    2.0 * prior.load_torque_scale_nm,
                ],
            },
            "optimizer": {
                "starts": estimate.starts,
                "successful_starts": estimate.successful_starts,
                "minimum_successful_starts": minimum_successful_starts,
                "cost": estimate.optimizer_cost,
                "normalized_rmse": estimate.normalized_rmse,
                "hit_bound": estimate.hit_bound,
                "bound_factor": bound_factor,
                "max_nfev": max_nfev,
                "seed": seed,
            },
            "rank_gate_fitted": fitted_rank.as_dict(),
            "fit_metrics": fit_metrics,
            "validation_metrics": validation_metrics,
            "confidence_intervals_approximate": intervals,
            "confidence_interval_audit": {
                "relative_half_widths": relative_ci_half_widths,
                "max_relative_half_width": max_ci_half_width,
                "limit": max_relative_ci_half_width,
            },
            "current_audit": {
                "measured_peak_abs_a": measured_peak_current,
                "modeled_peak_abs_a": modeled_peak_current,
                "prior_limit_a": prior.i_limit,
            },
            "acceptance": {
                "pass": accepted,
                "checks": acceptance_checks,
                "thresholds": {
                    "max_fit_nrmse": max_fit_nrmse,
                    "max_validation_nrmse": max_validation_nrmse,
                    "condition_limit": condition_limit,
                    "rank_tolerance": rank_tolerance,
                    "max_relative_ci_half_width": max_relative_ci_half_width,
                },
            },
            "claims": {
                "synthetic_validation": bool(accepted and source_kind == "synthetic"),
                "hardware_dataset_accepted": bool(accepted and source_kind == "hardware"),
                "automatic_pwm_used": False,
            },
            "integration": {
                "mic_ai_legacy_loader_compatible": True,
                "leakage_mapping": "Ls=Lr=Lm+Lsigma",
                "parameter_convention": {
                    "coordinate_system": "stationary_alpha_beta",
                    "clarke_scaling": "amplitude_invariant_2_over_3",
                    "identified_leakage": "Lsigma_equals_Lls_equals_Llr",
                    "identified_magnetizing_inductance": "Lm_is_dynamic_mutual_inductance",
                    "mcsdk_input_mapping": "LLS=Lsigma; LLR=Lsigma; LMS=Lm/1.5",
                    "mcsdk_runtime_mapping": "LM=1.5*LMS=Lm; LS=LLS+LM; LR=LLR+LM",
                },
            },
        }
    )
    return _finite_json(result)


__all__ = ["identify_motor", "validate_capture_payload", "validate_prior_payload"]

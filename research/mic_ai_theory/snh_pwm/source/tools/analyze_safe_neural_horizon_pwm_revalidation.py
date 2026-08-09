from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

CONTROLLER = "safe_neural_horizon_pwm_h2"
EXPECTED_CRITICAL_FAULT_SCENARIOS = {"fault_injection_runtime"}
DEFAULT_SCENARIOS = (
    "start_no_load",
    "start_with_load",
    "ramp_to_rated",
    "load_step",
    "load_shed",
    "reverse",
    "braking",
    "regeneration",
    "low_speed",
    "zero_speed",
    "field_weakening",
    "overload",
    "dc_sag",
    "motor_heating",
    "inverter_heating",
    "rs_error",
    "rr_error",
    "lm_error",
    "j_error",
    "random_load",
    "periodic_load",
    "shock_load",
    "two_mass_proxy",
    "current_sensor_noise",
    "speed_sensor_noise",
    "sensor_delay",
    "speed_sensor_failure",
    "current_sensor_failure",
    "ood",
    "fault_injection_runtime",
    "sensor_dropout",
)


def _worst(row: dict[str, Any], metric: str) -> float:
    raw = row.get(metric, {})
    if not isinstance(raw, dict):
        return float("nan")
    try:
        return float(raw.get("worst", float("nan")))
    except Exception:
        return float("nan")


def _mean(row: dict[str, Any], metric: str) -> float:
    raw = row.get(metric, {})
    if not isinstance(raw, dict):
        return float("nan")
    try:
        return float(raw.get("mean", float("nan")))
    except Exception:
        return float("nan")


def analyze_payload(payload: dict[str, Any]) -> dict[str, Any]:
    scenarios = [str(item) for item in payload.get("scenarios", [])]
    matrix = payload.get("matrix", {})
    effects = payload.get("paired_effects_vs_foc_svm", {})
    thresholds = payload.get("safety_thresholds", {})
    i_trip = float(thresholds.get("i_trip_a", float("nan"))) if isinstance(thresholds, dict) else float("nan")

    rows: dict[str, dict[str, Any]] = {}
    missing_controller: list[str] = []
    for scenario in scenarios:
        scenario_row = matrix.get(scenario, {}) if isinstance(matrix, dict) else {}
        controller_row = scenario_row.get(CONTROLLER) if isinstance(scenario_row, dict) else None
        if not isinstance(controller_row, dict):
            missing_controller.append(scenario)
            continue
        rows[scenario] = controller_row

    ordinary = [name for name in scenarios if name not in EXPECTED_CRITICAL_FAULT_SCENARIOS]
    unexpected_fault_scenarios: list[str] = []
    confidence_fallback_scenarios: list[str] = []
    for scenario in ordinary:
        row = rows.get(scenario, {})
        critical_metrics = (
            "fault_latch_events",
            "fault_oc_fault_steps",
            "fault_overtemp_fault_steps",
            "fault_undervoltage_fault_steps",
            "fault_overvoltage_fault_steps",
            "fault_nonfinite_fault_steps",
            "safety_violations",
            "feedback_decision_mismatch_count",
        )
        if any(_worst(row, metric) > 0.0 for metric in critical_metrics):
            unexpected_fault_scenarios.append(scenario)
        if _worst(row, "fault_ai_confidence_fault_steps") > 0.0:
            confidence_fallback_scenarios.append(scenario)

    expected_fault_checks: dict[str, bool] = {}
    for scenario in EXPECTED_CRITICAL_FAULT_SCENARIOS:
        row = rows.get(scenario, {})
        expected_fault_checks[scenario] = (
            _worst(row, "fault_latch_events") > 0.0
            and _worst(row, "fault_oc_fault_steps") > 0.0
            and _worst(row, "safety_violations") == 0.0
        )

    performance_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        effect = effects.get(scenario, {}) if isinstance(effects, dict) else {}
        controller_effect = effect.get(CONTROLLER, {}) if isinstance(effect, dict) else {}
        metrics = controller_effect.get("metrics", {}) if isinstance(controller_effect, dict) else {}
        speed = metrics.get("mean_abs_speed_error", {}) if isinstance(metrics, dict) else {}
        try:
            delta = float(speed.get("mean", float("nan")))
            ci_low = float(speed.get("ci95_normal_low", float("nan")))
            ci_high = float(speed.get("ci95_normal_high", float("nan")))
        except Exception:
            delta = ci_low = ci_high = float("nan")
        if all(math.isfinite(value) for value in (delta, ci_low, ci_high)):
            classification = "better" if ci_high < 0.0 else "worse" if ci_low > 0.0 else "inconclusive"
        else:
            classification = "missing"
        performance_rows.append(
            {
                "scenario": scenario,
                "delta_speed_error": delta,
                "ci95_low": ci_low,
                "ci95_high": ci_high,
                "classification": classification,
            }
        )

    counts = {
        label: sum(1 for row in performance_rows if row["classification"] == label)
        for label in ("better", "worse", "inconclusive", "missing")
    }
    max_current = max((_worst(row, "max_current_abs") for row in rows.values()), default=float("nan"))
    checks = {
        "hardware_claim_false": payload.get("hardware_claim") is False,
        "all_required_scenarios_present": set(DEFAULT_SCENARIOS).issubset(set(scenarios)),
        "scenario_count_at_least_31": len(scenarios) >= 31,
        "mc_trials_at_least_30": int(payload.get("mc_trials", 0)) >= 30,
        "duration_at_least_0p2s": float(payload.get("simulated_duration_s", 0.0)) >= 0.2,
        "duration_gate_pass": payload.get("dynamic_duration_gate_pass") is True,
        "paired_common_random_numbers": payload.get("paired_trial_seeds") is True,
        "controller_present_in_all_scenarios": not missing_controller,
        "no_unexpected_critical_faults": not unexpected_fault_scenarios,
        "expected_fault_injection_response": all(expected_fault_checks.values()),
        "trip_threshold_present": math.isfinite(i_trip) and i_trip > 0.0,
        "plant_current_below_trip": math.isfinite(i_trip) and math.isfinite(max_current) and max_current < i_trip,
        "paired_effects_complete": counts["missing"] == 0,
    }
    host_long_horizon_ready = all(checks.values())
    warnings = []
    if confidence_fallback_scenarios:
        warnings.append(
            "AI confidence fallback occurred in: " + ", ".join(sorted(confidence_fallback_scenarios))
        )
    if counts["worse"] or counts["inconclusive"]:
        warnings.append(
            f"speed-error comparison is not universally superior: worse={counts['worse']} "
            f"inconclusive={counts['inconclusive']}"
        )

    return {
        "status": "snh_pwm_long_horizon_revalidation",
        "host_long_horizon_ready": host_long_horizon_ready,
        "hardware_ready": False,
        "universal_superiority_supported": False,
        "checks": checks,
        "failures": [name for name, ok in checks.items() if not ok],
        "warnings": warnings,
        "scenario_count": len(scenarios),
        "mc_trials": int(payload.get("mc_trials", 0)),
        "simulated_duration_s": float(payload.get("simulated_duration_s", 0.0)),
        "safety_thresholds": thresholds,
        "max_plant_current_a": max_current,
        "unexpected_fault_scenarios": unexpected_fault_scenarios,
        "expected_fault_checks": expected_fault_checks,
        "confidence_fallback_scenarios": confidence_fallback_scenarios,
        "speed_error_classification": counts,
        "performance_rows": performance_rows,
    }


def _markdown(result: dict[str, Any]) -> str:
    counts = result["speed_error_classification"]
    lines = [
        "# SNH-PWM long-horizon revalidation",
        "",
        f"- Host ready: `{str(result['host_long_horizon_ready']).lower()}`",
        "- Hardware ready: `false`",
        f"- Scenarios: `{result['scenario_count']}`",
        f"- Monte Carlo trials: `{result['mc_trials']}`",
        f"- Duration per trial: `{result['simulated_duration_s']:.6f} s`",
        f"- Speed error vs FOC-SVM: better `{counts['better']}`, worse `{counts['worse']}`, inconclusive `{counts['inconclusive']}`",
        f"- Max plant current: `{result['max_plant_current_a']:.6f} A`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- [{'x' if ok else ' '}] `{name}`" for name, ok in result["checks"].items())
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in result["warnings"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a long-horizon SNH-PWM paired revalidation JSON.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    result = analyze_payload(payload)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["host_long_horizon_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

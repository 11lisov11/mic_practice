from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


PROPOSED = "cyclic_robust_viability_pwm"


def _worst(row: dict[str, Any], metric: str) -> float:
    payload = row.get(metric, {})
    try:
        return float(payload.get("worst", float("nan")))
    except (AttributeError, TypeError, ValueError):
        return float("nan")


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    comparison = payload.get("comparison", {})
    matrix = comparison.get("matrix", {}) if isinstance(comparison, dict) else {}
    scenarios = list(comparison.get("scenarios", [])) if isinstance(comparison, dict) else []
    paired = comparison.get("paired_effects_vs_foc_svm", {}) if isinstance(comparison, dict) else {}
    thresholds = comparison.get("safety_thresholds", {}) if isinstance(comparison, dict) else {}
    proposed_rows: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for scenario in scenarios:
        scenario_row = matrix.get(scenario, {}) if isinstance(matrix, dict) else {}
        row = scenario_row.get(PROPOSED) if isinstance(scenario_row, dict) else None
        if isinstance(row, dict):
            proposed_rows[str(scenario)] = row
        else:
            missing.append(str(scenario))

    max_current = max((_worst(row, "max_current_abs") for row in proposed_rows.values()), default=float("nan"))
    trip = float(thresholds.get("i_trip_a", float("nan"))) if isinstance(thresholds, dict) else float("nan")
    no_safety_violations = all(_worst(row, "safety_violations") == 0.0 for row in proposed_rows.values())
    ordinary_rows = {
        scenario: row for scenario, row in proposed_rows.items() if scenario != "fault_injection_runtime"
    }
    no_unexpected_latches = all(_worst(row, "fault_latch_events") == 0.0 for row in ordinary_rows.values())
    fault_injection_expected = True
    if "fault_injection_runtime" in proposed_rows:
        injected = proposed_rows["fault_injection_runtime"]
        fault_injection_expected = (
            _worst(injected, "fault_latch_events") > 0.0
            and _worst(injected, "fault_oc_fault_steps") > 0.0
            and _worst(injected, "safety_violations") == 0.0
        )
    candidate_reduction = all(
        _worst(row, "planner_mean_candidate_count") < 8.0 for row in proposed_rows.values()
    )
    predecessor_rejected = any(
        _worst(row, "planner_mean_viability_rejections") > 0.0 for row in proposed_rows.values()
    )
    predecessor_triggered = any(
        _worst(row, "planner_mean_viability_triggers") > 0.0 for row in proposed_rows.values()
    )

    classifications = {"better": 0, "worse": 0, "inconclusive": 0, "missing": 0}
    for scenario in scenarios:
        scenario_effects = paired.get(scenario, {}) if isinstance(paired, dict) else {}
        proposed_effect = scenario_effects.get(PROPOSED, {}) if isinstance(scenario_effects, dict) else {}
        metrics = proposed_effect.get("metrics", {}) if isinstance(proposed_effect, dict) else {}
        speed = metrics.get("mean_abs_speed_error", {}) if isinstance(metrics, dict) else {}
        try:
            low = float(speed["ci95_normal_low"])
            high = float(speed["ci95_normal_high"])
        except (KeyError, TypeError, ValueError):
            classifications["missing"] += 1
            continue
        if high < 0.0:
            classifications["better"] += 1
        elif low > 0.0:
            classifications["worse"] += 1
        else:
            classifications["inconclusive"] += 1

    equivariance = payload.get("equivariance_audit", {})
    falsification = payload.get("counterexample_search", {})
    checks = {
        "host_only_claim": payload.get("hardware_claim") is False,
        "novelty_not_overclaimed": payload.get("novelty_claim") is False,
        "at_least_six_scenarios": len(scenarios) >= 6,
        "at_least_three_paired_trials": int(comparison.get("mc_trials", 0)) >= 3,
        "at_least_0p05s_exploratory_duration": float(comparison.get("simulated_duration_s", 0.0)) >= 0.05,
        "proposed_controller_present": not missing and bool(proposed_rows),
        "c6_numeric_equivariance": bool(equivariance.get("pass")),
        "candidate_set_reduced": candidate_reduction,
        "no_observed_software_safety_violation": no_safety_violations,
        "no_unexpected_fault_latch": no_unexpected_latches,
        "expected_fault_injection_response": fault_injection_expected,
        "current_trip_threshold_present": math.isfinite(trip) and trip > 0.0,
        "observed_current_below_trip": math.isfinite(max_current) and math.isfinite(trip) and max_current < trip,
        "falsification_declared_incomplete": falsification.get("complete_search") is False,
        "paired_speed_effects_complete": classifications["missing"] == 0,
    }
    exploratory_ready = all(checks.values())
    publication_protocol_complete = (
        exploratory_ready
        and len(scenarios) >= 31
        and int(comparison.get("mc_trials", 0)) >= 30
        and float(comparison.get("simulated_duration_s", 0.0)) >= 0.2
    )
    warnings: list[str] = []
    if not predecessor_triggered:
        warnings.append("lazy viability predecessor was never triggered")
    elif not predecessor_rejected:
        warnings.append("viability predecessor was triggered but did not reject a candidate; its benefit is not demonstrated")
    if classifications["worse"]:
        warnings.append(f"speed error is significantly worse than FOC-SVM in {classifications['worse']} scenarios")
    if bool(falsification.get("performance_counterexample_found")):
        warnings.append("counterexample search found a parameter region with positive speed regret")
    if not publication_protocol_complete:
        warnings.append("publication protocol requires 31 scenarios, MC30 and at least 0.2 s per trial")

    return {
        "status": "c6_robust_viability_lab_audit",
        "exploratory_mathematical_ready": exploratory_ready,
        "publication_protocol_complete": publication_protocol_complete,
        "novelty_established": False,
        "hardware_ready": False,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "warnings": warnings,
        "scenario_count": len(scenarios),
        "mc_trials": int(comparison.get("mc_trials", 0)),
        "simulated_duration_s": float(comparison.get("simulated_duration_s", 0.0)),
        "max_observed_current_a": max_current,
        "current_trip_a": trip,
        "speed_error_classification": classifications,
        "viability_predecessor_triggered": predecessor_triggered,
        "viability_predecessor_rejected_candidate": predecessor_rejected,
        "unsafe_counterexample_found": bool(falsification.get("unsafe_counterexample_found")),
        "performance_counterexample_found": bool(falsification.get("performance_counterexample_found")),
    }


def _markdown(audit: dict[str, Any]) -> str:
    speed = audit["speed_error_classification"]
    lines = [
        "# C6-RV-PWM mathematical audit",
        "",
        f"- Exploratory mathematical ready: `{str(audit['exploratory_mathematical_ready']).lower()}`",
        f"- Publication protocol complete: `{str(audit['publication_protocol_complete']).lower()}`",
        "- Novelty established: `false`",
        "- Hardware ready: `false`",
        f"- Scenarios: `{audit['scenario_count']}`",
        f"- Paired trials: `{audit['mc_trials']}`",
        f"- Duration per trial: `{audit['simulated_duration_s']:.6f} s`",
        f"- Speed error vs FOC-SVM: better `{speed['better']}`, worse `{speed['worse']}`, inconclusive `{speed['inconclusive']}`",
        f"- Max observed current: `{audit['max_observed_current_a']:.6f} A`",
        f"- Viability predecessor triggered: `{str(audit['viability_predecessor_triggered']).lower()}`",
        f"- Viability predecessor rejected a candidate: `{str(audit['viability_predecessor_rejected_candidate']).lower()}`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in audit["checks"].items())
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in audit["warnings"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a C6 robust viability PWM lab JSON.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    audit = analyze(payload)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(audit), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["exploratory_mathematical_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

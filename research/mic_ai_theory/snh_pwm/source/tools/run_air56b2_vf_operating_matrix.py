from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.air56b2_nameplate_ensemble import Air56B2Nameplate
from tools.run_air56b2_vf_fidelity_study import run_study


@dataclass(frozen=True)
class VfOperatingScenario:
    scenario_id: str
    frequency_hz: float
    ramp_hz_per_s: float
    load_fraction: float
    steps: int
    minimum_final_speed_fraction_of_synchronous: float

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario_id must be non-empty")
        if not 0.0 < self.frequency_hz <= 50.0:
            raise ValueError("scenario frequency must be within (0, 50] Hz")
        if self.ramp_hz_per_s <= 0.0:
            raise ValueError("scenario ramp must be positive")
        if not 0.0 <= self.load_fraction <= 1.0:
            raise ValueError("scenario load fraction must be within [0, 1]")
        if self.steps < 1:
            raise ValueError("scenario steps must be positive")
        if not 0.0 <= self.minimum_final_speed_fraction_of_synchronous <= 1.0:
            raise ValueError("minimum final speed fraction must be within [0, 1]")


CANONICAL_SCENARIOS = (
    VfOperatingScenario("low_speed_light_load", 5.0, 25.0, 0.25, 10_000, 0.55),
    VfOperatingScenario("mid_speed_half_load", 15.0, 50.0, 0.50, 10_000, 0.70),
    VfOperatingScenario("high_speed_three_quarter_load", 30.0, 50.0, 0.75, 15_000, 0.75),
    VfOperatingScenario("rated_frequency_fan_load", 50.0, 40.0, 1.00, 25_000, 0.75),
)


def _scenario_result(
    scenario: VfOperatingScenario,
    *,
    count: int,
    master_seed: int,
) -> dict[str, Any]:
    study = run_study(
        count=count,
        steps=scenario.steps,
        master_seed=master_seed,
        frequency_command_hz=scenario.frequency_hz,
        ramp_hz_per_s=scenario.ramp_hz_per_s,
        load_fraction=scenario.load_fraction,
    )
    synchronous_speed_rpm = (
        60.0 * scenario.frequency_hz / Air56B2Nameplate().pole_pairs
    )
    final_speed_fractions = [
        trial["final_speed_rpm"] / synchronous_speed_rpm for trial in study["trials"]
    ]
    frequency_tolerance_hz = scenario.ramp_hz_per_s / 10_000.0 + 1.0e-12
    checks = {
        "base_fidelity_study_passed": study["status"] == "PASS",
        "command_frequency_reached": all(
            math.isclose(
                trial["final_frequency_hz"],
                scenario.frequency_hz,
                rel_tol=0.0,
                abs_tol=frequency_tolerance_hz,
            )
            for trial in study["trials"]
        ),
        "minimum_final_speed_reached": min(final_speed_fractions)
        >= scenario.minimum_final_speed_fraction_of_synchronous,
        "no_hidden_state_feedback": study["gates"][
            "controller_uses_no_true_state_feedback"
        ],
        "as5600_remains_teacher_only": study["gates"]["as5600_is_teacher_only"],
    }
    return {
        "scenario": asdict(scenario),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "synchronous_speed_rpm": synchronous_speed_rpm,
        "minimum_final_speed_fraction_of_synchronous": min(final_speed_fractions),
        "maximum_final_speed_fraction_of_synchronous": max(final_speed_fractions),
        "study": study,
    }


def run_operating_matrix(
    *,
    count: int,
    master_seed: int,
    scenarios: Sequence[VfOperatingScenario] = CANONICAL_SCENARIOS,
) -> dict[str, Any]:
    if count < 1:
        raise ValueError("count must be positive")
    if not scenarios:
        raise ValueError("at least one operating scenario is required")
    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("scenario identifiers must be unique")

    results = [
        _scenario_result(scenario, count=count, master_seed=master_seed)
        for scenario in scenarios
    ]
    first_reference = results[0]["study"]["f1_reference"]
    gates = {
        "all_scenarios_passed": all(result["status"] == "PASS" for result in results),
        "same_f1_ensemble_used_in_every_scenario": all(
            result["study"]["f1_reference"] == first_reference for result in results
        ),
        "controller_uses_no_true_state_feedback": all(
            result["checks"]["no_hidden_state_feedback"] for result in results
        ),
        "as5600_is_teacher_only": all(
            result["checks"]["as5600_remains_teacher_only"] for result in results
        ),
        "hardware_claim_absent": True,
    }
    all_trials = [
        trial for result in results for trial in result["study"]["trials"]
    ]
    return {
        "schema": "air56b2-vf-operating-matrix-v1",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "evidence_level": "host_simulation_only",
        "hardware_claim": False,
        "hardware_identified": False,
        "hardware_release_ready": False,
        "master_seed": int(master_seed),
        "component_seeds": results[0]["study"]["component_seeds"],
        "sample_count_per_scenario": int(count),
        "scenario_count": len(results),
        "total_trial_count": len(all_trials),
        "f1_reference": first_reference,
        "gates": gates,
        "summary": {
            "passed_scenarios": sum(result["status"] == "PASS" for result in results),
            "failed_scenarios": sum(result["status"] != "PASS" for result in results),
            "passed_trials": sum(trial["status"] == "PASS" for trial in all_trials),
            "failed_trials": sum(trial["status"] != "PASS" for trial in all_trials),
            "peak_true_current_a": max(trial["peak_true_current_a"] for trial in all_trials),
            "total_simulated_duration_s": sum(
                trial["simulated_duration_s"] for trial in all_trials
            ),
            "total_gateway_rejected_steps": sum(
                trial["gateway_rejected_steps"] for trial in all_trials
            ),
            "total_current_adc_clipped_steps": sum(
                trial["current_adc_clipped_steps"] for trial in all_trials
            ),
            "total_vdc_adc_clipped_steps": sum(
                trial["vdc_adc_clipped_steps"] for trial in all_trials
            ),
        },
        "scenarios": results,
        "limitations": [
            "The matrix covers steady fan-load operating points; it is not a fault-injection campaign.",
            "The motor family is constrained by nameplate data and priors, not bench identification.",
            "Passing this matrix does not authorize high-voltage commissioning.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the AIR56B2 scalar V/f baseline over canonical long operating points."
    )
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--master-seed", type=int, default=560225)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run_operating_matrix(count=args.count, master_seed=args.master_seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": payload["status"] == "PASS",
                "status": payload["status"],
                "scenario_count": payload["scenario_count"],
                "total_trial_count": payload["total_trial_count"],
                "output": str(args.output.resolve()),
                "hardware_release_ready": False,
            }
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
from typing import Any, Sequence


def _sign_test_upper_tail(wins: int, trials: int) -> float:
    if trials <= 0:
        return 1.0
    return float(sum(math.comb(trials, k) for k in range(wins, trials + 1)) / (2**trials))


def aggregate(payloads: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if len(payloads) < 2:
        raise ValueError("at least two independent study payloads are required")
    schemas = {payload.get("schema") for payload in payloads}
    seeds = [int(payload["seed"]) for payload in payloads]
    profile_seeds = [int(payload["protocol"]["profile_seed"]) for payload in payloads]
    design_seed_sets = [
        set(
            range(
                int(payload["protocol"]["profile_seed"]),
                int(payload["protocol"]["profile_seed"])
                + int(payload["protocol"]["design_repetitions"]),
            )
        )
        for payload in payloads
    ]
    design_seeds_disjoint = all(
        design_seed_sets[left].isdisjoint(design_seed_sets[right])
        for left in range(len(design_seed_sets))
        for right in range(left + 1, len(design_seed_sets))
    )

    paired_rows: list[tuple[float, float]] = []
    for payload in payloads:
        random_rows = {
            int(row["motor_index"]): row
            for row in payload["rows"]
            if row["method"] == "random_prbs" and row["estimate_status"] == "ok"
        }
        c6_rows = {
            int(row["motor_index"]): row
            for row in payload["rows"]
            if row["method"] == "c6_multiscale" and row["estimate_status"] == "ok"
        }
        for motor_index in sorted(set(random_rows) & set(c6_rows)):
            paired_rows.append(
                (
                    float(random_rows[motor_index]["max_relative_error"]),
                    float(c6_rows[motor_index]["max_relative_error"]),
                )
            )

    wins = sum(c6_error < random_error for random_error, c6_error in paired_rows)
    ratios = [c6 / max(random, 1.0e-15) for random, c6 in paired_rows]
    checks = {
        "schema_matches": schemas == {"mic-ai-model-based-identification-study-v1"},
        "root_seeds_unique": len(set(seeds)) == len(seeds),
        "profile_seeds_unique": len(set(profile_seeds)) == len(profile_seeds),
        "prbs_design_seed_sets_disjoint": design_seeds_disjoint,
        "fixed_sector_rank_deficient_every_series": all(
            payload["summary"]["fixed_sector"]["identifiability"]["rank"]
            < payload["summary"]["fixed_sector"]["identifiability"]["parameter_count"]
            for payload in payloads
        ),
        "c6_full_rank_every_series": all(
            payload["summary"]["c6_multiscale"]["identifiability"]["rank"]
            == payload["summary"]["c6_multiscale"]["identifiability"]["parameter_count"]
            and payload["summary"]["c6_multiscale"]["identifiability"]["gate_pass"]
            for payload in payloads
        ),
        "c6_d_information_beats_prbs_ensemble_every_series": all(
            float(payload["design_robustness"]["c6_information_win_rate"]) >= 0.90
            and float(payload["design_robustness"]["c6_information_sign_test_p_value_one_sided"])
            <= 0.01
            for payload in payloads
        ),
        "c6_median_target_error_below_5pct_every_series": all(
            float(payload["summary"]["c6_multiscale"]["median_max_relative_error"]) <= 0.05
            for payload in payloads
        ),
        "truth_restricted_to_post_fit_audit": all(
            payload["protocol"]["truth_used_for"] == "post-fit synthetic error audit only"
            for payload in payloads
        ),
        "separate_leakages_rejected_as_unidentifiable": all(
            int(payload["model_structure_audit"]["separate_leakage_rank"])
            < int(payload["model_structure_audit"]["separate_leakage_parameter_count"])
            and payload["model_structure_audit"]["separate_leakage_identifiable"] is False
            for payload in payloads
        ),
        "admissible_profiles_no_current_limit_exceedance": all(
            int(payload["summary"][method]["current_limit_exceedances"]) == 0
            for payload in payloads
            for method in ("random_prbs", "c6_multiscale")
        ),
    }
    sign_p = _sign_test_upper_tail(wins, len(paired_rows))
    replication_pass = all(checks.values())

    return {
        "schema": "mic-ai-model-based-identification-aggregate-v1",
        "series": len(payloads),
        "root_seeds": seeds,
        "profile_seeds": profile_seeds,
        "paired_trials": len(paired_rows),
        "c6_wins": wins,
        "c6_win_rate": wins / max(len(paired_rows), 1),
        "c6_win_sign_test_p_value_one_sided": sign_p,
        "median_c6_to_random_max_error_ratio": (
            float(statistics.median(ratios)) if ratios else None
        ),
        "checks": checks,
        "confirmatory_replication_pass": replication_pass,
        "claims": {
            "simulation_evidence": replication_pass,
            "hardware_validated": False,
            "world_novelty_established": False,
            "defensible_scientific_novelty_candidate": replication_pass,
            "scope": (
                "Independent synthetic-model evidence for identifiability-gated C6 multiscale "
                "excitation; physical accuracy and literature-wide priority remain unproven."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate independent identification studies")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in args.inputs]
    result = aggregate(payloads)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["confirmatory_replication_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

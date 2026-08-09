from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.cyclic_conformal_reachability import binomial_lower_tail


def _sign_test(wins: int, total: int) -> float:
    return sum(math.comb(total, index) for index in range(wins, total + 1)) / (2.0**total)


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("configuration", {})
    rows = payload.get("repetitions", [])
    alpha = float(config.get("alpha", float("nan")))
    calibration_count = int(config.get("calibration_trajectories", 0))
    expected_rank = math.ceil((calibration_count + 1) * (1.0 - alpha)) if 0.0 < alpha < 1.0 else -1
    c6_cover = 0
    c6_total = 0
    c6_ood_cover = 0
    c6_ood_total = 0
    ratios: list[float] = []
    ranks: list[int] = []
    all_seeds: list[int] = []
    malformed_rows = 0

    for row in rows:
        try:
            methods = row["methods"]
            c6 = methods["c6_canonical"]
            raw = methods["raw_global"]
            held = c6["held_out"]
            ood = c6["ood_span_1p75"]
            c6_cover += int(held["covered_trajectories"])
            c6_total += int(held["total_trajectories"])
            c6_ood_cover += int(ood["covered_trajectories"])
            c6_ood_total += int(ood["total_trajectories"])
            c6_log = float(held["log10_volume"])
            raw_log = float(raw["held_out"]["log10_volume"])
            ratios.append(10.0 ** (c6_log - raw_log))
            ranks.append(int(c6["tube"]["finite_sample_rank"]))
            all_seeds.extend(int(seed) for seed in row["split_seeds"])
        except (KeyError, TypeError, ValueError, OverflowError):
            malformed_rows += 1

    repetitions = len(rows)
    wins = sum(ratio < 1.0 for ratio in ratios)
    sign_p = _sign_test(wins, len(ratios)) if ratios else float("nan")
    median_ratio = statistics.median(ratios) if ratios else float("nan")
    target = 1.0 - alpha
    coverage = c6_cover / c6_total if c6_total else float("nan")
    coverage_p = binomial_lower_tail(c6_cover, c6_total, target) if c6_total else float("nan")
    ood_coverage = c6_ood_cover / c6_ood_total if c6_ood_total else float("nan")
    equivariance = payload.get("equivariance_audit", {})

    checks = {
        "raw_rows_well_formed": malformed_rows == 0 and len(ratios) == repetitions,
        "protocol_has_at_least_24_repetitions": repetitions >= 24,
        "protocol_has_independent_training_split": int(config.get("training_trajectories", 0)) >= 200,
        "protocol_has_at_least_400_calibration_blocks": calibration_count >= 400,
        "protocol_has_at_least_800_test_blocks": int(config.get("test_trajectories", 0)) >= 800,
        "protocol_scores_at_least_40_switching_steps": int(config.get("scored_steps_per_trajectory", 0)) >= 40,
        "all_split_seeds_are_globally_unique": len(all_seeds) == len(set(all_seeds)) == 4 * repetitions,
        "finite_sample_rank_recomputed": bool(ranks) and all(rank == expected_rank for rank in ranks),
        "c6_equivariance_recomputed": bool(equivariance.get("pass")),
        "pooled_coverage_not_significantly_below_target_1pct": math.isfinite(coverage_p) and coverage_p >= 0.01,
        "median_hypervolume_reduction_at_least_10pct": math.isfinite(median_ratio) and median_ratio <= 0.90,
        "paired_sharpness_sign_test_below_5pct": math.isfinite(sign_p) and sign_p < 0.05,
        "ood_exchangeability_limit_exposed": (
            math.isfinite(coverage) and math.isfinite(ood_coverage) and ood_coverage <= coverage - 0.20
        ),
        "world_novelty_not_overclaimed": payload.get("world_novelty_established") is False,
        "hardware_safety_not_claimed": payload.get("hardware_claim") is False,
    }
    return {
        "status": "independent_c6_conformal_reachability_audit",
        "defensible_scientific_novelty_candidate": all(checks.values()),
        "world_novelty_established": False,
        "hardware_ready": False,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "repetitions": repetitions,
        "c6_held_out_coverage": coverage,
        "target_coverage": target,
        "pooled_undercoverage_p_value": coverage_p,
        "c6_ood_coverage": ood_coverage,
        "median_c6_to_raw_hypervolume_ratio": median_ratio,
        "c6_sharpness_wins": wins,
        "paired_sign_test_p_value": sign_p,
        "finite_sample_rank": expected_rank,
        "claim_boundary": (
            "candidate method and finite-sample marginal block-coverage result in a host mathematical model; "
            "not an exhaustive priority search, recursive guarantee, OOD guarantee, or hardware validation"
        ),
    }


def _markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Independent C6 conformal reachability audit",
        "",
        f"- Defensible scientific novelty candidate: `{str(audit['defensible_scientific_novelty_candidate']).lower()}`",
        "- World novelty established: `false`",
        "- Hardware ready: `false`",
        f"- Repetitions: `{audit['repetitions']}`",
        f"- Held-out coverage: `{audit['c6_held_out_coverage']:.6f}` (target `{audit['target_coverage']:.6f}`)",
        f"- Undercoverage p-value: `{audit['pooled_undercoverage_p_value']:.6g}`",
        f"- OOD coverage: `{audit['c6_ood_coverage']:.6f}`",
        f"- Median C6/raw 5D hypervolume ratio: `{audit['median_c6_to_raw_hypervolume_ratio']:.6f}`",
        f"- Paired sign-test p-value: `{audit['paired_sign_test_p_value']:.6g}`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in audit["checks"].items())
    lines.extend(["", "## Claim boundary", "", audit["claim_boundary"], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently audit a C6 conformal reachability lab JSON.")
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
    return 0 if audit["defensible_scientific_novelty_candidate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

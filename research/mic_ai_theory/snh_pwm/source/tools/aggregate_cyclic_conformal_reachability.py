from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.cyclic_conformal_reachability import binomial_lower_tail
from tools.analyze_cyclic_conformal_reachability_lab import analyze


def _sign_test(wins: int, total: int) -> float:
    return sum(math.comb(total, index) for index in range(wins, total + 1)) / (2.0**total)


def aggregate(payloads: Sequence[dict[str, Any]]) -> dict[str, Any]:
    individual = [analyze(payload) for payload in payloads]
    root_seeds = [int(payload.get("configuration", {}).get("seed", -1)) for payload in payloads]
    split_seeds: list[int] = []
    ratios: list[float] = []
    covered = total = ood_covered = ood_total = 0
    protocol_keys = (
        "training_trajectories",
        "calibration_trajectories",
        "test_trajectories",
        "ood_trajectories",
        "scored_steps_per_trajectory",
        "burn_in_steps",
        "alpha",
    )
    protocols = []
    for payload in payloads:
        config = payload.get("configuration", {})
        protocols.append(tuple(config.get(key) for key in protocol_keys))
        for row in payload.get("repetitions", []):
            split_seeds.extend(int(seed) for seed in row.get("split_seeds", []))
            methods = row.get("methods", {})
            c6 = methods.get("c6_canonical", {})
            raw = methods.get("raw_global", {})
            held = c6.get("held_out", {})
            ood = c6.get("ood_span_1p75", {})
            covered += int(held.get("covered_trajectories", 0))
            total += int(held.get("total_trajectories", 0))
            ood_covered += int(ood.get("covered_trajectories", 0))
            ood_total += int(ood.get("total_trajectories", 0))
            c6_log = float(held.get("log10_volume", float("nan")))
            raw_log = float(raw.get("held_out", {}).get("log10_volume", float("nan")))
            ratios.append(10.0 ** (c6_log - raw_log))

    coverage = covered / total if total else float("nan")
    ood_coverage = ood_covered / ood_total if ood_total else float("nan")
    alpha = float(payloads[0].get("configuration", {}).get("alpha", float("nan"))) if payloads else float("nan")
    target = 1.0 - alpha
    coverage_p = binomial_lower_tail(covered, total, target) if total else float("nan")
    wins = sum(ratio < 1.0 for ratio in ratios)
    sign_p = _sign_test(wins, len(ratios)) if ratios else float("nan")
    median_ratio = statistics.median(ratios) if ratios else float("nan")
    checks = {
        "at_least_two_confirmatory_series": len(payloads) >= 2,
        "all_individual_audits_pass": bool(individual) and all(
            audit.get("defensible_scientific_novelty_candidate") for audit in individual
        ),
        "root_seeds_are_unique": len(root_seeds) == len(set(root_seeds)) and all(seed >= 0 for seed in root_seeds),
        "all_split_seeds_are_unique_across_series": (
            bool(split_seeds) and len(split_seeds) == len(set(split_seeds))
        ),
        "protocol_is_identical_across_series": bool(protocols) and len(set(protocols)) == 1,
        "at_least_48_total_repetitions": len(ratios) >= 48,
        "aggregate_coverage_not_significantly_below_target_1pct": (
            math.isfinite(coverage_p) and coverage_p >= 0.01
        ),
        "aggregate_median_hypervolume_reduction_at_least_10pct": (
            math.isfinite(median_ratio) and median_ratio <= 0.90
        ),
        "aggregate_paired_sharpness_sign_test_below_5pct": (
            math.isfinite(sign_p) and sign_p < 0.05
        ),
        "aggregate_ood_limit_exposed": (
            math.isfinite(coverage) and math.isfinite(ood_coverage) and ood_coverage <= coverage - 0.20
        ),
    }
    return {
        "status": "c6_conformal_confirmatory_replication_audit",
        "confirmatory_replication_pass": all(checks.values()),
        "defensible_scientific_novelty_candidate": all(checks.values()),
        "world_novelty_established": False,
        "hardware_ready": False,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "root_seeds": root_seeds,
        "series_count": len(payloads),
        "total_repetitions": len(ratios),
        "covered_trajectories": covered,
        "test_trajectories": total,
        "aggregate_held_out_coverage": coverage,
        "target_coverage": target,
        "aggregate_undercoverage_p_value": coverage_p,
        "aggregate_ood_coverage": ood_coverage,
        "median_c6_to_raw_hypervolume_ratio": median_ratio,
        "c6_sharpness_wins": wins,
        "paired_sign_test_p_value": sign_p,
        "individual_audits": individual,
    }


def _markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# C6-BCR confirmatory replication audit",
        "",
        f"- Replication pass: `{str(audit['confirmatory_replication_pass']).lower()}`",
        "- World novelty established: `false`",
        "- Hardware ready: `false`",
        f"- Root seeds: `{audit['root_seeds']}`",
        f"- Total repetitions: `{audit['total_repetitions']}`",
        f"- Aggregate held-out coverage: `{audit['aggregate_held_out_coverage']:.6f}`",
        f"- Target coverage: `{audit['target_coverage']:.6f}`",
        f"- Aggregate undercoverage p-value: `{audit['aggregate_undercoverage_p_value']:.6g}`",
        f"- Aggregate OOD coverage: `{audit['aggregate_ood_coverage']:.6f}`",
        f"- Median C6/raw 5D hypervolume ratio: `{audit['median_c6_to_raw_hypervolume_ratio']:.6f}`",
        f"- C6 sharpness wins: `{audit['c6_sharpness_wins']}/{audit['total_repetitions']}`",
        f"- Paired sign-test p-value: `{audit['paired_sign_test_p_value']:.6g}`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in audit["checks"].items())
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate independent C6-BCR confirmatory series.")
    parser.add_argument("input_json", type=Path, nargs="+")
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in args.input_json]
    audit = aggregate(payloads)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(audit), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["confirmatory_replication_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

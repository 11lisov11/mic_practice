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

from control.cyclic_conformal_reachability import binomial_lower_confidence_bound, binomial_lower_tail
from tools.analyze_cyclic_conformal_reachability_lab import analyze


def _sign_test(wins: int, total: int) -> float:
    return sum(math.comb(total, index) for index in range(wins, total + 1)) / (2.0**total)


def aggregate(payloads: Sequence[dict[str, Any]]) -> dict[str, Any]:
    individual = [analyze(payload) for payload in payloads]
    root_seeds = [int(payload.get("configuration", {}).get("seed", -1)) for payload in payloads]
    split_seeds: list[int] = []
    probe_seeds: list[int] = []
    ratios: list[float] = []
    covered = total = ood_covered = ood_total = 0
    probe_covered = probe_total = 0
    protocol_keys = (
        "training_trajectories",
        "calibration_trajectories",
        "test_trajectories",
        "ood_trajectories",
        "scored_steps_per_trajectory",
        "burn_in_steps",
        "alpha",
        "coverage_probe_repetitions",
        "coverage_noninferiority_margin",
        "coverage_error_probability",
        "sharpness_ratio_threshold",
        "shape_quantile",
    )
    protocols = []
    protocol_hashes = [str(audit.get("protocol_sha256", "")) for audit in individual]
    for payload in payloads:
        config = payload.get("configuration", {})
        protocols.append(tuple(config.get(key) for key in protocol_keys))
        probe = payload.get("independent_coverage_probe", {})
        probe_covered += int(probe.get("covered_probes", 0))
        probe_total += int(probe.get("probe_repetitions", 0))
        if probe.get("training_seed") is not None:
            probe_seeds.append(int(probe["training_seed"]))
        for row in probe.get("rows", []):
            probe_seeds.extend([int(row["calibration_seed"]), int(row["test_seed"])])
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
    first_config = payloads[0].get("configuration", {}) if payloads else {}
    noninferiority_margin = float(first_config.get("coverage_noninferiority_margin", float("nan")))
    coverage_error_probability = float(first_config.get("coverage_error_probability", float("nan")))
    sharpness_threshold = float(first_config.get("sharpness_ratio_threshold", float("nan")))
    noninferiority_threshold = target - noninferiority_margin
    probe_coverage = probe_covered / probe_total if probe_total else float("nan")
    probe_coverage_p = binomial_lower_tail(probe_covered, probe_total, target) if probe_total else float("nan")
    probe_lcb = (
        binomial_lower_confidence_bound(
            probe_covered,
            probe_total,
            error_probability=coverage_error_probability,
        )
        if probe_total > 0 and 0.0 < coverage_error_probability < 1.0
        else float("nan")
    )
    sharpness_non_ties = [
        ratio
        for ratio in ratios
        if math.isfinite(sharpness_threshold)
        and not math.isclose(ratio, sharpness_threshold, rel_tol=0.0, abs_tol=1.0e-15)
    ]
    wins = sum(ratio < sharpness_threshold for ratio in sharpness_non_ties)
    sign_p = _sign_test(wins, len(sharpness_non_ties)) if sharpness_non_ties else float("nan")
    median_ratio = statistics.median(ratios) if ratios else float("nan")
    checks = {
        "at_least_two_confirmatory_series": len(payloads) >= 2,
        "all_individual_host_method_audits_pass": bool(individual) and all(
            audit.get("host_method_evidence_pass") for audit in individual
        ),
        "root_seeds_are_unique": len(root_seeds) == len(set(root_seeds)) and all(seed >= 0 for seed in root_seeds),
        "root_seeds_are_disjoint_from_all_generation_streams": not set(root_seeds).intersection(
            split_seeds + probe_seeds
        ),
        "all_split_seeds_are_unique_across_series": (
            bool(split_seeds) and len(split_seeds) == len(set(split_seeds))
        ),
        "all_independent_probe_seeds_are_unique_across_series": (
            bool(probe_seeds)
            and len(probe_seeds) == len(set(probe_seeds))
            and not set(probe_seeds).intersection(split_seeds)
        ),
        "protocol_is_identical_across_series": bool(protocols) and len(set(protocols)) == 1,
        "protocol_source_hash_is_identical_across_series": bool(protocol_hashes)
        and all(protocol_hashes)
        and len(set(protocol_hashes)) == 1,
        "at_least_48_total_repetitions": len(ratios) >= 48,
        "at_least_800_total_independent_coverage_probes": probe_total >= 800,
        "aggregate_independent_probe_coverage_noninferiority_lcb99": (
            math.isfinite(probe_lcb) and probe_lcb >= noninferiority_threshold
        ),
        "aggregate_median_hypervolume_reduction_at_least_10pct": (
            math.isfinite(median_ratio) and median_ratio <= 0.90
        ),
        "aggregate_paired_10pct_sharpness_sign_test_below_5pct": (
            math.isfinite(sign_p) and sign_p < 0.05
        ),
    }
    return {
        "status": "c6_conformal_confirmatory_replication_audit",
        "confirmatory_replication_pass": all(checks.values()),
        "host_method_evidence_pass": all(checks.values()),
        "defensible_scientific_novelty_candidate": False,
        "world_novelty_established": False,
        "hardware_ready": False,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "root_seeds": root_seeds,
        "protocol_sha256": protocol_hashes[0] if protocol_hashes else "",
        "series_count": len(payloads),
        "total_repetitions": len(ratios),
        "covered_trajectories": covered,
        "test_trajectories": total,
        "aggregate_held_out_coverage_descriptive": coverage,
        "target_coverage": target,
        "aggregate_independent_probe_covered": probe_covered,
        "aggregate_independent_probe_count": probe_total,
        "aggregate_independent_probe_coverage": probe_coverage,
        "aggregate_independent_probe_undercoverage_p_value": probe_coverage_p,
        "aggregate_independent_probe_lower_confidence_bound_99": probe_lcb,
        "coverage_noninferiority_margin": noninferiority_margin,
        "coverage_noninferiority_threshold": noninferiority_threshold,
        "aggregate_ood_coverage": ood_coverage,
        "median_c6_to_raw_hypervolume_ratio": median_ratio,
        "c6_sharpness_wins": wins,
        "c6_sharpness_non_ties": len(sharpness_non_ties),
        "sharpness_ratio_threshold": sharpness_threshold,
        "paired_sign_test_p_value": sign_p,
        "coverage_inference_unit": "one held-out trajectory from one independent calibration fit",
        "claim_boundary": (
            "exact lower-tail coverage inference uses only independent calibration/test probes; pooled bulk "
            "held-out and OOD trajectories remain descriptive; this host replay does not establish preregistration, "
            "scientific novelty, estimator-fed validity, recursive coverage, or hardware safety"
        ),
        "individual_audits": individual,
    }


def _markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# C6-BCR confirmatory replication audit",
        "",
        f"- Replication pass: `{str(audit['confirmatory_replication_pass']).lower()}`",
        "- Scientific novelty auto-claimed: `false`",
        "- World novelty established: `false`",
        "- Hardware ready: `false`",
        f"- Root seeds: `{audit['root_seeds']}`",
        f"- Total repetitions: `{audit['total_repetitions']}`",
        f"- Descriptive aggregate held-out coverage: `{audit['aggregate_held_out_coverage_descriptive']:.6f}`",
        f"- Target coverage: `{audit['target_coverage']:.6f}`",
        f"- Aggregate independent coverage probes: `{audit['aggregate_independent_probe_covered']}/{audit['aggregate_independent_probe_count']}`",
        f"- Aggregate independent-probe coverage: `{audit['aggregate_independent_probe_coverage']:.6f}`",
        f"- Aggregate independent-probe undercoverage p-value: `{audit['aggregate_independent_probe_undercoverage_p_value']:.6g}`",
        f"- Aggregate independent-probe exact 99% lower bound: `{audit['aggregate_independent_probe_lower_confidence_bound_99']:.6f}`",
        f"- Coverage non-inferiority threshold: `{audit['coverage_noninferiority_threshold']:.6f}`",
        f"- Aggregate OOD coverage: `{audit['aggregate_ood_coverage']:.6f}`",
        f"- Median C6/raw 5D hypervolume ratio: `{audit['median_c6_to_raw_hypervolume_ratio']:.6f}`",
        f"- C6 >=10% sharpness wins: `{audit['c6_sharpness_wins']}/{audit['c6_sharpness_non_ties']}`",
        f"- Paired 10% sign-test p-value: `{audit['paired_sign_test_p_value']:.6g}`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in audit["checks"].items())
    lines.extend(["", "## Claim boundary", "", audit["claim_boundary"]])
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

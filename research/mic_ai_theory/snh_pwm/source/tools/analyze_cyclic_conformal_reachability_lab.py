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

from control.cyclic_conformal_reachability import (
    binomial_lower_confidence_bound,
    binomial_lower_tail,
    evaluate_tube,
    fit_conformal_tube,
)
from tools.run_cyclic_conformal_reachability_lab import (
    METHODS,
    build_protocol_manifest,
    generate_dataset,
)
from tools.run_cyclic_robust_viability_lab import run_equivariance_audit


def _sign_test(wins: int, total: int) -> float:
    return sum(math.comb(total, index) for index in range(wins, total + 1)) / (2.0**total)


def _int_or(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _float_or(value: Any, default: float = float("nan")) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _structures_close(actual: Any, expected: Any) -> bool:
    if isinstance(actual, dict) and isinstance(expected, dict):
        actual_by_key = {str(key): value for key, value in actual.items()}
        expected_by_key = {str(key): value for key, value in expected.items()}
        return actual_by_key.keys() == expected_by_key.keys() and all(
            _structures_close(actual_by_key[key], expected_by_key[key]) for key in actual_by_key
        )
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(
            _structures_close(left, right) for left, right in zip(actual, expected)
        )
    if type(actual) is bool or type(expected) is bool:
        return type(actual) is bool and type(expected) is bool and actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isfinite(float(actual)) and math.isfinite(float(expected)) and math.isclose(
            float(actual), float(expected), rel_tol=1.0e-12, abs_tol=1.0e-15
        )
    return actual == expected


def _replay_experiment(
    payload: dict[str, Any],
    config: dict[str, Any],
    rows: list[Any],
    probe: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    try:
        training_count = int(config["training_trajectories"])
        calibration_count = int(config["calibration_trajectories"])
        test_count = int(config["test_trajectories"])
        ood_count = int(config["ood_trajectories"])
        scored_steps = int(config["scored_steps_per_trajectory"])
        burn_in_steps = int(config["burn_in_steps"])
        alpha = float(config["alpha"])
        shape_quantile = float(config["shape_quantile"])
        ood_multiplier = float(config["ood_span_multiplier"])
        for row_index, saved_row in enumerate(rows):
            split_seeds = [int(value) for value in saved_row["split_seeds"]]
            if len(split_seeds) != 4:
                raise ValueError("each bulk split must contain four seeds")
            training = generate_dataset(
                count=training_count,
                seed=split_seeds[0],
                scored_steps=scored_steps,
                burn_in_steps=burn_in_steps,
            )
            calibration = generate_dataset(
                count=calibration_count,
                seed=split_seeds[1],
                scored_steps=scored_steps,
                burn_in_steps=burn_in_steps,
            )
            test = generate_dataset(
                count=test_count,
                seed=split_seeds[2],
                scored_steps=scored_steps,
                burn_in_steps=burn_in_steps,
            )
            ood = generate_dataset(
                count=ood_count,
                seed=split_seeds[3],
                scored_steps=scored_steps,
                burn_in_steps=burn_in_steps,
                span_scale=ood_multiplier,
            )
            expected_methods: dict[str, Any] = {}
            for method in METHODS:
                tube = fit_conformal_tube(
                    training,
                    calibration,
                    method=method,
                    alpha=alpha,
                    shape_quantile=shape_quantile,
                )
                expected_methods[method] = {
                    "tube": {
                        "method": tube.method,
                        "alpha": tube.alpha,
                        "shape_quantile": tube.shape_quantile,
                        "calibration_quantile": tube.calibration_quantile,
                        "finite_sample_rank": tube.finite_sample_rank,
                        "training_trajectories": tube.training_trajectories,
                        "calibration_trajectories": tube.calibration_trajectories,
                        "scales_by_key": tube.scales_by_key,
                    },
                    "held_out": evaluate_tube(tube, test),
                    "ood_span_1p75": evaluate_tube(tube, ood),
                }
            if not _structures_close(saved_row.get("methods"), expected_methods):
                failures.append(f"bulk repetition {row_index} does not replay")
                continue
            raw_log = float(expected_methods["raw_global"]["held_out"]["log10_volume"])
            c6_log = float(expected_methods["c6_canonical"]["held_out"]["log10_volume"])
            sector_log = float(expected_methods["sectorwise"]["held_out"]["log10_volume"])
            if not _structures_close(saved_row.get("c6_to_raw_volume_ratio"), 10.0 ** (c6_log - raw_log)):
                failures.append(f"bulk repetition {row_index} C6/raw ratio mismatch")
            if not _structures_close(
                saved_row.get("c6_to_sectorwise_volume_ratio"),
                10.0 ** (c6_log - sector_log),
            ):
                failures.append(f"bulk repetition {row_index} C6/sectorwise ratio mismatch")

        if probe.get("status") == "independent_calibration_test_coverage_probe":
            fixed_training = generate_dataset(
                count=training_count,
                seed=int(probe["training_seed"]),
                scored_steps=scored_steps,
                burn_in_steps=burn_in_steps,
            )
            for row_index, saved_probe_row in enumerate(probe.get("rows", [])):
                calibration = generate_dataset(
                    count=calibration_count,
                    seed=int(saved_probe_row["calibration_seed"]),
                    scored_steps=scored_steps,
                    burn_in_steps=burn_in_steps,
                )
                test = generate_dataset(
                    count=1,
                    seed=int(saved_probe_row["test_seed"]),
                    scored_steps=scored_steps,
                    burn_in_steps=burn_in_steps,
                )[0]
                tube = fit_conformal_tube(
                    fixed_training,
                    calibration,
                    method="c6_canonical",
                    alpha=alpha,
                    shape_quantile=shape_quantile,
                )
                score = float(tube.trajectory_score(test))
                expected_row = {
                    "probe": row_index,
                    "calibration_seed": int(saved_probe_row["calibration_seed"]),
                    "test_seed": int(saved_probe_row["test_seed"]),
                    "finite_sample_rank": int(tube.finite_sample_rank),
                    "calibration_quantile": float(tube.calibration_quantile),
                    "test_score": score,
                    "covered": bool(score <= tube.calibration_quantile + 1.0e-15),
                }
                if not _structures_close(saved_probe_row, expected_row):
                    failures.append(f"independent probe {row_index} does not replay")

        replayed_equivariance = run_equivariance_audit(
            samples=500,
            seed=int(config["seed"]) ^ 0xC6C6,
        )
        if not _structures_close(payload.get("equivariance_audit"), replayed_equivariance):
            failures.append("equivariance audit does not replay")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        failures.append(f"replay error: {exc}")
    return {"pass": not failures, "failures": failures}


def analyze(payload: dict[str, Any], *, replay: bool = True) -> dict[str, Any]:
    config = payload.get("configuration", {})
    rows = payload.get("repetitions", [])
    config = config if isinstance(config, dict) else {}
    rows = rows if isinstance(rows, list) else []
    alpha = _float_or(config.get("alpha"))
    calibration_count = _int_or(config.get("calibration_trajectories", 0))
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
    sharpness_threshold = _float_or(config.get("sharpness_ratio_threshold"))
    sharpness_non_ties = [
        ratio
        for ratio in ratios
        if math.isfinite(sharpness_threshold)
        and not math.isclose(ratio, sharpness_threshold, rel_tol=0.0, abs_tol=1.0e-15)
    ]
    wins = sum(ratio < sharpness_threshold for ratio in sharpness_non_ties)
    sign_p = _sign_test(wins, len(sharpness_non_ties)) if sharpness_non_ties else float("nan")
    median_ratio = statistics.median(ratios) if ratios else float("nan")
    target = 1.0 - alpha
    coverage = c6_cover / c6_total if c6_total else float("nan")
    ood_coverage = c6_ood_cover / c6_ood_total if c6_ood_total else float("nan")
    equivariance = payload.get("equivariance_audit", {})
    probe = payload.get("independent_coverage_probe", {})
    probe_rows = probe.get("rows", []) if isinstance(probe, dict) else []
    probe_count = _int_or(probe.get("probe_repetitions", 0)) if isinstance(probe, dict) else 0
    probe_covered = _int_or(probe.get("covered_probes", 0)) if isinstance(probe, dict) else 0
    probe_coverage = probe_covered / probe_count if probe_count else float("nan")
    probe_p = (
        binomial_lower_tail(probe_covered, probe_count, target)
        if probe_count > 0 and math.isfinite(target)
        else float("nan")
    )
    coverage_error_probability = _float_or(config.get("coverage_error_probability"))
    noninferiority_margin = _float_or(config.get("coverage_noninferiority_margin"))
    noninferiority_threshold = target - noninferiority_margin
    probe_lcb = (
        binomial_lower_confidence_bound(
            probe_covered,
            probe_count,
            error_probability=coverage_error_probability,
        )
        if probe_count > 0
        and math.isfinite(coverage_error_probability)
        and 0.0 < coverage_error_probability < 1.0
        else float("nan")
    )
    probe_seeds: list[int] = []
    probe_rows_well_formed = isinstance(probe_rows, list) and len(probe_rows) == probe_count
    probe_covered_from_rows = 0
    probe_ranks: list[int] = []
    probe_indices: list[int] = []
    seed_pairs_from_rows: list[list[int]] = []
    if isinstance(probe, dict) and probe.get("training_seed") is not None:
        try:
            probe_seeds.append(int(probe["training_seed"]))
        except (TypeError, ValueError, OverflowError):
            probe_rows_well_formed = False
    for row in probe_rows if isinstance(probe_rows, list) else []:
        try:
            calibration_seed = int(row["calibration_seed"])
            test_seed = int(row["test_seed"])
            quantile = float(row["calibration_quantile"])
            score = float(row["test_score"])
            covered_value = row["covered"]
            if type(covered_value) is not bool:
                raise ValueError("covered must be boolean")
            probe_indices.append(int(row["probe"]))
            seed_pairs_from_rows.append([calibration_seed, test_seed])
            probe_seeds.extend([calibration_seed, test_seed])
            probe_ranks.append(int(row["finite_sample_rank"]))
            probe_covered_from_rows += int(covered_value)
            probe_rows_well_formed = (
                probe_rows_well_formed
                and math.isfinite(quantile)
                and math.isfinite(score)
                and covered_value is bool(score <= quantile + 1.0e-15)
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            probe_rows_well_formed = False
    stored_probe_p = probe.get("undercoverage_p_value") if isinstance(probe, dict) else None
    stored_probe_coverage = probe.get("empirical_coverage") if isinstance(probe, dict) else None
    stored_probe_target = probe.get("target_coverage") if isinstance(probe, dict) else None
    stored_probe_significant = probe.get("significant_undercoverage_1pct") if isinstance(probe, dict) else None
    stored_probe_lcb = probe.get("lower_confidence_bound_99") if isinstance(probe, dict) else None
    stored_probe_margin = probe.get("noninferiority_margin") if isinstance(probe, dict) else None
    stored_probe_threshold = probe.get("noninferiority_threshold") if isinstance(probe, dict) else None
    stored_probe_noninferiority = probe.get("noninferiority_pass") if isinstance(probe, dict) else None
    stored_seed_pairs = probe.get("calibration_test_seed_pairs") if isinstance(probe, dict) else None
    probe_scalars_consistent = (
        probe_count > 0
        and 0 <= probe_covered <= probe_count
        and probe_covered_from_rows == probe_covered
        and probe_indices == list(range(probe_count))
        and stored_seed_pairs == seed_pairs_from_rows
        and _int_or(config.get("coverage_probe_repetitions", -1), -1) == probe_count
        and probe.get("status") == "independent_calibration_test_coverage_probe"
        and probe.get("method") == "c6_canonical"
        and probe.get("training_split_conditioned_on") is True
        and stored_probe_p is not None
        and stored_probe_coverage is not None
        and stored_probe_target is not None
        and type(stored_probe_significant) is bool
        and stored_probe_lcb is not None
        and stored_probe_margin is not None
        and stored_probe_threshold is not None
        and type(stored_probe_noninferiority) is bool
        and math.isclose(_float_or(stored_probe_p), probe_p, rel_tol=1.0e-12, abs_tol=1.0e-15)
        and math.isclose(_float_or(stored_probe_coverage), probe_coverage, rel_tol=0.0, abs_tol=1.0e-15)
        and math.isclose(_float_or(stored_probe_target), target, rel_tol=0.0, abs_tol=1.0e-15)
        and stored_probe_significant is bool(probe_p < 0.01)
        and math.isclose(_float_or(stored_probe_lcb), probe_lcb, rel_tol=1.0e-12, abs_tol=1.0e-15)
        and math.isclose(_float_or(stored_probe_margin), noninferiority_margin, rel_tol=0.0, abs_tol=1.0e-15)
        and math.isclose(_float_or(stored_probe_threshold), noninferiority_threshold, rel_tol=0.0, abs_tol=1.0e-15)
        and stored_probe_noninferiority is bool(probe_lcb >= noninferiority_threshold)
    )
    expected_protocol_manifest, expected_protocol_sha256 = build_protocol_manifest(config)
    protocol_manifest_matches = _structures_close(
        payload.get("protocol_manifest"), expected_protocol_manifest
    ) and payload.get("protocol_sha256") == expected_protocol_sha256
    replay_result = (
        _replay_experiment(payload, config, rows, probe if isinstance(probe, dict) else {})
        if replay
        else {"pass": False, "failures": ["deterministic replay disabled"]}
    )

    checks = {
        "raw_rows_well_formed": malformed_rows == 0 and len(ratios) == repetitions,
        "protocol_alpha_is_finite_and_in_open_unit_interval": math.isfinite(alpha) and 0.0 < alpha < 1.0,
        "protocol_has_at_least_24_repetitions": repetitions >= 24,
        "protocol_has_independent_training_split": _int_or(config.get("training_trajectories", 0)) >= 200,
        "protocol_has_at_least_400_calibration_blocks": calibration_count >= 400,
        "protocol_has_at_least_800_test_blocks": _int_or(config.get("test_trajectories", 0)) >= 800,
        "protocol_has_at_least_400_independent_coverage_probes": probe_count >= 400,
        "protocol_has_valid_coverage_noninferiority_margin": math.isfinite(noninferiority_margin)
        and 0.0 <= noninferiority_margin < target,
        "protocol_has_valid_coverage_error_probability": math.isfinite(coverage_error_probability)
        and 0.0 < coverage_error_probability <= 0.01,
        "protocol_has_10pct_sharpness_threshold": math.isclose(
            sharpness_threshold, 0.90, rel_tol=0.0, abs_tol=1.0e-15
        ),
        "protocol_scores_at_least_40_switching_steps": _int_or(
            config.get("scored_steps_per_trajectory", 0)
        ) >= 40,
        "bulk_split_seeds_are_globally_unique": len(all_seeds) == len(set(all_seeds)) == 4 * repetitions,
        "independent_probe_rows_well_formed": probe_rows_well_formed and probe_scalars_consistent,
        "independent_probe_seed_streams_are_globally_unique": (
            len(probe_seeds) == len(set(probe_seeds)) == 1 + 2 * probe_count
            and not set(probe_seeds).intersection(all_seeds)
        ),
        "finite_sample_rank_recomputed": bool(ranks) and all(rank == expected_rank for rank in ranks),
        "independent_probe_finite_sample_rank_recomputed": bool(probe_ranks)
        and all(rank == expected_rank for rank in probe_ranks),
        "protocol_manifest_and_source_hash_recomputed": protocol_manifest_matches,
        "deterministic_experiment_replay_pass": bool(replay_result["pass"]),
        "c6_equivariance_reported_pass": bool(equivariance.get("pass")),
        "independent_probe_coverage_noninferiority_lcb99": (
            math.isfinite(probe_lcb) and probe_lcb >= noninferiority_threshold
        ),
        "median_hypervolume_reduction_at_least_10pct": math.isfinite(median_ratio) and median_ratio <= 0.90,
        "paired_10pct_sharpness_sign_test_below_5pct": math.isfinite(sign_p) and sign_p < 0.05,
        "world_novelty_not_overclaimed": payload.get("world_novelty_established") is False,
        "scientific_novelty_not_auto_claimed": payload.get("defensible_scientific_novelty_candidate") is False,
        "preregistration_not_auto_claimed": payload.get("preregistration_claim") is False
        and payload.get("hypothesis_locked_before_test") is False,
        "oracle_state_assumption_explicit": expected_protocol_manifest.get("estimator_based") is False
        and expected_protocol_manifest.get("prediction_assumption")
        == "one_step_oracle_state_and_stator_flux_sector",
        "hardware_safety_not_claimed": payload.get("hardware_claim") is False,
    }
    host_method_evidence_pass = all(checks.values())
    return {
        "status": "independent_c6_conformal_reachability_audit",
        "host_method_evidence_pass": host_method_evidence_pass,
        "defensible_scientific_novelty_candidate": False,
        "world_novelty_established": False,
        "hardware_ready": False,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "repetitions": repetitions,
        "c6_held_out_coverage_descriptive": coverage,
        "target_coverage": target,
        "independent_probe_count": probe_count,
        "independent_probe_covered": probe_covered,
        "independent_probe_coverage": probe_coverage,
        "independent_probe_undercoverage_p_value": probe_p,
        "independent_probe_lower_confidence_bound_99": probe_lcb,
        "coverage_noninferiority_margin": noninferiority_margin,
        "coverage_noninferiority_threshold": noninferiority_threshold,
        "c6_ood_coverage": ood_coverage,
        "median_c6_to_raw_hypervolume_ratio": median_ratio,
        "c6_sharpness_wins": wins,
        "c6_sharpness_non_ties": len(sharpness_non_ties),
        "sharpness_ratio_threshold": sharpness_threshold,
        "paired_sign_test_p_value": sign_p,
        "finite_sample_rank": expected_rank,
        "protocol_sha256": expected_protocol_sha256,
        "replay": replay_result,
        "claim_boundary": (
            "candidate method and finite-sample marginal block-coverage result from independent calibration/test "
            "pairs in a one-step oracle-state host model; bulk held-out and OOD coverage are descriptive; "
            "the software audit does not establish preregistration, scientific novelty, recursive coverage, "
            "estimator-fed validity, or hardware validation"
        ),
    }


def _markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Independent C6 conformal reachability audit",
        "",
        f"- Host method evidence pass: `{str(audit['host_method_evidence_pass']).lower()}`",
        "- Scientific novelty auto-claimed: `false`",
        "- World novelty established: `false`",
        "- Hardware ready: `false`",
        f"- Repetitions: `{audit['repetitions']}`",
        f"- Descriptive bulk held-out coverage: `{audit['c6_held_out_coverage_descriptive']:.6f}`",
        f"- Independent coverage probes: `{audit['independent_probe_covered']}/{audit['independent_probe_count']}`",
        f"- Independent-probe coverage: `{audit['independent_probe_coverage']:.6f}` (target `{audit['target_coverage']:.6f}`)",
        f"- Independent-probe undercoverage p-value: `{audit['independent_probe_undercoverage_p_value']:.6g}`",
        f"- Independent-probe exact 99% lower bound: `{audit['independent_probe_lower_confidence_bound_99']:.6f}`",
        f"- Coverage non-inferiority threshold: `{audit['coverage_noninferiority_threshold']:.6f}`",
        f"- OOD coverage: `{audit['c6_ood_coverage']:.6f}`",
        f"- Median C6/raw 5D hypervolume ratio: `{audit['median_c6_to_raw_hypervolume_ratio']:.6f}`",
        f"- Paired 10% sharpness sign-test p-value: `{audit['paired_sign_test_p_value']:.6g}`",
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
    return 0 if audit["host_method_evidence_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import copy
import math
from random import Random

import pytest

from control.cyclic_conformal_reachability import (
    ResidualSample,
    ResidualTrajectory,
    binomial_lower_confidence_bound,
    binomial_lower_tail,
    evaluate_tube,
    fit_conformal_tube,
    split_conformal_quantile,
)
from control.cyclic_robust_viability_pwm import SECTOR_ANGLE, rotate_alpha_beta
from tools.run_cyclic_conformal_reachability_lab import generate_dataset, run_lab
from tools.analyze_cyclic_conformal_reachability_lab import analyze
from tools.aggregate_cyclic_conformal_reachability import aggregate


def _synthetic_trajectories(seed: int, count: int) -> list[ResidualTrajectory]:
    rng = Random(seed)
    trajectories: list[ResidualTrajectory] = []
    for trajectory_id in range(count):
        samples = []
        for _ in range(8):
            sector = rng.randrange(6)
            radial = rng.gauss(0.0, 2.0)
            tangential = rng.gauss(0.0, 0.20)
            rotor_radial = rng.gauss(0.0, 1.2)
            rotor_tangential = rng.gauss(0.0, 0.15)
            angle = sector * SECTOR_ANGLE
            ss_a, ss_b = rotate_alpha_beta(radial, tangential, angle)
            sr_a, sr_b = rotate_alpha_beta(rotor_radial, rotor_tangential, angle)
            samples.append(
                ResidualSample(
                    sector=sector,
                    values=(ss_a, ss_b, sr_a, sr_b, rng.gauss(0.0, 0.05)),
                )
            )
        trajectories.append(ResidualTrajectory(trajectory_id=trajectory_id, samples=tuple(samples)))
    return trajectories


def test_split_conformal_rank_uses_n_plus_one_correction() -> None:
    quantile, rank = split_conformal_quantile(list(range(1, 100)), alpha=0.05)
    assert rank == math.ceil(100 * 0.95)
    assert quantile == 95.0


def test_split_conformal_rejects_impossible_finite_rank() -> None:
    quantile, rank = split_conformal_quantile([1.0, 2.0, 3.0], alpha=0.05)
    assert rank == 4
    assert math.isinf(quantile)


def test_residual_blocks_reject_empty_nonfinite_or_invalid_sector_data() -> None:
    with pytest.raises(ValueError, match="sector"):
        ResidualSample(sector=6, values=(0.0, 0.0, 0.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="finite"):
        ResidualSample(sector=0, values=(0.0, 0.0, float("nan"), 0.0, 0.0))
    with pytest.raises(ValueError, match="at least one sample"):
        ResidualTrajectory(trajectory_id=0, samples=())


def test_c6_canonical_tube_is_sharper_on_rotated_anisotropic_blocks() -> None:
    rows = _synthetic_trajectories(7, 500)
    training, calibration, test = rows[:160], rows[160:320], rows[320:]
    raw = fit_conformal_tube(training, calibration, method="raw_global")
    c6 = fit_conformal_tube(training, calibration, method="c6_canonical")
    raw_eval = evaluate_tube(raw, test)
    c6_eval = evaluate_tube(c6, test)
    assert float(c6_eval["log10_volume"]) < float(raw_eval["log10_volume"])
    assert c6_eval["significant_undercoverage_1pct"] is False


def test_generated_splits_are_deterministic() -> None:
    first = generate_dataset(count=4, seed=19, scored_steps=5, burn_in_steps=2)
    second = generate_dataset(count=4, seed=19, scored_steps=5, burn_in_steps=2)
    assert first == second
    assert all(len(row.samples) == 5 for row in first)


def test_lab_smoke_has_no_hardware_or_world_novelty_claim() -> None:
    payload = run_lab(
        repetitions=1,
        training_trajectories=24,
        calibration_trajectories=30,
        test_trajectories=40,
        ood_trajectories=20,
        scored_steps=5,
        burn_in_steps=2,
        seed=31,
    )
    assert payload["world_novelty_established"] is False
    assert payload["hardware_claim"] is False
    assert payload["defensible_scientific_novelty_candidate"] is False
    assert payload["preregistration_claim"] is False
    assert payload["hypothesis_locked_before_test"] is False
    assert payload["protocol_manifest"]["estimator_based"] is False
    assert set(payload["summary"]) == {"raw_global", "sectorwise", "c6_canonical"}
    assert payload["coverage_statement"].startswith("finite-sample marginal coverage")


def test_independent_coverage_probe_uses_one_test_per_calibration_fit() -> None:
    payload = run_lab(
        repetitions=1,
        training_trajectories=24,
        calibration_trajectories=30,
        test_trajectories=40,
        ood_trajectories=20,
        scored_steps=5,
        burn_in_steps=2,
        coverage_probe_repetitions=25,
        seed=33,
    )
    probe = payload["independent_coverage_probe"]
    assert probe["probe_repetitions"] == 25
    assert len(probe["rows"]) == 25
    assert len(probe["calibration_test_seed_pairs"]) == 25
    assert probe["all_seed_streams_unique"] is True
    expected_p = binomial_lower_tail(probe["covered_probes"], 25, probe["target_coverage"])
    assert probe["undercoverage_p_value"] == pytest.approx(expected_p)
    expected_lcb = binomial_lower_confidence_bound(
        probe["covered_probes"],
        25,
        error_probability=payload["configuration"]["coverage_error_probability"],
    )
    assert probe["lower_confidence_bound_99"] == pytest.approx(expected_lcb)
    assert probe["noninferiority_pass"] is bool(expected_lcb >= probe["noninferiority_threshold"])
    assert payload["candidate_criteria"]["at_least_400_independent_coverage_probes"] is False

    audit = analyze(payload)
    assert audit["checks"]["independent_probe_rows_well_formed"] is True
    assert audit["checks"]["protocol_has_at_least_400_independent_coverage_probes"] is False


def test_independent_audit_recomputes_probe_statistics() -> None:
    payload = run_lab(
        repetitions=1,
        training_trajectories=24,
        calibration_trajectories=30,
        test_trajectories=40,
        ood_trajectories=20,
        scored_steps=5,
        burn_in_steps=2,
        coverage_probe_repetitions=8,
        seed=35,
    )
    tampered = copy.deepcopy(payload)
    tampered["independent_coverage_probe"]["undercoverage_p_value"] = -1.0
    audit = analyze(tampered)
    assert audit["checks"]["independent_probe_rows_well_formed"] is False

    tampered_row = copy.deepcopy(payload)
    tampered_row["independent_coverage_probe"]["rows"][0]["covered"] = "false"
    audit = analyze(tampered_row)
    assert audit["checks"]["independent_probe_rows_well_formed"] is False

    fabricated_score = copy.deepcopy(payload)
    fabricated_score["independent_coverage_probe"]["rows"][0]["calibration_quantile"] += 1.0
    fabricated_score["independent_coverage_probe"]["rows"][0]["test_score"] += 1.0
    audit = analyze(fabricated_score)
    assert audit["checks"]["independent_probe_rows_well_formed"] is True
    assert audit["checks"]["deterministic_experiment_replay_pass"] is False

    changed_protocol = copy.deepcopy(payload)
    changed_protocol["configuration"]["parameter_spans"]["rs_span"] = 0.9
    audit = analyze(changed_protocol)
    assert audit["checks"]["protocol_manifest_and_source_hash_recomputed"] is False


def test_invalid_alpha_is_rejected() -> None:
    rows = _synthetic_trajectories(11, 10)
    with pytest.raises(ValueError):
        fit_conformal_tube(rows[:5], rows[5:], method="raw_global", alpha=0.0)


def test_binomial_undercoverage_audit_is_numerically_stable() -> None:
    rows = _synthetic_trajectories(101, 900)
    tube = fit_conformal_tube(rows[:200], rows[200:400], method="c6_canonical")
    audit = evaluate_tube(tube, rows[400:])
    assert 0.0 <= float(audit["undercoverage_p_value"]) <= 1.0
    if float(audit["empirical_coverage"]) >= float(audit["target_coverage"]):
        assert audit["significant_undercoverage_1pct"] is False


def test_binomial_tail_matches_small_exact_case() -> None:
    assert binomial_lower_tail(0, 3, 0.5) == pytest.approx(0.125)
    assert binomial_lower_tail(1, 3, 0.5) == pytest.approx(0.5)


def test_exact_lower_coverage_bound_enforces_noninferiority() -> None:
    assert binomial_lower_confidence_bound(10, 10, error_probability=0.05) == pytest.approx(
        0.05 ** 0.1
    )
    assert binomial_lower_confidence_bound(369, 400, error_probability=0.01) < 0.92
    assert binomial_lower_confidence_bound(390, 400, error_probability=0.01) > 0.92


def test_independent_audit_rejects_smoke_protocol() -> None:
    payload = run_lab(
        repetitions=1,
        training_trajectories=24,
        calibration_trajectories=30,
        test_trajectories=40,
        ood_trajectories=20,
        scored_steps=5,
        burn_in_steps=2,
        seed=37,
    )
    audit = analyze(payload)
    assert audit["defensible_scientific_novelty_candidate"] is False
    assert audit["world_novelty_established"] is False
    assert audit["hardware_ready"] is False


def test_replication_audit_rejects_reused_root_seed() -> None:
    payload = run_lab(
        repetitions=1,
        training_trajectories=24,
        calibration_trajectories=30,
        test_trajectories=40,
        ood_trajectories=20,
        scored_steps=5,
        burn_in_steps=2,
        seed=41,
    )
    audit = aggregate([payload, payload])
    assert audit["confirmatory_replication_pass"] is False
    assert audit["checks"]["root_seeds_are_unique"] is False
    assert audit["checks"]["all_split_seeds_are_unique_across_series"] is False


def test_replication_audit_aggregates_only_independent_probe_units() -> None:
    payloads = [
        run_lab(
            repetitions=1,
            training_trajectories=24,
            calibration_trajectories=30,
            test_trajectories=40,
            ood_trajectories=20,
            scored_steps=5,
            burn_in_steps=2,
            coverage_probe_repetitions=6,
            seed=seed,
        )
        for seed in (43, 47)
    ]
    audit = aggregate(payloads)
    assert audit["aggregate_independent_probe_count"] == 12
    assert audit["checks"]["all_independent_probe_seeds_are_unique_across_series"] is True
    expected_p = binomial_lower_tail(
        audit["aggregate_independent_probe_covered"],
        audit["aggregate_independent_probe_count"],
        audit["target_coverage"],
    )
    assert audit["aggregate_independent_probe_undercoverage_p_value"] == pytest.approx(expected_p)
    expected_lcb = binomial_lower_confidence_bound(
        audit["aggregate_independent_probe_covered"],
        audit["aggregate_independent_probe_count"],
        error_probability=payloads[0]["configuration"]["coverage_error_probability"],
    )
    assert audit["aggregate_independent_probe_lower_confidence_bound_99"] == pytest.approx(expected_lcb)

    changed_protocol = copy.deepcopy(payloads)
    changed_protocol[1]["configuration"]["parameter_spans"]["rs_span"] = 0.9
    changed_audit = aggregate(changed_protocol)
    assert changed_audit["checks"]["protocol_source_hash_is_identical_across_series"] is False

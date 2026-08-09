from __future__ import annotations

import math
from random import Random

import pytest

from control.cyclic_conformal_reachability import (
    ResidualSample,
    ResidualTrajectory,
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
    assert set(payload["summary"]) == {"raw_global", "sectorwise", "c6_canonical"}
    assert payload["coverage_statement"].startswith("finite-sample marginal coverage")


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

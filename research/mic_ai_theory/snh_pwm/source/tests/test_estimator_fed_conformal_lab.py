from __future__ import annotations

import copy
import json
import math

import pytest

from tools.run_estimator_fed_conformal_lab import (
    MeasurementNoiseConfig,
    generate_paired_dataset,
    run_lab,
)
from tools.analyze_estimator_fed_conformal_lab import analyze


def test_paired_dataset_is_deterministic_and_keeps_oracle_estimator_pairing() -> None:
    first = generate_paired_dataset(count=3, seed=17, scored_steps=5, burn_in_steps=2)
    second = generate_paired_dataset(count=3, seed=17, scored_steps=5, burn_in_steps=2)
    assert first == second
    assert [row.oracle.trajectory_id for row in first] == [0, 1, 2]
    assert [row.estimator.trajectory_id for row in first] == [0, 1, 2]
    assert all(len(row.oracle.samples) == len(row.estimator.samples) == 5 for row in first)


def test_estimator_residuals_differ_from_oracle_without_receiving_true_flux() -> None:
    rows = generate_paired_dataset(count=2, seed=23, scored_steps=6, burn_in_steps=3)
    assert any(row.oracle.samples != row.estimator.samples for row in rows)
    assert all(row.state_error_samples == 6 for row in rows)
    assert all(row.sector_comparisons > 0 for row in rows)


def test_estimator_fed_lab_smoke_is_explicitly_exploratory() -> None:
    payload = run_lab(
        repetitions=2,
        training_trajectories=20,
        calibration_trajectories=30,
        test_trajectories=40,
        ood_trajectories=20,
        scored_steps=6,
        burn_in_steps=3,
        seed=29,
    )
    assert payload["estimator_based"] is True
    assert payload["protocol_manifest"]["true_flux_input_to_estimator"] is False
    assert payload["protocol_manifest"]["true_state_use"] == "simulation_target_and_diagnostics_only"
    assert payload["coverage_inference_claim"] is False
    assert payload["host_method_evidence_pass"] is False
    assert payload["scientific_novelty_claim"] is False
    assert payload["hardware_ready"] is False
    assert payload["host_exploratory_evidence_complete"] is False
    assert 0.0 <= payload["summary"]["median_estimated_sector_accuracy"] <= 1.0
    assert math.isfinite(payload["summary"]["median_estimator_to_oracle_volume_ratio"])


def test_zero_noise_nominal_dataset_has_near_perfect_sector_estimation() -> None:
    rows = generate_paired_dataset(
        count=4,
        seed=31,
        scored_steps=20,
        burn_in_steps=10,
        measurement_noise=MeasurementNoiseConfig(
            current_noise_fraction=0.0,
            current_offset_fraction=0.0,
            voltage_gain_sigma=0.0,
            voltage_noise_fraction=0.0,
            speed_noise_rad_s=0.0,
            speed_bias_rad_s=0.0,
        ),
        span_scale=0.0,
    )
    matches = sum(row.sector_matches for row in rows)
    comparisons = sum(row.sector_comparisons for row in rows)
    assert comparisons > 0
    assert matches / comparisons > 0.99


def test_measurement_noise_and_lab_counts_are_validated() -> None:
    with pytest.raises(ValueError):
        MeasurementNoiseConfig(current_noise_fraction=-0.1)
    with pytest.raises(ValueError):
        run_lab(repetitions=0)


def test_estimator_lab_analyzer_replays_and_rejects_tampering() -> None:
    payload = run_lab(
        repetitions=1,
        training_trajectories=20,
        calibration_trajectories=30,
        test_trajectories=40,
        ood_trajectories=20,
        scored_steps=6,
        burn_in_steps=3,
        seed=37,
    )
    serialized_payload = json.loads(json.dumps(payload))
    audit = analyze(serialized_payload)
    assert audit["host_exploratory_audit_pass"] is True
    assert audit["checks"]["deterministic_full_payload_replay_pass"] is True
    assert audit["host_method_evidence_pass"] is False
    assert math.isfinite(audit["derived_diagnostics"]["median_state_rmse"]["omega_m"])

    tampered = copy.deepcopy(serialized_payload)
    tampered["summary"]["median_estimator_to_oracle_volume_ratio"] *= 2.0
    tampered_audit = analyze(tampered)
    assert tampered_audit["host_exploratory_audit_pass"] is False
    assert tampered_audit["checks"]["deterministic_full_payload_replay_pass"] is False

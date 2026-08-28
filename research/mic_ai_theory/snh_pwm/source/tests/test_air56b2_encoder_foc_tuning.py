from __future__ import annotations

import json

from tools.tune_air56b2_encoder_foc_fidelity import tune_encoder_foc
from tools.tune_air56b2_foc_ensemble import tune


def test_encoder_foc_tuning_is_deterministic_and_disjoint() -> None:
    oracle = tune(
        candidate_count=2,
        train_count=1,
        validation_count=1,
        train_steps=4,
        validation_steps=4,
        top_k=1,
        master_seed=9,
    )
    kwargs = {
        "oracle_tuning_sha256": "a" * 64,
        "master_seed": 9,
        "candidate_limit": 2,
        "train_count": 1,
        "validation_count": 1,
        "train_steps": 20,
        "validation_steps": 20,
        "top_k": 1,
        "target_speed_fraction": 0.10,
        "speed_ramp_s": 0.01,
        "load_fraction": 0.0,
    }
    first = tune_encoder_foc(oracle, **kwargs)
    second = tune_encoder_foc(oracle, **kwargs)

    assert first == second
    assert first["hardware_claim"] is False
    assert first["hardware_release_ready"] is False
    assert first["train_reference"]["sample_seed"] != (
        first["validation_reference"]["sample_seed"]
    )
    assert first["gates"]["train_and_validation_are_disjoint"] is True
    assert first["gates"]["no_true_state_feedback"] is True
    assert first["feedback_contract"]["true_flux_speed_angle_to_controller"] is False
    json.dumps(first)

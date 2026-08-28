from __future__ import annotations

import hashlib
import json

import pytest

from tools.tune_air56b2_foc_ensemble import tune
from tools.run_air56b2_encoder_foc_fidelity_study import run_study


def _tuning_payload() -> dict:
    return tune(
        candidate_count=2,
        train_count=1,
        validation_count=1,
        train_steps=8,
        validation_steps=8,
        top_k=1,
        master_seed=13,
        controller_model_mode="matched_plant",
    )


def test_encoder_foc_study_is_deterministic_and_has_honest_contract() -> None:
    tuning = _tuning_payload()
    raw = json.dumps(tuning, sort_keys=True).encode("utf-8")
    kwargs = {
        "tuning_sha256": hashlib.sha256(raw).hexdigest(),
        "count": 1,
        "steps": 400,
        "master_seed": 13,
        "target_speed_fraction": 0.10,
        "speed_ramp_s": 0.01,
        "load_fraction": 0.0,
    }
    first = run_study(tuning, **kwargs)
    second = run_study(tuning, **kwargs)

    assert first == second
    assert first["hardware_claim"] is False
    assert first["hardware_release_ready"] is False
    assert first["feedback_contract"]["true_flux_speed_angle_to_controller"] is False
    assert first["feedback_contract"]["controller_load_torque_input"] == (
        "zero_open_loop_assumption"
    )
    assert first["feedback_contract"]["current_offset_handling"] == (
        "pre_pwm_zero_current_calibration"
    )
    assert first["gates"]["controller_receives_observer_state_only"] is True
    assert first["gates"]["as5600_encoder_feedback_used"] is True
    assert first["summary"]["total_true_state_feedback_steps"] == 0
    json.dumps(first)


@pytest.mark.parametrize(
    "overrides",
    [
        {"count": 0},
        {"steps": 0},
        {"target_speed_fraction": 0.0},
        {"target_speed_fraction": 1.1},
        {"speed_ramp_s": 0.0},
        {"load_fraction": -0.1},
        {"load_fraction": 1.1},
    ],
)
def test_encoder_foc_study_rejects_invalid_configuration(overrides) -> None:
    tuning = _tuning_payload()
    kwargs = {
        "tuning_sha256": "0" * 64,
        "count": 1,
        "steps": 10,
        "master_seed": 13,
        "target_speed_fraction": 0.10,
        "speed_ramp_s": 0.01,
        "load_fraction": 0.0,
    }
    kwargs.update(overrides)
    with pytest.raises(ValueError):
        run_study(tuning, **kwargs)

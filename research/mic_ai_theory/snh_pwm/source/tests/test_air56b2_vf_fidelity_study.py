from __future__ import annotations

import json

import pytest

from tools.run_air56b2_vf_fidelity_study import run_study


def test_vf_fidelity_study_is_deterministic_and_uses_no_hidden_feedback() -> None:
    first = run_study(
        count=2,
        steps=300,
        master_seed=431,
        frequency_command_hz=5.0,
        ramp_hz_per_s=500.0,
        load_fraction=0.25,
    )
    second = run_study(
        count=2,
        steps=300,
        master_seed=431,
        frequency_command_hz=5.0,
        ramp_hz_per_s=500.0,
        load_fraction=0.25,
    )

    assert first == second
    assert first["status"] == "PASS"
    assert first["hardware_claim"] is False
    assert first["hardware_identified"] is False
    assert first["model_roles"]["controller_internal_model"].startswith("F1_")
    assert first["model_roles"]["controller_load_torque_input"] == "zero_open_loop_assumption"
    assert first["model_roles"]["plant"].startswith("F2_")
    assert first["model_roles"]["dynamic_core_loss_applied"] is False
    assert first["model_roles"]["starting_torque"].startswith("F1S_")
    assert first["gates"]["controller_uses_no_true_state_feedback"] is True
    assert first["gates"]["as5600_is_teacher_only"] is True
    assert all(
        trial["checks"]["no_true_state_feedback_to_controller"]
        and trial["checks"]["as5600_not_used_by_controller"]
        and trial["controller_feedback_requested_steps"] == 0
        for trial in first["trials"]
    )
    assert all(trial["status"] == "PASS" for trial in first["trials"])
    json.dumps(first)


@pytest.mark.parametrize(
    "overrides",
    [
        {"count": 0},
        {"steps": 0},
        {"frequency_command_hz": 0.0},
        {"frequency_command_hz": 51.0},
        {"ramp_hz_per_s": 0.0},
        {"load_fraction": -0.1},
        {"load_fraction": 1.1},
    ],
)
def test_vf_fidelity_study_rejects_invalid_configuration(overrides) -> None:
    kwargs = {
        "count": 1,
        "steps": 10,
        "master_seed": 1,
        "frequency_command_hz": 5.0,
        "ramp_hz_per_s": 100.0,
        "load_fraction": 0.0,
    }
    kwargs.update(overrides)
    with pytest.raises(ValueError):
        run_study(**kwargs)

from __future__ import annotations

import json

import pytest

from tools.run_air56b2_vf_operating_matrix import (
    VfOperatingScenario,
    run_operating_matrix,
)


def test_vf_operating_matrix_is_deterministic_and_has_no_hidden_feedback() -> None:
    scenario = VfOperatingScenario("smoke", 5.0, 500.0, 0.25, 300, 0.0)
    first = run_operating_matrix(count=2, master_seed=431, scenarios=[scenario])
    second = run_operating_matrix(count=2, master_seed=431, scenarios=[scenario])

    assert first == second
    assert first["status"] == "PASS"
    assert first["hardware_release_ready"] is False
    assert first["total_trial_count"] == 2
    assert first["gates"]["controller_uses_no_true_state_feedback"] is True
    assert first["gates"]["as5600_is_teacher_only"] is True
    assert first["scenarios"][0]["checks"]["command_frequency_reached"] is True
    assert first["scenarios"][0]["study"]["model_roles"]["current_offset_handling"] == (
        "pre_pwm_zero_current_calibration"
    )
    json.dumps(first)


def test_vf_operating_matrix_rejects_empty_and_duplicate_scenarios() -> None:
    scenario = VfOperatingScenario("same", 5.0, 100.0, 0.0, 10, 0.0)
    with pytest.raises(ValueError):
        run_operating_matrix(count=1, master_seed=1, scenarios=[])
    with pytest.raises(ValueError):
        run_operating_matrix(count=1, master_seed=1, scenarios=[scenario, scenario])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scenario_id": "", "frequency_hz": 5.0, "ramp_hz_per_s": 1.0, "load_fraction": 0.0, "steps": 1, "minimum_final_speed_fraction_of_synchronous": 0.0},
        {"scenario_id": "x", "frequency_hz": 51.0, "ramp_hz_per_s": 1.0, "load_fraction": 0.0, "steps": 1, "minimum_final_speed_fraction_of_synchronous": 0.0},
        {"scenario_id": "x", "frequency_hz": 5.0, "ramp_hz_per_s": 0.0, "load_fraction": 0.0, "steps": 1, "minimum_final_speed_fraction_of_synchronous": 0.0},
        {"scenario_id": "x", "frequency_hz": 5.0, "ramp_hz_per_s": 1.0, "load_fraction": 1.1, "steps": 1, "minimum_final_speed_fraction_of_synchronous": 0.0},
        {"scenario_id": "x", "frequency_hz": 5.0, "ramp_hz_per_s": 1.0, "load_fraction": 0.0, "steps": 0, "minimum_final_speed_fraction_of_synchronous": 0.0},
        {"scenario_id": "x", "frequency_hz": 5.0, "ramp_hz_per_s": 1.0, "load_fraction": 0.0, "steps": 1, "minimum_final_speed_fraction_of_synchronous": 1.1},
    ],
)
def test_vf_operating_scenario_rejects_invalid_values(kwargs) -> None:
    with pytest.raises(ValueError):
        VfOperatingScenario(**kwargs)

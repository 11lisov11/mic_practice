from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from motor_identification.mcsdk_bridge import (
    MotorModelBridgeError,
    build_motor_model_bundle,
    canonical_sha256,
    validate_motor_model_bundle,
    validate_motor_profile,
)
from motor_identification.model import prior_from_payload


REPO = Path(__file__).resolve().parents[5]
PROFILE_PATH = REPO / "docs" / "mcsdk_acim_motor_profile.iek_air56b2_catalog_operator_confirmed_vf_candidate.json"


def _profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _accepted_result(*, source_kind: str = "hardware", motor_id: str | None = None) -> dict:
    profile = _profile()
    values = {
        "Rs": 4.2,
        "Rr": 3.6,
        "Lsigma": 0.018,
        "Lm": 0.42,
        "J": 0.0018,
        "B": 0.00012,
    }
    result = {
        "schema": "mic_ai.motor_identification.result.v1",
        "motor_id": motor_id or profile["motor_id"],
        "source_kind": source_kind,
        "capture_sha256": "a" * 64,
        "prior_sha256": "b" * 64,
        "accepted": True,
        "decision": "accepted",
        "blockers": [],
        "claims": {
            "synthetic_validation": source_kind == "synthetic",
            "hardware_dataset_accepted": source_kind == "hardware",
            "automatic_pwm_used": False,
        },
        "acceptance": {"pass": True, "checks": {"rank": True, "validation": True}},
        "estimated_params_si": {
            "Rs_ohm": values["Rs"],
            "Rr_ohm": values["Rr"],
            "Lsigma_h": values["Lsigma"],
            "Lm_h": values["Lm"],
            "J_kg_m2": values["J"],
            "B_nm_s": values["B"],
            "pole_pairs": profile["pole_pairs"],
            "i_limit_a": profile["rated_current_a"] * 1.5,
        },
        "confidence_intervals_approximate": {
            name: {
                "estimate": value,
                "lower_95": 0.9 * value,
                "upper_95": 1.1 * value,
            }
            for name, value in values.items()
        },
        "integration": {
            "parameter_convention": {
                "mcsdk_input_mapping": "LLS=Lsigma; LLR=Lsigma; LMS=Lm/1.5"
            }
        },
    }
    return result


def test_air56_profile_is_strictly_valid_and_finite() -> None:
    normalized = validate_motor_profile(_profile())
    assert normalized["pole_pairs"] == 1
    assert normalized["connection"] == "delta"
    assert normalized["rated_speed_rpm"] == 2720.0
    assert 0.0 < normalized["rated_slip"] < 0.30


def test_hardware_identification_builds_consistent_mcsdk_bundle() -> None:
    result = _accepted_result()
    bundle = build_motor_model_bundle(result, _profile())
    assert bundle["deployment_class"] == "hardware_candidate"
    assert bundle["eligible_for_foc_project_generation"] is True
    assert bundle["eligible_for_hv_release"] is False
    generated = bundle["mcsdk_generator_input_si"]
    runtime = bundle["mcsdk_runtime_equivalent_si"]
    assert math.isclose(generated["LMS_h"] * 1.5, runtime["LM_h"])
    assert math.isclose(generated["LLS_h"] + runtime["LM_h"], runtime["LS_h"])
    assert math.isclose(generated["LLR_h"] + runtime["LM_h"], runtime["LR_h"])
    assert len(canonical_sha256(bundle)) == 64
    validate_motor_model_bundle(bundle, require_hardware=True)


def test_synthetic_result_is_dry_run_only_and_rejected_by_default() -> None:
    result = _accepted_result(source_kind="synthetic")
    with pytest.raises(MotorModelBridgeError, match="hardware dataset"):
        build_motor_model_bundle(result, _profile())
    bundle = build_motor_model_bundle(result, _profile(), allow_synthetic=True)
    assert bundle["deployment_class"] == "simulation_only"
    assert bundle["eligible_for_foc_project_generation"] is False
    with pytest.raises(MotorModelBridgeError, match="hardware motor-model bundle"):
        validate_motor_model_bundle(bundle, require_hardware=True)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pole_pairs", 1.9, "finite integer"),
        ("rated_current_a", float("nan"), "finite"),
        ("rated_frequency_hz", float("inf"), "finite"),
    ],
)
def test_profile_rejects_fractional_or_nonfinite_values(field: str, value: float, message: str) -> None:
    profile = _profile()
    profile[field] = value
    with pytest.raises(MotorModelBridgeError, match=message):
        validate_motor_profile(profile)


def test_bridge_rejects_wrong_motor_and_pole_pair_count() -> None:
    with pytest.raises(MotorModelBridgeError, match="motor_id"):
        build_motor_model_bundle(_accepted_result(motor_id="another-motor"), _profile())

    result = _accepted_result()
    result["estimated_params_si"]["pole_pairs"] = 2
    with pytest.raises(MotorModelBridgeError, match="pole_pairs"):
        build_motor_model_bundle(result, _profile())


def test_bundle_validation_detects_mapping_tamper() -> None:
    bundle = build_motor_model_bundle(_accepted_result(), _profile())
    tampered = deepcopy(bundle)
    tampered["mcsdk_generator_input_si"]["LMS_h"] *= 1.01
    with pytest.raises(MotorModelBridgeError, match="LMS_h"):
        validate_motor_model_bundle(tampered)


def test_prior_rejects_fractional_pole_pairs_instead_of_truncating() -> None:
    prior = {
        "Rs_ohm": 1.0,
        "Rr_ohm": 1.0,
        "Lsigma_h": 0.01,
        "Lm_h": 0.1,
        "J_kg_m2": 0.001,
        "B_nm_s": 0.0001,
        "pole_pairs": 1.9,
        "i_limit_a": 2.0,
        "load_torque_scale_nm": 0.1,
    }
    with pytest.raises(ValueError, match="positive integer"):
        prior_from_payload(prior)

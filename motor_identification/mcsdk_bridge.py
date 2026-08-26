from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

from .schema import RESULT_SCHEMA


BUNDLE_SCHEMA = "mic_ai.motor_model_bundle.v1"
PROFILE_SCHEMA = "mic_ai.mcsdk.acim_motor_profile.v1"
PARAMETER_FIELDS = ("Rs_ohm", "Rr_ohm", "Lsigma_h", "Lm_h", "J_kg_m2", "B_nm_s")
CI_FIELDS = ("Rs", "Rr", "Lsigma", "Lm", "J", "B")


class MotorModelBridgeError(ValueError):
    pass


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite_number(
    payload: Mapping[str, Any],
    field: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    value = payload.get(field)
    if isinstance(value, bool):
        raise MotorModelBridgeError(f"{field} must be numeric, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MotorModelBridgeError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise MotorModelBridgeError(f"{field} must be finite")
    if not minimum <= number <= maximum:
        raise MotorModelBridgeError(f"{field}={number} is outside [{minimum}, {maximum}]")
    return number


def _positive_int(payload: Mapping[str, Any], field: str, *, maximum: int = 32) -> int:
    value = payload.get(field)
    if isinstance(value, bool):
        raise MotorModelBridgeError(f"{field} must be an integer, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MotorModelBridgeError(f"{field} must be an integer") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise MotorModelBridgeError(f"{field} must be a finite integer")
    integer = int(number)
    if not 1 <= integer <= maximum:
        raise MotorModelBridgeError(f"{field}={integer} is outside [1, {maximum}]")
    return integer


def validate_motor_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    if profile.get("schema") != PROFILE_SCHEMA:
        raise MotorModelBridgeError(f"profile schema must be {PROFILE_SCHEMA}")
    if profile.get("motor_type") != "acim":
        raise MotorModelBridgeError("profile motor_type must be acim")
    motor_id = str(profile.get("motor_id", "")).strip()
    motor_label = str(profile.get("motor_label", "")).strip()
    if not motor_id or not motor_label:
        raise MotorModelBridgeError("profile motor_id and motor_label must be non-empty")

    pole_pairs = _positive_int(profile, "pole_pairs")
    rated_line_voltage = _finite_number(profile, "rated_line_voltage_v", minimum=10.0, maximum=1000.0)
    rated_phase_voltage = _finite_number(profile, "rated_phase_voltage_v", minimum=5.0, maximum=1000.0)
    equivalent_phase_voltage = _finite_number(
        profile,
        "controller_equivalent_phase_voltage_v",
        minimum=5.0,
        maximum=1000.0,
    )
    rated_current = _finite_number(profile, "rated_current_a", minimum=0.01, maximum=1000.0)
    rated_frequency = _finite_number(profile, "rated_frequency_hz", minimum=1.0, maximum=1000.0)
    rated_speed = _finite_number(profile, "rated_speed_rpm", minimum=1.0, maximum=100000.0)
    rated_power = _finite_number(profile, "rated_power_w", minimum=1.0, maximum=10_000_000.0)
    connection = str(profile.get("connection", "")).strip().lower()
    if connection not in {"delta", "d", "star", "y"}:
        raise MotorModelBridgeError("profile connection must be delta/D or star/Y")

    synchronous_speed = 60.0 * rated_frequency / pole_pairs
    slip = (synchronous_speed - rated_speed) / synchronous_speed
    if not 0.0 < slip < 0.30:
        raise MotorModelBridgeError(f"rated speed implies implausible slip {slip}")
    expected_equivalent = rated_line_voltage / math.sqrt(3.0)
    if not math.isclose(equivalent_phase_voltage, expected_equivalent, rel_tol=5.0e-4, abs_tol=0.05):
        raise MotorModelBridgeError(
            "controller_equivalent_phase_voltage_v must equal rated_line_voltage_v/sqrt(3)"
        )
    if connection in {"delta", "d"} and not math.isclose(
        rated_phase_voltage,
        rated_line_voltage,
        rel_tol=1.0e-6,
        abs_tol=1.0e-6,
    ):
        raise MotorModelBridgeError("delta profile requires rated_phase_voltage_v= rated_line_voltage_v")

    return {
        "motor_id": motor_id,
        "motor_label": motor_label,
        "pole_pairs": pole_pairs,
        "rated_line_voltage_v": rated_line_voltage,
        "rated_phase_voltage_v": rated_phase_voltage,
        "controller_equivalent_phase_voltage_v": equivalent_phase_voltage,
        "rated_current_a": rated_current,
        "rated_frequency_hz": rated_frequency,
        "rated_speed_rpm": rated_speed,
        "rated_power_w": rated_power,
        "connection": "delta" if connection in {"delta", "d"} else "star",
        "synchronous_speed_rpm": synchronous_speed,
        "rated_slip": slip,
    }


def _validated_identification(
    result: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    allow_synthetic: bool,
) -> tuple[dict[str, float | int], dict[str, Any], str]:
    if result.get("schema") != RESULT_SCHEMA:
        raise MotorModelBridgeError(f"identification schema must be {RESULT_SCHEMA}")
    if result.get("accepted") is not True or result.get("decision") != "accepted":
        raise MotorModelBridgeError("identification result is not accepted")
    if result.get("blockers") not in ([], ()):
        raise MotorModelBridgeError("accepted identification result still contains blockers")
    acceptance = result.get("acceptance")
    if not isinstance(acceptance, Mapping) or acceptance.get("pass") is not True:
        raise MotorModelBridgeError("identification acceptance gate did not pass")
    checks = acceptance.get("checks")
    if not isinstance(checks, Mapping) or not checks or not all(value is True for value in checks.values()):
        raise MotorModelBridgeError("identification acceptance checks are incomplete")
    if str(result.get("motor_id", "")).strip() != profile["motor_id"]:
        raise MotorModelBridgeError("identification motor_id does not match target profile")

    source_kind = str(result.get("source_kind", "")).strip()
    claims = result.get("claims") if isinstance(result.get("claims"), Mapping) else {}
    hardware_accepted = source_kind == "hardware" and claims.get("hardware_dataset_accepted") is True
    if not hardware_accepted and not (allow_synthetic and source_kind == "synthetic"):
        raise MotorModelBridgeError("only an accepted hardware dataset may produce a deployment candidate")

    raw_params = result.get("estimated_params_si")
    if not isinstance(raw_params, Mapping):
        raise MotorModelBridgeError("identification result is missing estimated_params_si")
    ranges = {
        "Rs_ohm": (1.0e-5, 1.0e4),
        "Rr_ohm": (1.0e-5, 1.0e4),
        "Lsigma_h": (1.0e-8, 100.0),
        "Lm_h": (1.0e-8, 100.0),
        "J_kg_m2": (1.0e-9, 1.0e4),
        "B_nm_s": (1.0e-10, 1.0e4),
        "i_limit_a": (1.0e-3, 1.0e4),
    }
    params: dict[str, float | int] = {
        field: _finite_number(raw_params, field, minimum=bounds[0], maximum=bounds[1])
        for field, bounds in ranges.items()
    }
    params["pole_pairs"] = _positive_int(raw_params, "pole_pairs")
    if params["pole_pairs"] != profile["pole_pairs"]:
        raise MotorModelBridgeError("identified pole_pairs does not match target profile")

    integration = result.get("integration")
    convention = integration.get("parameter_convention") if isinstance(integration, Mapping) else None
    expected_mapping = "LLS=Lsigma; LLR=Lsigma; LMS=Lm/1.5"
    if not isinstance(convention, Mapping) or convention.get("mcsdk_input_mapping") != expected_mapping:
        raise MotorModelBridgeError("identification result lacks the explicit MCSDK inductance convention")

    intervals = result.get("confidence_intervals_approximate")
    if not isinstance(intervals, Mapping):
        raise MotorModelBridgeError("identification result is missing confidence intervals")
    normalized_intervals: dict[str, Any] = {}
    for result_name, parameter_field in zip(CI_FIELDS, PARAMETER_FIELDS):
        row = intervals.get(result_name)
        if not isinstance(row, Mapping):
            raise MotorModelBridgeError(f"confidence interval is missing {result_name}")
        estimate = _finite_number(row, "estimate", minimum=1.0e-12, maximum=1.0e6)
        lower = _finite_number(row, "lower_95", minimum=1.0e-12, maximum=1.0e6)
        upper = _finite_number(row, "upper_95", minimum=1.0e-12, maximum=1.0e6)
        if not lower <= estimate <= upper:
            raise MotorModelBridgeError(f"invalid confidence interval ordering for {result_name}")
        if not math.isclose(estimate, float(params[parameter_field]), rel_tol=1.0e-9, abs_tol=1.0e-12):
            raise MotorModelBridgeError(f"confidence interval estimate disagrees with {parameter_field}")
        normalized_intervals[result_name] = {
            "estimate": estimate,
            "lower_95": lower,
            "upper_95": upper,
        }
    return params, normalized_intervals, "hardware_candidate" if hardware_accepted else "simulation_only"


def build_motor_model_bundle(
    result: Mapping[str, Any],
    base_profile: Mapping[str, Any],
    *,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    profile = validate_motor_profile(base_profile)
    params, intervals, deployment_class = _validated_identification(
        result,
        profile,
        allow_synthetic=allow_synthetic,
    )
    rs = float(params["Rs_ohm"])
    rr = float(params["Rr_ohm"])
    leakage = float(params["Lsigma_h"])
    lm = float(params["Lm_h"])
    ls = leakage + lm
    lr = leakage + lm
    sigma = 1.0 - lm * lm / (ls * lr)
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "deployment_class": deployment_class,
        "eligible_for_foc_project_generation": deployment_class == "hardware_candidate",
        "eligible_for_hv_release": False,
        "motor": profile,
        "identified_model_si": dict(params),
        "confidence_intervals_approximate": intervals,
        "inductance_convention": {
            "identified": "Lsigma=Lls=Llr; Lm is dynamic mutual inductance",
            "mcsdk_input": "LLS=Lsigma; LLR=Lsigma; LMS=Lm/1.5",
            "mcsdk_runtime": "LM=1.5*LMS=Lm; LS=LLS+LM; LR=LLR+LM",
        },
        "mcsdk_generator_input_si": {
            "RS_ohm": rs,
            "RR_ohm": rr,
            "LLS_h": leakage,
            "LLR_h": leakage,
            "LMS_h": lm / 1.5,
            "pole_pairs": int(params["pole_pairs"]),
        },
        "mcsdk_runtime_equivalent_si": {
            "LM_h": lm,
            "LS_h": ls,
            "LR_h": lr,
            "tau_s_s": ls / rs,
            "tau_r_s": lr / rr,
            "sigma": sigma,
        },
        "provenance": {
            "base_profile_sha256": canonical_sha256(base_profile),
            "identification_result_sha256": canonical_sha256(result),
            "capture_sha256": result.get("capture_sha256"),
            "prior_sha256": result.get("prior_sha256"),
        },
        "status": (
            "hardware_identification_candidate_requires_staging_regeneration_and_review"
            if deployment_class == "hardware_candidate"
            else "synthetic_mapping_dry_run_not_for_firmware_or_hv"
        ),
    }
    validate_motor_model_bundle(bundle, require_hardware=False)
    return bundle


def validate_motor_model_bundle(
    bundle: Mapping[str, Any],
    *,
    require_hardware: bool = False,
) -> None:
    if bundle.get("schema") != BUNDLE_SCHEMA:
        raise MotorModelBridgeError(f"bundle schema must be {BUNDLE_SCHEMA}")
    deployment = bundle.get("deployment_class")
    if deployment not in {"hardware_candidate", "simulation_only"}:
        raise MotorModelBridgeError("invalid deployment_class")
    if require_hardware and deployment != "hardware_candidate":
        raise MotorModelBridgeError("hardware motor-model bundle is required")
    if bundle.get("eligible_for_hv_release") is not False:
        raise MotorModelBridgeError("motor-model bundle may never authorize HV release by itself")
    if bundle.get("eligible_for_foc_project_generation") is not (deployment == "hardware_candidate"):
        raise MotorModelBridgeError("FOC generation eligibility disagrees with deployment_class")

    profile = bundle.get("motor")
    params = bundle.get("identified_model_si")
    generator = bundle.get("mcsdk_generator_input_si")
    runtime = bundle.get("mcsdk_runtime_equivalent_si")
    if not all(isinstance(row, Mapping) for row in (profile, params, generator, runtime)):
        raise MotorModelBridgeError("bundle model blocks must be objects")
    assert isinstance(profile, Mapping) and isinstance(params, Mapping)
    assert isinstance(generator, Mapping) and isinstance(runtime, Mapping)
    if _positive_int(params, "pole_pairs") != _positive_int(profile, "pole_pairs"):
        raise MotorModelBridgeError("bundle pole-pair mismatch")

    rs = _finite_number(params, "Rs_ohm", minimum=1.0e-5, maximum=1.0e4)
    rr = _finite_number(params, "Rr_ohm", minimum=1.0e-5, maximum=1.0e4)
    leakage = _finite_number(params, "Lsigma_h", minimum=1.0e-8, maximum=100.0)
    lm = _finite_number(params, "Lm_h", minimum=1.0e-8, maximum=100.0)
    expected = {
        "RS_ohm": rs,
        "RR_ohm": rr,
        "LLS_h": leakage,
        "LLR_h": leakage,
        "LMS_h": lm / 1.5,
    }
    for field, value in expected.items():
        actual = _finite_number(generator, field, minimum=1.0e-12, maximum=1.0e6)
        if not math.isclose(actual, value, rel_tol=1.0e-12, abs_tol=1.0e-15):
            raise MotorModelBridgeError(f"bundle generator field {field} is inconsistent")
    runtime_expected = {
        "LM_h": lm,
        "LS_h": leakage + lm,
        "LR_h": leakage + lm,
        "tau_s_s": (leakage + lm) / rs,
        "tau_r_s": (leakage + lm) / rr,
        "sigma": 1.0 - lm * lm / ((leakage + lm) ** 2),
    }
    for field, value in runtime_expected.items():
        actual = _finite_number(runtime, field, minimum=0.0, maximum=1.0e9)
        if not math.isclose(actual, value, rel_tol=1.0e-12, abs_tol=1.0e-15):
            raise MotorModelBridgeError(f"bundle runtime field {field} is inconsistent")


__all__ = [
    "BUNDLE_SCHEMA",
    "MotorModelBridgeError",
    "build_motor_model_bundle",
    "canonical_sha256",
    "validate_motor_model_bundle",
    "validate_motor_profile",
]

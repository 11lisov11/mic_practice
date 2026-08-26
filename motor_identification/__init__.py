"""Fail-closed induction-motor parameter identification package."""

from .schema import CAPTURE_SCHEMA, PRIOR_SCHEMA, ContractReport, load_capture, validate_capture
from .service import identify_motor, validate_capture_payload
from .mcsdk_bridge import (
    BUNDLE_SCHEMA,
    MotorModelBridgeError,
    build_motor_model_bundle,
    validate_motor_model_bundle,
)

__all__ = [
    "BUNDLE_SCHEMA",
    "CAPTURE_SCHEMA",
    "PRIOR_SCHEMA",
    "ContractReport",
    "MotorModelBridgeError",
    "build_motor_model_bundle",
    "identify_motor",
    "load_capture",
    "validate_capture",
    "validate_capture_payload",
    "validate_motor_model_bundle",
]

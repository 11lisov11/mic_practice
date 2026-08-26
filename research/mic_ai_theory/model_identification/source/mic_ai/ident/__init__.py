"""
Identification utilities for induction motor parameter estimation.
"""

from .auto_id import run_auto_identification, run_full_identification, self_check_full_identification
from .estimators import (
    estimate_leq_from_dynamics,
    estimate_lm,
    estimate_rs_from_pulse,
    refine_params_multi_test,
    refine_params_with_model,
)
from .ident_result import IdentificationResult
from .motor_params import MotorParamsEstimated, MotorParamsTrue
from .apply import apply_estimated_params_to_env_config, load_and_apply_ident
from .signal_interface import IdentSignalInterface
from .model_based import (
    FIT_PARAMETER_NAMES,
    IdentificationDataset,
    IdentificationExperiment,
    IdentifiabilityReport,
    ParameterEstimate,
    analyze_identifiability,
    estimate_parameters,
    make_excitation_suite,
    separate_leakage_sensitivity_matrix,
    sensitivity_matrix,
    with_free_run_load_bias,
)

__all__ = [
    "run_auto_identification",
    "run_full_identification",
    "self_check_full_identification",
    "estimate_rs_from_pulse",
    "estimate_leq_from_dynamics",
    "estimate_lm",
    "refine_params_multi_test",
    "refine_params_with_model",
    "IdentificationResult",
    "MotorParamsEstimated",
    "MotorParamsTrue",
    "IdentSignalInterface",
    "apply_estimated_params_to_env_config",
    "load_and_apply_ident",
    "IdentificationDataset",
    "FIT_PARAMETER_NAMES",
    "IdentificationExperiment",
    "IdentifiabilityReport",
    "ParameterEstimate",
    "analyze_identifiability",
    "estimate_parameters",
    "make_excitation_suite",
    "separate_leakage_sensitivity_matrix",
    "sensitivity_matrix",
    "with_free_run_load_bias",
]

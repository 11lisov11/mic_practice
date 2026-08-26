from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, is_dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from random import Random
import sys
from typing import Any, Dict, Iterable, List, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.env import create_default_env
from control.cyclic_robust_viability_pwm import (
    CyclicRobustViabilityConfig,
    CyclicRobustViabilityPwmController,
)
from control.deadbeat_current_baseline import DeadbeatCurrentBaselineConfig, DeadbeatCurrentBaselineController
from control.dtc_baseline import DtcHysteresisBaselineConfig, DtcHysteresisBaselineController
from control.dtc_svm_baseline import DtcSvmBaselineConfig, DtcSvmBaselineController
from control.fcs_mpc_baseline import FcsMpcOneStepBaselineConfig, FcsMpcOneStepBaselineController
from control.foc_svm_key_baseline import FocSvmKeyBaselineConfig, FocSvmKeyBaselineController
from control.protected_ai_pwm_h1_baseline import ProtectedAiPwmH1BaselineController, protected_h1_config
from control.safe_neural_horizon_pwm import NeuralHorizonConfig, SafeNeuralHorizonPwmController
from control.sensorless_adaptive_foc_baseline import (
    SensorlessAdaptiveFocBaselineConfig,
    SensorlessAdaptiveFocBaselineController,
)
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    AlphaBetaMotorState,
    randomized_motor_params,
)
from models.two_level_inverter import TwoLevelInverterParams, alpha_beta_voltage, switch_events
from safety.ai_pwm_gateway import (
    AIPwmSafetyGateway,
    FaultFlag,
    GateOutput,
    GatewayLimits,
    has_direct_leg_transition,
    has_shoot_through,
    transition_waveform,
)


BASE_CONTROLLER_SPECS = [
    ("protected_ai_pwm_h1_baseline", 1, 5),
    ("fcs_mpc_one_step_baseline", 1, 1),
    ("foc_svm_key_baseline", 1, 1),
    ("dtc_hysteresis_baseline", 1, 1),
    ("dtc_svm_baseline", 1, 1),
    ("deadbeat_current_baseline", 1, 1),
    ("sensorless_adaptive_foc_baseline", 1, 8),
    ("safe_neural_horizon_pwm_h2", 2, 10),
]

EXTENDED_CONTROLLER_SPECS = [
    ("safe_neural_horizon_pwm_h3_thermal", 3, 12),
    ("safe_neural_horizon_pwm_h4_sparse", 4, 15),
]

BASELINE_CONFIG_TYPES = {
    "protected_ai_pwm_h1_baseline": NeuralHorizonConfig,
    "fcs_mpc_one_step_baseline": FcsMpcOneStepBaselineConfig,
    "foc_svm_key_baseline": FocSvmKeyBaselineConfig,
    "dtc_hysteresis_baseline": DtcHysteresisBaselineConfig,
    "dtc_svm_baseline": DtcSvmBaselineConfig,
    "deadbeat_current_baseline": DeadbeatCurrentBaselineConfig,
    "sensorless_adaptive_foc_baseline": SensorlessAdaptiveFocBaselineConfig,
}

DEFAULT_SCENARIOS = [
    "start_no_load",
    "start_with_load",
    "ramp_to_rated",
    "load_step",
    "load_shed",
    "reverse",
    "braking",
    "regeneration",
    "low_speed",
    "zero_speed",
    "field_weakening",
    "overload",
    "dc_sag",
    "motor_heating",
    "inverter_heating",
    "rs_error",
    "rr_error",
    "lm_error",
    "j_error",
    "random_load",
    "periodic_load",
    "shock_load",
    "two_mass_proxy",
    "current_sensor_noise",
    "speed_sensor_noise",
    "sensor_delay",
    "speed_sensor_failure",
    "current_sensor_failure",
    "ood",
    "fault_injection_runtime",
    "sensor_dropout",
]

ABLATION_SPECS = [
    ("ablation_h1_no_horizon", 1, 10),
    ("ablation_h2_dense_feedback", 2, 1),
    ("ablation_h2_sparse_feedback", 2, 25),
    ("ablation_h2_low_switching", 2, 10),
    ("ablation_h2_low_current", 2, 10),
]


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(float(v) for v in values)
    if len(values) == 1:
        return values[0]
    pos = max(0.0, min(1.0, q)) * (len(values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    frac = pos - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


def _summary(values: Iterable[float]) -> Dict[str, float]:
    arr = [float(v) for v in values]
    if not arr:
        return {
            "count": 0.0,
            "mean": 0.0,
            "sample_std": 0.0,
            "standard_error": 0.0,
            "ci95_normal_low": 0.0,
            "ci95_normal_high": 0.0,
            "median": 0.0,
            "p05": 0.0,
            "p95": 0.0,
            "worst": 0.0,
        }
    mean = sum(arr) / len(arr)
    sample_std = 0.0
    if len(arr) > 1:
        sample_std = math.sqrt(sum((value - mean) ** 2 for value in arr) / (len(arr) - 1))
    standard_error = sample_std / math.sqrt(len(arr))
    return {
        "count": float(len(arr)),
        "mean": mean,
        "sample_std": sample_std,
        "standard_error": standard_error,
        "ci95_normal_low": mean - 1.96 * standard_error,
        "ci95_normal_high": mean + 1.96 * standard_error,
        "median": _percentile(arr, 0.5),
        "p05": _percentile(arr, 0.05),
        "p95": _percentile(arr, 0.95),
        "worst": max(arr),
    }


def _make_base_params() -> tuple[AlphaBetaMotorParams, TwoLevelInverterParams]:
    env = create_default_env()
    motor = AlphaBetaMotorParams.from_motor_params(env.motor)
    inverter = TwoLevelInverterParams(
        Vdc=float(env.inverter.Vdc),
        f_pwm=float(env.inverter.f_pwm),
        dead_time_s=1.0e-6,
        min_pulse_s=2.0e-6,
        r_on_ohm=0.08,
        v_drop_v=0.8,
        e_sw_j_per_a=2.0e-6,
    )
    return motor, inverter


def controller_config_overrides_from_tuning(
    payload: Mapping[str, object],
    *,
    dt_s: float,
) -> Dict[str, object]:
    """Rebuild exact selected baseline configs from paired tuning evidence."""

    if payload.get("comparison_design") != "paired_common_random_numbers_across_variants_and_controllers":
        raise ValueError("baseline tuning payload does not declare paired common random numbers")
    if payload.get("selection_evidence_ready") is not True:
        raise ValueError("baseline tuning selection evidence is not ready")
    controllers = payload.get("controllers")
    if not isinstance(controllers, Mapping):
        raise ValueError("baseline tuning payload is missing controllers")

    overrides: Dict[str, object] = {}
    for label, config_type in BASELINE_CONFIG_TYPES.items():
        row = controllers.get(label)
        if not isinstance(row, Mapping):
            raise ValueError(f"baseline tuning payload is missing {label}")
        selected_name = row.get("selected_variant")
        selected_config = row.get("selected_config")
        variants = row.get("variants")
        if not isinstance(selected_name, str) or not isinstance(selected_config, Mapping):
            raise ValueError(f"baseline tuning payload has no selected configuration for {label}")
        if not isinstance(variants, Mapping):
            raise ValueError(f"baseline tuning payload has no variant table for {label}")
        selected_variant = variants.get(selected_name)
        if not isinstance(selected_variant, Mapping) or selected_variant.get("config") != selected_config:
            raise ValueError(f"selected configuration for {label} does not match its variant record")
        try:
            config = config_type(**dict(selected_config))
        except TypeError as exc:
            raise ValueError(f"invalid selected configuration for {label}: {exc}") from exc
        config_dt = float(getattr(config, "dt_s", float("nan")))
        if not math.isclose(config_dt, float(dt_s), rel_tol=0.0, abs_tol=1.0e-15):
            raise ValueError(
                f"selected configuration for {label} has dt_s={config_dt}, expected {float(dt_s)}"
            )
        overrides[label] = config
    return overrides


def _controller_specs(quick: bool = False) -> list[tuple[str, int, int]]:
    specs = list(BASE_CONTROLLER_SPECS)
    if quick:
        return [
            ("protected_ai_pwm_h1_baseline", 1, 5),
            ("fcs_mpc_one_step_baseline", 1, 1),
            ("foc_svm_key_baseline", 1, 1),
            ("dtc_hysteresis_baseline", 1, 1),
            ("dtc_svm_baseline", 1, 1),
            ("deadbeat_current_baseline", 1, 1),
            ("sensorless_adaptive_foc_baseline", 1, 8),
            ("safe_neural_horizon_pwm_h2", 2, 10),
        ]
    specs.extend(EXTENDED_CONTROLLER_SPECS)
    return specs


def _controller(
    *,
    label: str,
    base_motor: AlphaBetaMotorParams,
    inverter: TwoLevelInverterParams,
    horizon: int,
    feedback_period: int,
    config_override: object | None = None,
) -> SafeNeuralHorizonPwmController:
    if config_override is not None and label not in BASELINE_CONFIG_TYPES:
        raise ValueError(f"configuration overrides are not supported for {label}")

    def selected(default: object) -> object:
        if config_override is None:
            return default
        if not isinstance(config_override, type(default)):
            raise TypeError(
                f"configuration override for {label} must be {type(default).__name__}, "
                f"got {type(config_override).__name__}"
            )
        default_dt = float(getattr(default, "dt_s", inverter.t_pwm_s))
        override_dt = float(getattr(config_override, "dt_s", default_dt))
        if not math.isclose(override_dt, default_dt, rel_tol=0.0, abs_tol=1.0e-15):
            raise ValueError(
                f"configuration override for {label} has dt_s={override_dt}, expected {default_dt}"
            )
        return config_override

    if label.startswith("cyclic_robust_viability_pwm"):
        limits = GatewayLimits(
            t_pwm_s=inverter.t_pwm_s,
            dead_time_s=inverter.dead_time_s,
            min_pulse_s=inverter.min_pulse_s,
            i_soft_a=max(2.5 * base_motor.i_limit, 3.5),
            i_trip_a=max(3.5 * base_motor.i_limit, 5.0),
            vdc_min_v=0.4 * inverter.Vdc,
            vdc_max_v=1.25 * inverter.Vdc,
            tj_trip_c=125.0,
            confidence_min=0.35,
            risk_max=1.4,
        )
        cfg = CyclicRobustViabilityConfig(
            dt_s=inverter.t_pwm_s,
            use_parameter_set="nominal_only" not in label,
            use_viability_predecessor="no_viability" not in label,
            use_cyclic_reduction="full_vectors" not in label,
            cvar_weight=0.0 if "mean_only" in label else 0.55,
            worst_weight=0.0 if "mean_only" in label else 0.25,
            current_margin=0.82 if "tight_margin" in label else 0.92,
            viability_trigger_ratio=0.0 if "eager_viability" in label else 0.95,
        )
        return CyclicRobustViabilityPwmController(  # type: ignore[return-value]
            base_motor,
            inverter,
            AIPwmSafetyGateway(limits),
            cfg,
        )

    if label == "protected_ai_pwm_h1_baseline":
        limits = GatewayLimits(
            t_pwm_s=inverter.t_pwm_s,
            dead_time_s=inverter.dead_time_s,
            min_pulse_s=inverter.min_pulse_s,
            i_soft_a=max(2.5 * base_motor.i_limit, 3.5),
            i_trip_a=max(3.5 * base_motor.i_limit, 5.0),
            vdc_min_v=0.4 * inverter.Vdc,
            vdc_max_v=1.25 * inverter.Vdc,
            tj_trip_c=125.0,
            confidence_min=0.25,
            risk_max=1.4,
        )
        cfg = selected(protected_h1_config(dt_s=inverter.t_pwm_s, feedback_period=feedback_period))
        return ProtectedAiPwmH1BaselineController(base_motor, inverter, AIPwmSafetyGateway(limits), cfg)

    if label == "dtc_hysteresis_baseline":
        limits = GatewayLimits(
            t_pwm_s=inverter.t_pwm_s,
            dead_time_s=inverter.dead_time_s,
            min_pulse_s=inverter.min_pulse_s,
            i_soft_a=max(2.5 * base_motor.i_limit, 3.5),
            i_trip_a=max(3.5 * base_motor.i_limit, 5.0),
            vdc_min_v=0.4 * inverter.Vdc,
            vdc_max_v=1.25 * inverter.Vdc,
            tj_trip_c=125.0,
            confidence_min=0.35,
            risk_max=1.6,
        )
        cfg = selected(DtcHysteresisBaselineConfig(dt_s=inverter.t_pwm_s))
        return DtcHysteresisBaselineController(base_motor, inverter, AIPwmSafetyGateway(limits), cfg)  # type: ignore[return-value]

    if label == "dtc_svm_baseline":
        limits = GatewayLimits(
            t_pwm_s=inverter.t_pwm_s,
            dead_time_s=inverter.dead_time_s,
            min_pulse_s=inverter.min_pulse_s,
            i_soft_a=max(2.5 * base_motor.i_limit, 3.5),
            i_trip_a=max(3.5 * base_motor.i_limit, 5.0),
            vdc_min_v=0.4 * inverter.Vdc,
            vdc_max_v=1.25 * inverter.Vdc,
            tj_trip_c=125.0,
            confidence_min=0.35,
            risk_max=1.6,
        )
        cfg = selected(DtcSvmBaselineConfig(dt_s=inverter.t_pwm_s))
        return DtcSvmBaselineController(base_motor, inverter, AIPwmSafetyGateway(limits), cfg)  # type: ignore[return-value]

    if label == "deadbeat_current_baseline":
        limits = GatewayLimits(
            t_pwm_s=inverter.t_pwm_s,
            dead_time_s=inverter.dead_time_s,
            min_pulse_s=inverter.min_pulse_s,
            i_soft_a=max(2.5 * base_motor.i_limit, 3.5),
            i_trip_a=max(3.5 * base_motor.i_limit, 5.0),
            vdc_min_v=0.4 * inverter.Vdc,
            vdc_max_v=1.25 * inverter.Vdc,
            tj_trip_c=125.0,
            confidence_min=0.35,
            risk_max=1.6,
        )
        cfg = selected(DeadbeatCurrentBaselineConfig(dt_s=inverter.t_pwm_s))
        return DeadbeatCurrentBaselineController(base_motor, inverter, AIPwmSafetyGateway(limits), cfg)  # type: ignore[return-value]

    if label == "sensorless_adaptive_foc_baseline":
        limits = GatewayLimits(
            t_pwm_s=inverter.t_pwm_s,
            dead_time_s=inverter.dead_time_s,
            min_pulse_s=inverter.min_pulse_s,
            i_soft_a=max(2.5 * base_motor.i_limit, 3.5),
            i_trip_a=max(3.5 * base_motor.i_limit, 5.0),
            vdc_min_v=0.4 * inverter.Vdc,
            vdc_max_v=1.25 * inverter.Vdc,
            tj_trip_c=125.0,
            confidence_min=0.35,
            risk_max=1.6,
        )
        cfg = selected(SensorlessAdaptiveFocBaselineConfig(dt_s=inverter.t_pwm_s))
        return SensorlessAdaptiveFocBaselineController(base_motor, inverter, AIPwmSafetyGateway(limits), cfg)  # type: ignore[return-value]

    if label == "fcs_mpc_one_step_baseline":
        limits = GatewayLimits(
            t_pwm_s=inverter.t_pwm_s,
            dead_time_s=inverter.dead_time_s,
            min_pulse_s=inverter.min_pulse_s,
            i_soft_a=max(2.5 * base_motor.i_limit, 3.5),
            i_trip_a=max(3.5 * base_motor.i_limit, 5.0),
            vdc_min_v=0.4 * inverter.Vdc,
            vdc_max_v=1.25 * inverter.Vdc,
            tj_trip_c=125.0,
            confidence_min=0.35,
            risk_max=1.6,
        )
        cfg = selected(FcsMpcOneStepBaselineConfig(dt_s=inverter.t_pwm_s))
        return FcsMpcOneStepBaselineController(base_motor, inverter, AIPwmSafetyGateway(limits), cfg)  # type: ignore[return-value]

    if label == "foc_svm_key_baseline":
        limits = GatewayLimits(
            t_pwm_s=inverter.t_pwm_s,
            dead_time_s=inverter.dead_time_s,
            min_pulse_s=inverter.min_pulse_s,
            i_soft_a=max(2.5 * base_motor.i_limit, 3.5),
            i_trip_a=max(3.5 * base_motor.i_limit, 5.0),
            vdc_min_v=0.4 * inverter.Vdc,
            vdc_max_v=1.25 * inverter.Vdc,
            tj_trip_c=125.0,
            confidence_min=0.35,
            risk_max=1.6,
        )
        cfg = selected(FocSvmKeyBaselineConfig(dt_s=inverter.t_pwm_s))
        return FocSvmKeyBaselineController(base_motor, inverter, AIPwmSafetyGateway(limits), cfg)  # type: ignore[return-value]

    max_branching = 4 if horizon >= 3 else 5
    speed_kp = 0.04
    speed_ki = 1.5
    current_weight = 0.08
    switching_weight = 0.025
    thermal_weight = 0.01
    feedback_weight = 0.04
    flux_weight = 0.6
    torque_ripple_weight = 0.05
    risk_weight = 0.4
    feedback_error_threshold = 8.0
    confidence_min = 0.25

    if "fcs_mpc" in label:
        speed_kp = 0.035
        current_weight = 0.12
        switching_weight = 0.015
        feedback_weight = 0.0
    elif "foc_svm" in label:
        speed_kp = 0.03
        current_weight = 0.16
        switching_weight = 0.04
        torque_ripple_weight = 0.08
        flux_weight = 0.9
        feedback_weight = 0.0
        max_branching = 8
    elif "dtc_hysteresis" in label:
        speed_kp = 0.055
        current_weight = 0.05
        switching_weight = 0.008
        torque_ripple_weight = 0.16
        flux_weight = 0.75
    if "thermal" in label:
        thermal_weight = 0.035
        switching_weight += 0.01
    if "sparse" in label:
        feedback_weight = 0.18
        feedback_error_threshold = 60.0
    if "dense_feedback" in label:
        feedback_period = 1
        feedback_weight = 0.0
    if "sparse_feedback" in label:
        feedback_period = max(feedback_period, 25)
        feedback_weight = 0.22
        feedback_error_threshold = 80.0
    if "low_switching" in label:
        switching_weight = 0.12
    if "low_current" in label:
        current_weight = 0.28

    cfg = NeuralHorizonConfig(
        horizon=horizon,
        max_branching=max_branching,
        dt_s=inverter.t_pwm_s,
        feedback_base_period_steps=feedback_period,
        speed_kp=speed_kp,
        speed_ki=speed_ki,
        current_weight=current_weight,
        switching_weight=switching_weight,
        thermal_weight=thermal_weight,
        feedback_weight=feedback_weight,
        flux_weight=flux_weight,
        torque_ripple_weight=torque_ripple_weight,
        risk_weight=risk_weight,
        feedback_error_threshold_rad_s=feedback_error_threshold,
    )
    limits = GatewayLimits(
        t_pwm_s=inverter.t_pwm_s,
        dead_time_s=inverter.dead_time_s,
        min_pulse_s=inverter.min_pulse_s,
        i_soft_a=max(2.5 * base_motor.i_limit, 3.5),
        i_trip_a=max(3.5 * base_motor.i_limit, 5.0),
        vdc_min_v=0.4 * inverter.Vdc,
        vdc_max_v=1.25 * inverter.Vdc,
        tj_trip_c=125.0,
        confidence_min=confidence_min,
        risk_max=1.4,
    )
    return SafeNeuralHorizonPwmController(base_motor, inverter, AIPwmSafetyGateway(limits), cfg)


def _scenario_values(name: str, k: int, steps: int, omega_nom: float) -> tuple[float, float, float, bool]:
    """Return omega_ref, load_torque, vdc_scale, force_sensor_dropout."""

    name = str(name or "load_step").strip().lower()
    steps = max(int(steps), 1)
    ramp_steps = max(steps // 5, 1)
    progress = min(1.0, k / ramp_steps)

    if name == "start_no_load":
        return 0.6 * omega_nom * progress, 0.0, 1.0, False
    if name == "start_with_load":
        return 0.6 * omega_nom * progress, 0.35, 1.0, False
    if name == "ramp_to_rated":
        return 0.95 * omega_nom * min(1.0, k / max((3 * steps) // 4, 1)), 0.25, 1.0, False
    if name == "load_shed":
        return 0.6 * omega_nom, 0.45 if k < steps // 2 else 0.0, 1.0, False
    if name == "reverse":
        ref = 0.45 * omega_nom if k < steps // 2 else -0.35 * omega_nom
        return ref, 0.25, 1.0, False
    if name == "braking":
        ref = 0.75 * omega_nom if k < steps // 3 else 0.05 * omega_nom
        return ref, 0.15, 1.0, False
    if name == "regeneration":
        ref = 0.65 * omega_nom if k < steps // 3 else 0.25 * omega_nom
        load = -0.2 if k >= steps // 3 else 0.1
        return ref, load, 1.08, False
    if name == "low_speed":
        return 0.15 * omega_nom, 0.15, 1.0, False
    if name == "zero_speed":
        return 0.0, 0.12, 1.0, False
    if name == "field_weakening":
        return 1.15 * omega_nom, 0.2, 0.92, False
    if name == "overload":
        return 0.55 * omega_nom, 0.9 if k >= steps // 3 else 0.25, 1.0, False
    if name == "dc_sag":
        vdc_scale = 0.68 if steps // 3 <= k < (2 * steps) // 3 else 1.0
        return 0.55 * omega_nom, 0.3, vdc_scale, False
    if name == "motor_heating":
        return 0.55 * omega_nom, 0.45, 1.0, False
    if name == "inverter_heating":
        return 0.55 * omega_nom, 0.45, 1.0, False
    if name in {"rs_error", "rr_error", "lm_error", "j_error"}:
        return 0.55 * omega_nom * progress if k < ramp_steps else 0.55 * omega_nom, 0.3, 1.0, False
    if name == "random_load":
        # Deterministic pseudo-random profile; domain randomization still uses rng per trial.
        raw = math.sin(12.9898 * (k + 1)) * 43758.5453
        frac = raw - math.floor(raw)
        return 0.55 * omega_nom, 0.05 + 0.55 * frac, 1.0, False
    if name == "shock_load":
        load = 0.2
        if steps // 2 <= k < steps // 2 + max(2, steps // 20):
            load = 1.1
        return 0.55 * omega_nom, load, 1.0, False
    if name == "two_mass_proxy":
        load = 0.3 + 0.12 * math.sin(2.0 * math.pi * k / max(steps // 6, 1))
        return 0.5 * omega_nom, load, 1.0, False
    if name in {"current_sensor_noise", "speed_sensor_noise", "sensor_delay", "speed_sensor_failure", "current_sensor_failure", "ood", "fault_injection_runtime"}:
        return 0.55 * omega_nom * progress if k < ramp_steps else 0.55 * omega_nom, 0.3, 1.0, name in {"speed_sensor_failure", "sensor_delay"}
    if name == "sensor_dropout":
        return 0.55 * omega_nom * progress, 0.3, 1.0, True
    if name == "periodic_load":
        load = 0.25 + 0.15 * math.sin(2.0 * math.pi * k / max(steps // 4, 1))
        return 0.55 * omega_nom, load, 1.0, False
    # default: load step
    return 0.6 * omega_nom * progress if k < ramp_steps else 0.6 * omega_nom, 0.0 if k < steps // 2 else 0.35, 1.0, False


def run_trial(
    *,
    label: str,
    base_motor: AlphaBetaMotorParams,
    inverter: TwoLevelInverterParams,
    rng: Random,
    steps: int,
    horizon: int,
    feedback_period: int,
    scenario: str = "load_step",
    controller_config: object | None = None,
) -> Dict[str, float]:
    real_params = randomized_motor_params(base_motor, rng)
    scenario_name = str(scenario).strip().lower()
    if scenario_name == "rs_error":
        real_params = replace(real_params, Rs=real_params.Rs * 1.65)
    elif scenario_name == "rr_error":
        real_params = replace(real_params, Rr=real_params.Rr * 0.55)
    elif scenario_name == "lm_error":
        real_params = replace(real_params, Lm=max(1e-9, real_params.Lm * 0.72))
    elif scenario_name == "j_error":
        real_params = replace(real_params, J=max(1e-9, real_params.J * 2.2))
    elif scenario_name == "ood":
        real_params = replace(
            real_params,
            Rs=real_params.Rs * 2.0,
            Rr=real_params.Rr * 0.45,
            Lm=max(1e-9, real_params.Lm * 0.55),
            J=max(1e-9, real_params.J * 2.5),
        )
    real_motor = AlphaBetaInductionMotorModel(real_params, AlphaBetaMotorState())
    controller = _controller(
        label=label,
        base_motor=base_motor,
        inverter=inverter,
        horizon=horizon,
        feedback_period=feedback_period,
        config_override=controller_config,
    )
    controller.reset(AlphaBetaMotorState())

    omega_nom = 2.0 * math.pi * 50.0 / max(base_motor.p, 1)
    speed_errors: List[float] = []
    currents: List[float] = []
    torque_values: List[float] = []
    switch_total = 0
    fallback_count = 0
    fault_latch_count = 0
    fault_latch_events = 0
    fault_latched_previous = False
    fault_counts = {flag: 0 for flag in FaultFlag if flag is not FaultFlag.NONE}
    safety_violations = 0
    feedback_count = 0
    feedback_decision_mismatch_count = 0
    rejected_count = 0
    undervoltage_steps = 0
    planner_candidate_counts: List[float] = []
    planner_model_evaluations: List[float] = []
    planner_viability_rejections: List[float] = []
    planner_viability_triggers: List[float] = []
    planner_robust_currents: List[float] = []
    planner_recovery_margins: List[float] = []
    prev_vector = 0
    measured_state_history: list[AlphaBetaMotorState] = []

    for k in range(max(int(steps), 1)):
        omega_ref, load_torque, vdc_scale, force_sensor_dropout = _scenario_values(scenario_name, k, steps, omega_nom)
        step_inverter = replace(inverter, Vdc=float(inverter.Vdc) * float(vdc_scale))
        if vdc_scale < 0.75:
            undervoltage_steps += 1

        real_currents = real_motor.currents()
        measured_i_abs = real_currents.stator_abs
        if scenario_name == "current_sensor_noise":
            measured_i_abs = max(0.0, measured_i_abs + rng.gauss(0.0, 0.12 * max(base_motor.i_limit, 1e-6)))
        elif scenario_name == "current_sensor_failure" and k > steps // 3:
            measured_i_abs = 0.0
        elif scenario_name == "fault_injection_runtime" and steps // 2 <= k < steps // 2 + max(2, steps // 20):
            measured_i_abs = max(measured_i_abs, 1.2 * max(3.5 * base_motor.i_limit, 5.0))

        measured_state_history.append(real_motor.state)
        measured_state = real_motor.state
        if scenario_name == "sensor_delay" and len(measured_state_history) > 6:
            measured_state = measured_state_history[-6]
        if scenario_name == "speed_sensor_noise":
            measured_state = replace(measured_state, omega_m=measured_state.omega_m + rng.gauss(0.0, 0.03 * omega_nom))
        elif scenario_name == "speed_sensor_failure" and k > steps // 3:
            measured_state = replace(measured_state, omega_m=0.0)
        elif scenario_name == "motor_heating":
            measured_state = replace(measured_state, temp_s_c=95.0, temp_r_c=105.0)

        if scenario_name == "inverter_heating" and k > steps // 3:
            controller.tj_c = max(controller.tj_c, 115.0)

        if isinstance(controller, SafeNeuralHorizonPwmController):
            use_feedback = controller.feedback_needed(omega_ref=omega_ref)
            if k == 0:
                use_feedback = True
        else:
            speed_error_pre = omega_ref - controller.twin.state_hat.omega_m
            use_feedback = (
                k == 0
                or k % max(feedback_period, 1) == 0
                or abs(speed_error_pre) > controller.cfg.feedback_error_threshold_rad_s
                or controller.twin.uncertainty > controller.cfg.feedback_uncertainty_threshold
            )
        if force_sensor_dropout and k > steps // 4:
            use_feedback = k % max(feedback_period * 6, 1) == 0
        if use_feedback:
            feedback_count += 1

        step_kwargs = dict(
            omega_ref=omega_ref,
            load_torque_nm=load_torque,
            measured_state=measured_state if use_feedback else None,
            measured_i_abs=measured_i_abs,
            vdc=step_inverter.Vdc,
        )
        if isinstance(controller, SafeNeuralHorizonPwmController):
            step_kwargs["feedback_requested_override"] = use_feedback
        result = controller.step(**step_kwargs)
        planner_candidate_counts.append(float(result.metrics.get("candidate_count", 0.0)))
        planner_model_evaluations.append(float(result.metrics.get("total_model_evaluations", 0.0)))
        planner_viability_rejections.append(float(result.metrics.get("viability_rejections", 0.0)))
        planner_viability_triggers.append(float(result.metrics.get("viability_triggers", 0.0)))
        planner_robust_currents.append(float(result.metrics.get("robust_max_current", 0.0)))
        recovery_margin = float(result.metrics.get("recovery_margin", 0.0))
        if math.isfinite(recovery_margin):
            planner_recovery_margins.append(recovery_margin)
        if bool(result.feedback_requested) != bool(use_feedback):
            feedback_decision_mismatch_count += 1
        if not result.decision.accepted:
            fallback_count += 1
            rejected_count += 1
        if result.decision.fault_latched:
            fault_latch_count += 1
        if result.decision.fault_latched and not fault_latched_previous:
            fault_latch_events += 1
        fault_latched_previous = bool(result.decision.fault_latched)
        for flag in fault_counts:
            if flag in result.decision.fault_flags:
                fault_counts[flag] += 1

        waveform = transition_waveform(prev_vector, result.vector_id, dead_time_ticks=2)
        if has_shoot_through(waveform):
            safety_violations += 1
        switch_total += switch_events(prev_vector, result.vector_id)
        prev_vector = result.vector_id

        if result.decision.pwm_enabled:
            v_alpha, v_beta = alpha_beta_voltage(
                result.vector_id,
                step_inverter,
                i_alpha_beta=(real_currents.i_s_alpha, real_currents.i_s_beta),
            )
        else:
            v_alpha, v_beta = 0.0, 0.0
        step = real_motor.step(v_alpha, v_beta, load_torque, step_inverter.t_pwm_s)
        speed_errors.append(abs(omega_ref - step.state.omega_m))
        currents.append(step.currents.stator_abs)
        torque_values.append(step.torque_nm)

    torque_ripple = 0.0
    if len(torque_values) > 1:
        torque_ripple = sum(abs(b - a) for a, b in zip(torque_values, torque_values[1:])) / (len(torque_values) - 1)
    return {
        "mean_abs_speed_error": sum(speed_errors) / max(len(speed_errors), 1),
        "p95_abs_speed_error": _percentile(speed_errors, 0.95),
        "mean_current_abs": sum(currents) / max(len(currents), 1),
        "max_current_abs": max(currents) if currents else 0.0,
        "torque_ripple_proxy": torque_ripple,
        "switch_events": float(switch_total),
        "feedback_usage_ratio": feedback_count / max(steps, 1),
        "feedback_decision_mismatch_count": float(feedback_decision_mismatch_count),
        "fallback_count": float(fallback_count),
        "rejected_action_count": float(rejected_count),
        "fault_latch_count": float(fault_latch_count),
        "fault_latch_events": float(fault_latch_events),
        "safety_violations": float(safety_violations),
        "undervoltage_steps": float(undervoltage_steps),
        "planner_mean_candidate_count": sum(planner_candidate_counts) / max(len(planner_candidate_counts), 1),
        "planner_mean_model_evaluations": sum(planner_model_evaluations) / max(len(planner_model_evaluations), 1),
        "planner_mean_viability_rejections": sum(planner_viability_rejections) / max(len(planner_viability_rejections), 1),
        "planner_mean_viability_triggers": sum(planner_viability_triggers) / max(len(planner_viability_triggers), 1),
        "planner_max_robust_current": max(planner_robust_currents) if planner_robust_currents else 0.0,
        "planner_min_recovery_margin": min(planner_recovery_margins) if planner_recovery_margins else 0.0,
        "randomized_rs_ohm": float(real_params.Rs),
        "randomized_rr_ohm": float(real_params.Rr),
        "randomized_lm_h": float(real_params.Lm),
        "randomized_j_kg_m2": float(real_params.J),
        **{f"fault_{flag.name.lower()}_steps": float(count) for flag, count in fault_counts.items()},
    }


def _paired_trial_seeds(*, seed: int, scenario: str, trials: int, stream: str = "comparison") -> list[int]:
    """Create stable common-random-number seeds for paired controller comparisons."""

    material = f"SNH-PWM:{int(seed)}:{str(scenario).strip().lower()}:{stream}".encode("utf-8")
    root_seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    rng = Random(root_seed)
    return [rng.randrange(0, 2**63) for _ in range(max(int(trials), 1))]


def _study_metadata(*, inverter: TwoLevelInverterParams, steps: int) -> Dict[str, object]:
    duration_s = max(int(steps), 1) * float(inverter.t_pwm_s)
    minimum_dynamic_duration_s = 0.2
    return {
        "time_step_s": float(inverter.t_pwm_s),
        "simulated_duration_s": float(duration_s),
        "comparison_design": "paired_common_random_numbers",
        "paired_trial_seeds": True,
        "minimum_dynamic_duration_s": minimum_dynamic_duration_s,
        "dynamic_duration_gate_pass": bool(duration_s >= minimum_dynamic_duration_s),
        "mechanical_dynamics_claim_supported": bool(duration_s >= minimum_dynamic_duration_s),
    }


def _safety_thresholds(base_motor: AlphaBetaMotorParams) -> Dict[str, float]:
    return {
        "i_soft_a": float(max(2.5 * base_motor.i_limit, 3.5)),
        "i_trip_a": float(max(3.5 * base_motor.i_limit, 5.0)),
    }


def _run_seeded_trial(
    job: tuple[
        str,
        int,
        int,
        AlphaBetaMotorParams,
        TwoLevelInverterParams,
        int,
        int,
        int,
        str,
        object | None,
    ]
) -> tuple[str, int, Dict[str, float]]:
    (
        label,
        trial_index,
        trial_seed,
        base_motor,
        inverter,
        steps,
        horizon,
        feedback_period,
        scenario,
        controller_config,
    ) = job
    row = run_trial(
        label=label,
        base_motor=base_motor,
        inverter=inverter,
        rng=Random(trial_seed),
        steps=steps,
        horizon=horizon,
        feedback_period=feedback_period,
        scenario=scenario,
        controller_config=controller_config,
    )
    return label, trial_index, row


def _run_controller_trials(
    *,
    controller_specs: list[tuple[str, int, int]],
    trial_seeds: list[int],
    base_motor: AlphaBetaMotorParams,
    inverter: TwoLevelInverterParams,
    steps: int,
    scenario: str,
    workers: int,
    controller_config_overrides: Mapping[str, object] | None = None,
) -> Dict[str, list[Dict[str, float]]]:
    overrides = dict(controller_config_overrides or {})
    unknown = sorted(set(overrides) - {label for label, _, _ in controller_specs})
    if unknown:
        raise ValueError(f"configuration overrides reference controllers outside this run: {unknown}")
    jobs = [
        (
            label,
            trial_index,
            trial_seed,
            base_motor,
            inverter,
            steps,
            horizon,
            feedback_period,
            scenario,
            overrides.get(label),
        )
        for label, horizon, feedback_period in controller_specs
        for trial_index, trial_seed in enumerate(trial_seeds)
    ]
    if int(workers) > 1:
        with ProcessPoolExecutor(max_workers=int(workers)) as executor:
            completed = list(executor.map(_run_seeded_trial, jobs))
    else:
        completed = [_run_seeded_trial(job) for job in jobs]

    indexed: Dict[str, list[tuple[int, Dict[str, float]]]] = {label: [] for label, _, _ in controller_specs}
    for label, trial_index, row in completed:
        indexed[label].append((trial_index, row))
    return {
        label: [row for _, row in sorted(rows, key=lambda item: item[0])]
        for label, rows in indexed.items()
    }


def _summarize_rows(rows: list[Dict[str, float]]) -> Dict[str, object]:
    metrics: Dict[str, object] = {}
    for key in rows[0].keys():
        metrics[key] = _summary([row[key] for row in rows])
    metrics["failure_count"] = int(
        sum(1 for row in rows if row["safety_violations"] > 0.0 or row["fault_latch_count"] > 0.0)
    )
    return metrics


PAIRED_EFFECT_METRICS = (
    "mean_abs_speed_error",
    "p95_abs_speed_error",
    "mean_current_abs",
    "max_current_abs",
    "torque_ripple_proxy",
    "switch_events",
    "feedback_usage_ratio",
    "fallback_count",
)


def _paired_effects(rows: list[Dict[str, float]], baseline_rows: list[Dict[str, float]]) -> Dict[str, object]:
    if len(rows) != len(baseline_rows) or not rows:
        raise ValueError("paired effect rows must be non-empty and have equal length")
    out: Dict[str, object] = {
        "baseline": "foc_svm_key_baseline",
        "delta_definition": "controller_minus_baseline; negative is better for listed cost metrics",
        "trial_count": len(rows),
        "metrics": {},
    }
    metrics = out["metrics"]
    assert isinstance(metrics, dict)
    for key in PAIRED_EFFECT_METRICS:
        deltas = [float(row[key]) - float(base[key]) for row, base in zip(rows, baseline_rows)]
        summary = _summary(deltas)
        summary["win_fraction"] = sum(1 for value in deltas if value < 0.0) / len(deltas)
        summary["tie_fraction"] = sum(1 for value in deltas if value == 0.0) / len(deltas)
        metrics[key] = summary
    return out


def _dominates(left: Dict[str, object], right: Dict[str, object], keys: list[str]) -> bool:
    left_vals = [float(dict(left[k]).get("mean", 0.0)) for k in keys]
    right_vals = [float(dict(right[k]).get("mean", 0.0)) for k in keys]
    return all(a <= b for a, b in zip(left_vals, right_vals)) and any(a < b for a, b in zip(left_vals, right_vals))


def pareto_front(controllers: Dict[str, object]) -> list[str]:
    keys = [
        "mean_abs_speed_error",
        "mean_current_abs",
        "torque_ripple_proxy",
        "switch_events",
        "feedback_usage_ratio",
        "fallback_count",
    ]
    labels = list(controllers.keys())
    front: list[str] = []
    for label in labels:
        current = dict(controllers[label])
        dominated = False
        for other_label in labels:
            if other_label == label:
                continue
            other = dict(controllers[other_label])
            if _dominates(other, current, keys):
                dominated = True
                break
        if not dominated:
            front.append(label)
    return front


def run_study(
    *,
    mc: int,
    steps: int,
    seed: int,
    quick: bool = False,
    scenario: str = "load_step",
    workers: int = 1,
) -> Dict[str, object]:
    base_motor, inverter = _make_base_params()
    controller_specs = _controller_specs(quick=quick)

    trial_seeds = _paired_trial_seeds(seed=seed, scenario=scenario, trials=mc)
    out: Dict[str, object] = {
        "study": "Safe Neural Horizon PWM",
        "status": "host_simulation_only",
        "hardware_claim": False,
        "mc_trials": int(mc),
        "steps_per_trial": int(steps),
        "seed": int(seed),
        "scenario": str(scenario),
        "workers": max(int(workers), 1),
        "controllers": {},
        "safety_thresholds": _safety_thresholds(base_motor),
        **_study_metadata(inverter=inverter, steps=steps),
    }
    rows_by_controller = _run_controller_trials(
        controller_specs=controller_specs,
        trial_seeds=trial_seeds,
        base_motor=base_motor,
        inverter=inverter,
        steps=steps,
        scenario=scenario,
        workers=workers,
    )
    for label, _, _ in controller_specs:
        rows = rows_by_controller[label]
        out["controllers"][label] = _summarize_rows(rows)
    out["pareto_front"] = pareto_front(dict(out["controllers"]))
    baseline_rows = rows_by_controller.get("foc_svm_key_baseline")
    if baseline_rows is not None:
        out["paired_effects_vs_foc_svm"] = {
            label: _paired_effects(rows, baseline_rows)
            for label, rows in rows_by_controller.items()
            if label != "foc_svm_key_baseline"
        }
    return out


def run_fault_injection_matrix() -> Dict[str, object]:
    limits = GatewayLimits(i_soft_a=3.0, i_trip_a=4.0, vdc_min_v=50.0, vdc_max_v=500.0)
    cases = {
        "invalid_vector": {"vector_id": 99, "dwell_s": 100e-6, "confidence": 0.9, "predicted_i_abs": 0.2, "measured_i_abs": 0.2, "vdc": 300.0, "tj_c": 40.0},
        "too_short_pulse": {"vector_id": 1, "dwell_s": 0.1e-6, "confidence": 0.9, "predicted_i_abs": 0.2, "measured_i_abs": 0.2, "vdc": 300.0, "tj_c": 40.0},
        "overcurrent": {"vector_id": 1, "dwell_s": 100e-6, "confidence": 0.9, "predicted_i_abs": 0.2, "measured_i_abs": 4.5, "vdc": 300.0, "tj_c": 40.0},
        "overtemperature": {"vector_id": 1, "dwell_s": 100e-6, "confidence": 0.9, "predicted_i_abs": 0.2, "measured_i_abs": 0.2, "vdc": 300.0, "tj_c": 130.0},
        "undervoltage": {"vector_id": 1, "dwell_s": 100e-6, "confidence": 0.9, "predicted_i_abs": 0.2, "measured_i_abs": 0.2, "vdc": 40.0, "tj_c": 40.0},
        "uvlo_like_undervoltage": {"vector_id": 1, "dwell_s": 100e-6, "confidence": 0.9, "predicted_i_abs": 0.2, "measured_i_abs": 0.2, "vdc": 20.0, "tj_c": 40.0},
        "desat_like_overcurrent": {"vector_id": 1, "dwell_s": 100e-6, "confidence": 0.9, "predicted_i_abs": 0.2, "measured_i_abs": 8.0, "vdc": 300.0, "tj_c": 40.0},
        "low_confidence": {"vector_id": 1, "dwell_s": 100e-6, "confidence": 0.1, "predicted_i_abs": 0.2, "measured_i_abs": 0.2, "vdc": 300.0, "tj_c": 40.0},
        "watchdog": {"vector_id": 1, "dwell_s": 100e-6, "confidence": 0.9, "predicted_i_abs": 0.2, "measured_i_abs": 0.2, "vdc": 300.0, "tj_c": 40.0, "watchdog_ok": False},
    }
    results: Dict[str, object] = {}
    for name, payload in cases.items():
        gateway = AIPwmSafetyGateway(limits)
        req = payload.copy()
        watchdog_ok = bool(req.pop("watchdog_ok", True))
        from safety.ai_pwm_gateway import AIPwmRequest

        decision = gateway.evaluate(AIPwmRequest(**req, predicted_risk=0.1, watchdog_ok=watchdog_ok))
        results[name] = {
            "accepted": bool(decision.accepted),
            "pwm_enabled": bool(decision.pwm_enabled),
            "fault_flags": int(decision.fault_flags),
            "fault_latched": bool(decision.fault_latched),
            "shoot_through": bool(decision.gates.shoot_through),
        }
    raw_shoot = GateOutput(AH=True, AL=True)
    no_deadtime_wave = transition_waveform(0b100, 0b011, dead_time_ticks=0)
    safe_deadtime_wave = transition_waveform(0b100, 0b011, dead_time_ticks=2)
    results["raw_shoot_through_request_emulation"] = {
        "accepted": False,
        "pwm_enabled": False,
        "fault_flags": 0,
        "fault_latched": True,
        "shoot_through": bool(raw_shoot.shoot_through),
        "blocked_by_interface": True,
    }
    results["no_deadtime_transition_emulation"] = {
        "accepted": False,
        "pwm_enabled": False,
        "fault_flags": 0,
        "fault_latched": True,
        "shoot_through": bool(has_shoot_through(no_deadtime_wave)),
        "direct_leg_transition_without_deadtime": bool(has_direct_leg_transition(no_deadtime_wave)),
        "safe_deadtime_path_valid": not bool(has_direct_leg_transition(safe_deadtime_wave)),
        "blocked_by_gateway_deadtime_path": bool(has_direct_leg_transition(no_deadtime_wave))
        and not bool(has_direct_leg_transition(safe_deadtime_wave)),
    }
    return {
        "status": "host_gateway_fault_injection_only",
        "all_gateway_cases_no_shoot_through": all(
            not dict(row)["shoot_through"]
            for name, row in results.items()
            if name not in {"raw_shoot_through_request_emulation"}
        ),
        "raw_shoot_through_detector_triggered": bool(results["raw_shoot_through_request_emulation"]["shoot_through"]),
        "cases": results,
    }


def run_matrix(
    *,
    mc: int,
    steps: int,
    seed: int,
    quick: bool = False,
    scenarios: list[str] | None = None,
    include_ablation: bool = True,
    workers: int = 1,
    controller_config_overrides: Mapping[str, object] | None = None,
) -> Dict[str, object]:
    scenario_names = scenarios if scenarios is not None else (DEFAULT_SCENARIOS[:3] if quick else DEFAULT_SCENARIOS)
    base_motor, inverter = _make_base_params()
    controller_specs = _controller_specs(quick=quick)
    matrix: Dict[str, object] = {}
    paired_effects: Dict[str, object] = {}
    for scenario in scenario_names:
        trial_seeds = _paired_trial_seeds(seed=seed, scenario=scenario, trials=mc)
        scenario_payload: Dict[str, object] = {}
        rows_by_controller = _run_controller_trials(
            controller_specs=controller_specs,
            trial_seeds=trial_seeds,
            base_motor=base_motor,
            inverter=inverter,
            steps=steps,
            scenario=scenario,
            workers=workers,
            controller_config_overrides=controller_config_overrides,
        )
        for label, _, _ in controller_specs:
            rows = rows_by_controller[label]
            scenario_payload[label] = _summarize_rows(rows)
        scenario_payload["pareto_front"] = pareto_front(
            {k: v for k, v in scenario_payload.items() if k != "pareto_front"}
        )
        matrix[scenario] = scenario_payload
        baseline_rows = rows_by_controller.get("foc_svm_key_baseline")
        if baseline_rows is not None:
            paired_effects[scenario] = {
                label: _paired_effects(rows, baseline_rows)
                for label, rows in rows_by_controller.items()
                if label != "foc_svm_key_baseline"
            }

    ablation: Dict[str, object] = {}
    if include_ablation:
        ablation_trial_seeds = _paired_trial_seeds(
            seed=seed,
            scenario="load_step",
            trials=mc,
            stream="ablation",
        )
        ablation_rows = _run_controller_trials(
            controller_specs=ABLATION_SPECS,
            trial_seeds=ablation_trial_seeds,
            base_motor=base_motor,
            inverter=inverter,
            steps=steps,
            scenario="load_step",
            workers=workers,
        )
        for label, _, _ in ABLATION_SPECS:
            rows = ablation_rows[label]
            ablation[label] = _summarize_rows(rows)
        ablation["pareto_front"] = pareto_front({k: v for k, v in ablation.items() if k != "pareto_front"})

    serialized_overrides: Dict[str, object] = {}
    for label, config in dict(controller_config_overrides or {}).items():
        if not is_dataclass(config):
            raise TypeError(f"configuration override for {label} must be a dataclass instance")
        serialized_overrides[label] = asdict(config)

    return {
        "study": "Safe Neural Horizon PWM",
        "status": "host_simulation_matrix_only",
        "hardware_claim": False,
        "mc_trials": int(mc),
        "steps_per_trial": int(steps),
        "seed": int(seed),
        "workers": max(int(workers), 1),
        "baseline_tuning_applied": bool(serialized_overrides),
        "controller_config_overrides": serialized_overrides,
        "scenarios": scenario_names,
        "matrix": matrix,
        "paired_effects_vs_foc_svm": paired_effects,
        "ablation": ablation,
        "fault_injection": run_fault_injection_matrix(),
        "safety_thresholds": _safety_thresholds(base_motor),
        **_study_metadata(inverter=inverter, steps=steps),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Safe Neural Horizon PWM host-level research smoke/MC study.")
    parser.add_argument("--mc", type=int, default=8)
    parser.add_argument("--steps", type=int, default=160)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--scenario", default="load_step")
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--scenarios", default="", help="Comma-separated scenario list for --matrix.")
    parser.add_argument("--no-ablation", action="store_true")
    parser.add_argument("--workers", type=int, default=1, help="Parallel worker processes; deterministic output order is preserved.")
    parser.add_argument(
        "--baseline-tuning-json",
        default="",
        help="Paired tuning evidence whose exact selected configs must be applied to the final matrix.",
    )
    parser.add_argument("--out-json", default=".tmp_pytest/safe_neural_horizon_pwm_study.json")
    args = parser.parse_args()

    scenario_list = [x.strip() for x in str(args.scenarios).split(",") if x.strip()] or None
    tuning_source: Dict[str, object] | None = None
    controller_config_overrides: Dict[str, object] | None = None
    if str(args.baseline_tuning_json).strip():
        if not bool(args.matrix):
            parser.error("--baseline-tuning-json requires --matrix")
        tuning_path = Path(args.baseline_tuning_json).expanduser().resolve()
        tuning_bytes = tuning_path.read_bytes()
        tuning_payload = json.loads(tuning_bytes.decode("utf-8"))
        _, tuning_inverter = _make_base_params()
        controller_config_overrides = controller_config_overrides_from_tuning(
            tuning_payload,
            dt_s=tuning_inverter.t_pwm_s,
        )
        tuning_source = {
            "sha256": hashlib.sha256(tuning_bytes).hexdigest(),
            "selected_controller_count": len(controller_config_overrides),
        }
    if bool(args.matrix):
        payload = run_matrix(
            mc=args.mc,
            steps=args.steps,
            seed=args.seed,
            quick=bool(args.quick),
            scenarios=scenario_list,
            include_ablation=not bool(args.no_ablation),
            workers=max(int(args.workers), 1),
            controller_config_overrides=controller_config_overrides,
        )
    else:
        payload = run_study(
            mc=args.mc,
            steps=args.steps,
            seed=args.seed,
            quick=bool(args.quick),
            scenario=str(args.scenario),
            workers=max(int(args.workers), 1),
        )
    if tuning_source is not None:
        payload["baseline_tuning_source"] = tuning_source
    out = Path(args.out_json).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved: {out}")
    if "controllers" in payload:
        print(f"controllers: {len(payload['controllers'])}")
    else:
        print(f"scenarios: {len(payload.get('scenarios', []))}")


if __name__ == "__main__":
    main()

from __future__ import annotations

from random import Random

import pytest

from control.cyclic_robust_viability_pwm import (
    CyclicRobustViabilityConfig,
    CyclicRobustViabilityPwmController,
    parameter_sigma_points,
    rotate_state,
    rotate_vector_id,
)
from models.induction_motor_alpha_beta import AlphaBetaMotorState
from safety.ai_pwm_gateway import AIPwmSafetyGateway, GatewayLimits
from tools.run_cyclic_robust_viability_lab import (
    PROPOSED,
    run_comparison,
    run_counterexample_search,
    run_equivariance_audit,
)
from tools.analyze_cyclic_robust_viability_lab import analyze
from tools.run_safe_neural_horizon_pwm_study import _make_base_params, run_trial


def _controller(cfg: CyclicRobustViabilityConfig | None = None) -> CyclicRobustViabilityPwmController:
    motor, inverter = _make_base_params()
    limits = GatewayLimits(
        t_pwm_s=inverter.t_pwm_s,
        dead_time_s=inverter.dead_time_s,
        min_pulse_s=inverter.min_pulse_s,
        i_soft_a=max(2.5 * motor.i_limit, 3.5),
        i_trip_a=max(3.5 * motor.i_limit, 5.0),
        vdc_min_v=0.4 * inverter.Vdc,
        vdc_max_v=1.25 * inverter.Vdc,
        confidence_min=0.35,
        risk_max=1.4,
    )
    return CyclicRobustViabilityPwmController(motor, inverter, AIPwmSafetyGateway(limits), cfg)


def test_vector_rotation_forms_c6_action() -> None:
    for vector_id in range(8):
        assert rotate_vector_id(vector_id, 6) == vector_id
        for left in range(6):
            for right in range(6):
                assert rotate_vector_id(rotate_vector_id(vector_id, left), right) == rotate_vector_id(
                    vector_id, left + right
                )


def test_state_rotation_forms_c6_action() -> None:
    state = AlphaBetaMotorState(
        psi_s_alpha=0.12,
        psi_s_beta=-0.08,
        psi_r_alpha=0.05,
        psi_r_beta=0.04,
        omega_m=42.0,
    )
    restored = rotate_state(state, 6)
    assert restored.psi_s_alpha == pytest.approx(state.psi_s_alpha, abs=1.0e-12)
    assert restored.psi_s_beta == pytest.approx(state.psi_s_beta, abs=1.0e-12)
    assert restored.psi_r_alpha == pytest.approx(state.psi_r_alpha, abs=1.0e-12)
    assert restored.psi_r_beta == pytest.approx(state.psi_r_beta, abs=1.0e-12)
    assert restored.omega_m == state.omega_m


def test_parameter_sigma_set_has_nominal_and_axis_extremes() -> None:
    motor, _ = _make_base_params()
    points = parameter_sigma_points(motor, CyclicRobustViabilityConfig())
    assert len(points) == 9
    assert points[0] == motor
    assert min(point.Rs for point in points) < motor.Rs < max(point.Rs for point in points)
    assert min(point.Rr for point in points) < motor.Rr < max(point.Rr for point in points)
    assert min(point.Lm for point in points) < motor.Lm < max(point.Lm for point in points)
    assert min(point.J for point in points) < motor.J < max(point.J for point in points)


def test_numeric_motor_inverter_equivariance() -> None:
    audit = run_equivariance_audit(samples=40, seed=17)
    assert audit["pass"] is True
    assert audit["max_state_residual"] <= audit["tolerance"]


def test_controller_reduces_candidates_and_keeps_gateway_safe() -> None:
    motor, inverter = _make_base_params()
    row = run_trial(
        label=PROPOSED,
        base_motor=motor,
        inverter=inverter,
        rng=Random(23),
        steps=40,
        horizon=1,
        feedback_period=1,
        scenario="load_step",
    )
    assert 0.0 < row["planner_mean_candidate_count"] < 8.0
    assert row["planner_mean_model_evaluations"] > 0.0
    assert row["safety_violations"] == 0.0
    assert row["fault_latch_events"] == 0.0


def test_low_vdc_is_blocked_by_the_same_gateway() -> None:
    controller = _controller()
    result = controller.step(
        omega_ref=20.0,
        load_torque_nm=0.0,
        measured_state=AlphaBetaMotorState(),
        measured_i_abs=0.0,
        vdc=0.0,
    )
    assert result.decision.pwm_enabled is False
    assert result.decision.fault_latched is True


def test_counterexample_search_is_deterministic() -> None:
    first = run_counterexample_search(seed=31, population=4, generations=1, steps=8)
    second = run_counterexample_search(seed=31, population=4, generations=1, steps=8)
    assert first == second
    assert first["complete_search"] is False


def test_lazy_viability_preserves_trace_and_reduces_model_work() -> None:
    motor, inverter = _make_base_params()
    common = dict(
        base_motor=motor,
        inverter=inverter,
        steps=120,
        horizon=1,
        feedback_period=1,
        scenario="load_step",
    )
    lazy = run_trial(label=PROPOSED, rng=Random(41), **common)
    disabled = run_trial(label=f"{PROPOSED}_no_viability", rng=Random(41), **common)
    eager = run_trial(label=f"{PROPOSED}_eager_viability", rng=Random(41), **common)
    assert lazy["mean_abs_speed_error"] == disabled["mean_abs_speed_error"]
    assert lazy["mean_abs_speed_error"] == eager["mean_abs_speed_error"]
    assert lazy["max_current_abs"] == disabled["max_current_abs"]
    assert lazy["max_current_abs"] == eager["max_current_abs"]
    assert lazy["switch_events"] == disabled["switch_events"]
    assert lazy["switch_events"] == eager["switch_events"]
    assert disabled["planner_mean_model_evaluations"] <= lazy["planner_mean_model_evaluations"]
    assert lazy["planner_mean_model_evaluations"] < eager["planner_mean_model_evaluations"]


def test_parallel_comparison_is_deterministic() -> None:
    serial = run_comparison(
        scenarios=["start_no_load"],
        mc=2,
        steps=10,
        seed=19,
        workers=1,
    )
    parallel = run_comparison(
        scenarios=["start_no_load"],
        mc=2,
        steps=10,
        seed=19,
        workers=2,
    )
    serial.pop("workers")
    parallel.pop("workers")
    assert serial == parallel


def test_comparison_smoke_contains_proposed_and_paired_effect() -> None:
    payload = run_comparison(
        scenarios=["start_no_load"],
        mc=1,
        steps=12,
        seed=9,
        workers=1,
    )
    assert PROPOSED in payload["matrix"]["start_no_load"]
    assert PROPOSED in payload["paired_effects_vs_foc_svm"]["start_no_load"]
    assert payload["hardware_claim"] is False


def test_lab_audit_rejects_short_incomplete_smoke() -> None:
    comparison = run_comparison(
        scenarios=["start_no_load"],
        mc=1,
        steps=12,
        seed=10,
        workers=1,
    )
    audit = analyze(
        {
            "hardware_claim": False,
            "novelty_claim": False,
            "comparison": comparison,
            "equivariance_audit": run_equivariance_audit(samples=5, seed=10),
            "counterexample_search": run_counterexample_search(
                seed=10,
                population=4,
                generations=1,
                steps=5,
            ),
        }
    )
    assert audit["exploratory_mathematical_ready"] is False
    assert audit["publication_protocol_complete"] is False
    assert audit["novelty_established"] is False
    assert audit["hardware_ready"] is False

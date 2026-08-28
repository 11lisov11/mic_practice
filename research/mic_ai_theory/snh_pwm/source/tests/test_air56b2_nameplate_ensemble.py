from __future__ import annotations

import json
import math

import pytest

from config.env import NAMEPLATE_DEFAULT, create_default_env, estimate_motor_params_from_nameplate
from control.foc_svm_key_baseline import FocSvmKeyBaselineConfig, FocSvmKeyBaselineController
from models.air56b2_nameplate_ensemble import (
    Air56B2Nameplate,
    derive_nameplate,
    ensemble_manifest,
    equivalent_circuit_electromagnetic_torque,
    equivalent_circuit_max_torque,
    generate_air56b2_ensemble,
    select_nominal_sample,
)
from tools.run_air56b2_nameplate_ensemble_study import run_ensemble_study, split_seed
from tools.tune_air56b2_foc_ensemble import build_candidates, tune
from tools.validate_air56b2_foc_holdout import validate_holdout
from models.induction_motor_alpha_beta import AlphaBetaMotorParams
from models.two_level_inverter import TwoLevelInverterParams
from safety.ai_pwm_gateway import AIPwmSafetyGateway, GatewayLimits


def test_active_config_uses_official_air56b2_nameplate() -> None:
    assert NAMEPLATE_DEFAULT == {
        "P_n": 250.0,
        "U_ll": 220.0,
        "I_n": 1.24,
        "cos_phi_n": 0.78,
        "eta_n": 0.68,
        "f_n": 50.0,
        "p": 1,
        "n_rated": 2720.0,
        "connection": "D",
    }


def test_active_config_has_no_fake_nameplate_parameters() -> None:
    assert "J" not in NAMEPLATE_DEFAULT
    with pytest.raises(ValueError, match="only the official AIR56B2 fields"):
        estimate_motor_params_from_nameplate({**NAMEPLATE_DEFAULT, "J": 0.01})

    env = create_default_env()
    expected = select_nominal_sample(generate_air56b2_ensemble(256, seed=560225))
    assert env.motor == expected.motor
    assert env.foc.id_ref == pytest.approx(expected.magnetizing_current_a)
    assert env.motor.J != pytest.approx(0.01)


def test_nameplate_derived_quantities_and_power_balance() -> None:
    derived = derive_nameplate()
    assert derived.synchronous_speed_rpm == pytest.approx(3000.0)
    assert derived.rated_slip == pytest.approx((3000.0 - 2720.0) / 3000.0)
    assert derived.rated_torque_nm == pytest.approx(
        250.0 / (2.0 * math.pi * 2720.0 / 60.0)
    )
    assert derived.input_power_from_eta_w == pytest.approx(250.0 / 0.68)
    assert derived.apparent_power_va == pytest.approx(math.sqrt(3.0) * 220.0 * 1.24)
    assert derived.input_power_from_ui_w == pytest.approx(
        math.sqrt(3.0) * 220.0 * 1.24 * 0.78
    )
    assert derived.power_balance_relative_mismatch < 0.01
    assert derived.physical_phase_voltage_v == pytest.approx(220.0)
    assert derived.physical_phase_current_a == pytest.approx(1.24 / math.sqrt(3.0))
    assert derived.model_phase_voltage_v == pytest.approx(220.0 / math.sqrt(3.0))
    assert derived.model_phase_current_a == pytest.approx(1.24)


def test_delta_to_star_equivalent_preserves_complex_power_and_impedance_scaling() -> None:
    line_voltage = 220.0
    delta_impedance = complex(23.0, 17.0)
    delta_phase_current = line_voltage / delta_impedance
    delta_power = 3.0 * line_voltage * delta_phase_current.conjugate()

    star_voltage = line_voltage / math.sqrt(3.0)
    star_impedance = delta_impedance / 3.0
    star_phase_current = star_voltage / star_impedance
    star_power = 3.0 * star_voltage * star_phase_current.conjugate()

    assert star_power == pytest.approx(delta_power)
    assert abs(star_phase_current) == pytest.approx(
        math.sqrt(3.0) * abs(delta_phase_current)
    )


def test_ensemble_is_deterministic_and_physically_admissible() -> None:
    nameplate = Air56B2Nameplate()
    derived = derive_nameplate(nameplate)
    first = generate_air56b2_ensemble(32, seed=43156)
    second = generate_air56b2_ensemble(32, seed=43156)
    assert first == second

    for sample in first:
        motor = sample.motor
        assert motor.Rs > 0.0
        assert motor.Rr > 0.0
        assert motor.Ls_sigma > 0.0
        assert motor.Lr_sigma > 0.0
        assert motor.Lm > motor.Ls_sigma + motor.Lr_sigma
        determinant = (motor.Lm + motor.Ls_sigma) * (
            motor.Lm + motor.Lr_sigma
        ) - motor.Lm**2
        assert determinant > 0.0
        reconstructed_loss = (
            sample.stator_copper_loss_w
            + sample.rotor_copper_loss_w
            + sample.core_loss_w
            + sample.rotational_loss_w
        )
        assert reconstructed_loss == pytest.approx(derived.total_loss_w, rel=0.01)
        assert sample.rated_prediction.line_current_a == pytest.approx(1.24, rel=0.01)
        assert sample.rated_prediction.power_factor == pytest.approx(0.78, rel=0.01)
        assert sample.rated_prediction.output_power_w == pytest.approx(250.0, rel=0.01)
        assert sample.rated_prediction.efficiency == pytest.approx(0.68, rel=0.01)
        assert sample.predicted_start_current_ratio == pytest.approx(
            nameplate.start_current_ratio, rel=0.01
        )
        assert math.isfinite(sample.rated_prediction.start_torque_ratio)
        assert math.isfinite(sample.rated_prediction.max_torque_ratio)
        assert sample.rated_prediction.start_torque_ratio > 0.0
        assert sample.rated_prediction.max_torque_ratio >= sample.rated_prediction.start_torque_ratio
        assert 0.0 < sample.rated_prediction.max_torque_slip <= 1.0
        assert sample.hardware_identified is False


def test_thevenin_torque_matches_air_gap_power_and_analytical_maximum() -> None:
    sample = generate_air56b2_ensemble(1, seed=8128)[0]
    nameplate = Air56B2Nameplate()
    derived = derive_nameplate(nameplate)
    prediction = sample.rated_prediction
    omega_sync = 2.0 * math.pi * nameplate.frequency_hz / nameplate.pole_pairs
    direct_torque = (
        3.0
        * prediction.rotor_branch_current_a**2
        * sample.motor.Rr
        / derived.rated_slip
        / omega_sync
    )
    thevenin_torque = equivalent_circuit_electromagnetic_torque(
        sample.motor,
        core_resistance_ohm=sample.core_resistance_ohm,
        slip=derived.rated_slip,
    )
    assert thevenin_torque == pytest.approx(direct_torque, rel=1e-12)

    analytical_torque, analytical_slip = equivalent_circuit_max_torque(
        sample.motor,
        core_resistance_ohm=sample.core_resistance_ohm,
    )
    grid_slips = [10 ** (-4.0 + 4.0 * index / 20_000.0) for index in range(20_001)]
    grid_max = max(
        equivalent_circuit_electromagnetic_torque(
            sample.motor,
            core_resistance_ohm=sample.core_resistance_ohm,
            slip=slip,
        )
        for slip in grid_slips
    )
    assert analytical_torque == pytest.approx(grid_max, rel=1e-6)
    assert analytical_slip == pytest.approx(prediction.max_torque_slip)


def test_manifest_is_json_serializable_and_rejects_hardware_claim() -> None:
    samples = generate_air56b2_ensemble(3, seed=7)
    payload = ensemble_manifest(samples, master_seed=7)
    assert payload["status"] == "simulation_prior_only"
    assert payload["hardware_identified"] is False
    assert payload["physical_connection"] == "Delta_220V"
    assert payload["sample_count"] == 3
    assert payload["parameter_provenance"]["constrained_estimates"]["unique_from_nameplate"] is False
    assert payload["parameter_provenance"]["official_nameplate"]["source_url"].startswith(
        "https://cdn-01.iek.ru/"
    )
    assert payload["nominal_estimate"]["hardware_identified"] is False
    assert payload["nameplate"]["start_torque_ratio"] == 2.2
    assert payload["nameplate"]["max_torque_ratio"] == 2.2
    assert payload["f1_constraint_policy"]["validation_only_not_forced"] == [
        "start_torque_ratio",
        "max_torque_ratio",
    ]
    assert payload["schema"] == "air56b2-nameplate-ensemble-v2"
    assert "start_torque_ratio" in payload["rated_prediction_ranges"]
    assert "max_torque_ratio" in payload["f1_torque_ratio_discrepancy"]
    assert payload["f1_full_nameplate_fit_pass"] is False
    json.dumps(payload)


def test_splits_are_reproducible_disjoint_and_nominal_is_observed() -> None:
    seeds = {split_seed(560225, split) for split in ("train", "validation", "blind_holdout")}
    assert len(seeds) == 3
    samples = generate_air56b2_ensemble(9, seed=split_seed(560225, "train"))
    nominal = select_nominal_sample(samples)
    assert nominal in samples


def test_ensemble_study_smoke_uses_exact_samples() -> None:
    payload = run_ensemble_study(
        count=2,
        steps=8,
        master_seed=3,
        split="validation",
        scenarios=["air56b2_half_load"],
        quick=True,
        controller_model_mode="fixed_nominal",
    )
    assert payload["hardware_claim"] is False
    assert payload["sample_count"] == 2
    assert payload["dynamic_duration_gate_pass"] is False
    assert "foc_svm_key_baseline" in payload["matrix"]["air56b2_half_load"]
    assert payload["paired_effects_vs_foc_svm"]["air56b2_half_load"]
    acceptance = payload["matrix"]["air56b2_half_load"]["acceptance"]
    assert "foc_svm_key_baseline" in acceptance
    assert isinstance(acceptance["foc_svm_key_baseline"]["passed"], bool)


def test_foc_tuning_candidates_and_split_smoke() -> None:
    candidates = build_candidates(4, seed=11, dt_s=100e-6)
    assert len(candidates) == 4
    assert candidates == build_candidates(4, seed=11, dt_s=100e-6)
    payload = tune(
        candidate_count=2,
        train_count=1,
        validation_count=1,
        train_steps=8,
        validation_steps=8,
        top_k=1,
        master_seed=13,
        controller_model_mode="matched_plant",
    )
    assert payload["hardware_claim"] is False
    assert payload["blind_holdout_used"] is False
    assert payload["selected"]["candidate_index"] in {0, 1}


def test_foc_speed_pi_does_not_wind_up_while_torque_is_saturated() -> None:
    sample = generate_air56b2_ensemble(1, seed=99)[0]
    motor = AlphaBetaMotorParams.from_motor_params(sample.motor)
    inverter = TwoLevelInverterParams(Vdc=310.0, f_pwm=10_000.0)
    cfg = FocSvmKeyBaselineConfig(dt_s=inverter.t_pwm_s, speed_kp=0.1, speed_ki=1.0)
    gateway = AIPwmSafetyGateway(GatewayLimits(t_pwm_s=inverter.t_pwm_s))
    controller = FocSvmKeyBaselineController(motor, inverter, gateway, cfg)
    for _ in range(1000):
        assert controller._torque_ref(300.0, 0.0) == pytest.approx(cfg.torque_limit_nm)
    assert controller.speed_integral == pytest.approx(0.0)


def test_blind_holdout_rejects_payload_that_already_used_holdout() -> None:
    payload = tune(
        candidate_count=1,
        train_count=1,
        validation_count=1,
        train_steps=4,
        validation_steps=4,
        top_k=1,
        master_seed=21,
    )
    payload["blind_holdout_used"] = True
    with pytest.raises(ValueError, match="blind holdout was unused"):
        validate_holdout(payload, count=1, steps=4)

from __future__ import annotations

from dataclasses import replace

import numpy as np

from config.env import create_default_env
from mic_ai.core.env import DirectVoltageEnv
from mic_ai.ident.auto_id import run_full_identification
from mic_ai.ident.model_based import (
    FIT_PARAMETER_NAMES,
    PARAMETER_NAMES,
    SEPARATE_LEAKAGE_PARAMETER_NAMES,
    add_measurement_noise,
    analyze_identifiability,
    estimate_parameters,
    make_excitation_suite,
    relative_parameter_errors,
    separate_leakage_sensitivity_matrix,
    sensitivity_matrix,
    simulate_identification_experiments,
    with_free_run_load_bias,
)
from mic_ai.ident.motor_params import MotorParamsTrue
from mic_ai.ident.signal_interface import IdentSignalInterface
from tools.run_safe_neural_horizon_pwm_study import _make_base_params
from tools.run_model_based_identification_study import run_study
from tools.analyze_model_based_identification_study import aggregate


def test_fixed_sector_reveals_rank_loss_while_c6_is_full_rank() -> None:
    motor, _ = _make_base_params()
    fixed = make_excitation_suite("fixed_sector", steps_per_stage=240, seed=11)
    c6 = make_excitation_suite("c6_multiscale", steps_per_stage=240, seed=11)

    fixed_report = analyze_identifiability(sensitivity_matrix(motor, fixed))
    c6_report = analyze_identifiability(sensitivity_matrix(motor, c6))

    assert fixed_report.numerical_rank < len(FIT_PARAMETER_NAMES)
    assert fixed_report.identifiable is False
    assert c6_report.numerical_rank == len(FIT_PARAMETER_NAMES)
    assert c6_report.identifiable is True
    assert c6_report.condition_number < fixed_report.condition_number


def test_stator_and_rotor_leakage_are_not_separately_identifiable() -> None:
    motor, _ = _make_base_params()
    experiments = make_excitation_suite("c6_multiscale", steps_per_stage=240)
    report = analyze_identifiability(
        separate_leakage_sensitivity_matrix(motor, experiments),
        parameter_names=SEPARATE_LEAKAGE_PARAMETER_NAMES,
    )

    assert report.numerical_rank < len(SEPARATE_LEAKAGE_PARAMETER_NAMES)
    assert report.identifiable is False


def test_model_based_fit_recovers_changed_parameters_without_truth_initialization() -> None:
    prior, _ = _make_base_params()
    truth = replace(prior, Rs=prior.Rs * 1.12, Rr=prior.Rr * 0.88, Lm=prior.Lm * 1.08, J=prior.J * 1.2)
    experiments = make_excitation_suite("c6_multiscale", steps_per_stage=480, vdc=48.0, seed=9)
    true_load_torque = 0.003
    exact = simulate_identification_experiments(
        truth,
        with_free_run_load_bias(experiments, true_load_torque),
    )
    observed = add_measurement_noise(exact, noise_scales=(1.0e-5, 1.0e-5, 1.0e-5), seed=17)

    result = estimate_parameters(
        observed,
        prior,
        experiments,
        noise_scales=(1.0e-5, 1.0e-5, 1.0e-5),
        starts=2,
        seed=23,
        max_nfev=100,
    )
    errors = relative_parameter_errors(result.params, truth)

    assert result.successful_starts == 2
    assert max(errors[name] for name in ("Rs", "Rr", "Lm", "J")) < 0.01
    assert abs(result.load_torque_nm - true_load_torque) < 1.0e-4


def test_legacy_full_identification_does_not_seed_jb_from_simulator_truth() -> None:
    t = np.linspace(0.0, 0.9, 10)
    u_d = np.asarray([0.0, 0.0] + [10.0] * 8)
    i_d = np.asarray([0.0, 0.0, 0.5, 0.9, 1.2, 1.45, 1.62, 1.72, 1.79, 1.84])
    env = type(
        "TruthContainer",
        (),
        {"motor_true_params": MotorParamsTrue(2.0, 3.0, 0.2, 0.2, 0.18, 9.0, 8.0)},
    )()

    result = run_full_identification(
        env,
        motor_name="leakage-regression",
        enable_refine=False,
        data_rs_leq={"t": t, "u_d": u_d, "i_d": i_d},
        data_locked_rotor_q={"t": t, "u_q": u_d, "i_q": i_d},
        data_mech_runup={"t": t, "omega": t, "torque_cmd": np.ones_like(t)},
    )

    assert result.estimated.J == 0.01
    assert result.estimated.B == 1.0e-3
    assert result.true_params is not None
    assert result.true_params.J == 9.0


def test_direct_voltage_environment_labels_q_voltage_as_proxy_not_torque() -> None:
    interface = IdentSignalInterface(DirectVoltageEnv(create_default_env()))
    interface.reset()
    interface.apply_torque_step(0.25)

    assert interface.torque_command_mode == "iq_ref"


def test_identification_study_smoke_blocks_rank_deficient_profile() -> None:
    payload = run_study(
        seed=31,
        motors=1,
        steps_per_stage=96,
        starts=1,
        max_nfev=20,
        design_repetitions=4,
    )

    assert payload["summary"]["fixed_sector"]["identifiability"]["rank"] < len(FIT_PARAMETER_NAMES)
    assert payload["summary"]["fixed_sector"]["estimated_motors"] == 0
    assert payload["claims"]["hardware_validated"] is False
    assert payload["claims"]["world_novelty_established"] is False


def test_aggregate_rejects_reused_study_seed() -> None:
    payload = run_study(
        seed=37,
        motors=1,
        steps_per_stage=96,
        starts=1,
        max_nfev=20,
        design_repetitions=4,
    )
    audit = aggregate([payload, payload])

    assert audit["checks"]["root_seeds_unique"] is False
    assert audit["confirmatory_replication_pass"] is False


def test_aggregate_requires_disjoint_prbs_design_seeds() -> None:
    first = run_study(
        seed=41,
        motors=1,
        steps_per_stage=96,
        starts=1,
        max_nfev=20,
        design_repetitions=4,
    )
    second = run_study(
        seed=42,
        motors=1,
        steps_per_stage=96,
        starts=1,
        max_nfev=20,
        design_repetitions=4,
    )
    second["protocol"]["profile_seed"] = first["protocol"]["profile_seed"] + 1
    audit = aggregate([first, second])

    assert audit["checks"]["prbs_design_seed_sets_disjoint"] is False
    assert audit["confirmatory_replication_pass"] is False

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
MANIFEST_TOOL = REPOSITORY_ROOT / "tools" / "build_air56b2_research_manifest.py"
SPEC = importlib.util.spec_from_file_location("air56b2_research_manifest_tool", MANIFEST_TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


OFFICIAL_FIELDS = {
    "output_power_w",
    "line_voltage_v",
    "line_current_a",
    "power_factor",
    "efficiency",
    "frequency_hz",
    "rated_speed_rpm",
    "pole_pairs",
    "connection",
    "start_current_ratio",
    "start_torque_ratio",
    "max_torque_ratio",
}


def _payloads() -> dict[str, dict]:
    samples = [{"index": index, "seed": 1000 + index} for index in range(256)]
    ensemble = {
        "schema": "air56b2-nameplate-ensemble-v2",
        "hardware_identified": False,
        "sample_count": len(samples),
        "master_seed": 560225,
        "samples": samples,
        "parameter_provenance": {
            "official_nameplate": {"fields": sorted(OFFICIAL_FIELDS)},
            "constrained_estimates": {"unique_from_nameplate": False},
        },
        "f1_all_torque_ratios_within_fit_tolerance": False,
        "f1_constraint_policy": {
            "validation_only_not_forced": [
                "start_torque_ratio",
                "max_torque_ratio",
            ]
        },
    }
    full_digest = MODULE._sample_reference_digest(ensemble)
    prefix_digest = MODULE._sample_reference_digest(ensemble, count=24)
    matrix_prefix_digest = MODULE._sample_reference_digest(ensemble, count=12)
    component_seeds = {"F2": 22, "F3": 33}
    return {
        "gpu_preflight": {"gpu_ready": True},
        "result_consistency": {"status": "PASS"},
        "nameplate_ensemble": ensemble,
        "fidelity_bundle": {
            "schema": "air56b2-fidelity-bundle-v1",
            "status": "PASS",
            "hardware_claim": False,
            "component_seeds": component_seeds,
            "f1_reference": {
                "master_seed": 560225,
                "sample_count": 256,
                "sample_reference_sha256": full_digest,
            },
            "starting_regime": {
                "schema": "air56b2-starting-regime-f1s-v1",
                "status": "PASS",
                "gates": {"targets_match": True},
            },
            "fidelity": {
                "hardware_claim": False,
                "hardware_identified": False,
                "parameters_measured": False,
                "nameplate_unchanged": True,
            },
        },
        "loss_optimization_study": {
            "schema": "air56b2-loss-optimization-study-v1",
            "status": "PASS",
            "hardware_claim": False,
            "hardware_release_ready": False,
            "input": {"sha256": "pending"},
            "case_count_expected": 480,
            "case_count_comparable": 480,
            "case_count_infeasible": 0,
            "summary": {"worse_case_count": 0},
            "gates": {"all_cases_passed": True},
        },
        "sensorless_independent_plant_study": {
            "schema": "air56b2-sensorless-independent-plant-study-v1",
            "status": "PASS",
            "hardware_claim": False,
            "hardware_release_ready": False,
            "controller_plant_shared_state": False,
            "observer_input_contract": "applied_alpha_beta_voltage_and_delayed_quantized_stator_current_only",
            "plant_contract": "independent_i_s_psi_r_state_space_with_rk4",
            "input": {"sha256": "pending"},
            "gates": {"validation_passed": True},
        },
        "id_policy_benchmark": {
            "schema": "air56b2-id-policy-benchmark-v1",
            "status": "PASS",
            "hardware_claim": False,
            "hardware_release_ready": False,
            "input": {"sha256": "pending"},
            "gates": {"holdout_passed": True},
        },
        "id_policy_bundle": {
            "schema": "air56b2-id-policy-checkpoint-bundle-v1",
            "status": "simulation_only",
            "hardware_release_ready": False,
            "benchmark": {"sha256": "pending"},
            "source": {"sha256": "pending"},
        },
        "id_ref_lut": {
            "schema": "air56b2-id-ref-lut-v1",
            "status": "simulation_only",
            "hardware_release_ready": False,
        },
        "common_control_benchmark": {
            "schema": "air56b2-common-control-benchmark-v1",
            "status": "PASS",
            "hardware_claim": False,
            "hardware_release_ready": False,
            "case_count": 600,
            "bootstrap": {"cluster_count": 12, "replicates": 2000},
            "inputs": {
                "fidelity_bundle": {"sha256": "pending"},
                "policy_benchmark": {"sha256": "pending"},
                "id_ref_lut": {"sha256": "pending"},
            },
            "gates": {"same_holdout": True},
        },
        "vf_fidelity_study": {
            "schema": "air56b2-vf-fidelity-study-v1",
            "status": "PASS",
            "hardware_claim": False,
            "sample_count": 24,
            "component_seeds": component_seeds,
            "f1_reference": {
                "master_seed": 560225,
                "sample_count": 24,
                "sample_reference_sha256": prefix_digest,
            },
            "gates": {
                "controller_uses_no_true_state_feedback": True,
                "as5600_is_teacher_only": True,
            },
            "model_roles": {
                "controller_feedback": [
                    "delayed_quantized_current_magnitude",
                    "delayed_quantized_vdc",
                ],
                "controller_load_torque_input": "zero_open_loop_assumption",
                "as5600": "recorded_teacher_channel_not_used_for_vf_control",
                "current_offset_handling": "pre_pwm_zero_current_calibration",
            },
        },
        "vf_operating_matrix": {
            "schema": "air56b2-vf-operating-matrix-v1",
            "status": "PASS",
            "hardware_claim": False,
            "hardware_release_ready": False,
            "master_seed": 560225,
            "component_seeds": component_seeds,
            "sample_count_per_scenario": 12,
            "scenario_count": 4,
            "total_trial_count": 48,
            "f1_reference": {
                "master_seed": 560225,
                "sample_count": 12,
                "sample_reference_sha256": matrix_prefix_digest,
            },
            "gates": {
                "all_scenarios_passed": True,
                "same_f1_ensemble_used_in_every_scenario": True,
                "controller_uses_no_true_state_feedback": True,
                "as5600_is_teacher_only": True,
                "hardware_claim_absent": True,
            },
        },
        "protection_fault_matrix": {
            "schema": "air56b2-protection-fault-matrix-v1",
            "status": "PASS",
            "hardware_claim": False,
            "hardware_release_ready": False,
            "master_seed": 560225,
            "component_seeds": {"F3": component_seeds["F3"]},
            "sample_count": 24,
            "fault_case_count_per_sample": 7,
            "total_fault_case_count": 168,
            "f1_reference": {
                "master_seed": 560225,
                "sample_count": 24,
                "sample_reference_sha256": prefix_digest,
            },
            "gates": {
                "all_fault_cases_passed": True,
                "every_fault_tested_on_every_sample": True,
                "critical_faults_disable_all_gates": True,
                "fault_latch_requires_explicit_reset": True,
                "hardware_claim_absent": True,
            },
        },
        "foc_tuning": {
            "blind_holdout_used": False,
            "hardware_claim": False,
            "hardware_release_ready": False,
            "master_seed": 560225,
            "train_seed": MODULE._split_seed(560225, "train"),
            "validation_seed": MODULE._split_seed(560225, "validation"),
            "train_sample_count": 6,
            "validation_sample_count": 10,
            "train_reference": {"sample_count": 6, "sample_reference_sha256": "a" * 64},
            "validation_reference": {
                "sample_count": 10,
                "sample_reference_sha256": "b" * 64,
            },
            "state_feedback_contract": "oracle_full_simulated_state",
            "selected": {
                "candidate_index": 3,
                "config": {"example": 1.0},
                "validation_metrics": {"passed": True},
            },
        },
        "foc_blind_holdout": {
            "hardware_claim": False,
            "holdout_seed": MODULE._split_seed(560225, "blind_holdout"),
            "holdout_sample_count": 30,
            "holdout_reference": {"sample_count": 30, "sample_reference_sha256": "c" * 64},
            "reconstructed_train_reference": {
                "sample_count": 6,
                "sample_reference_sha256": "a" * 64,
            },
            "selected_candidate_index": 3,
            "selected_config": {"example": 1.0},
            "state_feedback_contract": "oracle_full_simulated_state",
            "algorithm_feasibility_pass": True,
            "nameplate_only_release_pass": False,
            "hardware_release_ready": False,
        },
        "encoder_foc_tuning": {
            "schema": "air56b2-encoder-foc-tuning-v1",
            "status": "PASS",
            "hardware_claim": False,
            "hardware_release_ready": False,
            "master_seed": 560225,
            "oracle_tuning_sha256": "pending",
            "train_reference": {"sample_seed": 101, "sample_count": 3},
            "validation_reference": {"sample_seed": 202, "sample_count": 6},
            "gates": {
                "selected_validation_passed": True,
                "no_true_state_feedback": True,
            },
            "selected": {
                "candidate_index": 5,
                "config": {"encoder": 1.0},
            },
        },
        "encoder_foc_fidelity_study": {
            "schema": "air56b2-encoder-foc-fidelity-study-v1",
            "status": "PASS",
            "hardware_claim": False,
            "hardware_release_ready": False,
            "master_seed": 560225,
            "sample_count": 24,
            "component_seeds": component_seeds,
            "tuning_sha256": "pending",
            "selected_candidate_index": 5,
            "f1_reference": {
                "sample_count": 24,
                "sample_reference_sha256": prefix_digest,
            },
            "gates": {"all_trials_passed": True},
            "feedback_contract": {
                "true_flux_speed_angle_to_controller": False,
                "controller_load_torque_input": "zero_open_loop_assumption",
                "current_offset_handling": "pre_pwm_zero_current_calibration",
            },
            "summary": {"total_true_state_feedback_steps": 0},
        },
    }


def _write_artifacts(directory: Path, payloads: dict[str, dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for label, filename in MODULE.REQUIRED.items():
        (directory / filename).write_text(
            json.dumps(payloads[label], indent=2) + "\n",
            encoding="utf-8",
        )
    tuning_path = directory / MODULE.REQUIRED["foc_tuning"]
    tuning_digest = MODULE._read(tuning_path)[1]
    holdout_path = directory / MODULE.REQUIRED["foc_blind_holdout"]
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    holdout["tuning_sha256"] = tuning_digest
    holdout_path.write_text(json.dumps(holdout, indent=2) + "\n", encoding="utf-8")
    encoder_tuning_path = directory / MODULE.REQUIRED["encoder_foc_tuning"]
    encoder_tuning = json.loads(encoder_tuning_path.read_text(encoding="utf-8"))
    encoder_tuning["oracle_tuning_sha256"] = tuning_digest
    encoder_tuning_path.write_text(
        json.dumps(encoder_tuning, indent=2) + "\n",
        encoding="utf-8",
    )
    encoder_tuning_digest = MODULE._read(encoder_tuning_path)[1]
    encoder_study_path = directory / MODULE.REQUIRED["encoder_foc_fidelity_study"]
    encoder_study = json.loads(encoder_study_path.read_text(encoding="utf-8"))
    encoder_study["tuning_sha256"] = encoder_tuning_digest
    encoder_study_path.write_text(
        json.dumps(encoder_study, indent=2) + "\n",
        encoding="utf-8",
    )
    fidelity_digest = MODULE._read(directory / MODULE.REQUIRED["fidelity_bundle"])[1]
    for label in (
        "loss_optimization_study",
        "sensorless_independent_plant_study",
        "id_policy_benchmark",
    ):
        path = directory / MODULE.REQUIRED[label]
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["input"]["sha256"] = fidelity_digest
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    policy_digest = MODULE._read(directory / MODULE.REQUIRED["id_policy_benchmark"])[1]
    policy_bundle_path = directory / MODULE.REQUIRED["id_policy_bundle"]
    policy_bundle = json.loads(policy_bundle_path.read_text(encoding="utf-8"))
    policy_bundle["benchmark"]["sha256"] = policy_digest
    policy_bundle["source"]["sha256"] = fidelity_digest
    policy_bundle_path.write_text(
        json.dumps(policy_bundle, indent=2) + "\n",
        encoding="utf-8",
    )
    lut_digest = MODULE._read(directory / MODULE.REQUIRED["id_ref_lut"])[1]
    common_path = directory / MODULE.REQUIRED["common_control_benchmark"]
    common = json.loads(common_path.read_text(encoding="utf-8"))
    common["inputs"]["fidelity_bundle"]["sha256"] = fidelity_digest
    common["inputs"]["policy_benchmark"]["sha256"] = policy_digest
    common["inputs"]["id_ref_lut"]["sha256"] = lut_digest
    common_path.write_text(json.dumps(common, indent=2) + "\n", encoding="utf-8")


def test_research_manifest_accepts_aligned_evidence(tmp_path: Path) -> None:
    _write_artifacts(tmp_path, _payloads())
    manifest = MODULE.build_manifest(tmp_path)

    assert manifest["schema"] == "air56b2-research-package-manifest-v6"
    assert manifest["status"] == "PASS"
    assert manifest["pc_research_ready_for_hardware_identification"] is True
    assert manifest["hardware_release_ready"] is False
    assert all(manifest["gates"].values())


def test_research_manifest_rejects_tampered_f1_reference(tmp_path: Path) -> None:
    payloads = copy.deepcopy(_payloads())
    payloads["fidelity_bundle"]["f1_reference"]["sample_reference_sha256"] = "0" * 64
    _write_artifacts(tmp_path, payloads)
    manifest = MODULE.build_manifest(tmp_path)

    assert manifest["status"] == "FAIL"
    assert manifest["gates"]["fidelity_bundle_matches_ensemble"] is False


def test_research_manifest_rejects_hidden_load_feedback_claim(tmp_path: Path) -> None:
    payloads = copy.deepcopy(_payloads())
    payloads["vf_fidelity_study"]["model_roles"]["controller_load_torque_input"] = (
        "true_plant_load"
    )
    _write_artifacts(tmp_path, payloads)
    manifest = MODULE.build_manifest(tmp_path)

    assert manifest["status"] == "FAIL"
    assert manifest["gates"]["vf_controller_has_no_hidden_state_feedback"] is False

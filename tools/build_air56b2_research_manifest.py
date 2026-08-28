#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED = {
    "gpu_preflight": "gpu_research_preflight.json",
    "result_consistency": "research_result_consistency.json",
    "nameplate_ensemble": "air56b2_nameplate_ensemble.json",
    "fidelity_bundle": "air56b2_fidelity_bundle.json",
    "loss_optimization_study": "air56b2_loss_optimization_study.json",
    "sensorless_independent_plant_study": "air56b2_sensorless_independent_plant_study.json",
    "id_policy_benchmark": "air56b2_policy_benchmark.json",
    "id_policy_bundle": "air56b2_id_policy_bundle.json",
    "id_ref_lut": "air56b2_id_ref_lut.json",
    "common_control_benchmark": "air56b2_common_control_benchmark.json",
    "vf_fidelity_study": "air56b2_vf_fidelity_study.json",
    "vf_operating_matrix": "air56b2_vf_operating_matrix.json",
    "protection_fault_matrix": "air56b2_protection_fault_matrix.json",
    "foc_tuning": "air56b2_foc_matched_tuning.json",
    "foc_blind_holdout": "air56b2_foc_blind_holdout.json",
    "encoder_foc_tuning": "air56b2_encoder_foc_tuning.json",
    "encoder_foc_fidelity_study": "air56b2_encoder_foc_fidelity_study.json",
}


def _read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload, hashlib.sha256(raw).hexdigest()


def _sample_reference_digest(ensemble: dict[str, Any], *, count: int | None = None) -> str:
    samples = ensemble.get("samples")
    if not isinstance(samples, list):
        raise ValueError("nameplate ensemble samples must be a list")
    selected = samples if count is None else samples[: int(count)]
    references: list[tuple[int, int]] = []
    for sample in selected:
        if not isinstance(sample, dict):
            raise ValueError("nameplate ensemble sample must be an object")
        references.append((int(sample["index"]), int(sample["seed"])))
    raw = json.dumps(references, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _split_seed(master_seed: int, split: str) -> int:
    digest = hashlib.sha256(f"AIR56B2:{master_seed}:{split}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big")


def build_manifest(artifacts: Path) -> dict[str, Any]:
    loaded: dict[str, dict[str, Any]] = {}
    files: dict[str, Any] = {}
    for label, filename in REQUIRED.items():
        path = artifacts / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing canonical artifact: {path}")
        payload, digest = _read(path)
        loaded[label] = payload
        files[label] = {
            "path": str(path.resolve()),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
        }

    tuning_selected = loaded["foc_tuning"].get("selected", {})
    validation_metrics = (
        tuning_selected.get("validation_metrics", {})
        if isinstance(tuning_selected, dict)
        else {}
    )
    ensemble = loaded["nameplate_ensemble"]
    fidelity_bundle = loaded["fidelity_bundle"]
    vf_study = loaded["vf_fidelity_study"]
    vf_matrix = loaded["vf_operating_matrix"]
    fault_matrix = loaded["protection_fault_matrix"]
    tuning = loaded["foc_tuning"]
    holdout = loaded["foc_blind_holdout"]
    encoder_tuning = loaded["encoder_foc_tuning"]
    encoder_study = loaded["encoder_foc_fidelity_study"]
    loss_study = loaded["loss_optimization_study"]
    sensorless_study = loaded["sensorless_independent_plant_study"]
    policy_benchmark = loaded["id_policy_benchmark"]
    policy_bundle = loaded["id_policy_bundle"]
    id_ref_lut = loaded["id_ref_lut"]
    common_benchmark = loaded["common_control_benchmark"]
    encoder_selected = encoder_tuning.get("selected", {})
    encoder_reference = encoder_study.get("f1_reference", {})
    encoder_count = int(encoder_study.get("sample_count", 0))
    encoder_prefix_reference_digest = _sample_reference_digest(
        ensemble,
        count=encoder_count,
    )
    bundle_reference = fidelity_bundle.get("f1_reference", {})
    vf_reference = vf_study.get("f1_reference", {})
    bundle_starting = fidelity_bundle.get("starting_regime", {})
    bundle_fidelity = fidelity_bundle.get("fidelity", {})
    vf_gates = vf_study.get("gates", {})
    ensemble_count = int(ensemble.get("sample_count", 0))
    vf_count = int(vf_study.get("sample_count", 0))
    ensemble_reference_digest = _sample_reference_digest(ensemble)
    vf_prefix_reference_digest = _sample_reference_digest(ensemble, count=vf_count)
    vf_matrix_count = int(vf_matrix.get("sample_count_per_scenario", 0))
    vf_matrix_reference = vf_matrix.get("f1_reference", {})
    vf_matrix_prefix_reference_digest = _sample_reference_digest(
        ensemble,
        count=vf_matrix_count,
    )
    fault_matrix_count = int(fault_matrix.get("sample_count", 0))
    fault_matrix_reference = fault_matrix.get("f1_reference", {})
    fault_matrix_prefix_reference_digest = _sample_reference_digest(
        ensemble,
        count=fault_matrix_count,
    )
    official_fields = set(
        ensemble.get("parameter_provenance", {})
        .get("official_nameplate", {})
        .get("fields", [])
    )
    required_official_fields = {
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
    gates = {
        "gpu_ready": loaded["gpu_preflight"].get("gpu_ready") is True,
        "research_result_consistency": loaded["result_consistency"].get("status") == "PASS",
        "ensemble_is_not_hardware_identified": (
            loaded["nameplate_ensemble"].get("hardware_identified") is False
        ),
        "ensemble_has_256_samples": loaded["nameplate_ensemble"].get("sample_count") == 256,
        "nameplate_provenance_schema_v2": ensemble.get("schema") == "air56b2-nameplate-ensemble-v2",
        "official_nameplate_fields_complete": official_fields == required_official_fields,
        "non_nameplate_parameters_marked_as_estimates": (
            ensemble.get("parameter_provenance", {})
            .get("constrained_estimates", {})
            .get("unique_from_nameplate")
            is False
        ),
        "f1_torque_limit_disclosed": (
            ensemble.get("f1_all_torque_ratios_within_fit_tolerance") is False
            and ensemble.get("f1_constraint_policy", {}).get("validation_only_not_forced")
            == ["start_torque_ratio", "max_torque_ratio"]
        ),
        "fidelity_bundle_passed": (
            fidelity_bundle.get("schema") == "air56b2-fidelity-bundle-v1"
            and fidelity_bundle.get("status") == "PASS"
            and fidelity_bundle.get("hardware_claim") is False
        ),
        "fidelity_bundle_matches_ensemble": (
            bundle_reference.get("master_seed") == ensemble.get("master_seed")
            and bundle_reference.get("sample_count") == ensemble_count
            and bundle_reference.get("sample_reference_sha256")
            == ensemble_reference_digest
        ),
        "f1s_starting_extension_passed": (
            bundle_starting.get("schema") == "air56b2-starting-regime-f1s-v1"
            and bundle_starting.get("status") == "PASS"
            and all(bundle_starting.get("gates", {}).values())
        ),
        "f2_f3_priors_have_no_hardware_claim": (
            bundle_fidelity.get("hardware_claim") is False
            and bundle_fidelity.get("hardware_identified") is False
            and bundle_fidelity.get("parameters_measured") is False
            and bundle_fidelity.get("nameplate_unchanged") is True
        ),
        "loss_optimization_study_passed": (
            loss_study.get("schema") == "air56b2-loss-optimization-study-v1"
            and loss_study.get("status") == "PASS"
            and loss_study.get("hardware_claim") is False
            and loss_study.get("hardware_release_ready") is False
            and all(loss_study.get("gates", {}).values())
            and loss_study.get("input", {}).get("sha256")
            == files["fidelity_bundle"]["sha256"]
        ),
        "classical_loss_baseline_has_complete_comparable_matrix": (
            loss_study.get("case_count_expected")
            == loss_study.get("case_count_comparable")
            and loss_study.get("case_count_infeasible") == 0
            and loss_study.get("summary", {}).get("worse_case_count") == 0
        ),
        "sensorless_independent_plant_study_passed": (
            sensorless_study.get("schema")
            == "air56b2-sensorless-independent-plant-study-v1"
            and sensorless_study.get("status") == "PASS"
            and sensorless_study.get("hardware_claim") is False
            and sensorless_study.get("hardware_release_ready") is False
            and sensorless_study.get("controller_plant_shared_state") is False
            and all(sensorless_study.get("gates", {}).values())
            and sensorless_study.get("input", {}).get("sha256")
            == files["fidelity_bundle"]["sha256"]
        ),
        "sensorless_observer_uses_only_voltage_and_current": (
            sensorless_study.get("observer_input_contract")
            == "applied_alpha_beta_voltage_and_delayed_quantized_stator_current_only"
            and sensorless_study.get("plant_contract")
            == "independent_i_s_psi_r_state_space_with_rk4"
        ),
        "id_policy_holdout_benchmark_passed": (
            policy_benchmark.get("schema") == "air56b2-id-policy-benchmark-v1"
            and policy_benchmark.get("status") == "PASS"
            and policy_benchmark.get("hardware_claim") is False
            and policy_benchmark.get("hardware_release_ready") is False
            and all(policy_benchmark.get("gates", {}).values())
            and policy_benchmark.get("input", {}).get("sha256")
            == files["fidelity_bundle"]["sha256"]
        ),
        "id_policy_checkpoint_and_lut_are_linked": (
            policy_bundle.get("schema") == "air56b2-id-policy-checkpoint-bundle-v1"
            and policy_bundle.get("status") == "simulation_only"
            and policy_bundle.get("hardware_release_ready") is False
            and policy_bundle.get("benchmark", {}).get("sha256")
            == files["id_policy_benchmark"]["sha256"]
            and policy_bundle.get("source", {}).get("sha256")
            == files["fidelity_bundle"]["sha256"]
            and id_ref_lut.get("schema") == "air56b2-id-ref-lut-v1"
            and id_ref_lut.get("status") == "simulation_only"
            and id_ref_lut.get("hardware_release_ready") is False
        ),
        "common_control_benchmark_passed": (
            common_benchmark.get("schema") == "air56b2-common-control-benchmark-v1"
            and common_benchmark.get("status") == "PASS"
            and common_benchmark.get("hardware_claim") is False
            and common_benchmark.get("hardware_release_ready") is False
            and common_benchmark.get("case_count") == 600
            and all(common_benchmark.get("gates", {}).values())
        ),
        "common_control_benchmark_evidence_is_linked": (
            common_benchmark.get("inputs", {}).get("fidelity_bundle", {}).get("sha256")
            == files["fidelity_bundle"]["sha256"]
            and common_benchmark.get("inputs", {}).get("policy_benchmark", {}).get("sha256")
            == files["id_policy_benchmark"]["sha256"]
            and common_benchmark.get("inputs", {}).get("id_ref_lut", {}).get("sha256")
            == files["id_ref_lut"]["sha256"]
            and common_benchmark.get("bootstrap", {}).get("cluster_count") == 12
            and common_benchmark.get("bootstrap", {}).get("replicates") == 2000
        ),
        "vf_fidelity_study_passed": (
            vf_study.get("schema") == "air56b2-vf-fidelity-study-v1"
            and vf_study.get("status") == "PASS"
            and vf_study.get("hardware_claim") is False
            and all(vf_gates.values())
        ),
        "vf_study_matches_ensemble_prefix": (
            vf_count > 0
            and vf_count <= ensemble_count
            and vf_reference.get("master_seed") == ensemble.get("master_seed")
            and vf_reference.get("sample_count") == vf_count
            and vf_reference.get("sample_reference_sha256")
            == vf_prefix_reference_digest
            and vf_study.get("component_seeds")
            == fidelity_bundle.get("component_seeds")
        ),
        "vf_controller_has_no_hidden_state_feedback": (
            vf_study.get("model_roles", {}).get("controller_feedback")
            == ["delayed_quantized_current_magnitude", "delayed_quantized_vdc"]
            and vf_study.get("model_roles", {}).get("controller_load_torque_input")
            == "zero_open_loop_assumption"
            and vf_study.get("model_roles", {}).get("as5600")
            == "recorded_teacher_channel_not_used_for_vf_control"
            and vf_study.get("model_roles", {}).get("current_offset_handling")
            == "pre_pwm_zero_current_calibration"
            and vf_gates.get("controller_uses_no_true_state_feedback") is True
            and vf_gates.get("as5600_is_teacher_only") is True
        ),
        "vf_operating_matrix_passed": (
            vf_matrix.get("schema") == "air56b2-vf-operating-matrix-v1"
            and vf_matrix.get("status") == "PASS"
            and vf_matrix.get("hardware_claim") is False
            and vf_matrix.get("hardware_release_ready") is False
            and vf_matrix.get("scenario_count") == 4
            and vf_matrix.get("total_trial_count") == 4 * vf_matrix_count
            and all(vf_matrix.get("gates", {}).values())
        ),
        "vf_operating_matrix_evidence_is_linked": (
            vf_matrix_count > 0
            and vf_matrix_count <= ensemble_count
            and vf_matrix.get("master_seed") == ensemble.get("master_seed")
            and vf_matrix.get("component_seeds")
            == fidelity_bundle.get("component_seeds")
            and vf_matrix_reference.get("master_seed")
            == ensemble.get("master_seed")
            and vf_matrix_reference.get("sample_count") == vf_matrix_count
            and vf_matrix_reference.get("sample_reference_sha256")
            == vf_matrix_prefix_reference_digest
        ),
        "vf_operating_matrix_has_no_hidden_feedback": (
            vf_matrix.get("gates", {}).get(
                "controller_uses_no_true_state_feedback"
            )
            is True
            and vf_matrix.get("gates", {}).get("as5600_is_teacher_only") is True
        ),
        "protection_fault_matrix_passed": (
            fault_matrix.get("schema") == "air56b2-protection-fault-matrix-v1"
            and fault_matrix.get("status") == "PASS"
            and fault_matrix.get("hardware_claim") is False
            and fault_matrix.get("hardware_release_ready") is False
            and fault_matrix.get("fault_case_count_per_sample") == 7
            and fault_matrix.get("total_fault_case_count")
            == 7 * fault_matrix_count
            and all(fault_matrix.get("gates", {}).values())
        ),
        "protection_fault_matrix_evidence_is_linked": (
            fault_matrix_count > 0
            and fault_matrix_count <= ensemble_count
            and fault_matrix.get("master_seed") == ensemble.get("master_seed")
            and fault_matrix.get("component_seeds", {}).get("F3")
            == fidelity_bundle.get("component_seeds", {}).get("F3")
            and fault_matrix_reference.get("master_seed")
            == ensemble.get("master_seed")
            and fault_matrix_reference.get("sample_count") == fault_matrix_count
            and fault_matrix_reference.get("sample_reference_sha256")
            == fault_matrix_prefix_reference_digest
        ),
        "validation_passed": validation_metrics.get("passed") is True,
        "foc_oracle_scope_disclosed": (
            tuning.get("state_feedback_contract") == "oracle_full_simulated_state"
            and holdout.get("state_feedback_contract") == "oracle_full_simulated_state"
            and tuning.get("hardware_claim") is False
            and tuning.get("hardware_release_ready") is False
            and holdout.get("hardware_claim") is False
        ),
        "foc_split_seeds_are_canonical": (
            tuning.get("master_seed") == ensemble.get("master_seed")
            and tuning.get("train_seed")
            == _split_seed(int(ensemble.get("master_seed", -1)), "train")
            and tuning.get("validation_seed")
            == _split_seed(int(ensemble.get("master_seed", -1)), "validation")
            and holdout.get("holdout_seed")
            == _split_seed(int(ensemble.get("master_seed", -1)), "blind_holdout")
        ),
        "foc_evidence_chain_is_linked": (
            holdout.get("tuning_sha256") == files["foc_tuning"]["sha256"]
            and holdout.get("selected_candidate_index")
            == tuning_selected.get("candidate_index")
            and holdout.get("selected_config") == tuning_selected.get("config")
            and holdout.get("reconstructed_train_reference")
            == tuning.get("train_reference")
            and tuning.get("train_reference", {}).get("sample_count")
            == tuning.get("train_sample_count")
            and tuning.get("validation_reference", {}).get("sample_count")
            == tuning.get("validation_sample_count")
            and holdout.get("holdout_reference", {}).get("sample_count")
            == holdout.get("holdout_sample_count")
        ),
        "encoder_foc_tuning_passed": (
            encoder_tuning.get("schema") == "air56b2-encoder-foc-tuning-v1"
            and encoder_tuning.get("status") == "PASS"
            and encoder_tuning.get("hardware_claim") is False
            and encoder_tuning.get("hardware_release_ready") is False
            and encoder_tuning.get("oracle_tuning_sha256")
            == files["foc_tuning"]["sha256"]
            and encoder_tuning.get("master_seed") == ensemble.get("master_seed")
            and encoder_tuning.get("gates", {}).get("selected_validation_passed")
            is True
            and encoder_tuning.get("gates", {}).get("no_true_state_feedback") is True
        ),
        "encoder_foc_train_validation_are_disjoint": (
            encoder_tuning.get("train_reference", {}).get("sample_seed")
            != encoder_tuning.get("validation_reference", {}).get("sample_seed")
            and encoder_tuning.get("train_reference", {}).get("sample_count") == 3
            and encoder_tuning.get("validation_reference", {}).get("sample_count") == 6
        ),
        "encoder_foc_fidelity_study_passed": (
            encoder_study.get("schema") == "air56b2-encoder-foc-fidelity-study-v1"
            and encoder_study.get("status") == "PASS"
            and encoder_study.get("hardware_claim") is False
            and encoder_study.get("hardware_release_ready") is False
            and all(encoder_study.get("gates", {}).values())
        ),
        "encoder_foc_evidence_chain_is_linked": (
            encoder_study.get("tuning_sha256")
            == files["encoder_foc_tuning"]["sha256"]
            and encoder_study.get("selected_candidate_index")
            == encoder_selected.get("candidate_index")
            and encoder_study.get("master_seed") == ensemble.get("master_seed")
            and encoder_study.get("component_seeds")
            == fidelity_bundle.get("component_seeds")
            and encoder_count > 0
            and encoder_count <= ensemble_count
            and encoder_reference.get("sample_count") == encoder_count
            and encoder_reference.get("sample_reference_sha256")
            == encoder_prefix_reference_digest
        ),
        "encoder_foc_uses_measurements_not_true_state": (
            encoder_study.get("feedback_contract", {}).get(
                "true_flux_speed_angle_to_controller"
            )
            is False
            and encoder_study.get("feedback_contract", {}).get(
                "controller_load_torque_input"
            )
            == "zero_open_loop_assumption"
            and encoder_study.get("feedback_contract", {}).get(
                "current_offset_handling"
            )
            == "pre_pwm_zero_current_calibration"
            and encoder_study.get("summary", {}).get("total_true_state_feedback_steps")
            == 0
        ),
        "tuning_did_not_use_holdout": tuning.get("blind_holdout_used") is False,
        "blind_holdout_algorithm_feasibility": (
            holdout.get("algorithm_feasibility_pass") is True
        ),
        "nameplate_only_release_rejected": (
            holdout.get("nameplate_only_release_pass") is False
        ),
        "hardware_release_rejected": (
            holdout.get("hardware_release_ready") is False
        ),
    }
    return {
        "schema": "air56b2-research-package-manifest-v6",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "pc_research_ready_for_hardware_identification": all(gates.values()),
        "hardware_release_ready": False,
        "motor": "IEK AIR56B2 0.25 kW 220 V Delta",
        "gates": gates,
        "selected_foc_candidate": tuning_selected.get("candidate_index"),
        "selected_foc_config": tuning_selected.get("config"),
        "selected_encoder_foc_candidate": encoder_selected.get("candidate_index"),
        "selected_encoder_foc_config": encoder_selected.get("config"),
        "files": files,
        "interpretation": (
            "The scalar V/f baseline passed its canonical point and four-point operating "
            "matrix and protected-gateway fault matrix. A classical loss baseline, "
            "an honest voltage/current-only sensorless observer on an independent RK4 plant, "
            "and a paired 600-case comparison of fixed flux, classical optimum, neural id policy, "
            "bounded extremum search, and a guarded disabled-release LUT also passed. "
            "Encoder-observer FOC passed deterministic F1/F1S/F2/F3 host "
            "gates. The oracle-state FOC also passed model-matched "
            "validation and blind holdout. A frozen "
            "nameplate-only model failed robustness, so hardware identification remains mandatory."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the canonical AIR56B2 research manifest.")
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_manifest(args.artifacts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": payload["status"] == "PASS",
                "status": payload["status"],
                "output": str(args.output.resolve()),
                "hardware_release_ready": False,
            }
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

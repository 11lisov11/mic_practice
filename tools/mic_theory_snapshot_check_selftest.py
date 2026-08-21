from __future__ import annotations

import json
import tempfile
from pathlib import Path

from mic_theory_snapshot_check import (
    C6_AUDIT,
    C6_CONFORMAL_AUDITS,
    C6_CONFORMAL_REPLICATION_AUDIT,
    CANONICAL_AUDIT,
    MANIFEST_NAME,
    MODEL_ID_AUDIT,
    MODEL_ID_STUDIES,
    build_manifest,
    verify_manifest,
    verify_model_identification_audit,
    verify_c6_audit,
    verify_c6_conformal_audit,
    verify_c6_conformal_replication_audit,
    verify_revalidation_audit,
)


VALID_AUDIT = {
    "status": "snh_pwm_long_horizon_revalidation",
    "host_long_horizon_ready": True,
    "hardware_ready": False,
    "universal_superiority_supported": False,
    "checks": {"long_horizon": True},
    "failures": [],
    "scenario_count": 31,
    "mc_trials": 30,
    "simulated_duration_s": 0.2,
    "safety_thresholds": {"i_trip_a": 6.125},
    "max_plant_current_a": 5.65,
}

VALID_C6_AUDIT = {
    "status": "c6_robust_viability_lab_audit",
    "exploratory_mathematical_ready": True,
    "publication_protocol_complete": False,
    "novelty_established": False,
    "hardware_ready": False,
    "checks": {"host_only": True},
    "failures": [],
    "scenario_count": 31,
    "mc_trials": 5,
    "simulated_duration_s": 0.2,
    "max_observed_current_a": 4.58,
    "current_trip_a": 6.125,
}

VALID_C6_CONFORMAL_AUDIT = {
    "status": "independent_c6_conformal_reachability_audit",
    "defensible_scientific_novelty_candidate": True,
    "world_novelty_established": False,
    "hardware_ready": False,
    "checks": {"independent_audit": True},
    "failures": [],
    "repetitions": 24,
    "c6_held_out_coverage": 0.95,
    "target_coverage": 0.95,
    "pooled_undercoverage_p_value": 0.2,
    "median_c6_to_raw_hypervolume_ratio": 0.75,
    "paired_sign_test_p_value": 0.003,
    "finite_sample_rank": 381,
}

VALID_C6_CONFORMAL_REPLICATION_AUDIT = {
    "status": "c6_conformal_confirmatory_replication_audit",
    "confirmatory_replication_pass": True,
    "defensible_scientific_novelty_candidate": True,
    "world_novelty_established": False,
    "hardware_ready": False,
    "checks": {"replication": True},
    "failures": [],
    "root_seeds": [20260810, 20260811],
    "total_repetitions": 48,
    "aggregate_held_out_coverage": 0.950625,
    "aggregate_undercoverage_p_value": 0.7,
    "median_c6_to_raw_hypervolume_ratio": 0.74,
    "paired_sign_test_p_value": 5.0e-8,
}

VALID_MODEL_ID_AUDIT = {
    "confirmatory_replication_pass": True,
    "paired_trials": 24,
    "checks": {"replication": True},
    "claims": {
        "simulation_evidence": True,
        "hardware_validated": False,
        "world_novelty_established": False,
        "defensible_scientific_novelty_candidate": True,
    },
}

VALID_MODEL_ID_STUDIES = (
    {
        "seed": 20260820,
        "protocol": {"motors": 12},
        "design_robustness": {"prbs_designs": 32, "c6_information_win_rate": 1.0},
        "summary": {
            "c6_multiscale": {"current_limit_exceedances": 0, "median_max_relative_error": 0.01}
        },
        "claims": {"hardware_validated": False, "world_novelty_established": False},
    },
    {
        "seed": 20260821,
        "protocol": {"motors": 12},
        "design_robustness": {"prbs_designs": 32, "c6_information_win_rate": 1.0},
        "summary": {
            "c6_multiscale": {"current_limit_exceedances": 0, "median_max_relative_error": 0.01}
        },
        "claims": {"hardware_validated": False, "world_novelty_established": False},
    },
)


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for relative in sorted(__import__("mic_theory_snapshot_check").REQUIRED_FILES):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture:{relative}\n", encoding="utf-8")
        (root / CANONICAL_AUDIT).write_text(json.dumps(VALID_AUDIT), encoding="utf-8")
        (root / C6_AUDIT).write_text(json.dumps(VALID_C6_AUDIT), encoding="utf-8")
        for relative in C6_CONFORMAL_AUDITS:
            (root / relative).write_text(json.dumps(VALID_C6_CONFORMAL_AUDIT), encoding="utf-8")
        (root / C6_CONFORMAL_REPLICATION_AUDIT).write_text(
            json.dumps(VALID_C6_CONFORMAL_REPLICATION_AUDIT), encoding="utf-8"
        )
        (root / MODEL_ID_AUDIT).write_text(json.dumps(VALID_MODEL_ID_AUDIT), encoding="utf-8")
        for relative, payload in zip(MODEL_ID_STUDIES, VALID_MODEL_ID_STUDIES):
            (root / relative).write_text(json.dumps(payload), encoding="utf-8")

        manifest = build_manifest(root)
        (root / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
        assert verify_manifest(root)["ok"] is True

        cache = root / "model_identification" / "source" / "tests" / "__pycache__" / "fixture.pyc"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"python-cache")
        assert verify_manifest(root)["ok"] is True

        pytest_cache = root / "snh_pwm" / "source" / ".pytest_cache" / "v" / "cache" / "nodeids"
        pytest_cache.parent.mkdir(parents=True, exist_ok=True)
        pytest_cache.write_text("pytest-cache", encoding="utf-8")
        assert verify_manifest(root)["ok"] is True

        target = root / "PROVENANCE.json"
        target.write_text("tampered\n", encoding="utf-8")
        result = verify_manifest(root)
        assert result["ok"] is False
        assert any("PROVENANCE.json" in item for item in result["failures"])

        invalid_audit = dict(VALID_AUDIT, hardware_ready=True)
        (root / CANONICAL_AUDIT).write_text(json.dumps(invalid_audit), encoding="utf-8")
        assert any("hardware_ready" in item for item in verify_revalidation_audit(root))

        invalid_c6_audit = dict(VALID_C6_AUDIT, novelty_established=True)
        (root / C6_AUDIT).write_text(json.dumps(invalid_c6_audit), encoding="utf-8")
        assert any("novelty_established" in item for item in verify_c6_audit(root))

        invalid_conformal = dict(VALID_C6_CONFORMAL_AUDIT, hardware_ready=True)
        (root / C6_CONFORMAL_AUDITS[0]).write_text(json.dumps(invalid_conformal), encoding="utf-8")
        assert any(
            "hardware_ready" in item
            for item in verify_c6_conformal_audit(root, C6_CONFORMAL_AUDITS[0])
        )

        invalid_replication = dict(VALID_C6_CONFORMAL_REPLICATION_AUDIT, root_seeds=[20260810, 20260810])
        (root / C6_CONFORMAL_REPLICATION_AUDIT).write_text(
            json.dumps(invalid_replication), encoding="utf-8"
        )
        assert any("blind root seeds" in item for item in verify_c6_conformal_replication_audit(root))

        invalid_model_id = dict(VALID_MODEL_ID_AUDIT, confirmatory_replication_pass=False)
        (root / MODEL_ID_AUDIT).write_text(json.dumps(invalid_model_id), encoding="utf-8")
        assert any("replication" in item for item in verify_model_identification_audit(root))

    print("PASS: mic_theory_snapshot_check_selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

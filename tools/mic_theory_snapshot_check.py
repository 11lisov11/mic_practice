from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


MANIFEST_NAME = "SNAPSHOT_MANIFEST.json"
CANONICAL_AUDIT = "snh_pwm/revalidation/snh_paired_mc30_all31_0p2s_rev4_final_audit.json"
C6_AUDIT = "snh_pwm/c6_rv_pwm/revalidation/c6_rv_lab_all31_mc5_0p2s_rev3_lazy_audit.json"
C6_CONFORMAL_AUDITS = (
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_seed_20260810_audit.json",
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_seed_20260811_audit.json",
)
C6_CONFORMAL_REPLICATION_AUDIT = (
    "snh_pwm/c6_conformal_reachability/revalidation/"
    "c6_conformal_confirmatory_20260810_20260811_audit.json"
)
MODEL_ID_AUDIT = "model_identification/revalidation/aggregate_20260820_20260821.json"
MODEL_ID_STUDIES = (
    "model_identification/revalidation/exploratory_20260820.json",
    "model_identification/revalidation/confirmatory_20260821.json",
)
REQUIRED_FILES = {
    "PROVENANCE.json",
    "README_RU.md",
    "articles/ieee_manuscript.md",
    "articles/pgups_article_ru.md",
    "articles/snh_pwm_article_draft.md",
    "legacy_mic/three_motor_release/motor_tuning_acceptance_summary.json",
    "legacy_mic/three_motor_release/step28_ieee_summary.csv",
    "snh_pwm/revalidation/FINAL_MC30_SUMMARY_RU.md",
    "snh_pwm/revalidation/snh_paired_mc30_all31_0p2s_rev4_final.json",
    "snh_pwm/revalidation/snh_paired_mc30_all31_0p2s_rev4_final_audit.json",
    "snh_pwm/revalidation/snh_paired_mc30_all31_0p2s_rev4_final_audit.md",
    "snh_pwm/source/control/safe_neural_horizon_pwm.py",
    "snh_pwm/source/safety/ai_pwm_gateway.py",
    "snh_pwm/source/tools/analyze_safe_neural_horizon_pwm_revalidation.py",
    "snh_pwm/source/config/env.py",
    "snh_pwm/source/models/transformations.py",
    "snh_pwm/source/control/cyclic_robust_viability_pwm.py",
    "snh_pwm/source/tools/run_cyclic_robust_viability_lab.py",
    "snh_pwm/source/tools/analyze_cyclic_robust_viability_lab.py",
    "snh_pwm/source/tests/test_cyclic_robust_viability_pwm.py",
    "snh_pwm/c6_rv_pwm/RESEARCH_RU.md",
    "snh_pwm/c6_rv_pwm/revalidation/c6_rv_lab_all31_mc5_0p2s_rev3_lazy.json",
    C6_AUDIT,
    "snh_pwm/c6_rv_pwm/revalidation/c6_rv_lab_all31_mc5_0p2s_rev3_lazy_audit.md",
    "snh_pwm/source/control/cyclic_conformal_reachability.py",
    "snh_pwm/source/tools/run_cyclic_conformal_reachability_lab.py",
    "snh_pwm/source/tools/analyze_cyclic_conformal_reachability_lab.py",
    "snh_pwm/source/tools/aggregate_cyclic_conformal_reachability.py",
    "snh_pwm/source/tests/test_cyclic_conformal_reachability.py",
    "snh_pwm/c6_conformal_reachability/RESEARCH_RU.md",
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_rev1_action_frame_rejected.json",
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_rev2_flux_frame_short.json",
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_seed_20260809.json",
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_seed_20260809_audit.json",
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_seed_20260809_audit.md",
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_seed_20260810.json",
    C6_CONFORMAL_AUDITS[0],
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_seed_20260810_audit.md",
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_seed_20260811.json",
    C6_CONFORMAL_AUDITS[1],
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_lab_seed_20260811_audit.md",
    C6_CONFORMAL_REPLICATION_AUDIT,
    "snh_pwm/c6_conformal_reachability/revalidation/c6_conformal_confirmatory_20260810_20260811_audit.md",
    "model_identification/RESEARCH_RU.md",
    "model_identification/source/mic_ai/ident/model_based.py",
    "model_identification/source/mic_ai/ident/auto_id.py",
    "model_identification/source/mic_ai/core/env.py",
    "model_identification/source/tools/run_model_based_identification_study.py",
    "model_identification/source/tools/analyze_model_based_identification_study.py",
    "model_identification/source/tests/test_model_based_identification.py",
    MODEL_ID_STUDIES[0],
    MODEL_ID_STUDIES[1],
    MODEL_ID_AUDIT,
}


def verify_model_identification_audit(root: Path) -> list[str]:
    failures: list[str] = []
    try:
        audit = json.loads((root / MODEL_ID_AUDIT).read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid model-identification aggregate: {exc}"]

    if audit.get("confirmatory_replication_pass") is not True:
        failures.append("model-identification replication must pass")
    if int(audit.get("paired_trials", 0)) < 24:
        failures.append("model-identification aggregate must contain at least 24 paired trials")
    checks = audit.get("checks")
    if not isinstance(checks, dict) or not checks or not all(checks.values()):
        failures.append("model-identification aggregate checks must all pass")
    claims = audit.get("claims", {})
    expected_claims = {
        "simulation_evidence": True,
        "hardware_validated": False,
        "world_novelty_established": False,
        "defensible_scientific_novelty_candidate": True,
    }
    for key, value in expected_claims.items():
        if claims.get(key) != value:
            failures.append(f"model-identification claim {key} must be {value!r}")

    study_seeds: list[int] = []
    for relative in MODEL_ID_STUDIES:
        try:
            study = json.loads((root / relative).read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"invalid model-identification study {relative}: {exc}")
            continue
        study_seeds.append(int(study.get("seed", -1)))
        if int(study.get("protocol", {}).get("motors", 0)) < 12:
            failures.append(f"model-identification study {relative} must contain at least 12 motors")
        design = study.get("design_robustness", {})
        if int(design.get("prbs_designs", 0)) < 32:
            failures.append(f"model-identification study {relative} needs at least 32 PRBS designs")
        if float(design.get("c6_information_win_rate", 0.0)) < 0.9:
            failures.append(f"model-identification study {relative} lacks D-information evidence")
        c6 = study.get("summary", {}).get("c6_multiscale", {})
        if int(c6.get("current_limit_exceedances", -1)) != 0:
            failures.append(f"model-identification study {relative} exceeds current limit")
        if float(c6.get("median_max_relative_error", 1.0)) > 0.05:
            failures.append(f"model-identification study {relative} exceeds 5% median error")
        study_claims = study.get("claims", {})
        if study_claims.get("hardware_validated") is not False:
            failures.append(f"model-identification study {relative} must not claim hardware validation")
        if study_claims.get("world_novelty_established") is not False:
            failures.append(f"model-identification study {relative} must not claim world novelty")
    if len(set(study_seeds)) != len(MODEL_ID_STUDIES):
        failures.append("model-identification study seeds must be unique")
    return failures


def verify_revalidation_audit(root: Path) -> list[str]:
    path = root / CANONICAL_AUDIT
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid canonical revalidation audit: {exc}"]

    failures: list[str] = []
    expected = {
        "status": "snh_pwm_long_horizon_revalidation",
        "host_long_horizon_ready": True,
        "hardware_ready": False,
        "universal_superiority_supported": False,
    }
    for key, value in expected.items():
        if audit.get(key) != value:
            failures.append(f"canonical audit {key} must be {value!r}")
    if int(audit.get("scenario_count", 0)) < 31:
        failures.append("canonical audit must contain at least 31 scenarios")
    if int(audit.get("mc_trials", 0)) < 30:
        failures.append("canonical audit must contain at least 30 Monte Carlo trials")
    if float(audit.get("simulated_duration_s", 0.0)) < 0.2:
        failures.append("canonical audit duration must be at least 0.2 s")
    if audit.get("failures"):
        failures.append("canonical audit contains failed checks")

    checks = audit.get("checks")
    if not isinstance(checks, dict) or not checks or not all(checks.values()):
        failures.append("canonical audit checks must all pass")

    thresholds = audit.get("safety_thresholds", {})
    try:
        max_current = float(audit.get("max_plant_current_a"))
        trip_current = float(thresholds.get("i_trip_a"))
        if not 0.0 <= max_current < trip_current:
            failures.append("canonical audit current must remain below trip threshold")
    except (TypeError, ValueError):
        failures.append("canonical audit current thresholds are invalid")
    return failures


def verify_c6_audit(root: Path) -> list[str]:
    path = root / C6_AUDIT
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid C6-RV-PWM audit: {exc}"]

    failures: list[str] = []
    expected = {
        "status": "c6_robust_viability_lab_audit",
        "exploratory_mathematical_ready": True,
        "publication_protocol_complete": False,
        "novelty_established": False,
        "hardware_ready": False,
    }
    for key, value in expected.items():
        if audit.get(key) != value:
            failures.append(f"C6-RV-PWM audit {key} must be {value!r}")
    if int(audit.get("scenario_count", 0)) < 31:
        failures.append("C6-RV-PWM audit must contain at least 31 scenarios")
    if int(audit.get("mc_trials", 0)) < 5:
        failures.append("C6-RV-PWM exploratory audit must contain at least five paired trials")
    if float(audit.get("simulated_duration_s", 0.0)) < 0.2:
        failures.append("C6-RV-PWM audit duration must be at least 0.2 s")
    if audit.get("failures"):
        failures.append("C6-RV-PWM audit contains failed checks")
    checks = audit.get("checks")
    if not isinstance(checks, dict) or not checks or not all(checks.values()):
        failures.append("C6-RV-PWM audit checks must all pass")
    try:
        max_current = float(audit.get("max_observed_current_a"))
        trip_current = float(audit.get("current_trip_a"))
        if not 0.0 <= max_current < trip_current:
            failures.append("C6-RV-PWM observed current must remain below trip threshold")
    except (TypeError, ValueError):
        failures.append("C6-RV-PWM current thresholds are invalid")
    return failures


def verify_c6_conformal_audit(root: Path, relative: str) -> list[str]:
    path = root / relative
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid C6 conformal audit {relative}: {exc}"]

    failures: list[str] = []
    expected = {
        "status": "independent_c6_conformal_reachability_audit",
        "defensible_scientific_novelty_candidate": True,
        "world_novelty_established": False,
        "hardware_ready": False,
    }
    for key, value in expected.items():
        if audit.get(key) != value:
            failures.append(f"C6 conformal audit {relative} field {key} must be {value!r}")
    if int(audit.get("repetitions", 0)) < 24:
        failures.append(f"C6 conformal audit {relative} must contain at least 24 repetitions")
    if int(audit.get("finite_sample_rank", 0)) != 381:
        failures.append(f"C6 conformal audit {relative} must use finite-sample rank 381")
    try:
        coverage = float(audit.get("c6_held_out_coverage"))
        target = float(audit.get("target_coverage"))
        undercoverage_p = float(audit.get("pooled_undercoverage_p_value"))
        volume_ratio = float(audit.get("median_c6_to_raw_hypervolume_ratio"))
        sign_p = float(audit.get("paired_sign_test_p_value"))
        if not 0.90 <= coverage <= 1.0 or target != 0.95 or undercoverage_p < 0.01:
            failures.append(f"C6 conformal audit {relative} coverage evidence is invalid")
        if not 0.0 < volume_ratio <= 0.90 or not 0.0 <= sign_p < 0.05:
            failures.append(f"C6 conformal audit {relative} sharpness evidence is invalid")
    except (TypeError, ValueError):
        failures.append(f"C6 conformal audit {relative} metrics are invalid")
    checks = audit.get("checks")
    if not isinstance(checks, dict) or not checks or not all(checks.values()):
        failures.append(f"C6 conformal audit {relative} checks must all pass")
    if audit.get("failures"):
        failures.append(f"C6 conformal audit {relative} contains failed checks")
    return failures


def verify_c6_conformal_replication_audit(root: Path) -> list[str]:
    path = root / C6_CONFORMAL_REPLICATION_AUDIT
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid C6 conformal replication audit: {exc}"]

    failures: list[str] = []
    expected = {
        "status": "c6_conformal_confirmatory_replication_audit",
        "confirmatory_replication_pass": True,
        "defensible_scientific_novelty_candidate": True,
        "world_novelty_established": False,
        "hardware_ready": False,
    }
    for key, value in expected.items():
        if audit.get(key) != value:
            failures.append(f"C6 conformal replication field {key} must be {value!r}")
    if audit.get("root_seeds") != [20260810, 20260811]:
        failures.append("C6 conformal replication must use blind root seeds 20260810 and 20260811")
    if int(audit.get("total_repetitions", 0)) < 48:
        failures.append("C6 conformal replication must contain at least 48 repetitions")
    try:
        coverage = float(audit.get("aggregate_held_out_coverage"))
        undercoverage_p = float(audit.get("aggregate_undercoverage_p_value"))
        volume_ratio = float(audit.get("median_c6_to_raw_hypervolume_ratio"))
        sign_p = float(audit.get("paired_sign_test_p_value"))
        if not 0.90 <= coverage <= 1.0 or undercoverage_p < 0.01:
            failures.append("C6 conformal replication coverage evidence is invalid")
        if not 0.0 < volume_ratio <= 0.90 or not 0.0 <= sign_p < 0.05:
            failures.append("C6 conformal replication sharpness evidence is invalid")
    except (TypeError, ValueError):
        failures.append("C6 conformal replication metrics are invalid")
    checks = audit.get("checks")
    if not isinstance(checks, dict) or not checks or not all(checks.values()):
        failures.append("C6 conformal replication checks must all pass")
    if audit.get("failures"):
        failures.append("C6 conformal replication contains failed checks")
    return failures


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(root: Path) -> dict[str, object]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return {
        "schema": "mic_ai_theory_snapshot/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "files": files,
    }


def verify_manifest(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST_NAME
    failures: list[str] = []
    if not manifest_path.is_file():
        return {"ok": False, "failures": [f"missing {MANIFEST_NAME}"]}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return {"ok": False, "failures": ["manifest files must be a list"]}

    expected_paths: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            failures.append("invalid manifest entry")
            continue
        relative = str(item.get("path", ""))
        if not relative or relative.startswith("/") or ".." in Path(relative).parts:
            failures.append(f"unsafe manifest path: {relative!r}")
            continue
        expected_paths.add(relative)
        path = root / Path(relative)
        if not path.is_file():
            failures.append(f"missing file: {relative}")
            continue
        if path.stat().st_size != int(item.get("bytes", -1)):
            failures.append(f"size mismatch: {relative}")
        if _sha256(path) != str(item.get("sha256", "")):
            failures.append(f"sha256 mismatch: {relative}")

    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != MANIFEST_NAME
    }
    for relative in sorted(actual_paths - expected_paths):
        failures.append(f"untracked snapshot file: {relative}")
    for relative in sorted(REQUIRED_FILES - actual_paths):
        failures.append(f"required file absent: {relative}")
    if CANONICAL_AUDIT in actual_paths:
        failures.extend(verify_revalidation_audit(root))
    if C6_AUDIT in actual_paths:
        failures.extend(verify_c6_audit(root))
    for relative in C6_CONFORMAL_AUDITS:
        if relative in actual_paths:
            failures.extend(verify_c6_conformal_audit(root, relative))
    if C6_CONFORMAL_REPLICATION_AUDIT in actual_paths:
        failures.extend(verify_c6_conformal_replication_audit(root))
    if MODEL_ID_AUDIT in actual_paths:
        failures.extend(verify_model_identification_audit(root))

    return {
        "ok": not failures,
        "schema": manifest.get("schema"),
        "file_count": len(entries),
        "required_file_count": len(REQUIRED_FILES),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write or verify the MIC Theory snapshot manifest.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "research" / "mic_ai_theory",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.write:
        payload = build_manifest(root)
        (root / MANIFEST_NAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    result = verify_manifest(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

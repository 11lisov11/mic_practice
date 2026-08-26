from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_estimator_fed_conformal_lab import (
    MeasurementNoiseConfig,
    build_protocol_manifest,
    run_lab,
)


def _structures_close(actual: Any, expected: Any) -> bool:
    if isinstance(actual, dict) and isinstance(expected, dict):
        actual_by_key = {str(key): value for key, value in actual.items()}
        expected_by_key = {str(key): value for key, value in expected.items()}
        return actual_by_key.keys() == expected_by_key.keys() and all(
            _structures_close(actual_by_key[key], expected_by_key[key]) for key in actual_by_key
        )
    if type(expected) is bool or expected is None or isinstance(expected, str):
        return actual is expected if type(expected) is bool or expected is None else actual == expected
    if isinstance(expected, (int, float)):
        if isinstance(expected, bool) or not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return False
        if math.isnan(float(expected)):
            return math.isnan(float(actual))
        return math.isclose(float(actual), float(expected), rel_tol=1.0e-12, abs_tol=1.0e-15)
    if isinstance(expected, (list, tuple)):
        return isinstance(actual, (list, tuple)) and len(actual) == len(expected) and all(
            _structures_close(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("configuration", {})
    if not isinstance(config, dict):
        raise ValueError("payload configuration must be an object")
    noise_payload = config.get("measurement_noise", {})
    if not isinstance(noise_payload, dict):
        raise ValueError("measurement_noise must be an object")
    noise = MeasurementNoiseConfig(**noise_payload)
    expected = run_lab(
        repetitions=int(config.get("repetitions", 0)),
        training_trajectories=int(config.get("training_trajectories", 0)),
        calibration_trajectories=int(config.get("calibration_trajectories", 0)),
        test_trajectories=int(config.get("test_trajectories", 0)),
        ood_trajectories=int(config.get("ood_trajectories", 0)),
        scored_steps=int(config.get("scored_steps_per_trajectory", 0)),
        burn_in_steps=int(config.get("burn_in_steps", 0)),
        alpha=float(config.get("alpha", float("nan"))),
        seed=int(config.get("seed", -1)),
        measurement_noise=noise,
    )
    expected_manifest, expected_sha256 = build_protocol_manifest(config)
    summary = expected["summary"]
    repetitions = expected["repetitions"]
    rmse_names = ("psi_s_alpha", "psi_s_beta", "psi_r_alpha", "psi_r_beta", "omega_m")
    derived_diagnostics = {
        "median_state_rmse": {
            name: statistics.median(
                float(row["test_estimator_diagnostics"]["state_rmse"][name])
                for row in repetitions
            )
            for name in rmse_names
        },
        "median_oracle_c6_log10_volume": statistics.median(
            float(row["oracle_c6"]["held_out"]["log10_volume"]) for row in repetitions
        ),
        "median_estimator_c6_log10_volume": statistics.median(
            float(row["estimator_c6"]["held_out"]["log10_volume"]) for row in repetitions
        ),
        "estimator_c6_held_out_coverage_range_descriptive": [
            min(float(row["estimator_c6"]["held_out"]["empirical_coverage"]) for row in repetitions),
            max(float(row["estimator_c6"]["held_out"]["empirical_coverage"]) for row in repetitions),
        ],
        "estimator_c6_ood_coverage_range_descriptive": [
            min(float(row["estimator_c6"]["ood_span_1p75"]["empirical_coverage"]) for row in repetitions),
            max(float(row["estimator_c6"]["ood_span_1p75"]["empirical_coverage"]) for row in repetitions),
        ],
    }
    checks = {
        "protocol_manifest_and_source_hash_recomputed": _structures_close(
            payload.get("protocol_manifest"), expected_manifest
        )
        and payload.get("protocol_sha256") == expected_sha256,
        "deterministic_full_payload_replay_pass": _structures_close(payload, expected),
        "estimator_inputs_exclude_true_flux": expected_manifest.get("true_flux_input_to_estimator") is False,
        "true_state_is_simulation_target_only": expected_manifest.get("true_state_use")
        == "simulation_target_and_diagnostics_only",
        "estimator_sector_accuracy_is_finite": math.isfinite(
            float(summary["median_estimated_sector_accuracy"])
        ),
        "no_test_flux_clip_events": int(summary["test_flux_clip_events"]) == 0,
        "bulk_coverage_is_not_claimed_as_inference": payload.get("coverage_inference_claim") is False,
        "method_pass_is_not_auto_claimed": payload.get("host_method_evidence_pass") is False,
        "scientific_novelty_is_not_claimed": payload.get("scientific_novelty_claim") is False
        and payload.get("world_novelty_established") is False,
        "hardware_readiness_is_not_claimed": payload.get("hardware_ready") is False,
    }
    return {
        "status": "estimator_fed_c6_bcr_exploratory_replay_audit",
        "host_exploratory_audit_pass": all(checks.values()),
        "host_method_evidence_pass": False,
        "coverage_inference_claim": False,
        "hardware_ready": False,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "protocol_sha256": expected_sha256,
        "summary": summary,
        "derived_diagnostics": derived_diagnostics,
        "claim_boundary": (
            "deterministically replayed estimator-fed host exploration; coverage remains descriptive and no "
            "independent-probe, hardware-estimator, recursive-safety, or novelty claim is made"
        ),
    }


def _markdown(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    diagnostics = audit["derived_diagnostics"]
    lines = [
        "# Estimator-fed C6-BCR exploratory replay audit",
        "",
        f"- Exploratory audit pass: `{str(audit['host_exploratory_audit_pass']).lower()}`",
        "- Host method evidence pass: `false`",
        "- Coverage inference claim: `false`",
        "- Hardware ready: `false`",
        f"- Protocol SHA-256: `{audit['protocol_sha256']}`",
        f"- Median estimated-sector accuracy: `{summary['median_estimated_sector_accuracy']:.6f}`",
        f"- Median estimator C6 coverage, descriptive: "
        f"`{summary['median_estimator_c6_held_out_coverage_descriptive']:.6f}`",
        f"- Median estimator/oracle volume ratio: `{summary['median_estimator_to_oracle_volume_ratio']:.6g}`",
        f"- Median estimator C6/raw volume ratio: `{summary['median_estimator_c6_to_raw_volume_ratio']:.6f}`",
        f"- Test flux clip events: `{summary['test_flux_clip_events']}`",
        f"- Median stator-flux RMSE alpha/beta: "
        f"`{diagnostics['median_state_rmse']['psi_s_alpha']:.6g}` / "
        f"`{diagnostics['median_state_rmse']['psi_s_beta']:.6g}` Wb",
        f"- Median rotor-flux RMSE alpha/beta: "
        f"`{diagnostics['median_state_rmse']['psi_r_alpha']:.6g}` / "
        f"`{diagnostics['median_state_rmse']['psi_r_beta']:.6g}` Wb",
        f"- Median speed RMSE: `{diagnostics['median_state_rmse']['omega_m']:.6g}` rad/s",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in audit["checks"].items())
    lines.extend(["", f"Boundary: {audit['claim_boundary']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay an estimator-fed C6-BCR exploratory JSON.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    audit = analyze(payload)
    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(audit), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["host_exploratory_audit_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

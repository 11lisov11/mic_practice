#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from urllib import request

from mic_theory_snapshot_check import verify_manifest
from run_metadata import collect_run_metadata


EXPORT_DIR_NAMES = {
    "_calibration_exports",
    "_la_exports",
    "_mic_ai_exports",
    "_preflight_exports",
    "_readiness_exports",
    "_research_exports",
}

CODE_SUFFIXES = {".c", ".cpp", ".h", ".hpp", ".ino", ".py", ".js", ".html", ".css", ".ini", ".toml"}

FIRMWARE_HMI_PREFIXES = [
    "UNOQ_MOTOR",
    "bluepill_uart_pwm_pio",
    "nucleo_g431_uart_bridge_pio",
    "web_hmi",
]

FULL_PREFLIGHT_PREFIXES = [
    *FIRMWARE_HMI_PREFIXES,
    "tools",
    "motor_identification",
]

FULL_PREFLIGHT_FILES = [
    "tools/adb_deploy_web_hmi.py",
    "tools/active_pwm_guard.py",
    "tools/active_pwm_guard_selftest.py",
    "tools/encoder_test.py",
    "tools/logic2_recover.py",
    "tools/dense_overlap_sweep.py",
    "tools/dense_overlap_sweep_selftest.py",
    "tools/ui_access.py",
    "tools/ui_pwm_case.py",
    "tools/ui_pwm_case_selftest.py",
    "tools/ui_pwm_suite.py",
    "tools/scalar_vf_preflight.py",
    "tools/foc_mic_preflight.py",
    "tools/hv_j7_preflight.py",
    "tools/bpfoc_backend_preflight.py",
    "tools/fan_preflight.py",
    "tools/fan_preflight_selftest.py",
    "tools/bench_gate_report.py",
    "tools/bench_gate_report_selftest.py",
    "tools/current_bench_status.py",
    "tools/current_bench_status_selftest.py",
    "tools/refresh_bench_status.py",
    "tools/refresh_bench_status_selftest.py",
    "tools/start_guard_static_check.py",
    "tools/firmware_config_safety_check.py",
    "tools/platformio_env_safety_check.py",
    "tools/protocol_contract_check.py",
    "tools/protocol_safety_selftest.py",
    "tools/pc_direct_hmi_selftest.py",
    "tools/web_hmi_command_guard_selftest.py",
    "tools/bluepill_pwm_selftest_preflight.py",
    "tools/bluepill_runtime_static_preflight.py",
    "tools/bluepill_runtime_static_preflight_selftest.py",
    "tools/bluepill_uart_diagnose.py",
    "tools/bluepill_uart_diagnose_selftest.py",
    "tools/uart_loopback_preflight.py",
    "tools/uart_loopback_preflight_selftest.py",
    "tools/saleae_highlevel_probe.py",
    "tools/saleae_pwm_analyze.py",
    "tools/saleae_pwm_analyze_selftest.py",
    "tools/runtime_python.py",
    "tools/runtime_python_selftest.py",
    "tools/run_metadata.py",
    "tools/run_metadata_selftest.py",
    "tools/mic_ai_compare.py",
    "tools/full_system_preflight.py",
    "tools/unoq_web_server.py",
    "requirements.txt",
]

RESEARCH_MATRIX_FILES = [
    "tools/mic_ai_compare.py",
    "tools/mic_research_matrix.py",
    "tools/mic_research_report.py",
    "tools/run_metadata.py",
    "tools/unoq_web_server.py",
    "requirements.txt",
]

CALIBRATION_FILES = [
    "tools/telemetry_calibration.py",
    "tools/run_metadata.py",
    "tools/unoq_web_server.py",
    "requirements.txt",
]

MOTOR_IDENTIFICATION_PREFIXES = ["motor_identification"]
MOTOR_IDENTIFICATION_FILES = [
    "tools/motor_parameter_identification.py",
    "tools/motor_parameter_identification_selftest.py",
    "requirements-identification.txt",
]
MOTOR_IDENTIFICATION_RESULT_SCHEMA = "mic_ai.motor_identification.result.v1"


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def urlopen_direct(req_or_url, timeout_s: float):
    opener = request.build_opener(request.ProxyHandler({}))
    return opener.open(req_or_url, timeout=timeout_s)


def http_get_json(url: str, timeout_s: float) -> dict:
    with urlopen_direct(url, timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def status(base_url: str, timeout_s: float) -> dict:
    payload = http_get_json(base_url.rstrip("/") + "/api/status", timeout_s)
    if not payload.get("ok"):
        raise RuntimeError(f"status failed: {payload}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"bad status payload: {payload}")
    return data


def as_float(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        out = float(v)
        if not math.isfinite(out):
            return None
        return out
    except Exception:
        return None


def as_int(v, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


def read_json(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def newest(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    return sorted(existing, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def newest_glob(root: Path, pattern: str) -> Path | None:
    return newest(list(root.glob(pattern)))


def add_check(
    checks: list[dict],
    name: str,
    ok: bool,
    *,
    severity: str = "fail",
    detail: str = "",
    evidence=None,
) -> None:
    checks.append(
        {
            "name": name,
            "ok": bool(ok),
            "severity": severity,
            "detail": detail,
            "evidence": evidence,
        }
    )


def should_skip_source_path(path: Path) -> bool:
    parts = set(path.parts)
    if ".git" in parts or ".pio" in parts or ".venv" in parts or "__pycache__" in parts:
        return True
    if any(name in parts for name in EXPORT_DIR_NAMES):
        return True
    return False


def rel_posix(repo: Path, path: Path) -> str:
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def in_prefix(rel: str, prefix: str) -> bool:
    clean = prefix.strip("/\\")
    return rel == clean or rel.startswith(clean + "/")


def latest_file_mtime(repo: Path, suffixes: set[str], *, include_requirements: bool = False) -> tuple[float, str]:
    latest = 0.0
    latest_path = ""
    for path in repo.rglob("*"):
        if not path.is_file() or should_skip_source_path(path):
            continue
        is_requirements = path.name.startswith("requirements") and path.suffix.lower() == ".txt"
        if path.suffix.lower() not in suffixes and not (include_requirements and is_requirements):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > latest:
            latest = mtime
            latest_path = str(path)
    return latest, latest_path


def latest_scoped_source_mtime(repo: Path, prefixes: list[str], files: list[str]) -> dict:
    latest = 0.0
    latest_path = ""
    wanted_files = {f.replace("\\", "/") for f in files}
    for path in repo.rglob("*"):
        if not path.is_file() or should_skip_source_path(path):
            continue
        rel = rel_posix(repo, path)
        if rel not in wanted_files and not any(in_prefix(rel, prefix) for prefix in prefixes):
            continue
        is_requirements = path.name.startswith("requirements") and path.suffix.lower() == ".txt"
        if path.suffix.lower() not in CODE_SUFFIXES and not is_requirements:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > latest:
            latest = mtime
            latest_path = str(path)
    return {
        "path": latest_path,
        "mtime": latest,
        "prefixes": prefixes,
        "files": files,
    }


def collect_source_scopes(repo: Path) -> dict:
    return {
        "full_preflight": latest_scoped_source_mtime(repo, FULL_PREFLIGHT_PREFIXES, FULL_PREFLIGHT_FILES),
        "research_matrix": latest_scoped_source_mtime(repo, FIRMWARE_HMI_PREFIXES, RESEARCH_MATRIX_FILES),
        "calibration": latest_scoped_source_mtime(repo, FIRMWARE_HMI_PREFIXES, CALIBRATION_FILES),
        "motor_identification": latest_scoped_source_mtime(
            repo,
            MOTOR_IDENTIFICATION_PREFIXES,
            MOTOR_IDENTIFICATION_FILES,
        ),
    }


def latest_evidence_source_file_mtime(repo: Path) -> tuple[float, str]:
    # Documentation changes should not force fresh HIL/HV evidence. These are
    # the files that can change firmware behavior, HMI telemetry, or tooling.
    return latest_file_mtime(repo, CODE_SUFFIXES, include_requirements=True)


def latest_documentation_mtime(repo: Path) -> tuple[float, str]:
    return latest_file_mtime(repo, {".md"}, include_requirements=False)


def check_artifact_fresh(
    checks: list[dict],
    path: Path | None,
    *,
    source_scope: dict,
    name: str,
) -> None:
    if path is None:
        add_check(checks, name, False, detail="artifact is missing")
        return
    try:
        artifact_mtime = path.stat().st_mtime
    except OSError:
        add_check(checks, name, False, detail="artifact stat failed", evidence=str(path))
        return
    latest_evidence_source_mtime = float(source_scope.get("mtime", 0.0) or 0.0)
    latest_evidence_source_path = str(source_scope.get("path", "") or "")
    add_check(
        checks,
        name,
        artifact_mtime >= latest_evidence_source_mtime,
        detail=(
            "artifact is older than current evidence-relevant sources"
            if artifact_mtime < latest_evidence_source_mtime
            else "artifact is not older than current evidence-relevant sources"
        ),
        evidence={
            "artifact": str(path),
            "artifact_mtime": artifact_mtime,
            "latest_evidence_source_mtime": latest_evidence_source_mtime,
            "latest_evidence_source_path": latest_evidence_source_path,
            "source_scope": {
                "prefixes": source_scope.get("prefixes", []),
                "files": source_scope.get("files", []),
            },
        },
    )


def latest_full_preflight(repo: Path) -> tuple[Path | None, dict | None]:
    candidates: list[Path] = []
    for path in repo.glob("tools/_preflight_exports/full_system_preflight_*/summary.json"):
        data = read_json(path)
        summary = data.get("summary", {}) if isinstance(data, dict) else {}
        if isinstance(summary, dict) and summary.get("build_only") is True:
            continue
        candidates.append(path)
    path = newest(candidates)
    return path, read_json(path)


def latest_research_matrix(repo: Path) -> tuple[Path | None, dict | None]:
    candidates: list[Path] = []
    for path in repo.glob("tools/_research_exports/*/summary.json"):
        data = read_json(path)
        if data and data.get("tool") == "mic_research_matrix":
            candidates.append(path)
    path = newest(candidates)
    return path, read_json(path)


def latest_calibration(repo: Path) -> tuple[Path | None, dict | None]:
    candidates: list[Path] = []
    for path in repo.glob("tools/_calibration_exports/*/summary.json"):
        data = read_json(path)
        if data and data.get("tool") == "telemetry_calibration":
            candidates.append(path)
    path = newest(candidates)
    return path, read_json(path)


def latest_motor_identification(repo: Path, explicit_path: str = "") -> tuple[Path | None, dict | None]:
    if str(explicit_path).strip():
        path = Path(explicit_path).expanduser().resolve()
        return path, read_json(path)
    candidates: list[Path] = []
    for path in repo.glob("tools/_research_exports/**/result*.json"):
        data = read_json(path)
        if data and data.get("schema") == MOTOR_IDENTIFICATION_RESULT_SCHEMA:
            candidates.append(path)
    path = newest(candidates)
    return path, read_json(path)


def latest_bench_gate(repo: Path) -> tuple[Path | None, dict | None]:
    path = newest(list(repo.glob("tools/_preflight_exports/bench_gate_report_*/summary.json")))
    return path, read_json(path)


def find_named_check(summary: dict | None, name: str) -> dict | None:
    if not isinstance(summary, dict):
        return None
    checks = summary.get("checks", [])
    if not isinstance(checks, list):
        return None
    for item in checks:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def check_live_status(result: dict, args) -> None:
    checks = result["checks"]
    if args.offline:
        add_check(checks, "live_status_available", False, severity="warn", detail="skipped by --offline")
        return
    try:
        st = status(args.url, args.timeout)
    except Exception as exc:
        result["live_status_error"] = str(exc)
        severity = "warn" if args.profile == "bringup" else "fail"
        add_check(checks, "live_status_available", False, severity=severity, detail=str(exc))
        return

    result["live_status"] = st
    add_check(checks, "live_status_available", True, evidence=args.url)
    add_check(checks, "status_safe", st.get("state") == "SAFE", detail=f"state={st.get('state')}")
    add_check(checks, "status_pwm_off", as_int(st.get("pwm"), 1) == 0, detail=f"pwm={st.get('pwm')}")
    add_check(checks, "status_estop_clear", as_int(st.get("estop"), 1) == 0, detail=f"estop={st.get('estop')}")
    add_check(checks, "status_bp_fault_clear", as_int(st.get("bp_fault"), 255) == 0, detail=f"bp_fault={st.get('bp_fault')}")
    add_check(
        checks,
        "status_bp_bad_clear",
        max([as_int(st.get(key), 999999) for key in ("bp_bad_cnt", "bp_bad") if key in st], default=999999) == 0,
        detail=f"bp_bad={max([as_int(st.get(key), 999999) for key in ('bp_bad_cnt', 'bp_bad') if key in st], default=999999)}",
    )
    if args.profile == "science":
        add_check(checks, "status_encoder_ok", as_int(st.get("enc_ok"), 0) == 1, detail=f"enc_ok={st.get('enc_ok')}")

    vdc_values = [as_float(st.get(k)) for k in ("bp_vdc", "vdc")]
    vdc_values = [v for v in vdc_values if v is not None]
    vdc = max(vdc_values, default=None)
    if vdc is None:
        add_check(checks, "status_vbus_readable", False, detail="bp_vdc/vdc missing")
    else:
        add_check(checks, "status_vbus_readable", True, evidence=vdc)
        if not args.allow_hv:
            add_check(
                checks,
                "status_low_voltage_guard",
                abs(vdc) <= float(args.max_start_vdc),
                detail=f"vdc={vdc:.1f} V max_start_vdc={float(args.max_start_vdc):.1f} V",
            )

    bp_age = as_float(st.get("bp_rsp_age_ms", st.get("bp_age_ms")))
    if bp_age is not None:
        add_check(
            checks,
            "status_bluepill_fresh",
            bp_age <= float(args.max_bp_age_ms),
            detail=f"bp_age_ms={bp_age:.0f} max={float(args.max_bp_age_ms):.0f}",
        )
    else:
        add_check(checks, "status_bluepill_fresh", False, detail="bp response age missing")

    if args.profile == "science":
        add_check(checks, "status_temp_valid", as_int(st.get("bp_temp_valid"), 0) == 1, detail=f"bp_temp_valid={st.get('bp_temp_valid')}")
        add_check(checks, "status_temp_not_faulted", as_int(st.get("bp_temp_fault"), 1) == 0, detail=f"bp_temp_fault={st.get('bp_temp_fault')}")
        add_check(checks, "status_phase_valid", as_int(st.get("bp_phase_valid"), 0) == 1, detail=f"bp_phase_valid={st.get('bp_phase_valid')}")
        for key in ("ia", "ib", "ic", "i_rms"):
            add_check(checks, f"status_{key}_readable", as_float(st.get(key)) is not None, detail=f"{key}={st.get(key)}")


def check_theory_snapshot(result: dict, repo: Path, args) -> None:
    root = repo / "research" / "mic_ai_theory"
    verification = verify_manifest(root)
    severity = "fail" if args.profile == "science" else "warn"
    add_check(
        result["checks"],
        "mic_theory_snapshot_integrity",
        verification.get("ok") is True,
        severity=severity,
        detail=f"failures={verification.get('failures', [])}",
        evidence={"root": str(root), **verification},
    )


def check_bench_gate_artifact(result: dict, repo: Path) -> None:
    checks = result["checks"]
    path, data = latest_bench_gate(repo)
    result["latest_bench_gate_summary"] = str(path) if path else None
    if not data:
        add_check(checks, "bench_gate_present", False, detail="no bench_gate_report summary found")
        return

    bench_next_actions = [item for item in data.get("next_actions", []) if isinstance(item, dict)]
    next_ids = [str(item.get("id", "")) for item in bench_next_actions]
    add_check(checks, "bench_gate_present", True, evidence=str(path))
    add_check(
        checks,
        "bench_gate_ready_for_active_pwm",
        data.get("ready_for_active_pwm") is True,
        detail=f"ready_for_active_pwm={data.get('ready_for_active_pwm')} failed={data.get('failed')} warnings={data.get('warnings')}",
        evidence={"summary": str(path), "next_actions": next_ids, "bench_next_actions": bench_next_actions},
    )

    fresh = find_named_check(data, "latest_build_only_preflight_fresh")
    if fresh is not None:
        add_check(
            checks,
            "bench_gate_build_only_fresh",
            fresh.get("ok") is True,
            detail=str(fresh.get("detail", "")),
            evidence=fresh.get("evidence"),
        )

    runtime_checks = [
        ("latest_runtime_static_preflight_pass", "bench_gate_runtime_static_preflight_pass"),
        ("runtime_static_preflight_fresh_for_build", "bench_gate_runtime_static_preflight_fresh"),
        ("runtime_static_pwm_lines_low", "bench_gate_runtime_static_pwm_lines_low"),
    ]
    for bench_name, readiness_name in runtime_checks:
        runtime_check = find_named_check(data, bench_name)
        if runtime_check is not None:
            add_check(
                checks,
                readiness_name,
                runtime_check.get("ok") is True,
                detail=str(runtime_check.get("detail", "")),
                evidence=runtime_check.get("evidence"),
            )

    static_low_checks = [
        ("latest_static_low_preflight_present", "bench_gate_static_low_preflight_present"),
        ("latest_static_low_preflight_pass", "bench_gate_static_low_preflight_pass"),
        ("static_low_preflight_fresh_for_build", "bench_gate_static_low_preflight_fresh"),
        ("static_low_runtime_restored", "bench_gate_static_low_runtime_restored"),
        ("static_low_diagnostic_conclusion_present", "bench_gate_static_low_diagnostic_conclusion"),
    ]
    for bench_name, readiness_name in static_low_checks:
        static_low_check = find_named_check(data, bench_name)
        if static_low_check is not None:
            add_check(
                checks,
                readiness_name,
                static_low_check.get("ok") is True,
                detail=str(static_low_check.get("detail", "")),
                evidence=static_low_check.get("evidence"),
            )

    saleae = find_named_check(data, "saleae_static_probe_fresh_for_build")
    if saleae is not None:
        add_check(
            checks,
            "bench_gate_saleae_static_probe_fresh",
            saleae.get("ok") is True,
            detail=str(saleae.get("detail", "")),
            evidence=saleae.get("evidence"),
        )

    saleae_checks = [
        ("saleae_probe_pwm_static_safe_flag", "bench_gate_saleae_static_safe_flag", "fail"),
        ("saleae_strict_static_safe_exit", "bench_gate_saleae_strict_static_safe_exit", "fail"),
        ("saleae_static_pwm_lines_low", "bench_gate_saleae_static_pwm_lines_low", "fail"),
        ("saleae_static_sample_rate_meets_requested", "bench_gate_saleae_sample_rate", "warn"),
    ]
    for bench_name, readiness_name, severity in saleae_checks:
        saleae_check = find_named_check(data, bench_name)
        if saleae_check is not None:
            add_check(
                checks,
                readiness_name,
                saleae_check.get("ok") is True,
                severity=severity,
                detail=str(saleae_check.get("detail", "")),
                evidence=saleae_check.get("evidence"),
            )

    uart = find_named_check(data, "stm32_uart_protocol_pass")
    if uart is not None:
        add_check(
            checks,
            "bench_gate_uart_protocol_pass",
            uart.get("ok") is True,
            detail=str(uart.get("detail", "")),
            evidence=uart.get("evidence"),
        )


def check_full_preflight_artifact(
    result: dict,
    repo: Path,
    args,
    source_scope: dict,
) -> None:
    checks = result["checks"]
    if args.profile == "bringup":
        add_check(
            checks,
            "full_preflight_required",
            False,
            severity="warn",
            detail="not required for bringup profile; bench_gate_report already verifies latest build-only evidence",
        )
        return

    path, data = latest_full_preflight(repo)
    result["latest_full_preflight_summary"] = str(path) if path else None
    if not data:
        add_check(checks, "full_preflight_present", False, detail="no full_system_preflight summary found")
        return
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    add_check(checks, "full_preflight_present", True, evidence=str(path))
    check_artifact_fresh(
        checks,
        path,
        source_scope=source_scope,
        name="full_preflight_fresh",
    )
    add_check(checks, "full_preflight_overall_pass", summary.get("overall_pass") is True, detail=f"overall_pass={summary.get('overall_pass')}")
    add_check(checks, "full_preflight_required_hil_pass", summary.get("required_hil_pass") is True, detail=f"required_hil_pass={summary.get('required_hil_pass')}")
    add_check(checks, "full_preflight_pwm_suite_pass", summary.get("full_suite_pass") is True, detail=f"full_suite_pass={summary.get('full_suite_pass')}")
    add_check(checks, "full_preflight_final_safe", summary.get("final_safe") is True, detail=f"final_safe={summary.get('final_safe')}")
    add_check(
        checks,
        "full_preflight_bluepill_pwm_selftest_pass",
        summary.get("bluepill_pwm_selftest_pass") is True,
        severity="warn",
        detail=(
            f"bluepill_pwm_selftest_stage_enabled={summary.get('bluepill_pwm_selftest_stage_enabled')} "
            f"bluepill_pwm_selftest_pass={summary.get('bluepill_pwm_selftest_pass')}"
        ),
    )

    if args.profile == "science":
        add_check(
            checks,
            "full_preflight_precharge_relay_gate_enabled",
            summary.get("precharge_relay_stage_enabled") is True,
            detail=f"precharge_relay_stage_enabled={summary.get('precharge_relay_stage_enabled')}",
        )
        add_check(
            checks,
            "full_preflight_precharge_relay_pass",
            summary.get("precharge_relay_pass") is True,
            detail=f"precharge_relay_pass={summary.get('precharge_relay_pass')}",
        )
        add_check(
            checks,
            "full_preflight_precharge_relay_saleae_enabled",
            summary.get("precharge_relay_saleae_enabled") is True,
            detail=f"precharge_relay_saleae_enabled={summary.get('precharge_relay_saleae_enabled')}",
        )
        add_check(
            checks,
            "full_preflight_precharge_relay_saleae_pass",
            summary.get("precharge_relay_saleae_pass") is True,
            detail=f"precharge_relay_saleae_pass={summary.get('precharge_relay_saleae_pass')}",
        )
        add_check(checks, "full_preflight_fan_gate_enabled", summary.get("fan_stage_enabled") is True, detail=f"fan_stage_enabled={summary.get('fan_stage_enabled')}")
        add_check(checks, "full_preflight_fan_pass", summary.get("fan_pass") is True, detail=f"fan_pass={summary.get('fan_pass')}")
        add_check(checks, "full_preflight_bpfoc_gate_enabled", summary.get("bpfoc_stage_enabled") is True, detail=f"bpfoc_stage_enabled={summary.get('bpfoc_stage_enabled')}")
        add_check(checks, "full_preflight_bpfoc_pass", summary.get("bpfoc_pass") is True, detail=f"bpfoc_pass={summary.get('bpfoc_pass')}")
        add_check(checks, "full_preflight_hv_gate_enabled", summary.get("hv_stage_enabled") is True, detail=f"hv_stage_enabled={summary.get('hv_stage_enabled')}")
        add_check(checks, "full_preflight_hv_pass", summary.get("hv_pass") is True, detail=f"hv_pass={summary.get('hv_pass')}")


def check_research_matrix_artifact(
    result: dict,
    repo: Path,
    args,
    source_scope: dict,
) -> None:
    checks = result["checks"]
    if args.profile != "science":
        add_check(checks, "research_matrix_required", False, severity="warn", detail=f"not required for {args.profile} profile")
        return

    path, data = latest_research_matrix(repo)
    result["latest_research_matrix_summary"] = str(path) if path else None
    if not data:
        add_check(checks, "research_matrix_present", False, detail="no mic_research_matrix summary found")
        return

    aggregate = data.get("aggregate", {}) if isinstance(data.get("aggregate"), dict) else {}
    rows = data.get("rows", []) if isinstance(data.get("rows"), list) else []
    add_check(checks, "research_matrix_present", True, evidence=str(path))
    check_artifact_fresh(
        checks,
        path,
        source_scope=source_scope,
        name="research_matrix_fresh",
    )
    add_check(checks, "research_matrix_ready", aggregate.get("research_ready") is True, detail=f"research_ready={aggregate.get('research_ready')}")
    add_check(checks, "research_matrix_has_rows", len(rows) > 0, detail=f"rows={len(rows)}")
    add_check(
        checks,
        "research_matrix_min_repeats",
        min((int(v.get("runs_total", 0)) for v in aggregate.get("by_freq", {}).values()), default=0) >= int(args.min_repeats),
        detail=f"min_repeats_required={int(args.min_repeats)}",
    )
    bench_context = data.get("bench_context", {}) if isinstance(data.get("bench_context"), dict) else {}
    add_check(
        checks,
        "research_matrix_bench_context_present",
        bool(bench_context),
        detail=f"keys={sorted(bench_context.keys()) if bench_context else []}",
    )
    for key in ("motor_label", "load_note", "supply_note"):
        value = str(bench_context.get(key, "")).strip()
        add_check(
            checks,
            f"research_matrix_bench_context_{key}",
            bool(value),
            detail=f"{key}={value}",
        )


def calibration_stat_samples(data: dict, key: str) -> int:
    stats = data.get("stats", {}) if isinstance(data.get("stats"), dict) else {}
    item = stats.get(key, {}) if isinstance(stats.get(key), dict) else {}
    return as_int(item.get("samples"), 0)


def check_calibration_artifact(
    result: dict,
    repo: Path,
    args,
    source_scope: dict,
) -> None:
    checks = result["checks"]
    if args.profile != "science":
        add_check(checks, "calibration_required", False, severity="warn", detail=f"not required for {args.profile} profile")
        return

    path, data = latest_calibration(repo)
    result["latest_calibration_summary"] = str(path) if path else None
    if not data:
        add_check(checks, "calibration_present", False, detail="no telemetry_calibration summary found")
        return

    add_check(checks, "calibration_present", True, evidence=str(path))
    check_artifact_fresh(
        checks,
        path,
        source_scope=source_scope,
        name="calibration_fresh",
    )
    add_check(checks, "calibration_summary_pass", data.get("pass") is True, detail=f"pass={data.get('pass')}")
    add_check(checks, "calibration_samples_collected", as_int(data.get("samples_collected"), 0) > 0, detail=f"samples_collected={data.get('samples_collected')}")
    add_check(checks, "calibration_no_online_error", not data.get("online_error"), detail=f"online_error={data.get('online_error')}")
    zero_current = data.get("zero_current_sanity", {}) if isinstance(data.get("zero_current_sanity"), dict) else {}
    add_check(
        checks,
        "calibration_zero_current_pass",
        zero_current.get("pass") is True,
        detail=f"zero_current_sanity.pass={zero_current.get('pass')}",
    )
    for key in ("bp_vbus_raw", "bp_temp_raw", "ia", "ib", "ic", "i_rms"):
        add_check(checks, f"calibration_{key}_samples", calibration_stat_samples(data, key) > 0, detail=f"samples={calibration_stat_samples(data, key)}")
    add_check(
        checks,
        "calibration_vbus_constants",
        data.get("vbus_calibration") is not None,
        severity="warn",
        detail="missing vbus_calibration block; raw snapshot may still be useful",
    )
    add_check(
        checks,
        "calibration_temp_constants",
        data.get("temp_tso_calibration") is not None,
        severity="warn",
        detail="missing temp_tso_calibration block; raw snapshot may still be useful",
    )


def check_motor_identification_artifact(
    result: dict,
    repo: Path,
    args,
    source_scope: dict,
) -> None:
    checks = result["checks"]
    if args.profile != "science":
        add_check(
            checks,
            "motor_identification_required",
            False,
            severity="warn",
            detail=f"not required for {args.profile} profile",
        )
        return

    path, data = latest_motor_identification(repo, args.motor_identification_result)
    result["latest_motor_identification_result"] = str(path) if path else None
    if not data:
        add_check(
            checks,
            "motor_identification_present",
            False,
            detail="no motor identification result found",
        )
        return

    add_check(checks, "motor_identification_present", True, evidence=str(path))
    check_artifact_fresh(
        checks,
        path,
        source_scope=source_scope,
        name="motor_identification_fresh",
    )
    add_check(
        checks,
        "motor_identification_schema",
        data.get("schema") == MOTOR_IDENTIFICATION_RESULT_SCHEMA,
        detail=f"schema={data.get('schema')}",
    )
    add_check(
        checks,
        "motor_identification_accepted",
        data.get("accepted") is True and data.get("decision") == "accepted",
        detail=f"accepted={data.get('accepted')} decision={data.get('decision')}",
        evidence={"blockers": data.get("blockers", [])},
    )
    claims = data.get("claims", {}) if isinstance(data.get("claims"), dict) else {}
    add_check(
        checks,
        "motor_identification_hardware_source",
        data.get("source_kind") == "hardware" and claims.get("hardware_dataset_accepted") is True,
        detail=(
            f"source_kind={data.get('source_kind')} "
            f"hardware_dataset_accepted={claims.get('hardware_dataset_accepted')}"
        ),
    )
    contract = data.get("contract", {}) if isinstance(data.get("contract"), dict) else {}
    acceptance = data.get("acceptance", {}) if isinstance(data.get("acceptance"), dict) else {}
    add_check(
        checks,
        "motor_identification_contract",
        contract.get("pass") is True,
        detail=f"contract.pass={contract.get('pass')}",
    )
    add_check(
        checks,
        "motor_identification_acceptance_checks",
        acceptance.get("pass") is True
        and isinstance(acceptance.get("checks"), dict)
        and all(value is True for value in acceptance["checks"].values()),
        detail=f"acceptance.pass={acceptance.get('pass')}",
        evidence=acceptance.get("checks"),
    )
    for key in ("rank_gate_prior", "rank_gate_fitted"):
        rank = data.get(key, {}) if isinstance(data.get(key), dict) else {}
        add_check(
            checks,
            f"motor_identification_{key}",
            rank.get("identifiable") is True
            and as_int(rank.get("numerical_rank"), 0) == 7
            and as_int(rank.get("required_rank"), 0) == 7,
            detail=(
                f"identifiable={rank.get('identifiable')} "
                f"rank={rank.get('numerical_rank')}/{rank.get('required_rank')}"
            ),
        )
    dataset = data.get("dataset", {}) if isinstance(data.get("dataset"), dict) else {}
    fit_experiments = dataset.get("fit_experiments", [])
    validation_experiments = dataset.get("validation_experiments", [])
    fit_run_ids = dataset.get("fit_run_ids", [])
    validation_run_ids = dataset.get("validation_run_ids", [])
    add_check(
        checks,
        "motor_identification_independent_validation",
        isinstance(fit_experiments, list)
        and isinstance(validation_experiments, list)
        and bool(fit_experiments)
        and bool(validation_experiments)
        and set(map(str, fit_experiments)).isdisjoint(set(map(str, validation_experiments)))
        and isinstance(fit_run_ids, list)
        and isinstance(validation_run_ids, list)
        and bool(fit_run_ids)
        and bool(validation_run_ids)
        and set(map(str, fit_run_ids)).isdisjoint(set(map(str, validation_run_ids)))
        and as_int(dataset.get("validation_samples"), 0) > 0,
        detail=(
            f"fit_experiments={len(fit_experiments) if isinstance(fit_experiments, list) else 0} "
            f"validation_experiments={len(validation_experiments) if isinstance(validation_experiments, list) else 0} "
            f"fit_run_ids={fit_run_ids} validation_run_ids={validation_run_ids} "
            f"validation_samples={dataset.get('validation_samples')}"
        ),
    )
    integration = data.get("integration", {}) if isinstance(data.get("integration"), dict) else {}
    add_check(
        checks,
        "motor_identification_mic_ai_compatible",
        integration.get("mic_ai_legacy_loader_compatible") is True
        and isinstance(data.get("estimated_params"), dict)
        and all(name in data["estimated_params"] for name in ("Rs", "Rr", "Ls", "Lr", "Lm", "J", "B")),
        detail=f"legacy_loader_compatible={integration.get('mic_ai_legacy_loader_compatible')}",
    )


def add_action(actions: list[dict], seen: set[str], action_id: str, title: str, detail: str, command: str | None = None) -> None:
    if action_id in seen:
        return
    seen.add(action_id)
    item = {
        "id": action_id,
        "title": title,
        "detail": detail,
    }
    if command:
        item["command"] = command
    actions.append(item)


def build_next_actions(failed: list[dict], warnings: list[dict], args) -> list[dict]:
    names = {str(c.get("name")) for c in failed}
    warn_names = {str(c.get("name")) for c in warnings}
    actions: list[dict] = []
    seen: set[str] = set()
    url = args.url

    bench_gate_fail = next((c for c in failed if c.get("name") == "bench_gate_ready_for_active_pwm"), None)
    if bench_gate_fail:
        evidence = bench_gate_fail.get("evidence", {}) if isinstance(bench_gate_fail.get("evidence"), dict) else {}
        bench_action_records = {
            str(item.get("id", "")): item
            for item in evidence.get("bench_next_actions", [])
            if isinstance(item, dict)
        }
        bench_action_details = {
            action_id: str(item.get("detail", ""))
            for action_id, item in bench_action_records.items()
        }
        bench_action_commands = {
            action_id: str(item.get("command", ""))
            for action_id, item in bench_action_records.items()
            if item.get("command")
        }
        for action_id in evidence.get("next_actions", []):
            if action_id == "run_full_build_only_preflight":
                add_action(
                    actions,
                    seen,
                    "run_full_build_only_preflight",
                    "Refresh the build-only preflight evidence.",
                    "Bench gate reports that source files changed after the latest build-only preflight.",
                    "py -3 -u .\\tools\\full_system_preflight.py --build-only --timeout-build 300",
                )
            elif action_id == "run_runtime_static_preflight":
                add_action(
                    actions,
                    seen,
                    "run_runtime_static_preflight",
                    "Run the runtime static PWM preflight.",
                    bench_action_details.get(
                        "run_runtime_static_preflight",
                        "Active PWM requires HV/J7 disconnected, DC bus discharged, latest Blue Pill runtime upload, and Saleae proof that CH0..CH6 are static-safe.",
                    ),
                    bench_action_commands.get("run_runtime_static_preflight", "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off"),
                )
            elif action_id == "run_static_low_isolation_preflight":
                add_action(
                    actions,
                    seen,
                    "run_static_low_isolation_preflight",
                    "Run the static-low isolation preflight.",
                    bench_action_details.get(
                        "run_static_low_isolation_preflight",
                        "Use this only with HV/J7 disconnected and the DC bus discharged. It flashes a diagnostic Blue Pill firmware that keeps PWM pins LOW, captures Saleae CH0..CH6, then restores runtime firmware.",
                    ),
                    bench_action_commands.get("run_static_low_isolation_preflight", "py -3 -u .\\tools\\bluepill_static_low_preflight.py --confirm-hv-off"),
                )
            elif action_id == "run_uart_loopback":
                add_action(
                    actions,
                    seen,
                    "run_uart_loopback",
                    "Run a fresh USB-UART loopback test.",
                    bench_action_details.get(
                        "run_uart_loopback",
                        "Disconnect USB-UART TX/RX from STM32, short TX to RX on the isolated side, then prove the adapter can write/read. Close HMI/serial monitors that may hold the same COM port.",
                    ),
                    bench_action_commands.get("run_uart_loopback", "py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080"),
                )
            elif action_id == "fix_usb_uart_loopback":
                add_action(
                    actions,
                    seen,
                    "fix_usb_uart_loopback",
                    "Fix USB-UART/isolator before reconnecting STM32.",
                    "Adapter loopback failed; inspect isolator power, USB-UART, cable, driver and TX/RX short.",
                )
            elif action_id == "reconnect_stm32_uart_and_rerun_protocol":
                add_action(
                    actions,
                    seen,
                    "reconnect_stm32_uart_and_rerun_protocol",
                    "Reconnect STM32 UART and rerun protocol diagnosis.",
                    "Loopback passed; reconnect TX/RX cross to PA3/PA2 with common isolated GND.",
                    "py -3 -u .\\tools\\bluepill_uart_diagnose.py --port COM3 --dtr-rts-matrix",
                )
            elif action_id == "check_stm32_uart_wiring_or_firmware":
                add_action(
                    actions,
                    seen,
                    "check_stm32_uart_wiring_or_firmware",
                    "Check STM32 UART wiring or flashed firmware.",
                    "PC can write bytes but STM32 does not answer. Check PA2/PA3, isolated GND, power and bluepill_uart_pwm firmware.",
                )
            elif action_id == "refresh_saleae_static_probe":
                add_action(
                    actions,
                    seen,
                    "refresh_saleae_static_probe",
                    "Refresh the static Saleae PWM capture.",
                    "Capture CH0..CH6 and run the static no-edge/no-overlap analysis before any active PWM test.",
                    "py -3 -u .\\tools\\saleae_highlevel_probe.py --channels 0,1,2,3,4,5,6 --rate 24000000 --auto-rate --duration 0.12 --require-static-safe",
                )
            elif action_id == "fix_pwm_safe_static_levels":
                add_action(
                    actions,
                    seen,
                    "fix_pwm_safe_static_levels",
                    "Fix SAFE/static PWM input levels before active PWM.",
                    bench_action_details.get(
                        "fix_pwm_safe_static_levels",
                        "Saleae shows at least one PWM input CH0..CH5 HIGH while the bench should be SAFE. Verify channel mapping, Blue Pill power/firmware, GPIO force-low behavior, IPM pull-ups, and keep EM_STOP/HV disabled until CH0..CH5 are LOW.",
                    ),
                    bench_action_commands.get("fix_pwm_safe_static_levels", "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off"),
                )
            elif action_id == "restore_hmi_safe_status":
                add_action(
                    actions,
                    seen,
                    "restore_hmi_safe_status",
                    "Restore safe live HMI/status access.",
                    bench_action_details.get(
                        "restore_hmi_safe_status",
                        "Active PWM requires /api/status to be reachable and to report SAFE, pwm=0, enable=false, estop=0, bp_fault=0, bp_bad/bp_bad_cnt=0.",
                    ),
                    bench_action_commands.get("restore_hmi_safe_status", "py -3 -u .\\tools\\unoq_web_server.py --serial COM3 --baud 115200 --port 18080"),
                )

    if "live_status_available" in names:
        add_action(
            actions,
            seen,
            "restore_hmi_safe_status",
            "Restore safe live HMI/status access.",
            "Readiness cannot prove bench state until /api/status is reachable.",
            "py -3 -u .\\tools\\ui_access.py --forward-port 18080",
        )

    if "live_status_available" in names or "status_bluepill_fresh" in names:
        add_action(
            actions,
            seen,
            "diagnose_bluepill_uart",
            "Diagnose the direct PC-to-Blue-Pill UART path.",
            "This sends only safe MODE_OFF+CLEAR_FAULT frames and distinguishes write-timeout, no-response, and protocol-reply cases.",
            "py -3 -u .\\tools\\bluepill_uart_diagnose.py --port COM3 --dtr-rts-matrix",
        )

    unsafe = {
        "status_safe",
        "status_pwm_off",
        "status_estop_clear",
        "status_bp_fault_clear",
        "status_bp_bad_clear",
        "status_bluepill_fresh",
        "status_temp_valid",
        "status_temp_not_faulted",
        "status_phase_valid",
    }
    if names & unsafe:
        add_action(
            actions,
            seen,
            "restore_safe_bench",
            "Return the bench to a clean SAFE state.",
            "Do not run research commands until status shows SAFE, pwm=0, estop=0, bp_fault=0, bp_bad_cnt=0 and fresh Blue Pill telemetry.",
        )

    if "status_low_voltage_guard" in names or "status_vbus_readable" in names:
        add_action(
            actions,
            seen,
            "resolve_vbus_guard",
            "Resolve Vbus before low-voltage tests.",
            "Discharge/remove HV for low-voltage runs, fix Vbus telemetry if it is unreadable, or rerun only an intentional HV stage with --allow-hv.",
        )

    if "status_encoder_ok" in names:
        add_action(
            actions,
            seen,
            "fix_encoder",
            "Fix and prove AS5600 encoder telemetry.",
            "MIC scientific runs require enc_ok=1 and stable angle/speed telemetry.",
            f"py -3 -u .\\tools\\encoder_test.py --url {url} --duration 3 --poll 0.05",
        )

    full_preflight_names = {
        "full_preflight_present",
        "full_preflight_fresh",
        "full_preflight_overall_pass",
        "full_preflight_required_hil_pass",
        "full_preflight_pwm_suite_pass",
        "full_preflight_final_safe",
        "full_preflight_precharge_relay_gate_enabled",
        "full_preflight_precharge_relay_pass",
        "full_preflight_precharge_relay_saleae_enabled",
        "full_preflight_precharge_relay_saleae_pass",
        "full_preflight_fan_gate_enabled",
        "full_preflight_fan_pass",
        "full_preflight_bpfoc_gate_enabled",
        "full_preflight_bpfoc_pass",
    }
    if names & full_preflight_names:
        add_action(
            actions,
            seen,
            "run_low_voltage_full_preflight",
            "Run a fresh extended low-voltage regression.",
            "This refreshes build, HMI, encoder, PB4 precharge relay/CH7, scalar/VF, FOC/MIC, Saleae PWM/deadtime, fan and BPFOC evidence for the current worktree.",
            f"py -3 -u .\\tools\\full_system_preflight.py --url {url} --with-precharge-relay --precharge-relay-arm-confirm \"ARM LOWV\" --precharge-relay-la-channel 7 --with-fan --with-bpfoc",
        )

    if "full_preflight_bluepill_pwm_selftest_pass" in warn_names or "full_preflight_bluepill_pwm_selftest_pass" in names:
        add_action(
            actions,
            seen,
            "run_bluepill_pwm_selftest",
            "Run the ST-Link Blue Pill PWM self-test capture.",
            "Use this when UART/HMI control is blocked or when you need direct evidence that TIM1 complementary PWM pins toggle without static overlap. Requires HV disconnected and DC bus discharged.",
            "py -3 -u .\\tools\\bluepill_pwm_selftest_preflight.py --confirm-hv-off --rate 6000000",
        )

    if "full_preflight_hv_gate_enabled" in names or "full_preflight_hv_pass" in names:
        add_action(
            actions,
            seen,
            "run_hv_preflight",
            "Run HV/J7 regression after low-voltage PASS.",
            "Only do this on an intentionally energized, externally protected HV bench with E-STOP and verified Vbus telemetry.",
            f"py -3 -u .\\tools\\full_system_preflight.py --url {url} --with-hv",
        )

    calibration_fail = {n for n in names if n.startswith("calibration_")}
    if "calibration_present" in names or calibration_fail:
        add_action(
            actions,
            seen,
            "capture_telemetry_calibration",
            "Capture telemetry calibration evidence.",
            "At minimum capture raw Vbus, temperature, current and fan telemetry snapshots; SAFE/pwm=0 zero-current sanity must pass before scientific current comparisons.",
            f"py -3 -u .\\tools\\telemetry_calibration.py --url {url} --samples 100",
        )

    calibration_warn = {"calibration_vbus_constants", "calibration_temp_constants"} & warn_names
    if calibration_warn:
        add_action(
            actions,
            seen,
            "compute_calibration_constants",
            "Compute final Vbus/temperature constants if needed.",
            "Use known meter readings and known heatsink temperature to turn raw snapshots into constants before making calibrated claims.",
            "py -3 -u .\\tools\\telemetry_calibration.py --vbus-zero-raw <ZERO_RAW> --vbus-cal-raw <CAL_RAW> --meter-vdc <METER_VDC> --known-temp-c <TEMP_C> --allow-hv",
        )

    research_names = {n for n in names if n.startswith("research_matrix_")}
    if "research_matrix_present" in names or research_names:
        add_action(
            actions,
            seen,
            "run_mic_research_matrix",
            "Run the MIC/FOC research matrix on a rotating motor.",
            "This produces aggregate.csv and summary.json with repeated FOC vs MIC evidence. Use --allow-hv only after HV/J7 PASS.",
            f"py -3 -u .\\tools\\mic_research_matrix.py --url {url} --freqs 2,5,10,20 --repeats {int(args.min_repeats)} --duration 10 --warmup 1.0 --require-encoder --motor-label \"<motor/nameplate>\" --load-note \"<load condition>\" --supply-note \"<supply/current-limit>\"",
        )

        add_action(
            actions,
            seen,
            "generate_mic_report",
            "Generate the Markdown/SVG research report.",
            "Run this after the matrix finishes and point it to the produced summary.json.",
            "py -3 -u .\\tools\\mic_research_report.py .\\tools\\_research_exports\\<run>\\summary.json --calibration-summary .\\tools\\_calibration_exports\\<run>\\summary.json",
        )

    if "mic_theory_snapshot_integrity" in names or "mic_theory_snapshot_integrity" in warn_names:
        add_action(
            actions,
            seen,
            "repair_mic_theory_snapshot",
            "Repair or intentionally refresh the MIC Theory snapshot.",
            "Scientific conclusions require all transferred theory, article and evidence files to match their SHA-256 manifest.",
            "py -3 -u .\\tools\\mic_theory_snapshot_check.py",
        )

    motor_identification_fail = {
        name for name in names if name.startswith("motor_identification_")
    }
    if motor_identification_fail:
        add_action(
            actions,
            seen,
            "capture_motor_identification_dataset",
            "Capture and identify motor parameters from independent hardware runs.",
            "Synthetic results do not satisfy the science gate. Record calibrated standstill, free-run and coast traces for separate fit and validation run_id values, validate the bundle, then run the offline identifier.",
            "py -3 -u .\\tools\\motor_parameter_identification.py validate --input <capture_bundle>; if ($LASTEXITCODE -eq 0) { py -3 -u .\\tools\\motor_parameter_identification.py identify --input <capture_bundle> --prior <prior.json> --output .\\tools\\_research_exports\\motor_identification_hardware\\result.json }",
        )

    if not actions:
        add_action(
            actions,
            seen,
            "ready_to_review",
            "No blocking next action from this gate.",
            "Review warnings, archive artifacts, then proceed according to the bench safety plan.",
        )

    return actions


def main() -> int:
    ap = argparse.ArgumentParser(description="Check bench readiness for bring-up, low-voltage regression, or MIC scientific runs.")
    ap.add_argument("--url", default="http://127.0.0.1:18080")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--profile", choices=("bringup", "science", "low_voltage"), default="science")
    ap.add_argument("--offline", action="store_true", help="Skip live /api/status checks.")
    ap.add_argument("--allow-hv", action="store_true", help="Do not fail live status when Vbus is above --max-start-vdc.")
    ap.add_argument("--max-start-vdc", type=float, default=60.0)
    ap.add_argument("--max-bp-age-ms", type=float, default=1000.0)
    ap.add_argument("--min-repeats", type=int, default=3)
    ap.add_argument(
        "--motor-identification-result",
        default="",
        help="Optional explicit motor-identification result JSON; science profile otherwise uses the latest result under tools/_research_exports.",
    )
    ap.add_argument("--outdir", default="tools/_readiness_exports")
    ap.add_argument("--tag", default="research_readiness")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    latest_evidence_mtime, latest_evidence_path = latest_evidence_source_file_mtime(repo)
    latest_doc_mtime, latest_doc_path = latest_documentation_mtime(repo)
    source_scopes = collect_source_scopes(repo)
    run_dir = (repo / args.outdir).resolve() / f"{args.tag}_{ts_tag()}"
    run_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "tool": "research_readiness_check",
        "profile": args.profile,
        "url": args.url,
        "run_dir": str(run_dir),
        "run_metadata": collect_run_metadata(repo),
        "latest_evidence_source": {
            "path": latest_evidence_path,
            "mtime": latest_evidence_mtime,
            "scope": "firmware, HMI, tooling, config, requirements; documentation excluded from artifact freshness",
        },
        "latest_documentation": {
            "path": latest_doc_path,
            "mtime": latest_doc_mtime,
        },
        "source_scopes": source_scopes,
        "checks": [],
    }

    check_live_status(result, args)
    check_theory_snapshot(result, repo, args)
    check_bench_gate_artifact(result, repo)
    check_full_preflight_artifact(result, repo, args, source_scopes["full_preflight"])
    check_research_matrix_artifact(result, repo, args, source_scopes["research_matrix"])
    check_calibration_artifact(result, repo, args, source_scopes["calibration"])
    check_motor_identification_artifact(
        result,
        repo,
        args,
        source_scopes["motor_identification"],
    )

    failed = [c for c in result["checks"] if c.get("severity") == "fail" and not c.get("ok")]
    warnings = [c for c in result["checks"] if c.get("severity") == "warn" and not c.get("ok")]
    result["ready"] = len(failed) == 0
    result["failed_checks"] = failed
    result["warnings"] = warnings
    result["next_actions"] = build_next_actions(failed, warnings, args)
    result["checked_at_unix"] = time.time()

    out_path = run_dir / "summary.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "ready": result["ready"],
                "profile": args.profile,
                "failed": len(failed),
                "warnings": len(warnings),
                "next_actions": len(result["next_actions"]),
                "summary": str(out_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["ready"] else 4


if __name__ == "__main__":
    raise SystemExit(main())

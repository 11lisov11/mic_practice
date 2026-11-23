"""Run offline release checks, retaining logs and exact source fingerprints."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


PROJECT = "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"


def source_hashes(root):
    paths = list((root / PROJECT / "Src").glob("*.c"))
    paths += list((root / PROJECT / "Inc").glob("*.h"))
    paths += [p for p in (root / "UNOQ_MOTOR").iterdir()
              if p.suffix in (".ino", ".h", ".cpp")]
    paths += [root / "web_hmi/server.py", root / "web_hmi/requirements.txt"]
    paths += list((root / "web_hmi/static").glob("*"))
    paths += list((root / "tools").glob("*.py"))
    paths += list((root / "tools").glob("*.cfg"))
    paths += list((root / "research/uart_v3").glob("*"))
    paths += list((root / "research/ipm_break").glob("*"))
    paths += list((root / "research/uart_rx").glob("*"))
    paths += [root / "tools/build_acim_reference.ps1", root / "tools/build_unoq_mcsdk_scalar.ps1"]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths)) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--baseline-source", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources_before = source_hashes(root)
    simple = ["fault_diagnostics_selftest", "fault_context_selftest",
              "web_hmi_command_guard_selftest", "web_hmi_control_access_selftest",
              "vbus_calibration_identity_selftest", "install_vbus_hmi_fix_selftest",
              "wifi_motor_first_start_selftest", "uno_nucleo_mcsdk_contract_check",
              "as5600_hmi_selftest", "as5600_wifi_readonly_probe_selftest",
              "verify_production_guard_semantics_selftest",
              "audit_uart_noise_readonly_selftest", "power_stage_readonly_audit_selftest",
              "verify_production_wifi_idle_selftest", "verify_wifi_command_path_selftest",
              "analyze_mcsdk_modulation_selftest", "collect_wifi_telemetry_selftest",
              "wifi_http_via_wsl_selftest", "run_wifi_nucleo_pwm_bench_selftest",
              "install_unoq_control_owner_selftest", "run_current_pwm_801_selftest",
              "reset_unoq_nucleo_idle_selftest", "wifi_motor_extended_trial_selftest",
              "install_uart_v3_pair_selftest", "uart_v3_hmi_status_selftest",
              "uart_v3_pwm_bench_selftest", "powered_trial_selftest", "sender_trial_tools_selftest",
              "vf_30s_profile_selftest", "coast30_gate_selftest", "unoq_wifi_hmi_deploy_selftest", "ipm_break_install_selftest",
              "router_serial_ownership_selftest", "unoq_rx_fix_selftest", "rx_short_trial_selftest"]
    detailed = ["production_mcsdk_link_dynamic_selftest", "uno_supervisory_runtime_selftest",
                "mcsdk_async_clear_diagnostics_selftest", "ipm_sd_irq_selftest",
                "mcsdk_startup_ramp_selftest", "uno_matrix_renderer_selftest",
                "uart_guard_release_selftest", "uart_fifo_fault_stress_selftest",
                "uno_control_ownership_selftest", "uart_command_corruption_selftest",
                "uno_reply_restart_selftest", "uart_v3_candidate_selftest", "uart_v3_uno_peer_selftest",
                "uart_v3_sender_invariant_selftest", "ipm_break_snapshot_selftest", "ipm_break_wifi_selftest",
                "unoq_idle_deadline_selftest", "unoq_rpc_priority_selftest", "unoq_bridge_boot_selftest",
                "unoq_llext_selftest", "unoq_fault_context_fix_selftest", "unoq_boot_trial_selftest"]
    tests = []
    start = time.monotonic()
    for name in simple + detailed:
        cmd = [sys.executable, str(root / "tools" / (name + ".py"))]
        if name in detailed:
            cmd += ["--outdir", str(out / name)]
        if name == "production_mcsdk_link_dynamic_selftest":
            cmd += ["--mutation-check"]
        if name == "uart_v3_candidate_selftest":
            cmd += ["--integrated"]
        if name == "uart_guard_release_selftest":
            cmd += ["--baseline-source", str(args.baseline_source.resolve(strict=True))]
        try:
            proc = subprocess.run(cmd, cwd=root, capture_output=True, timeout=300)
            (out / (name + ".log")).write_bytes(proc.stdout + proc.stderr)
            entry = {"test": name, "exit_code": proc.returncode,
                     "pass": proc.returncode == 0}
            if name in detailed and (out / name / "report.json").exists():
                report = json.loads((out / name / "report.json").read_text(encoding="utf-8-sig"))
                entry["pass"] = entry["pass"] and report.get("pass") is True
                entry["report"] = name + "/report.json"
        except subprocess.TimeoutExpired as exc:
            (out / (name + ".log")).write_bytes((exc.stdout or b"") + (exc.stderr or b""))
            entry = {"test": name, "exit_code": None, "pass": False, "error": "timeout"}
        tests.append(entry)
        print(json.dumps(entry), flush=True)
    unchanged = sources_before == source_hashes(root)
    report = {"schema": "mic_ai.uart_update_regression.v1",
              "pass": all(t["pass"] for t in tests) and unchanged,
              "tests": tests, "source_sha256": sources_before,
              "sources_unchanged_during_tests": unchanged,
              "duration_sec": round(time.monotonic() - start, 3),
              "hardware_commands": 0, "hardware_validated": False,
              "hv_release_approved": False,
              "checksum_qualification_pass": json.loads(
                  (out / "uart_command_corruption_selftest/report.json").read_text()
              ).get("checksum_qualification_pass", False)
              if (out / "uart_command_corruption_selftest/report.json").exists() else False}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pass": report["pass"], "suites": len(tests), "report": str(out / "report.json")}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify production idle guards over Wi-Fi without enabling PWM."""
import argparse
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from run_wifi_nucleo_pwm_bench import (
    WifiHmi, read_control_token, wait_status, capture, analyze_static, sha256,
)
from runtime_python import ensure_modules_or_reexec


def safe_zero_bus(status):
    try:
        vdc = float(status["vdc"])
        age = float(status["bp_age_ms"])
        return (math.isfinite(vdc) and 0 <= vdc <= 2 and math.isfinite(age)
                and 0 <= age < 300 and status.get("bp_vbus_valid") == 1
                and status.get("state") == "SAFE" and status.get("pwm") == 0
                and status.get("hmi_hv_armed") == 0
                and (int(status["bp_status"]) & 0x22) == 0)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def uart_progress(samples):
    """Use adjacent sequence changes when the good-message counter saturates."""
    if len(samples) < 2 or not all(safe_zero_bus(s) for s in samples):
        return False
    for sample in samples:
        if type(sample.get("bp_good")) is not int or not 0 <= sample["bp_good"] <= 65535:
            return False
        if type(sample.get("bp_seq")) is not int or not 0 <= sample["bp_seq"] <= 255:
            return False
    return (any(b["bp_good"] > a["bp_good"] for a, b in zip(samples, samples[1:]))
            or (all(s["bp_good"] == 65535 for s in samples)
                and any(b["bp_seq"] != a["bp_seq"] for a, b in zip(samples, samples[1:]))))


def raw_uart_diagnostics():
    # Read-only RPC access exposes firmware counters not yet mapped by the HMI.
    # All control commands still use the direct Wi-Fi HTTP endpoint.
    script = """
import sys, json
sys.path.insert(0, '/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
client = RouterClient('/var/run/arduino-router.sock')
try:
    reply = client.call('get', [])
    if not reply or reply[2] is not None or not isinstance(reply[3], str):
        raise RuntimeError('get RPC unavailable')
    data = dict(item.split('=', 1) for item in reply[3].split() if '=' in item)
    keys = ('bp_clear_pending', 'bp_bad_integrity', 'bp_bad_sequence', 'bp_superseded')
    print(json.dumps({k: int(data[k]) for k in keys}))
finally:
    client.close()
"""
    result = subprocess.run(
        ["adb", "-s", "3880458060", "shell",
         "/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python", "-"],
        input=script, text=True, capture_output=True, timeout=10, check=True)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-hv-off", action="store_true")
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--wifi-via-wsl", action="store_true")
    parser.add_argument("--uno-image", type=Path,
                        help="Exact UNO Q image installed during this run; defaults to package image")
    parser.add_argument("--expected-uno-build", type=int,
                        help="Expected UNO Q build ID; defaults to package manifest")
    args = parser.parse_args()
    if not args.confirm_hv_off or not 60 <= args.samples <= 600:
        parser.error("HV-off confirmation and 60..600 samples required")
    ensure_modules_or_reexec(["saleae"], "MIC_PRACTICE_PRODUCTION_IDLE_REEXEC")
    from saleae import automation

    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    package = args.package.resolve()
    manifest = json.loads((package / "uno_q_mcu/unoq_mcsdk_scalar.build-manifest.json").read_text(encoding="utf-8-sig"))
    nucleo_manifest = json.loads((package / "nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json").read_text(encoding="utf-8-sig"))
    report = {"schema": "mic_ai.production_wifi_idle.v1", "pass": False,
              "host_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "production_outputs_off_no_power_stage_validation",
              "commands": [], "samples": [], "checks": {}, "images": {}}
    for key, path in (
        ("uno_production", args.uno_image or package / "uno_q_mcu/UNOQ_MOTOR.ino.elf-zsk.bin"),
        ("nucleo_production", package / "nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"),
    ):
        report["images"][key] = {"path": str(path), "sha256": sha256(path)}
    hmi = None
    try:
        token = read_control_token("adb", "3880458060", "/home/arduino/.config/mic-ai/control_token")
        hmi = WifiHmi("http://192.168.1.138:8080", token, report["commands"],
                      via_wsl=args.wifi_via_wsl)
        before = hmi.status()
        report["before"] = before
        if not safe_zero_bus(before):
            raise RuntimeError("Expected disarmed, outputs-off, zero-bus state")
        hmi.post("/api/stop-sequence", {"emergency": False}, "production STOP")
        hmi.command("CLEAR")
        wait_status(hmi, lambda s: s.get("pwm") == 0 and s.get("bp_bad") == 0
                    and s.get("bp_bad_cnt") == 0, 8, "zero UART counters after explicit CLEAR")
        baseline = raw_uart_diagnostics()
        report["uart_baseline"] = baseline
        if baseline["bp_clear_pending"] != 0:
            raise RuntimeError("CLEAR did not complete; counters could be repeatedly reset")
        began = time.monotonic()
        for _ in range(args.samples):
            status = hmi.status()
            status["host_elapsed_s"] = time.monotonic() - began
            report["samples"].append(status)
            if status.get("pwm") != 0:
                raise RuntimeError("Unexpected PWM enabled during idle test")
            time.sleep(0.5)
        samples = report["samples"]
        checks = report["checks"]
        expected_uno_build = args.expected_uno_build or manifest["firmware_build_id"]
        checks["new_uno_identity"] = all(s.get("fw_build") == expected_uno_build for s in samples)
        checks["nucleo_identity"] = all(s.get("mc_fw_build") == nucleo_manifest["firmware_build_id"] for s in samples)
        checks["safe_zero_bus_all_samples"] = all(safe_zero_bus(s) for s in samples)
        checks["safe_vf_disarmed"] = all(s.get("state") == "SAFE" and s.get("mode") == "VF"
            and s.get("hmi_hv_armed") == 0 and s.get("pwm") == 0 for s in samples)
        checks["no_reported_uart_errors"] = all(s.get("bp_bad") == 0 and s.get("bp_bad_cnt") == 0 for s in samples)
        checks["fresh_uart"] = all(float(s.get("bp_age_ms", 999999)) < 300 for s in samples)
        checks["internal_fault_code_5_with_zero_bus"] = all(
            s.get("bp_fault") == 5 and float(s.get("vdc", 999)) <= 2 for s in samples
        )
        checks["uart_progress"] = uart_progress(samples)
        report["duration_s"] = time.monotonic() - began
        # No ARM request is sent. An unarmed START must be rejected.
        if not safe_zero_bus(hmi.status()):
            raise RuntimeError("Unexpected ARM before negative test")
        code, response = hmi.request("POST", "/api/start-sequence", {})
        report["commands"].append({"label": "negative unarmed START", "path": "/api/start-sequence",
                                   "body": {}, "http_status": code,
                                   "transport": "wsl_nat_wifi_http" if args.wifi_via_wsl else "direct_wifi_http"})
        report["start_rejected"] = {"http_status": code, "response": response}
        checks["start_rejected_unarmed_zero_bus"] = code == 409 and response.get("ok") is False
        if not checks["start_rejected_unarmed_zero_bus"]:
            raise RuntimeError("Production START guard failed")
        with automation.Manager.connect(port=10430) as manager:
            device = "A7D1BB81883C0092"
            if not any(d.device_id == device and not d.is_simulation for d in manager.get_devices()):
                raise RuntimeError("Physical Saleae not present")
            csv = capture(manager, device, out / "production_static", 0.2)
            report["production_outputs"] = analyze_static(csv)
            checks["all_six_static_low"] = report["production_outputs"]["pass"]
        report["after"] = hmi.status()
        report["pass"] = all(checks.values())
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if hmi is not None:
            code, response = hmi.fail_safe_stop()
            report["final_stop"] = {"http_status": code, "ok": response.get("ok")}
            if code != 200 or response.get("ok") is not True:
                report["pass"] = False
            try:
                final = hmi.status()
                report["after_final_stop"] = final
                report["checks"]["safe_after_final_stop"] = safe_zero_bus(final)
                diagnostics = raw_uart_diagnostics()
                report["uart_final"] = diagnostics
                report["checks"]["clear_completed"] = diagnostics["bp_clear_pending"] == 0
                baseline = report.get("uart_baseline", {})
                report["checks"]["lifetime_uart_errors_unchanged"] = all(
                    diagnostics[k] == baseline.get(k) for k in ("bp_bad_integrity", "bp_bad_sequence"))
                report["checks"]["final_uart_counters_zero"] = final.get("bp_bad") == 0 and final.get("bp_bad_cnt") == 0
                report["pass"] = report["pass"] and all(report["checks"].values())
            except Exception as exc:
                report["final_state_error"] = str(exc)
                report["pass"] = False
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("pass", "checks", "error", "duration_s")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

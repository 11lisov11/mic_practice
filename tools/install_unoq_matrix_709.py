"""Install the audited matrix-only Uno update on an already discharged stand."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

from install_vbus_hmi_fix_remote import precheck
from run_wifi_nucleo_pwm_bench import WifiHmi, read_control_token


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / "artifacts/current_pwm_20261007/full_debug_r1"
    destination = out / "matrix_709_install.json"
    if destination.exists():
        raise RuntimeError("Do not overwrite installation evidence")
    audit = json.loads((out / "matrix_only_source_audit.json").read_text())
    if audit.get("pass") is not True:
        raise RuntimeError("Matrix-only source audit required")
    sketch = root / "UNOQ_MOTOR/UNOQ_MOTOR.ino"
    if hashlib.sha256(sketch.read_bytes()).hexdigest() != audit["candidate_sha256"]:
        raise RuntimeError("Source changed after audit")
    folder = out / "uno_matrix_709"
    manifest = json.loads((folder / "unoq_mcsdk_scalar.build-manifest.json").read_text(encoding="utf-8-sig"))
    if manifest["firmware_build_id"] != 2026100709:
        raise RuntimeError("Unexpected candidate identity")
    image = folder / manifest["flash_artifact"]
    entry = next(a for a in manifest["artifacts"] if a["file"] == image.name)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    if image.stat().st_size != entry["bytes"] or digest != entry["sha256"].lower():
        raise RuntimeError("Candidate image hash mismatch")
    token = read_control_token("adb", "3880458060", "/home/arduino/.config/mic-ai/control_token")
    hmi = WifiHmi("http://192.168.1.138:8080", token, [], via_wsl=True)
    report = {"pass": False, "image_sha256": digest, "nucleo_programmed": False,
              "motor_start_commands": [], "recovery_commands": [], "samples": []}

    def safe_status(recover=False):
        deadline = time.monotonic() + 30
        recovered = False
        while True:
            try:
                status = hmi.status()
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
                continue
            ok, reason = precheck(status)
            if (not ok and recover and not recovered and status.get("bp_fault") == 2
                    and status.get("mc_bad_cnt") == 0 and precheck(dict(status, bp_fault=5))[0]):
                report["recovery_commands"].append({"command": "CLEAR", "before": status,
                                                    "reason": "expected idle peer reset timeout"})
                code, response = hmi.request("POST", "/api/cmd", {"cmd": "CLEAR"})
                if code != 200 or response.get("ok") is not True:
                    raise RuntimeError("Idle reset CLEAR rejected")
                recovered = True
                time.sleep(1)
                continue
            if not ok:
                if recover and time.monotonic() < deadline and reason.startswith("stale telemetry"):
                    time.sleep(1)
                    continue
                raise RuntimeError(reason)
            return status

    try:
        report["before"] = safe_status()
        if (report["before"]["fw_build"], report["before"]["mc_fw_build"]) != (2026100708, 2026100708):
            raise RuntimeError("Installation requires known baseline 708/708")
        command = ["arduino-cli", "upload", "-p", "COM10", "-b", "arduino:zephyr:unoq", "-i", str(image),
                   "--upload-property", f"upload.artifacts.sketch={image}",
                   "--upload-property", "upload.port.properties.serialNumber=3880458060"]
        for label, args in (("flash", command), ("verify", command + [
                "--upload-property", f"build.variant.path={root / 'tools'}",
                "--upload-property", "openocd_cfg=verify_unoq_sketch.cfg"])):
            safe_status(recover=label == "verify")
            result = subprocess.run(args, capture_output=True, text=True, timeout=120)
            (out / f"matrix_709_{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            if result.returncode:
                raise RuntimeError(label + " failed")
            report[label + "_verified"] = True
            status = safe_status(recover=True)
            if (status["fw_build"], status["mc_fw_build"]) != (2026100709, 2026100708):
                raise RuntimeError("Unexpected live identity")
        for _ in range(10):
            status = safe_status()
            if any(status.get(k) != 0 for k in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence")):
                raise RuntimeError("UART error after installation")
            if status.get("hmi_vbus_hv_calibrated") != 1:
                raise RuntimeError("Existing calibration rejected")
            report["samples"].append(status)
            time.sleep(.5)
        report["pass"] = True
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        hmi.close()
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("pass", "error", "flash_verified", "verify_verified", "image_sha256")}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Install reviewed Uno ownership update only on a discharged USB-connected stand."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from collect_wifi_telemetry import read_token
from install_vbus_hmi_fix_remote import precheck
from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status
from verify_wifi_command_path import get_wifi_logs


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source_checks(root, regression, ownership):
    if regression.get("pass") is not True or regression.get("sources_unchanged_during_tests") is not True:
        raise RuntimeError("passed unchanged-source regression required")
    if ownership.get("pass") is not True or ownership.get("removed_callback_guard_detected") is not True:
        raise RuntimeError("ownership check and negative control required")
    for report, key in ((regression, "source_sha256"), (ownership, "sources")):
        for relative, expected in report[key].items():
            if digest(root / relative) != expected:
                raise RuntimeError("source changed after tests: " + relative)


def safe_idle(status):
    ok, reason = precheck(status)
    if not ok:
        raise RuntimeError(reason)
    if status.get("mc_fw_build") != 2026100801 or status.get("fw_build") not in (2026100804, 2026101001):
        raise RuntimeError("unreviewed board identities")
    if any(status.get(k) != 0 for k in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence")):
        raise RuntimeError("transport not clean before programming")
    return True


def recoverable_peer_pause(before, after):
    """Allow one explicit CLEAR for a known programming-induced idle timeout."""
    if (after.get("bp_fault") != 2 or after.get("mc_diag_valid") != 1
            or after.get("mc_uart_error_flags") != 0 or after.get("mc_last_bad_reason") != 0):
        return False
    if any(after.get(k) != 0 for k in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence")):
        return False
    same_first = (before.get("mc_diag_valid") == 1
                  and before.get("mc_fault_detail") == after.get("mc_fault_detail"))
    if not same_first and after.get("mc_fault_reason") != 13:
        return False
    try:
        return safe_idle(dict(after, bp_fault=5))
    except RuntimeError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-power-off", action="store_true")
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--regression", type=Path, required=True)
    parser.add_argument("--ownership", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--resume-install", type=Path,
                        help="Resume verify-only after a recorded successful flash; never reflash")
    args = parser.parse_args()
    if not args.confirm_power_off:
        parser.error("operator confirmation of mains/J4 off and discharged bus required")
    root = Path(__file__).resolve().parents[1]
    verify_source_checks(root, json.loads(args.regression.read_text(encoding="utf-8-sig")),
                         json.loads(args.ownership.read_text(encoding="utf-8-sig")))
    build = args.build.resolve(strict=True)
    manifest = json.loads((build / "unoq_mcsdk_scalar.build-manifest.json").read_text(encoding="utf-8-sig"))
    if (manifest.get("firmware_build_id"), manifest.get("rpc_schema_version")) != (2026101001, 3):
        raise RuntimeError("wrong Uno build or RPC schema")
    for entry in manifest["artifacts"]:
        path = build / entry["file"]
        if digest(path) != entry["sha256"].lower() or path.stat().st_size != entry["bytes"]:
            raise RuntimeError("compiled artifact mismatch")
    image = build / manifest["flash_artifact"]
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"pass": False, "nucleo_programmed": False, "motor_start_commands": [],
              "powered_CRC_cause_proven": False, "hv_release_approved": False,
              "scope": "Uno ownership update, USB programming and idle-only qualification",
              "image_sha256": digest(image), "commands": [], "samples": []}
    hmi = WifiHmi("http://192.168.1.138:8080", read_token(args.token_file), report["commands"], via_wsl=True)

    def run(command, name, timeout=120):
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
        (out / f"{name}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout

    def await_build(build_id):
        return wait_status(hmi, lambda s: s.get("fw_build") == build_id
                           and s.get("mc_fw_build") == 2026100801
                           and s.get("state") == "SAFE" and s.get("pwm") == 0
                           and s.get("hmi_hv_armed") == 0
                           and s.get("bp_vbus_valid") == 1 and s.get("vdc", 999) <= 2
                           and s.get("mc_age_ms", 999) < 300, 45, "disarmed current Uno identity")

    def safe_after_pause(before, status):
        if recoverable_peer_pause(before, status):
            report.setdefault("peer_pause_recoveries", []).append(status)
            hmi.command("CLEAR")
            status = wait_status(hmi, lambda s: s.get("bp_fault") in (0, 5)
                                 and s.get("mc_clear_pending") == 0, 10, "idle peer pause acknowledged")
        safe_idle(status)
        return status

    try:
        before = hmi.status()
        report["before"] = before
        if args.resume_install:
            prior = json.loads(args.resume_install.read_text(encoding="utf-8-sig"))
            if (prior.get("flash_completed") is not True or prior.get("image_sha256") != digest(image)
                    or before.get("fw_build") != 2026101001):
                raise RuntimeError("resume requires exact previously flashed image and live identity")
            safe_idle(prior["before"])
            safe_after_pause(prior["before"], before)
            report["resumed_flash_evidence"] = str(args.resume_install.resolve())
            report["flash_completed"] = True
        else:
            safe_idle(before)
            if before["fw_build"] != 2026100804:
                raise RuntimeError("installation requires baseline Uno 804")
        run(["adb", "-s", "3880458060", "get-state"], "adb_presence")
        # Install only the compatible HMI identity rule; the remote installer
        # checks live safety again, backs up the server, and preserves calibration.
        server = root / "web_hmi/server.py"
        installer = root / "tools/install_vbus_hmi_fix_remote.py"
        candidate = "/home/arduino/server_control_owner_1001.py"
        remote_installer = "/home/arduino/install_control_owner_hmi.py"
        if not args.resume_install:
            run(["adb", "-s", "3880458060", "push", str(server), candidate], "push_server")
            run(["adb", "-s", "3880458060", "push", str(installer), remote_installer], "push_hmi_installer")
            run(["adb", "-s", "3880458060", "shell", "python3", remote_installer,
                 "--candidate", candidate, "--sha256", digest(server)], "install_hmi", timeout=90)
        safe_idle(hmi.status())
        command = ["arduino-cli", "upload", "-p", "COM10", "-b", "arduino:zephyr:unoq",
                   "-i", str(image), "--upload-property", f"upload.artifacts.sketch={image}",
                   "--upload-property", "upload.port.properties.serialNumber=3880458060"]
        if not args.resume_install:
            run(command, "flash")
            report["flash_completed"] = True
            report["after_flash"] = await_build(2026101001)
            safe_after_pause(before, report["after_flash"])
        verify_before = hmi.status()
        safe_idle(verify_before)
        run(command + ["--upload-property", f"build.variant.path={root / 'tools'}",
                       "--upload-property", "openocd_cfg=verify_unoq_sketch.cfg"], "verify")
        report["verify_only_passed"] = True
        after = await_build(2026101001)
        safe_after_pause(verify_before, after)
        for _ in range(30):
            status = hmi.status()
            safe_idle(status)
            if status["fw_build"] != 2026101001 or status.get("hmi_vbus_hv_calibrated") != 1:
                raise RuntimeError("new identity or unchanged calibration rejected")
            report["samples"].append(status)
            time.sleep(.25)
        report["uart_progress"] = any(b.get("mc_seq") != a.get("mc_seq")
                                       for a, b in zip(report["samples"], report["samples"][1:]))
        if not report["uart_progress"]:
            raise RuntimeError("no fresh UART sequence progress")
        (out / "wifi_logs.txt").write_text(get_wifi_logs(hmi, hmi.token), encoding="utf-8")
        report["pass"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        hmi.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in (
        "pass", "error", "flash_completed", "verify_only_passed", "uart_progress", "image_sha256")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

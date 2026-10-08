"""Install build 708 only on a discharged, disarmed stand; never start PWM."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from install_vbus_hmi_fix_remote import precheck
from run_wifi_nucleo_pwm_bench import WifiHmi, read_control_token


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_image(folder: Path, manifest_name: str, image_name: str) -> Path:
    manifest = json.loads((folder / manifest_name).read_text(encoding="utf-8-sig"))
    if manifest.get("firmware_build_id") != 2026100708:
        raise ValueError("Only build 2026100708 is allowed")
    expected = next(e for e in manifest["artifacts"] if e["file"] == image_name)
    image = folder / image_name
    if image.stat().st_size != expected["bytes"] or digest(image) != expected["sha256"].lower():
        raise ValueError(f"Image does not match manifest: {image_name}")
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-hv-and-j4-off", action="store_true")
    parser.add_argument("--resume-after-uno-write", action="store_true")
    parser.add_argument("--verify-installed", action="store_true")
    args = parser.parse_args()
    if not args.confirm_hv_and_j4_off:
        parser.error("Physically disconnected mains and disabled J4 are required")
    root = Path(__file__).resolve().parents[1]
    out = root / "artifacts/current_pwm_20261007/async_clear_708"
    report_path = out / "install_report.json"
    if report_path.exists():
        raise RuntimeError("Installation report already exists; do not overwrite evidence")
    uno = verified_image(out / "uno_q", "unoq_mcsdk_scalar.build-manifest.json",
                         "UNOQ_MOTOR.ino.elf-zsk.bin")
    name = "ACIM-NUCLEOG431RB-IPM15B-VF_OL"
    nucleo = verified_image(out / "nucleo", name + ".build-manifest.json", name + ".hex")
    binary = verified_image(out / "nucleo", name + ".build-manifest.json", name + ".bin")
    token = read_control_token("adb", "3880458060", "/home/arduino/.config/mic-ai/control_token")
    hmi = WifiHmi("http://192.168.1.138:8080", token, [], via_wsl=True)
    report = {"pass": False, "motor_commands": [], "hv_release_approved": False,
              "scope": "diagnostic-only update and idle verification; no active PWM",
              "images": {"uno": digest(uno), "nucleo_hex": digest(nucleo)},
              "completed": [], "prechecks": [], "samples": [], "recovery_commands": []}

    def safe_status(timeout: float = 25, recover_reset_timeout: bool = False) -> dict:
        deadline = time.monotonic() + timeout
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
            # Programming restarts the UART peer. CLEAR is legal only while all
            # original zero-bus/off guards hold; no ENABLE or START is issued.
            if (not ok and recover_reset_timeout and not recovered
                    and status.get("bp_fault") == 2 and status.get("mc_bad_cnt") == 0
                    and precheck(dict(status, bp_fault=5))[0]):
                report["recovery_commands"].append({"command": "CLEAR",
                    "reason": "idle link timeout during verified peer restart", "before": status})
                code, payload = hmi.request("POST", "/api/cmd", {"cmd": "CLEAR"})
                if code != 200 or payload.get("ok") is not True:
                    raise RuntimeError("Discharged idle CLEAR was rejected")
                recovered = True
                time.sleep(1)
                continue
            if not ok:
                if (recover_reset_timeout and reason.startswith("bus not discharged")
                        and time.monotonic() < deadline):
                    time.sleep(1)
                    continue
                raise RuntimeError("Programming blocked: " + reason)
            return status

    def run(command: list[str], log_name: str, timeout: float = 90) -> None:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        (out / log_name).write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Step failed: {log_name}; exit {result.returncode}")
        report["completed"].append(log_name)

    try:
        report["prechecks"].append(safe_status(
            recover_reset_timeout=args.resume_after_uno_write or args.verify_installed))
        cmd = ["arduino-cli", "upload", "-p", "COM10", "-b", "arduino:zephyr:unoq",
               "-i", str(uno), "--upload-property", f"upload.artifacts.sketch={uno}",
               "--upload-property", "upload.port.properties.serialNumber=3880458060"]
        if args.verify_installed:
            current = report["prechecks"][-1]
            if current["fw_build"] != 2026100708 or current["mc_fw_build"] != 2026100708:
                raise RuntimeError("Verification-only requires both installed builds 708")
        elif not args.resume_after_uno_write:
            run(cmd, "uno_flash.log")
        elif report["prechecks"][-1]["fw_build"] != 2026100708:
            raise RuntimeError("Resume requires the already written Uno build 708")
        report["prechecks"].append(safe_status(recover_reset_timeout=True))
        if not args.verify_installed:
            run(cmd + ["--upload-property", f"build.variant.path={root / 'tools'}",
                       "--upload-property", "openocd_cfg=verify_unoq_sketch.cfg"], "uno_verify.log")
        report["prechecks"].append(safe_status(recover_reset_timeout=True))
        cli = "C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe"
        connection = [cli, "-c", "port=SWD", "mode=UR", "reset=HWrst",
                      "sn=003A002C3335510933383531"]
        if not args.verify_installed:
            run(connection + ["-w", str(nucleo), "-v", "-rst"], "nucleo_flash_verify.log", 60)
        report["prechecks"].append(safe_status(recover_reset_timeout=True))
        readback = out / "nucleo_readback.bin"
        try:
            run(connection + ["-u", "0x08000000", str(binary.stat().st_size), str(readback)],
                "nucleo_readback.log", 60)
        finally:
            run(connection + ["-rst"], "nucleo_reset_after_readback.log", 30)
        report["nucleo_byte_readback_match"] = readback.read_bytes() == binary.read_bytes()
        if not report["nucleo_byte_readback_match"]:
            raise RuntimeError("Nucleo readback differs from image")
        for _ in range(30):
            status = safe_status(recover_reset_timeout=True)
            if status["fw_build"] != 2026100708 or status["mc_fw_build"] != 2026100708:
                raise RuntimeError("Live firmware IDs do not match verified images")
            if (status.get("mc_diag_valid") != 1 or status.get("mc_bad_cnt") != 0
                    or status.get("mc_bad_integrity") != 0 or status.get("mc_bad_sequence") != 0):
                raise RuntimeError("Idle diagnostics or UART counters are not clean")
            report["samples"].append(status)
            time.sleep(1)
        report["new_good_messages"] = (report["samples"][-1]["mc_good_cnt"]
                                        - report["samples"][0]["mc_good_cnt"])
        report["pass"] = report["new_good_messages"] > 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        hmi.close()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in
                      ("pass", "error", "completed", "nucleo_byte_readback_match", "new_good_messages",
                       "hv_release_approved")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Install the boot-armed BKIN recorder in the verified sub-10-V, SAFE state."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid

from unoq_wifi_hmi_deploy import ssh_base

ROOT = Path(__file__).resolve().parents[1]
URL = "http://192.168.1.138:8080"
UNO_SERIAL = "3880458060"
STLINK_SERIAL = "003A002C3335510933383531"
OLD_PAIR = (2026101703, 2026101702)
NEW_PAIR = (2026101711, 2026101710)
PROGRAMMER = Path("C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def live_status() -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL + "/api/status", timeout=8) as response:
        payload = json.load(response)
    if payload.get("ok") is not True or not isinstance(payload.get("data"), dict):
        raise RuntimeError("HMI status is unavailable")
    return payload["data"]


def validate_status(status: dict, expected_pair: tuple[int, int], allow_boot_link_event: bool = False) -> None:
    pair = (status.get("fw_build"), status.get("mc_fw_build"))
    if pair != expected_pair:
        raise RuntimeError(f"unexpected firmware pair: {pair}")
    if status.get("state") != "SAFE" or status.get("pwm") != 0:
        raise RuntimeError("drive is not SAFE with PWM off")
    if status.get("estop") != 0 or status.get("hmi_hv_armed") != 0:
        raise RuntimeError("E-stop or HV arm is active")
    for key in ("vdc", "bp_vdc"):
        value = status.get(key)
        if type(value) not in (int, float) or not 0 <= value <= 10:
            raise RuntimeError(f"bus voltage is above the programming limit: {key}={value}")
    if status.get("bp_vbus_valid") != 1 or status.get("bp_temp_valid") != 1 or status.get("bp_temp_fault") != 0:
        raise RuntimeError("fresh Nucleo bus/temperature telemetry is not valid")
    for key in ("mc_age_ms", "bp_vbus_age_ms", "bp_temp_age_ms"):
        value = status.get(key)
        if type(value) not in (int, float) or not 0 <= value < 300:
            raise RuntimeError(f"stale telemetry: {key}={value}")
    faults = (status.get("bp_fault"), status.get("mc_fault"))
    mask = status.get("mc_fault_occurred_mask")
    current = status.get("mc_fault_current_mask")
    reason = status.get("mc_fault_reason")
    boot_link_event = (allow_boot_link_event and faults == (2, 2) and reason == 13
                       and mask == 0 and current == 0
                       and status.get("bp_uart_error_flags") == 0
                       and status.get("mc_uart_error_flags") == 0)
    for key in ("bp_bad_cnt", "mc_bad_cnt", "bp_bad_sequence", "mc_bad_sequence",
                "bp_uart_error_flags", "mc_uart_error_flags", "bp_transport_fault", "mc_transport_fault"):
        value = status.get(key)
        bad_counter = key in ("bp_bad_cnt", "mc_bad_cnt") and boot_link_event and value == 1
        link_latch = key in ("bp_transport_fault", "mc_transport_fault") and boot_link_event and value == 7
        if value != 0 and not (bad_counter or link_latch):
            raise RuntimeError(f"UART is not currently clean: {key}={value}")
    bus_off_fault = faults in ((5, 5), (0, 5), (5, 0)) and reason == 8 and current in (0, 4) and mask in (4, 0x400, 0x404)
    if faults != (0, 0) and not bus_off_fault and not boot_link_event:
        raise RuntimeError(f"unexpected latched drive fault: {faults}, reason={reason}, mask={mask}/{current}")


def verify_package(candidate: Path) -> tuple[Path, Path, dict]:
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != "mic_ai.bkin_boot_armed_candidate.v1":
        raise RuntimeError("unexpected candidate schema")
    if manifest.get("pair") != list(NEW_PAIR) or manifest.get("predecessor_pair") != list(OLD_PAIR):
        raise RuntimeError("candidate pair identities do not match the connected pair")
    if manifest.get("hv_release_approved") is not False or manifest.get("pwm_or_motor_control_changed") is not False:
        raise RuntimeError("candidate is not diagnostic-only")
    if manifest.get("build_verification", {}).get("host_selftest", {}).get("pass") is not True:
        raise RuntimeError("candidate host self-tests did not pass")
    if manifest.get("build_verification", {}).get("host_selftest", {}).get("checks") != 11:
        raise RuntimeError("candidate host self-test coverage is incomplete")
    for relative, expected in manifest.get("files_sha256", {}).items():
        path = candidate / relative
        if not path.is_file() or sha(path) != expected.lower():
            raise RuntimeError(f"candidate source hash mismatch: {relative}")
    uno_dir = candidate / "build/uno"
    uno_manifest = json.loads((uno_dir / "unoq_mcsdk_scalar.build-manifest.json").read_text(encoding="utf-8-sig"))
    if uno_manifest.get("firmware_build_id") != NEW_PAIR[0]:
        raise RuntimeError("Uno build ID mismatch")
    uno_image = uno_dir / "UNOQ_MOTOR.ino.elf-zsk.bin"
    uno_item = next((entry for entry in uno_manifest.get("artifacts", []) if entry.get("file") == uno_image.name), None)
    if not uno_item or sha(uno_image) != str(uno_item.get("sha256", "")).lower() or uno_image.stat().st_size != uno_item.get("bytes"):
        raise RuntimeError("Uno image hash/size mismatch")
    nuc_dir = candidate / "build/nucleo"
    nuc_manifest = json.loads((nuc_dir / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json").read_text(encoding="utf-8-sig"))
    if nuc_manifest.get("firmware_build_id") != NEW_PAIR[1] or nuc_manifest.get("build_errors") != 0 or nuc_manifest.get("build_warnings") != 0:
        raise RuntimeError("Nucleo build metadata is not clean")
    nuc_image = nuc_dir / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"
    nuc_item = next((entry for entry in nuc_manifest.get("artifacts", []) if entry.get("file") == nuc_image.name), None)
    if not nuc_item or sha(nuc_image) != str(nuc_item.get("sha256", "")).lower() or nuc_image.stat().st_size != nuc_item.get("bytes"):
        raise RuntimeError("Nucleo image hash/size mismatch")
    release = json.loads((nuc_dir / "mcsdk_release_preflight.json").read_text(encoding="utf-8-sig"))
    if release.get("pass") is not False:
        raise RuntimeError("expected non-approved diagnostic release gate state is absent")
    return uno_image, nuc_image, manifest


def run(command: list[str], label: str, outdir: Path, report: dict, timeout: int = 240) -> str:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    (outdir / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    report.setdefault("commands", []).append({"label": label, "exit_code": result.returncode})
    if result.returncode:
        raise RuntimeError(f"{label} failed; see {outdir / (label + '.log')}")
    return result.stdout


def board_ports() -> tuple[str, str]:
    data = json.loads(subprocess.check_output(["arduino-cli", "board", "list", "--format", "json"], text=True))
    found = {}
    for entry in data.get("detected_ports", []):
        props = entry.get("port", {}).get("properties", {})
        serial = props.get("serialNumber")
        if serial in (UNO_SERIAL, STLINK_SERIAL):
            found[serial] = entry["port"]["address"]
    if UNO_SERIAL not in found or STLINK_SERIAL not in found:
        raise RuntimeError("the expected Uno Q and Nucleo ST-Link are not both connected")
    return found[UNO_SERIAL], found[STLINK_SERIAL]


def calibration_hash(outdir: Path, report: dict) -> str:
    ssh = ssh_base("192.168.1.138", 2222, "arduino", ROOT / ".unoq_ssh/id_ed25519", ROOT / ".unoq_ssh/known_hosts")
    output = run(ssh + ["sha256sum /home/arduino/.config/mic-ai/vbus_calibration.json"], "calibration_hash", outdir, report, 20)
    value = output.split()[0].lower()
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise RuntimeError("invalid Vbus calibration SHA-256")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-mains-off", action="store_true",
                        help="J1/mains must be off; J4 auxiliary 15 V may remain on under 10 V bus")
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    outdir = (args.outdir or ROOT / "artifacts/live_bench_20261017" / ("bkin_boot_armed_install_" + uuid.uuid4().hex)).resolve()
    if outdir.exists():
        parser.error(f"output directory already exists: {outdir}")
    outdir.mkdir(parents=True)
    report = {"pass": False, "dry_run": args.dry_run, "candidate": str(candidate),
              "candidate_pair": NEW_PAIR, "predecessor_pair": OLD_PAIR,
              "install_order": ["nucleo", "uno_q"], "mcu_flash_commands": 0,
              "actuation_commands": 0, "calibration_changed": False,
              "mains_off_user_reported": args.confirm_mains_off,
              "j4_may_remain_on": True, "motor_commands": 0, "clear_commands": 0,
              "hv_release_approved": False}
    try:
        uno_image, nuc_image, manifest = verify_package(candidate)
        report["uno_image_sha256"] = sha(uno_image)
        report["nucleo_image_sha256"] = sha(nuc_image)
        status = live_status()
        validate_status(status, OLD_PAIR)
        report["before"] = status
        report["usb_ports"] = {"uno_q": board_ports()[0], "nucleo_stlink": board_ports()[1]}
        if not PROGRAMMER.is_file():
            raise RuntimeError("STM32CubeProgrammer is unavailable")
        if not args.dry_run and not args.confirm_mains_off:
            raise RuntimeError("J1/mains-off confirmation is required; J4 may remain on")
        report["calibration_before_sha256"] = calibration_hash(outdir, report)
        if args.dry_run:
            report["pass"] = True
        else:
            run([str(PROGRAMMER), "-c", "port=SWD", "mode=UR", "sn=" + STLINK_SERIAL,
                 "-w", str(nuc_image), "-v", "-rst"], "flash_verify_nucleo", outdir, report)
            report["mcu_flash_commands"] += 1
            report["nucleo_readback_verified"] = True
            try:
                inter = live_status()
                report["after_nucleo"] = {k: inter.get(k) for k in
                    ("fw_build", "mc_fw_build", "state", "pwm", "vdc", "bp_vdc", "bp_fault", "mc_fault")}
                if inter.get("state") != "SAFE" or inter.get("pwm") != 0:
                    raise RuntimeError("Nucleo update did not remain SAFE with PWM off")
            except RuntimeError:
                raise
            except Exception as exc:
                report["after_nucleo_status_error"] = f"{type(exc).__name__}: {exc}"

            uno_port, _ = board_ports()
            run(["arduino-cli", "upload", "-p", uno_port, "-b", "arduino:zephyr:unoq", "-i", str(uno_image),
                 "--upload-property", "upload.artifacts.sketch=" + str(uno_image),
                 "--upload-property", "upload.port.properties.serialNumber=" + UNO_SERIAL],
                "flash_uno", outdir, report)
            report["mcu_flash_commands"] += 1
            run(["arduino-cli", "upload", "-p", uno_port, "-b", "arduino:zephyr:unoq", "-i", str(uno_image),
                 "--upload-property", "upload.artifacts.sketch=" + str(uno_image),
                 "--upload-property", "upload.port.properties.serialNumber=" + UNO_SERIAL,
                 "--upload-property", "build.variant.path=" + str(ROOT / "tools"),
                 "--upload-property", "openocd_cfg=verify_unoq_sketch.cfg"],
                "verify_uno", outdir, report)
            report["uno_readback_verified"] = True
            run(["arduino-cli", "upload", "-p", uno_port, "-b", "arduino:zephyr:unoq", "-i", str(uno_image),
                 "--upload-property", "upload.artifacts.sketch=" + str(uno_image),
                 "--upload-property", "upload.port.properties.serialNumber=" + UNO_SERIAL,
                 "--upload-property", "build.variant.path=" + str(ROOT / "tools"),
                 "--upload-property", "openocd_cfg=unoq_reset_run.cfg"],
                "release_uno_after_readback", outdir, report)
            report["uno_mcu_resumed_after_readback"] = True
            report["calibration_after_sha256"] = calibration_hash(outdir, report)
            report["calibration_unchanged"] = report["calibration_before_sha256"] == report["calibration_after_sha256"]
            if not report["calibration_unchanged"]:
                raise RuntimeError("Vbus calibration changed during the firmware update")

            deadline = time.monotonic() + 60
            last_status = None
            last_error = None
            while time.monotonic() < deadline:
                time.sleep(1)
                try:
                    last_status = live_status()
                    if (last_status.get("fw_build"), last_status.get("mc_fw_build")) != NEW_PAIR:
                        continue
                    validate_status(last_status, NEW_PAIR, allow_boot_link_event=True)
                    report["after"] = last_status
                    report["pair_live"] = True
                    report["pass"] = True
                    break
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
            if not report.get("pair_live"):
                report["after"] = last_status
                report["post_flash_error"] = last_error or "new firmware pair did not appear within 60 seconds"
                report["recovery_required"] = True
            if report.get("pair_live"):
                report["current_fault_note"] = "No CLEAR or START was sent; low-bus undervoltage/old latched diagnostic may remain."
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        (outdir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in
        ("pass", "dry_run", "mcu_flash_commands", "nucleo_readback_verified", "uno_readback_verified",
         "calibration_unchanged", "pair_live", "recovery_required", "error", "post_flash_error")}, ensure_ascii=False))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())

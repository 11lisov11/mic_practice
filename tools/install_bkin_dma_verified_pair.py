"""Install the hash-verified BKIN DMA diagnostic pair on the isolated bench."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import urllib.error
from urllib.request import ProxyHandler, build_opener
import uuid

from unoq_wifi_hmi_deploy import ssh_base


ROOT = Path(__file__).resolve().parents[1]
URL = "http://192.168.1.138:8080"
UNO_SERIAL = "3880458060"
STLINK_SERIAL = "003A002C3335510933383531"
OLD_PAIR = (2026101507, 2026101506)
NEW_PAIR = (2026101703, 2026101702)
PROGRAMMER = Path("C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def live_status() -> dict:
    opener = build_opener(ProxyHandler({}))
    with opener.open(URL + "/api/status", timeout=5) as response:
        payload = json.load(response)
    if payload.get("ok") is not True or not isinstance(payload.get("data"), dict):
        raise RuntimeError("live HMI status is unavailable")
    return payload["data"]


def is_startup_link_timeout(status: dict) -> bool:
    pair = (status.get("fw_build"), status.get("mc_fw_build"))
    return (
        pair in ((NEW_PAIR[0], OLD_PAIR[1]), NEW_PAIR)
        and status.get("bp_fault") == 2 and status.get("mc_fault") == 2
        and status.get("bp_fault_reason") == 13 and status.get("mc_fault_reason") == 13
        and status.get("bp_status") == 25 and status.get("mc_status") == 25
        and status.get("bp_transport_fault") == 7 and status.get("mc_transport_fault") == 7
        and status.get("bp_bad_cnt") == 1 and status.get("mc_bad_cnt") == 1
        and status.get("bp_bad_integrity") == 0 and status.get("mc_bad_integrity") == 0
        and status.get("bp_bad_sequence") == 0 and status.get("mc_bad_sequence") == 0
        and status.get("bp_uart_error_flags") == 0 and status.get("mc_uart_error_flags") == 0
        and status.get("mc_last_uart_error_flags") == 0 and status.get("mc_last_bad_reason") == 13
        and status.get("mc_fault_current_mask") == 0 and status.get("mc_fault_occurred_mask") == 0
    )


def validate_status(status: dict, allowed_pairs: tuple[tuple[int, int], ...],
                    allow_startup_link_timeout: bool = False,
                    allow_bus_off_undervoltage: bool = False) -> None:
    pair = (status.get("fw_build"), status.get("mc_fw_build"))
    if pair not in allowed_pairs:
        raise RuntimeError(f"unexpected live firmware pair: {pair}")
    if status.get("state") != "SAFE" or status.get("pwm") != 0:
        raise RuntimeError("drive is not in SAFE with PWM off")
    startup_link_timeout = allow_startup_link_timeout and is_startup_link_timeout(status)
    bus_off_undervoltage = (
        allow_bus_off_undervoltage
        and status.get("bp_fault") == 5 and status.get("mc_fault") == 5
        and status.get("mc_fault_reason") == 8 and status.get("mc_fault_current_mask") in (0, 4)
        and status.get("mc_fault_occurred_mask") in (4, 0x404)
        and type(status.get("vdc")) in (int, float) and 0 <= status["vdc"] <= 10
        and type(status.get("bp_vdc")) in (int, float) and 0 <= status["bp_vdc"] <= 10
    )
    for key in ("estop", "hmi_hv_armed", "hmi_hv_started", "bp_fault",
                "bp_temp_fault", "bp_transport_fault"):
        if startup_link_timeout and key in ("bp_fault", "bp_transport_fault"):
            continue
        if bus_off_undervoltage and key == "bp_fault":
            continue
        if key in status and status[key] not in (0, False, None):
            raise RuntimeError(f"active safety/transport flag: {key}={status[key]}")
    if ("mc_fault" in status and status["mc_fault"] not in (0, False, None)
            and not startup_link_timeout and not bus_off_undervoltage):
        raise RuntimeError(f"active safety/transport flag: mc_fault={status['mc_fault']}")
    if "mc_transport_fault" in status and status["mc_transport_fault"] not in (0, False, None) and not startup_link_timeout:
        raise RuntimeError(f"active safety/transport flag: mc_transport_fault={status['mc_transport_fault']}")
    if status.get("bp_vbus_valid") != 1 or status.get("bp_temp_valid") != 1:
        raise RuntimeError("fresh Nucleo bus/temperature telemetry is required")
    for key in ("mc_age_ms", "bp_vbus_age_ms", "bp_temp_age_ms"):
        value = status.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < 300:
            raise RuntimeError(f"stale or missing telemetry age: {key}")
    for key in ("vdc", "bp_vdc"):
        value = status.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10:
            raise RuntimeError(f"bus exceeds the isolated programming limit: {key}={value}")
    for key in ("bp_bad_cnt", "mc_bad_cnt", "bp_uart_error_flags", "mc_uart_error_flags",
                "bp_bad_sequence", "mc_bad_sequence"):
        if startup_link_timeout and key in ("bp_bad_cnt", "mc_bad_cnt"):
            continue
        if key in status and status[key] != 0:
            raise RuntimeError(f"UART is not clean: {key}={status[key]}")


def verify_package(candidate: Path) -> tuple[Path, Path, dict]:
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != "mic_ai.bkin_dma_verified_candidate.v1":
        raise RuntimeError("unexpected candidate manifest")
    if manifest.get("pair") != list(NEW_PAIR) or manifest.get("predecessor_pair") != list(OLD_PAIR):
        raise RuntimeError("candidate pair identities do not match the live upgrade path")
    if manifest.get("pwm_or_motor_control_changed") is not False or manifest.get("calibration_changed") is not False:
        raise RuntimeError("candidate changes motor control or calibration")
    if manifest.get("build_verification", {}).get("unoq", {}).get("pass") is not True:
        raise RuntimeError("Uno Q build was not verified")
    nuc_build = manifest.get("build_verification", {}).get("nucleo", {})
    if nuc_build.get("pass") is not True or nuc_build.get("errors") != 0 or nuc_build.get("warnings") != 0:
        raise RuntimeError("Nucleo build was not verified cleanly")
    if manifest.get("build_verification", {}).get("host_selftest", {}).get("checks") != 17:
        raise RuntimeError("candidate host self-tests are incomplete")

    for relative, expected in manifest.get("files_sha256", {}).items():
        path = candidate / relative
        if not path.is_file() or sha(path) != expected.lower():
            raise RuntimeError(f"candidate source hash mismatch: {relative}")

    uno_dir = candidate / "build/uno"
    uno_build = json.loads((uno_dir / "unoq_mcsdk_scalar.build-manifest.json").read_text(encoding="utf-8-sig"))
    if uno_build.get("firmware_build_id") != NEW_PAIR[0]:
        raise RuntimeError("unexpected Uno image identity")
    uno_image = uno_dir / "UNOQ_MOTOR.ino.elf-zsk.bin"
    uno_record = next((item for item in uno_build.get("artifacts", []) if item.get("file") == uno_image.name), None)
    if not uno_record or sha(uno_image) != uno_record["sha256"].lower() or uno_image.stat().st_size != uno_record["bytes"]:
        raise RuntimeError("Uno image hash/size verification failed")

    nuc_image = candidate / "build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"
    if sha(nuc_image) != nuc_build.get("hex_sha256", "").lower() or nuc_image.stat().st_size != nuc_build.get("hex_bytes"):
        raise RuntimeError("Nucleo image hash/size verification failed")
    return uno_image, nuc_image, manifest


def run(command: list[str], label: str, outdir: Path, report: dict, timeout: int = 180) -> str:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    (outdir / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    report["commands"].append({"label": label, "exit_code": result.returncode})
    if result.returncode:
        raise RuntimeError(f"{label} failed; see {outdir / (label + '.log')}")
    return result.stdout


def ports() -> tuple[str, str]:
    data = json.loads(subprocess.check_output(["arduino-cli", "board", "list", "--format", "json"], text=True))
    found = {}
    for entry in data.get("detected_ports", []):
        props = entry.get("port", {}).get("properties", {})
        serial = props.get("serialNumber")
        if serial in (UNO_SERIAL, STLINK_SERIAL):
            found[serial] = entry["port"]["address"]
    if UNO_SERIAL not in found or STLINK_SERIAL not in found:
        raise RuntimeError("the exact Uno Q and Nucleo ST-Link USB identities are not both present")
    return found[UNO_SERIAL], found[STLINK_SERIAL]


def wait_pair(expected: tuple[int, int], allowed: tuple[tuple[int, int], ...], timeout_s: int = 45,
              allow_startup_link_timeout: bool = False) -> dict:
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        try:
            status = live_status()
            validate_status(status, allowed, allow_startup_link_timeout)
            if (status.get("fw_build"), status.get("mc_fw_build")) == expected:
                return status
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"firmware identity {expected} did not become live: {last_error or 'timeout'}")


def calibration_hash(outdir: Path, report: dict) -> str:
    ssh = ssh_base("192.168.1.138", 2222, "arduino", ROOT / ".unoq_ssh/id_ed25519", ROOT / ".unoq_ssh/known_hosts")
    output = run(ssh + ["sha256sum /home/arduino/.config/mic-ai/vbus_calibration.json"], "calibration_hash", outdir, report, 20)
    value = output.split()[0]
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise RuntimeError("invalid calibration SHA256 response")
    return value.lower()


def optional_status(report: dict, key: str) -> dict | None:
    """Read telemetry during an all-off firmware handoff without making it a gate."""
    try:
        status = live_status()
        report[key] = {
            "fw_build": status.get("fw_build"),
            "mc_fw_build": status.get("mc_fw_build"),
            "state": status.get("state"),
            "pwm": status.get("pwm"),
            "vdc": status.get("vdc"),
            "bp_vdc": status.get("bp_vdc"),
            "bp_fault": status.get("bp_fault"),
            "mc_fault": status.get("mc_fault"),
            "bp_transport_fault": status.get("bp_transport_fault"),
            "mc_transport_fault": status.get("mc_transport_fault"),
            "mc_age_ms": status.get("mc_age_ms"),
            "bp_age_ms": status.get("bp_age_ms"),
        }
        return status
    except Exception as exc:
        report[key + "_error"] = f"{type(exc).__name__}: {exc}"
        return None


def validate_post_flash_status(status: dict) -> None:
    validate_status(status, (NEW_PAIR,), allow_bus_off_undervoltage=True)
    for key in ("bp_transport_fault", "mc_transport_fault", "bp_bad_cnt", "mc_bad_cnt",
                "bp_bad_integrity", "mc_bad_integrity", "bp_bad_sequence", "mc_bad_sequence",
                "bp_uart_error_flags", "mc_uart_error_flags"):
        if status.get(key) != 0:
            raise RuntimeError(f"post-flash link is not clean: {key}={status.get(key)}")
    faults = (status.get("bp_fault"), status.get("mc_fault"))
    if faults == (0, 0):
        return
    expected_bus_off_uv = (
        faults == (5, 5) and status.get("mc_fault_reason") == 8
        and status.get("mc_fault_current_mask") in (0, 4)
        and status.get("mc_fault_occurred_mask") in (4, 0x404)
        and 0 <= status.get("vdc", -1) <= 10 and 0 <= status.get("bp_vdc", -1) <= 10
    )
    if not expected_bus_off_uv:
        raise RuntimeError(f"unexpected post-flash drive fault state: {faults}")


def clear_startup_link_timeout(report: dict, status: dict) -> dict:
    if not is_startup_link_timeout(status):
        return status
    if (status.get("state") != "SAFE" or status.get("pwm") != 0 or status.get("estop") != 0
            or status.get("hmi_hv_armed") != 0 or status.get("hmi_hv_started") != 0
            or status.get("bp_temp_fault") != 0):
        raise RuntimeError("refusing startup-link CLEAR outside SAFE, PWM-off, unarmed state")
    token_path = ROOT / ".unoq_ssh/control_token"
    token = token_path.read_text(encoding="utf-8").strip()
    if len(token) < 16:
        raise RuntimeError("control token is unavailable for the safe startup-link CLEAR")
    opener = build_opener(ProxyHandler({}))
    request = urllib.request.Request(URL + "/api/cmd", data=json.dumps({"cmd": "CLEAR"}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "X-UNOQ-Control-Token": token}, method="POST")
    try:
        with opener.open(request, timeout=8) as response:
            reply = json.load(response)
            http_status = response.status
    except urllib.error.HTTPError as exc:
        reply = json.loads(exc.read().decode("utf-8") or "{}")
        http_status = exc.code
    report.setdefault("control_commands", []).append({"cmd": "CLEAR", "reason": "single startup LINK_TIMEOUT",
        "http_status": http_status, "ok": reply.get("ok") is True})
    report["clear_commands"] = report.get("clear_commands", 0) + 1
    if http_status != 200 or reply.get("ok") is not True:
        raise RuntimeError("safe startup-link CLEAR was rejected")

    deadline = time.monotonic() + 8
    last_error = "timeout"
    while time.monotonic() < deadline:
        time.sleep(0.25)
        try:
            recovered = live_status()
            validate_post_flash_status(recovered)
            return recovered
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(f"startup-link CLEAR did not restore a clean off-state link: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("--confirm-mains-j4-off", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    outdir = (args.outdir or (ROOT / "artifacts/live_bench_20261017" / ("bkin_dma_install_" + uuid.uuid4().hex))).resolve()
    if outdir.exists():
        parser.error(f"output directory already exists: {outdir}")
    outdir.mkdir(parents=True)
    report = {"pass": False, "dry_run": args.dry_run, "commands": [], "mcu_flash_commands": 0,
              "clear_commands": 0, "control_commands": [],
              "motor_commands": 0, "hv_release_approved": False, "candidate": str(candidate),
              "install_order": ["nucleo", "uno_q"], "recovery_required": False}
    try:
        uno_image, nuc_image, manifest = verify_package(candidate)
        report["candidate_pair"] = NEW_PAIR
        report["predecessor_pair"] = OLD_PAIR
        report["uno_image_sha256"] = sha(uno_image)
        report["nucleo_image_sha256"] = sha(nuc_image)
        report["manifest_prepared_only"] = manifest.get("installed") is False

        status = live_status()
        intermediate_nucleo = (OLD_PAIR[0], NEW_PAIR[1])
        validate_status(status, (OLD_PAIR, NEW_PAIR), allow_startup_link_timeout=True,
                        allow_bus_off_undervoltage=True)
        report["before"] = status
        uno_port, stlink_port = ports()
        report["usb_ports"] = {"uno_q": uno_port, "nucleo_stlink": stlink_port}
        if not PROGRAMMER.is_file():
            raise RuntimeError("STM32CubeProgrammer is unavailable")
        if not args.dry_run and not args.confirm_mains_j4_off:
            raise RuntimeError("physical mains/J4-off confirmation is required for MCU programming")

        report["calibration_before_sha256"] = calibration_hash(outdir, report)
        live_pair = (status.get("fw_build"), status.get("mc_fw_build"))
        if args.dry_run:
            report["already_installed"] = live_pair == NEW_PAIR
            report["pass"] = True
        elif live_pair == NEW_PAIR:
            report["already_installed"] = True
            if is_startup_link_timeout(status):
                report["startup_link_timeout_cleared"] = True
                report["after_clear"] = clear_startup_link_timeout(report, status)
            else:
                validate_post_flash_status(status)
            report["calibration_after_sha256"] = calibration_hash(outdir, report)
            report["calibration_unchanged"] = report["calibration_before_sha256"] == report["calibration_after_sha256"]
            if not report["calibration_unchanged"]:
                raise RuntimeError("Vbus calibration hash changed while verifying installed pair")
            report["pair_live"] = True
            report["pass"] = True
        else:
            if live_pair != OLD_PAIR:
                raise RuntimeError("fresh install requires the complete known-good predecessor pair")

            # Update Nucleo first. This keeps Uno's UART host and HMI alive while
            # the target-side diagnostic recorder is replaced. Both outputs are
            # physically isolated, and no motor command is issued in this script.
            validate_status(live_status(), (OLD_PAIR,))
            run([str(PROGRAMMER), "-c", "port=SWD", "mode=UR", "sn=" + STLINK_SERIAL,
                 "-w", str(nuc_image), "-v", "-rst"], "flash_verify_nucleo", outdir, report, 180)
            report["mcu_flash_commands"] += 1
            report["nucleo_readback_verified"] = True
            after_nucleo = optional_status(report, "after_nucleo")
            if after_nucleo and (after_nucleo.get("state") != "SAFE" or after_nucleo.get("pwm") != 0):
                raise RuntimeError("Nucleo handoff did not remain SAFE with PWM off; Uno update aborted")

            # Flash and read back Uno only after the Nucleo image has verified.
            # The second OpenOCD invocation can restart the app MCU and invalidate
            # the Linux-side serial route, so do not require RPC during that gap.
            before_uno = optional_status(report, "before_uno")
            if before_uno:
                before_uno_pair = (before_uno.get("fw_build"), before_uno.get("mc_fw_build"))
                if before_uno_pair not in (OLD_PAIR, intermediate_nucleo):
                    raise RuntimeError(f"unexpected pair during handoff: {before_uno_pair}")
                if before_uno.get("state") != "SAFE" or before_uno.get("pwm") != 0:
                    raise RuntimeError("handoff did not remain SAFE with PWM off; Uno update aborted")
            run(["arduino-cli", "upload", "-p", uno_port, "-b", "arduino:zephyr:unoq", "-i", str(uno_image),
                 "--upload-property", "upload.artifacts.sketch=" + str(uno_image),
                 "--upload-property", "upload.port.properties.serialNumber=" + UNO_SERIAL],
                "flash_uno", outdir, report, 240)
            report["mcu_flash_commands"] += 1
            run(["arduino-cli", "upload", "-p", uno_port, "-b", "arduino:zephyr:unoq", "-i", str(uno_image),
                 "--upload-property", "upload.artifacts.sketch=" + str(uno_image),
                 "--upload-property", "upload.port.properties.serialNumber=" + UNO_SERIAL,
                 "--upload-property", "build.variant.path=" + str(ROOT / "tools"),
                 "--upload-property", "openocd_cfg=verify_unoq_sketch.cfg"],
                "verify_uno", outdir, report, 240)
            report["uno_readback_verified"] = True
            report["calibration_after_sha256"] = calibration_hash(outdir, report)
            report["calibration_unchanged"] = report["calibration_before_sha256"] == report["calibration_after_sha256"]
            if not report["calibration_unchanged"]:
                raise RuntimeError("Vbus calibration hash changed during MCU programming")
            try:
                report["after"] = wait_pair(NEW_PAIR, (NEW_PAIR,), 45, allow_startup_link_timeout=True)
                if is_startup_link_timeout(report["after"]):
                    report["startup_link_timeout_cleared"] = True
                    report["after_clear"] = clear_startup_link_timeout(report, report["after"])
                else:
                    report["startup_link_timeout_cleared"] = False
                    validate_post_flash_status(report["after"])
                report["pair_live"] = True
                report["pass"] = True
            except Exception as exc:
                report["pair_live"] = False
                report["recovery_required"] = True
                report["post_flash_error"] = f"{type(exc).__name__}: {exc}"
            report["flash_pair_verified"] = bool(report.get("nucleo_readback_verified") and
                                                  report.get("uno_readback_verified"))
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        (outdir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in (
        "pass", "dry_run", "already_installed", "mcu_flash_commands", "uno_readback_verified",
        "nucleo_readback_verified", "calibration_unchanged", "pair_live", "flash_pair_verified",
        "clear_commands", "startup_link_timeout_cleared", "recovery_required", "error")}, ensure_ascii=False))
    return 0 if report["pass"] or report.get("flash_pair_verified") else 1


if __name__ == "__main__":
    raise SystemExit(main())

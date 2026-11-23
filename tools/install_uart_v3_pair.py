"""Install the reviewed v3 pair on a discharged stand; idle qualification only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

from collect_wifi_telemetry import read_token
from install_vbus_hmi_fix_remote import precheck
from prepare_uart_v3_candidate import nucleo_source, uno_source
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL, parse_registers
from run_wifi_nucleo_pwm_bench import WifiHmi
from verify_wifi_command_path import get_wifi_logs


ADB_SERIAL = "3880458060"
OLD_PAIR = (2026101002, 2026100801)
NEW_PAIR = (2026101004, 2026101003)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_package(root: Path, snapshot: Path, regression: Path) -> tuple[Path, Path]:
    report = json.loads(regression.read_text(encoding="utf-8-sig"))
    if report.get("pass") is not True or report.get("sources_unchanged_during_tests") is not True:
        raise RuntimeError("passed unchanged-source regression required")
    tests = {t["test"]: t for t in report["tests"]}
    for name in ("uart_v3_candidate_selftest", "uart_v3_uno_peer_selftest", "install_uart_v3_pair_selftest"):
        if tests.get(name, {}).get("pass") is not True:
            raise RuntimeError("missing passed installer/candidate check: " + name)
    for relative, expected in report["source_sha256"].items():
        if sha(root / relative) != expected:
            raise RuntimeError("source changed after regression: " + relative)
    if (snapshot / "nucleo/Src/main.c").read_text() != nucleo_source(root):
        raise RuntimeError("Nucleo candidate does not match tested generator")
    if (snapshot / "UNOQ_MOTOR/UNOQ_MOTOR.ino").read_text() != uno_source(root):
        raise RuntimeError("Uno candidate does not match tested generator")
    header = root / "research/uart_v3/uart_v3_transport.h"
    for path in (snapshot / "nucleo/Inc/uart_v3_transport.h", snapshot / "UNOQ_MOTOR/uart_v3_transport.h"):
        if sha(path) != sha(header):
            raise RuntimeError("candidate transport header mismatch")
    build = snapshot / "uno_build"
    manifest = json.loads((build / "unoq_mcsdk_scalar.build-manifest.json").read_text(encoding="utf-8-sig"))
    if (manifest.get("firmware_build_id"), manifest.get("rpc_schema_version")) != (NEW_PAIR[0], 3):
        raise RuntimeError("wrong Uno identity")
    for item in manifest["artifacts"]:
        path = build / item["file"]
        if path.stat().st_size != item["bytes"] or sha(path) != item["sha256"].lower():
            raise RuntimeError("Uno build artifact mismatch")
    nuc = snapshot / "nucleo/STM32CubeIDE/Debug"
    manifest = json.loads((nuc / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("firmware_build_id") != NEW_PAIR[1]:
        raise RuntimeError("wrong Nucleo identity")
    for item in manifest["artifacts"]:
        path = nuc / item["file"]
        if path.stat().st_size != item["bytes"] or sha(path) != item["sha256"].lower():
            raise RuntimeError("Nucleo build artifact mismatch")
    return build / "UNOQ_MOTOR.ino.elf-zsk.bin", nuc / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin"


def initial_idle(s: dict) -> None:
    ok, reason = precheck(s)
    if not ok:
        raise RuntimeError(reason)
    if (s.get("fw_build"), s.get("mc_fw_build")) != OLD_PAIR:
        raise RuntimeError("installation requires the exact 1002/801 baseline")
    for field in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence", "mc_uart_error_flags",
                  "mc_last_uart_error_flags", "uno_tx_short_writes"):
        if s.get(field) != 0:
            raise RuntimeError("baseline transport is not clean: " + field)


def new_idle(s: dict, allow_cutover_history: bool = False) -> None:
    if ((s.get("fw_build"), s.get("mc_fw_build")) != NEW_PAIR or s.get("state") != "SAFE"
            or s.get("pwm") != 0 or s.get("hmi_hv_armed") != 0 or s.get("estop") != 0
            or int(s.get("bp_status", 255)) & 0x22):
        raise RuntimeError("new pair not disarmed SAFE")
    for field in ("vdc", "bp_vdc"):
        value = float(s.get(field, math.nan))
        if not math.isfinite(value) or not 0 <= value <= 2:
            raise RuntimeError("new bus not discharged")
    if not 0 <= s.get("bp_vbus_raw", 999) <= 20:
        raise RuntimeError("raw bus exceeds programming limit")
    for field in ("mc_age_ms", "bp_vbus_age_ms", "bp_temp_age_ms"):
        value = float(s.get(field, math.nan))
        if not math.isfinite(value) or not 0 <= value < 300:
            raise RuntimeError("stale new telemetry: " + field)
    if (s.get("rpc_schema_version") != 3 or s.get("mc_capabilities") != 1
            or s.get("mc_diag_valid") != 1 or s.get("bp_vbus_valid") != 1
            or s.get("bp_temp_valid") != 1 or s.get("bp_temp_fault") != 0
            or any(s.get(k) != 0 for k in ("precharge", "pfc", "brake", "bp_ext"))):
        raise RuntimeError("invalid contract or active service output")
    temp = float(s.get("bp_temp_c", math.nan))
    if (not math.isfinite(temp) or not -10 <= temp < 80
            or s.get("mc_fault_current_mask") not in (0, 4)
            or s.get("mc_fault_occurred_mask") not in (0, 4)):
        raise RuntimeError("unexpected temperature or MCSDK protection event")
    if s.get("bp_fault") not in ((0, 2, 3, 5) if allow_cutover_history else (0, 5)):
        raise RuntimeError("unexpected new fault")
    if any(s.get(k) != 0 for k in ("mc_bad_integrity", "mc_bad_sequence", "uno_tx_short_writes")):
        raise RuntimeError("new Uno transport errors")
    for field in ("bp_ne_accepted", "bp_ne_observed", "bp_ne_flags", "bp_transport_fault"):
        if type(s.get(field)) is not int or not 0 <= s[field] <= 65535:
            raise RuntimeError("missing v3 diagnostic field: " + field)
    if allow_cutover_history:
        if (s.get("mc_fault_reason") not in (0, 1, 2, 8, 13)
                or s.get("mc_last_bad_reason") not in (0, 1, 2, 13)
                or s.get("mc_uart_error_flags") != 0 or s.get("mc_last_uart_error_flags") != 0
                or s.get("mc_fault_motor_state") not in (0, 10)
                or s.get("mc_fault_current_mask") not in (0, 4)
                or s.get("mc_fault_occurred_mask") not in (0, 4)):
            raise RuntimeError("cutover error is not an expected idle protocol/undervoltage event")
    elif (s.get("mc_bad_cnt") != 0 or s.get("mc_uart_error_flags") != 0
          or s.get("mc_last_uart_error_flags") != 0 or s.get("mc_last_bad_reason") != 0
          or s.get("bp_transport_fault") != 0):
        raise RuntimeError("new transport not clean after explicit cutover ACK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-power-off", action="store_true")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--regression", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_power_off:
        parser.error("mains/J4 off and discharged stand required")
    root = Path(__file__).resolve().parents[1]
    image, nuc_image = verify_package(root, args.snapshot.resolve(strict=True), args.regression.resolve(strict=True))
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"pass": False, "motor_start_commands": [], "hv_release_approved": False,
              "scope": "coordinated v3 pair update, idle-only; no ARM/START",
              "commands": [], "samples": [], "images": {"uno": sha(image), "nucleo": sha(nuc_image)}}
    hmi = WifiHmi("http://192.168.1.138:8080", read_token(args.token_file), report["commands"], via_wsl=True)

    def run(cmd: list[str], label: str, timeout: int = 120) -> str:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        (out / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(label + " failed")
        return result.stdout

    def cli(extra: list[str], label: str, reset: bool = False) -> str:
        return run([PROGRAMMER, "-c", "port=SWD", "sn=" + SERIAL,
                    "mode=" + ("UR" if reset else "HOTPLUG"),
                    *(["reset=HWrst"] if reset else []), *extra], label, 90)

    def calibration_hash(label: str) -> str:
        return run(["adb", "-s", ADB_SERIAL, "shell", "sha256sum",
                    "/home/arduino/.config/mic-ai/vbus_calibration.json"], label).split()[0]

    try:
        before = hmi.status()
        initial_idle(before)
        report["before"] = before
        report["calibration_before_sha256"] = calibration_hash("calibration_before")
        boards = json.loads(run(["arduino-cli", "board", "list", "--format", "json"], "board_presence"))
        serials = {p.get("port", {}).get("properties", {}).get("serialNumber")
                   for p in boards["detected_ports"]}
        if not {SERIAL, ADB_SERIAL} <= serials:
            raise RuntimeError("both exact USB boards must be present")
        baseline = root / "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin"
        if sha(baseline) != "b10b9cda5bc2cf7ed6329bef7c14b42527ac6c745f76a75f304bc945014b4275":
            raise RuntimeError("rollback baseline hash mismatch")
        backup = out / "nucleo_before.bin"
        cli(["-u", "0x08000000", str(baseline.stat().st_size), str(backup)], "backup_nucleo")
        if backup.read_bytes() != baseline.read_bytes():
            raise RuntimeError("connected Nucleo differs from known 801 image")
        report["nucleo_baseline_byte_verified"] = True
        # Install the calibration-compatible HMI BEFORE MCU protocol cutover.
        # Its explicit candidate HV gate blocks powered START even with valid saved points.
        server = root / "web_hmi/server.py"
        remote = "/home/arduino/server_uart_v3_candidate.py"
        installer = "/home/arduino/install_uart_v3_hmi.py"
        run(["adb", "-s", ADB_SERIAL, "push", str(server), remote], "push_server")
        run(["adb", "-s", ADB_SERIAL, "push", str(root / "tools/install_vbus_hmi_fix_remote.py"), installer], "push_hmi_installer")
        run(["adb", "-s", ADB_SERIAL, "shell", "python3", installer,
             "--candidate", remote, "--sha256", sha(server)], "install_hmi", 90)
        initial_idle(hmi.status())
        report["hmi_installed_sha256"] = sha(server)
        cli(["-w", str(nuc_image), "0x08000000", "-v", "-rst"], "flash_nucleo", True)
        report["nucleo_flash_completed"] = True
        readback = out / "nucleo_v3_readback.bin"
        cli(["-u", "0x08000000", str(nuc_image.stat().st_size), str(readback)], "verify_nucleo_readback")
        if readback.read_bytes() != nuc_image.read_bytes():
            raise RuntimeError("Nucleo candidate readback mismatch")
        report["nucleo_byte_verified"] = True
        upload = ["arduino-cli", "upload", "-p", "COM10", "-b", "arduino:zephyr:unoq", "-i", str(image),
                  "--upload-property", f"upload.artifacts.sketch={image}",
                  "--upload-property", "upload.port.properties.serialNumber=" + ADB_SERIAL]
        run(upload, "flash_uno", 180)
        report["uno_flash_completed"] = True
        # Do verification before live RPC qualification: the normal verify recipe resets
        # the MCU and can require a subsequent full board power-cycle for RouterBridge.
        run(upload + ["--upload-property", f"build.variant.path={root / 'tools'}",
                      "--upload-property", "openocd_cfg=verify_unoq_sketch.cfg"], "verify_uno", 180)
        report["uno_flash_verify_passed"] = True
        words = parse_registers(cli(["-r32", "0x40012c44", "1"], "nucleo_outputs_off"))
        report["nucleo_bdtr"] = words[0x40012c44]
        if report["nucleo_bdtr"] & 0x8000:
            raise RuntimeError("Nucleo TIM1 MOE unexpectedly enabled")
        report["calibration_after_sha256"] = calibration_hash("calibration_after")
        report["calibration_unchanged"] = report["calibration_after_sha256"] == report["calibration_before_sha256"]
        if not report["calibration_unchanged"]:
            raise RuntimeError("calibration changed")
        deadline = time.monotonic() + 40
        status = None
        while time.monotonic() < deadline:
            try:
                trial = hmi.status()
                if (trial.get("fw_build"), trial.get("mc_fw_build")) == NEW_PAIR:
                    status = trial
                    break
            except Exception as exc:
                report["last_rpc_error"] = str(exc)
            time.sleep(1)
        if status is None:
            report["needs_cold_power_cycle"] = True
            raise RuntimeError("both images verified; RouterBridge did not recover after warm reset")
        stable = []
        for _ in range(8):
            s = hmi.status()
            new_idle(s, True)
            stable.append(s)
            time.sleep(.25)
        report["cutover_history"] = stable
        if len({s["mc_bad_cnt"] for s in stable}) != 1:
            raise RuntimeError("errors still growing; no cutover ACK allowed")
        if stable[-1]["mc_bad_cnt"] != 0 or stable[-1]["bp_transport_fault"] != 0:
            hmi.command("CLEAR")
            time.sleep(1)
        for _ in range(60):
            s = hmi.status()
            new_idle(s)
            report["samples"].append(s)
            time.sleep(.5)
        report["uart_progress"] = any(a["mc_seq"] != b["mc_seq"]
                                       for a, b in zip(report["samples"], report["samples"][1:]))
        if not report["uart_progress"] or report["samples"][-1].get("hmi_vbus_hv_calibrated") != 1:
            raise RuntimeError("missing fresh UART or retained calibration")
        (out / "wifi_logs.txt").write_text(get_wifi_logs(hmi, hmi.token), encoding="utf-8")
        report["pass"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        hmi.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("pass", "error", "nucleo_flash_completed", "nucleo_byte_verified",
                      "uno_flash_completed", "uno_flash_verify_passed", "calibration_unchanged", "needs_cold_power_cycle")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

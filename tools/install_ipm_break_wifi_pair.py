"""Install a hash-verified passive diagnostic pair, only on a discharged stand."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from collect_wifi_telemetry import read_token
from prepare_ipm_break_wifi import ROOT, REFERENCE, UNO, ASSETS, NUCLEO_ID, UNO_ID, nucleo_main, uno_sketch, hmi_server, patched_irq, source_hashes
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL
from run_wifi_nucleo_pwm_bench import WifiHmi
from unoq_wifi_hmi_deploy import ssh_base
from verify_wifi_command_path import get_wifi_logs

OLD_PAIR = (2026101008, 2026101006)
NEW_PAIR = (UNO_ID, NUCLEO_ID)
UNO_SERIAL = "3880458060"
URL = "http://192.168.1.138:8080"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def idle_safe(s, maintenance_boot_reject=False):
    try:
        if (s["fw_build"], s["mc_fw_build"]) not in (OLD_PAIR, (UNO_ID, OLD_PAIR[1]), NEW_PAIR):
            return False
        if s["state"] != "SAFE" or s["pwm"] != 0 or s["hmi_hv_armed"] != 0 or s["estop"] != 0:
            return False
        if s["bp_status"] & 0x22 or s["rpc_schema_version"] != 3 or s["mc_capabilities"] != 1:
            return False
        if s["bp_mcsdk_telemetry"] != 1 or s["bp_vbus_valid"] != 1 or s["bp_temp_valid"] != 1:
            return False
        for key in ("mc_age_ms", "bp_vbus_age_ms", "bp_temp_age_ms"):
            if type(s[key]) not in (int, float) or not math.isfinite(s[key]) or not 0 <= s[key] < 300:
                return False
        for key in ("vdc", "bp_vdc"):
            if type(s[key]) not in (int, float) or not math.isfinite(s[key]) or not 0 <= s[key] <= 2:
                return False
        if type(s["bp_vbus_raw"]) is not int or not 0 <= s["bp_vbus_raw"] <= 20:
            return False
        flash_pause_timeout = (
            (s["fw_build"], s["mc_fw_build"]) == (UNO_ID, OLD_PAIR[1])
            and s["bp_fault"] == 2 and s["bp_status"] == 25
            and s.get("bp_transport_fault") == 7 and s.get("bp_bad_cnt") == 1
            and s.get("mc_last_bad_reason") == 13 and s.get("mc_last_uart_error_flags") == 0)
        if s["bp_fault"] != 0 and not flash_pause_timeout:
            # Maintenance only: the installed first-fault snapshot records
            # undervoltage after the already archived DP trip. Never CLEAR it
            # to make an updater gate pass, and never use this as a RUN gate.
            if (s["bp_fault"] != 5 or s["mc_diag_valid"] != 1 or s["mc_fault_reason"] != 8
                    or s["mc_fault_current_mask"] != 4 or s["mc_fault_occurred_mask"] not in (4, 0x404)):
                return False
        if not flash_pause_timeout and (s["bp_bad_cnt"] != 0 or s["bp_transport_fault"] != 0):
            return False
        boot_reject = (maintenance_boot_reject and flash_pause_timeout
                      and type(s["bp_bad"]) is int and 0 <= s["bp_bad"] <= 65535
                      and s["bp_bad_integrity"] == s["bp_bad"])
        if not boot_reject and (s["bp_bad"] != 0 or s["bp_bad_integrity"] != 0):
            return False
        return all(s[k] == 0 for k in ("bp_temp_fault",
            "bp_bad_sequence", "bp_clear_pending", "precharge", "pfc", "brake", "bp_ext"))
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def verify_package(candidate, regression):
    report = json.loads(regression.read_text(encoding="utf-8-sig"))
    if report.get("pass") is not True or report.get("sources_unchanged_during_tests") is not True:
        raise RuntimeError("Unchanged-source full regression must pass")
    for k, v in report["source_sha256"].items():
        if sha(ROOT / k) != v:
            raise RuntimeError("Regression source changed: " + k)
    if not any(t.get("test") == "ipm_break_wifi_selftest" and t.get("pass") for t in report["tests"]):
        raise RuntimeError("Matched wire/HTTP tests missing")
    manifest = json.loads((candidate / "manifest.json").read_text())
    if (manifest["uno_build"], manifest["nucleo_build"]) != NEW_PAIR:
        raise RuntimeError("Unexpected pair identity")
    if manifest["baseline_nucleo"] != source_hashes(REFERENCE) or manifest["baseline_uno"] != source_hashes(UNO):
        raise RuntimeError("Frozen reference changed")
    for folder, key in (("nucleo", "candidate_nucleo"), ("UNOQ_MOTOR", "candidate_uno")):
        current = source_hashes(candidate / folder)
        if any(current.get(k) != v for k, v in manifest[key].items()):
            raise RuntimeError("Candidate source changed: " + folder)
    for relative, expected in (
        ("nucleo/Src/main.c", nucleo_main((REFERENCE / "Src/main.c").read_text(encoding="utf-8-sig"))),
        ("nucleo/Src/stm32g4xx_mc_it.c", patched_irq((REFERENCE / "Src/stm32g4xx_mc_it.c").read_text(encoding="utf-8-sig"))),
        ("UNOQ_MOTOR/UNOQ_MOTOR.ino", uno_sketch((UNO / "UNOQ_MOTOR.ino").read_text(encoding="utf-8-sig"))),
        ("web_hmi/server.py", hmi_server((ROOT / "web_hmi/server.py").read_text(encoding="utf-8-sig")))):
        if (candidate / relative).read_text(encoding="utf-8-sig") != expected:
            raise RuntimeError("Candidate differs from tested generator: " + relative)
    for path in (candidate / "nucleo/Inc/break_wire.h", candidate / "UNOQ_MOTOR/break_wire.h"):
        if sha(path) != sha(ASSETS / "break_wire.h"):
            raise RuntimeError("Mismatched diagnostic protocol header")
    dirs = [(candidate / "uno_build", "unoq_mcsdk_scalar.build-manifest.json", UNO_ID),
            (candidate / "nucleo/STM32CubeIDE/Debug", "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json", NUCLEO_ID)]
    for folder, name, identity in dirs:
        build = json.loads((folder / name).read_text(encoding="utf-8-sig"))
        if build.get("firmware_build_id") != identity:
            raise RuntimeError("Wrong image build")
        for item in build["artifacts"]:
            path = folder / item["file"]
            if sha(path) != item["sha256"].lower() or path.stat().st_size != item["bytes"]:
                raise RuntimeError("Image hash/length mismatch")
    return (candidate / "uno_build/UNOQ_MOTOR.ino.elf-zsk.bin",
            candidate / "nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--regression", type=Path, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument("--confirm-mains-j4-off", action="store_true")
    p.add_argument("--check-only", action="store_true")
    args = p.parse_args()
    candidate = args.candidate.resolve(strict=True)
    uno_image, nuc_image = verify_package(candidate, args.regression.resolve(strict=True))
    if args.check_only:
        print(json.dumps(dict(package_verified=True, uno_sha256=sha(uno_image), nucleo_sha256=sha(nuc_image), hardware_commands=0)))
        return 0
    if not args.confirm_mains_j4_off:
        p.error("Physical mains/J4-off confirmation is required, in addition to the live <=2V gate")
    out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    report = dict(pass_=False, commands=[], start_commands=0, hv_release_approved=False,
                  uno_image_sha256=sha(uno_image), nucleo_image_sha256=sha(nuc_image))
    hmi = WifiHmi(URL, read_token(str(ROOT / ".unoq_ssh/control_token")), report["commands"], via_wsl=False)
    ssh = ssh_base("192.168.1.138", 2222, "arduino", ROOT / ".unoq_ssh/id_ed25519", ROOT / ".unoq_ssh/known_hosts")
    def run(command, label, timeout=180):
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        (out / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        report["commands"].append({"label": label, "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError(label + " failed; see log")
        return result.stdout
    def cal_hash(label):
        return run(ssh + ["sha256sum /home/arduino/.config/mic-ai/vbus_calibration.json"], label).split()[0]
    def guarded_status():
        s = hmi.status()
        report["last_programming_gate_status"] = s
        if not idle_safe(s, maintenance_boot_reject=True):
            raise RuntimeError("Live programming gate rejected state; no START/CLEAR will be sent")
        return s
    try:
        report["before"] = before = guarded_status()
        report["before_strict_idle_qualified"] = idle_safe(before)
        # Historical boot rejection is retained, never cleared or used as RUN
        # approval. Any changing rejection counter aborts before programming.
        counter_keys = ("bp_bad", "bp_bad_cnt", "bp_bad_integrity", "bp_bad_sequence", "bp_transport_fault")
        for _ in range(3):
            time.sleep(1)
            checked = guarded_status()
            if any(checked[k] != before[k] for k in counter_keys):
                raise RuntimeError("UART rejection counters increased; programming aborted")
        (out / "before_wifi_logs.txt").write_text(get_wifi_logs(hmi, hmi.token), encoding="utf-8")
        boards = json.loads(run(["arduino-cli", "board", "list", "--format", "json"], "usb_inventory"))
        ports = {d["port"].get("properties", {}).get("serialNumber"): d["port"]["address"] for d in boards["detected_ports"]}
        if UNO_SERIAL not in ports or SERIAL not in ports:
            raise RuntimeError("Both exact USB board serials must be present")
        report["calibration_before_sha256"] = cal_hash("calibration_before")
        remote = "/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py"
        goal = sha(candidate / "web_hmi/server.py")
        installed = run(ssh + ["sha256sum " + remote], "hmi_before").split()[0]
        if installed != goal:
            if (before["fw_build"], before["mc_fw_build"]) != OLD_PAIR:
                raise RuntimeError("HMI must be installed before changing MCU identities")
            run([sys.executable, ROOT / "tools/unoq_wifi_hmi_deploy.py", "--candidate-server", candidate / "web_hmi/server.py",
                 "--confirm-mains-j4-off", "--outdir", out / "hmi_deploy"], "deploy_hmi", 180)
        if (before["fw_build"], before["mc_fw_build"]) == OLD_PAIR:
            guarded_status()
            run(["arduino-cli", "upload", "-p", ports[UNO_SERIAL], "-b", "arduino:zephyr:unoq", "-i", uno_image,
                 "--upload-property", "upload.artifacts.sketch=" + str(uno_image),
                 "--upload-property", "upload.port.properties.serialNumber=" + UNO_SERIAL,
                 "--upload-property", "build.variant.path=" + str(ROOT / "tools"),
                 "--upload-property", "openocd_cfg=flash_verify_unoq_sketch.cfg"], "flash_verify_uno")
            report["uno_flash_verified"] = True
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                try:
                    s = guarded_status()
                    if s["fw_build"] == UNO_ID:
                        break
                except Exception as exc:
                    report["last_rpc_error"] = str(exc)
                time.sleep(1)
            else:
                last = report.get("last_programming_gate_status", {})
                report["needs_cold_power_cycle"] = last.get("fw_build") != UNO_ID
                raise RuntimeError("Uno flash verified; live intermediate programming gate not confirmed; Nucleo not yet changed")
        s = guarded_status()
        if s["mc_fw_build"] == OLD_PAIR[1]:
            run([PROGRAMMER, "-c", "port=SWD", "mode=UR", "sn=" + SERIAL, "-w", nuc_image,
                 "0x08000000", "-v", "-rst"], "flash_verify_nucleo")
            report["nucleo_flash_verified"] = True
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                s = hmi.status()
                if (s["fw_build"], s["mc_fw_build"]) == NEW_PAIR:
                    break
            except Exception as exc:
                report["last_rpc_error"] = str(exc)
            time.sleep(1)
        else:
            raise RuntimeError("Matched pair live identity not confirmed")
        time.sleep(3)
        report["after"] = s = hmi.status()
        report["pair_image_installation_complete"] = (s["fw_build"], s["mc_fw_build"]) == NEW_PAIR
        report["strict_idle_qualified"] = idle_safe(s)
        report["calibration_after_sha256"] = cal_hash("calibration_after")
        report["calibration_unchanged"] = report["calibration_before_sha256"] == report["calibration_after_sha256"]
        if not report["calibration_unchanged"]:
            raise RuntimeError("Calibration bytes changed")
        report["pass_"] = report["strict_idle_qualified"]
        if not report["pass_"]:
            report["error"] = "Images installed; strict idle qualification is pending. No powered approval."
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        hmi.close(); report["pass"] = report.pop("pass_")
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report.get(k) for k in ("pass", "uno_flash_verified", "nucleo_flash_verified",
        "needs_cold_power_cycle", "calibration_unchanged", "error")}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

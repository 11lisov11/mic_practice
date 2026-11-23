"""Install only the pinned Uno sender fix, preserving the Nucleo and calibration."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from collect_wifi_telemetry import read_token
from install_vbus_hmi_fix_remote import precheck
from prepare_uart_v3_sender_fix import patched_sketch
from run_wifi_nucleo_pwm_bench import WifiHmi, run_logged
from uart_update_regression import source_hashes
from verify_wifi_command_path import get_wifi_logs


SERIAL = "3880458060"
NEW_PAIR = (2026101008, 2026101006)
IMAGE_SHA = "1ebb68a6bf9180643ec471e240b4ab125c51866f8da1d69c974421bbd403708a"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_candidate(root, snapshot, regression):
    reference = root / "artifacts/live_bench_20261010/uart_v3_candidate/firmware_r6/UNOQ_MOTOR"
    candidate = snapshot / "UNOQ_MOTOR"
    if {p.name for p in reference.iterdir() if p.is_file()} != {p.name for p in candidate.iterdir() if p.is_file()}:
        raise ValueError("candidate file set changed")
    for old in reference.iterdir():
        if not old.is_file():
            continue
        new = candidate / old.name
        if old.suffix == ".ino":
            if new.read_text(encoding="utf-8-sig") != patched_sketch(old.read_text(encoding="utf-8-sig")):
                raise ValueError("sender delta differs from reviewed two-line change")
        elif old.read_bytes() != new.read_bytes():
            raise ValueError("unreviewed sender helper change: " + old.name)
    image = snapshot / "uno_build/UNOQ_MOTOR.ino.elf-zsk.bin"
    if sha(image) != IMAGE_SHA:
        raise ValueError("unreviewed firmware image")
    build = json.loads((snapshot / "uno_build/unoq_mcsdk_scalar.build-manifest.json").read_text(encoding="utf-8-sig"))
    if build.get("firmware_build_id") != NEW_PAIR[0]:
        raise ValueError("wrong build identity")
    for item in build["artifacts"]:
        path = image.parent / item["file"]
        if path.stat().st_size != item["bytes"] or sha(path) != item["sha256"].lower():
            raise ValueError("build artifact mismatch")
    report = json.loads(regression.read_text(encoding="utf-8-sig"))
    if (report.get("pass") is not True or report.get("sources_unchanged_during_tests") is not True
            or len(report.get("tests", [])) < 41 or report.get("source_sha256") != source_hashes(root)):
        raise ValueError("current unchanged-source full regression required")
    if not any(t.get("test") == "uart_v3_sender_invariant_selftest" and t.get("pass") is True
               for t in report["tests"]):
        raise ValueError("sender invariant reproduction missing")
    return image


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--regression", type=Path, required=True)
    p.add_argument("--token-file", type=Path, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument("--confirm-mains-j4-off", action="store_true",
                   help="Physical mains isolation, J4 off and meter below 10 V confirmed by operator")
    p.add_argument("--check-only", action="store_true")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    image = verify_candidate(root, args.snapshot.resolve(strict=True), args.regression.resolve(strict=True))
    if args.check_only:
        print(json.dumps(dict(package_verified=True, image_sha256=sha(image), hardware_commands=0)))
        return 0
    if not args.confirm_mains_j4_off:
        p.error("explicit physical deenergization confirmation required")
    out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    rep = dict(pass_=False, commands=[], samples=[], image_sha256=sha(image),
               nucleo_flashed=False, start_commands=0, hv_release_approved=False)
    h = WifiHmi("http://192.168.1.138:8080", read_token(str(args.token_file)), rep["commands"], via_wsl=False)

    def run(command, label, timeout=180):
        log = out / (label + ".log")
        run_logged(command, log, timeout)
        return log.read_text(encoding="utf-8")

    def cal_hash(label):
        return run(["adb", "-s", SERIAL, "shell", "sha256sum",
                    "/home/arduino/.config/mic-ai/vbus_calibration.json"], label).split()[0]

    try:
        rep["before"] = s = h.status()
        if (s.get("fw_build"), s.get("mc_fw_build")) != (2026101007, 2026101006):
            raise RuntimeError("exact 1007/1006 reference pair required")
        if not precheck(s, 10)[0]:
            raise RuntimeError(precheck(s, 10)[1])
        (out / "before_wifi_logs.txt").write_text(get_wifi_logs(h, h.token), encoding="utf-8")
        rep["calibration_before_sha256"] = cal_hash("calibration_before")
        boards = json.loads(run(["arduino-cli", "board", "list", "--format", "json"], "board_presence"))
        ports = [v["port"]["address"] for v in boards["detected_ports"]
                 if v.get("port", {}).get("properties", {}).get("serialNumber") == SERIAL]
        if len(ports) != 1:
            raise RuntimeError("exact Uno USB serial not identified")
        server = root / "web_hmi/server.py"
        run(["adb", "-s", SERIAL, "push", str(server), "/tmp/mic_sender_hmi.py"], "push_hmi")
        run(["adb", "-s", SERIAL, "push", str(root / "tools/install_vbus_hmi_fix_remote.py"),
             "/tmp/mic_sender_hmi_installer.py"], "push_hmi_installer")
        run(["adb", "-s", SERIAL, "shell", "python3", "/tmp/mic_sender_hmi_installer.py",
             "--candidate", "/tmp/mic_sender_hmi.py", "--sha256", sha(server),
             "--max-vdc", "10", "--confirm-mains-off"], "install_hmi", 90)
        rep["hmi_installed_sha256"] = sha(server)
        if not precheck(h.status(), 10)[0]:
            raise RuntimeError("live programming precheck changed")
        run(["arduino-cli", "upload", "-p", ports[0], "-b", "arduino:zephyr:unoq", "-i", str(image),
             "--upload-property", "upload.artifacts.sketch=" + str(image),
             "--upload-property", "upload.port.properties.serialNumber=" + SERIAL,
             "--upload-property", "build.variant.path=" + str(root / "tools"),
             "--upload-property", "openocd_cfg=flash_verify_unoq_sketch.cfg"], "flash_verify_uno", 180)
        rep["uno_flash_verified"] = True
        time.sleep(8)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                s = h.status()
            except Exception as exc:
                rep["last_rpc_error"] = str(exc)
                time.sleep(1)
                continue
            if (s.get("fw_build"), s.get("mc_fw_build")) == NEW_PAIR:
                break
            time.sleep(1)
        else:
            rep["needs_cold_power_cycle"] = True
            raise RuntimeError("image verified; live RPC identity has not recovered")
        rep["after"] = s
        if not precheck(s, 10)[0] or s.get("hmi_vbus_hv_calibrated") != 1:
            raise RuntimeError("new pair idle/calibration precheck failed")
        for _ in range(15):
            s = h.status(); rep["samples"].append(s)
            if not precheck(s, 10)[0]:
                raise RuntimeError("new idle/output check failed")
            time.sleep(1)
        rep["calibration_after_sha256"] = cal_hash("calibration_after")
        rep["calibration_unchanged"] = rep["calibration_before_sha256"] == rep["calibration_after_sha256"]
        if not rep["calibration_unchanged"]:
            raise RuntimeError("calibration bytes changed")
        rep["pass_"] = True
    except Exception as exc:
        rep["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        h.close(); rep["pass"] = rep.pop("pass_")
        (out / "report.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: rep.get(k) for k in ("pass", "uno_flash_verified", "nucleo_flashed",
                     "calibration_unchanged", "needs_cold_power_cycle", "error")}))
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

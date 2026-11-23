"""Verify/reset Uno and promptly reset Nucleo on a discharged, disarmed bench."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import time

from collect_wifi_telemetry import read_token
from run_current_pwm_801 import verified_images
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL
from run_wifi_nucleo_pwm_bench import WifiHmi, run_logged, sha256, wait_status
from verify_wifi_command_path import get_wifi_logs


def reset_safe(s):
    try:
        return ((s.get("fw_build"), s.get("mc_fw_build")) == (2026101001, 2026100801)
                and s.get("state") == "SAFE" and s.get("pwm") == 0
                and s.get("hmi_hv_armed") == 0 and not (s["bp_status"] & 0x22)
                and s.get("bp_vbus_valid") == 1
                and math.isfinite(s["vdc"]) and 0 <= s["vdc"] <= 2
                and 0 <= s["bp_vbus_raw"] <= 20
                and 0 <= s["mc_age_ms"] < 300 and 0 <= s["bp_vbus_age_ms"] < 300
                and all(s.get(k) == 0 for k in ("precharge", "pfc", "brake", "bp_ext")))
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm-power-off", action="store_true")
    p.add_argument("--uno-build", type=Path, required=True)
    p.add_argument("--token-file", type=Path, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    a = p.parse_args()
    if not a.confirm_power_off:
        p.error("physical mains and J4 off required")
    root = Path(__file__).resolve().parents[1]
    build = a.uno_build.resolve(strict=True)
    manifest = json.loads((build / "unoq_mcsdk_scalar.build-manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("firmware_build_id") != 2026101001:
        raise RuntimeError("Only reviewed Uno 1001 supports this startup timing")
    image = build / manifest["flash_artifact"]
    if sha256(image) != "92f3c7484ceb31ff67e04a1d0b08292499f1875cf49fef12fe6d14c4a4fece38":
        raise RuntimeError("Uno image is not the verified ownership build")
    _, nuc_bin = verified_images(root / "firmware/updates/installed_804_801/nucleo", 2026100801)
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    r = {"pass": False, "commands": [], "samples": [], "arm_commands": 0, "start_commands": 0,
         "mcu_flash_writes": 0, "hv_release_approved": False,
         "scope": "Idle coordinated reset; counters reset by MCU reboot, prior evidence retained"}
    h = WifiHmi("http://192.168.1.138:8080", read_token(a.token_file), r["commands"], via_wsl=True)
    try:
        before = h.status()
        r["before"] = before
        (out / "before_reset.json").write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
        if not reset_safe(before):
            raise RuntimeError("Discharged, disarmed exact pair required")
        h.fail_safe_stop()
        if not reset_safe(h.status()):
            raise RuntimeError("State changed before reset")
        command = ["arduino-cli", "upload", "-p", "COM10", "-b", "arduino:zephyr:unoq",
                   "-i", str(image), "--upload-property", f"upload.artifacts.sketch={image}",
                   "--upload-property", "upload.port.properties.serialNumber=3880458060",
                   "--upload-property", f"build.variant.path={root / 'tools'}",
                   "--upload-property", "openocd_cfg=verify_unoq_sketch.cfg"]
        run_logged(command, out / "uno_verify_reset.log", timeout=120)
        r["uno_verify_only_passed"] = True
        began = time.monotonic()
        run_logged([PROGRAMMER, "-c", "port=SWD", "mode=HOTPLUG", "sn=" + SERIAL, "-rst"],
                   out / "nucleo_reset.log", timeout=15)
        r["nucleo_reset_after_verify_s"] = round(time.monotonic() - began, 3)
        if r["nucleo_reset_after_verify_s"] >= 4:
            raise RuntimeError("Reset exceeded the reviewed Uno startup window")
        wait_status(h, reset_safe, 45, "production pair resumed SAFE")
        for _ in range(30):
            s = h.status()
            r["samples"].append(s)
            if (not reset_safe(s) or s.get("estop") != 0 or s.get("bp_fault") not in (0, 5)
                    or any(s.get(k) != 0 for k in (
                        "mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence", "mc_uart_error_flags",
                        "mc_last_uart_error_flags", "uno_tx_short_writes"))):
                raise RuntimeError("Post-reset idle transport/state unhealthy")
            time.sleep(.2)
        h.post("/api/arm-profile", {"profile": "hv"}, "restore disarmed production profile")
        r["after"] = wait_status(h, lambda s: reset_safe(s) and s.get("hmi_arm_profile") == "hv"
            and s.get("hmi_vbus_hv_calibrated") == 1, 5, "restored profile and preserved calibration")
        readback = out / "nucleo_after_reset.bin"
        run_logged([PROGRAMMER, "-c", "port=SWD", "mode=HOTPLUG", "sn=" + SERIAL,
                    "-u", "0x08000000", str(nuc_bin.stat().st_size), str(readback)],
                   out / "nucleo_readonly_verify.log", timeout=15)
        r["nucleo_image_unchanged"] = readback.read_bytes() == nuc_bin.read_bytes()
        (out / "wifi_logs.txt").write_text(get_wifi_logs(h, h.token), encoding="utf-8")
        r["pass"] = r["nucleo_image_unchanged"] and r["uno_verify_only_passed"]
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        code, data = h.fail_safe_stop()
        r["final_stop"] = {"http": code, "ok": data.get("ok") is True}
        r["pass"] = r["pass"] and code == 200 and data.get("ok") is True
        h.close()
        (out / "report.json").write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: r.get(k) for k in ("pass", "error", "uno_verify_only_passed",
          "nucleo_image_unchanged", "nucleo_reset_after_verify_s", "final_stop")}, indent=2))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

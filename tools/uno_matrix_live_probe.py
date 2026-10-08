"""Read Uno Q matrix SRAM during zero-bus Wi-Fi setpoints; never enable PWM."""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import re
import struct
import subprocess
import time

from run_wifi_nucleo_pwm_bench import WifiHmi
from wifi_idle_setpoint_check import healthy_off


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--observe", action="store_true", help="15-second LED test, then 20-second digit holds")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    core = Path.home() / "AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0"
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    if reference.get("pass") is not True:
        raise ValueError("Renderer reference did not pass")
    token = getpass.getpass("Control token (hidden): ")
    report = {"pass": False, "no_reset_halt_or_flash": True, "commands": [], "issued_commands": [], "samples": [],
              "physical_led_observation": "pending", "pwm_enabled": False}
    hmi = WifiHmi("http://192.168.1.138:8080", token, report["commands"], via_wsl=True)
    began = False
    try:
        before = hmi.status()
        if not healthy_off(before):
            raise RuntimeError("Expected zero bus, SAFE, disarmed build 708")
        report["before"] = before
        image = (root / "artifacts/current_pwm_20261007/full_debug_r1/uno_matrix_709/UNOQ_MOTOR.ino.elf-zsk.bin"
                 if before["fw_build"] == 2026100709 else
                 root / "artifacts/current_pwm_20261007/async_clear_708/uno_q/UNOQ_MOTOR.ino.elf-zsk.bin")
        began = True
        if args.observe:
            report["issued_commands"].append("DISPLAY TEST")
            code, response = hmi.request("POST", "/api/cmd", {"cmd": "DISPLAY TEST"})
            if code != 200 or response.get("ok") is not True:
                raise RuntimeError("Display-only self-test rejected")
            deadline = time.monotonic() + 16
            report["display_test_observations"] = []
            while time.monotonic() < deadline:
                status = hmi.status()
                if not healthy_off(status):
                    raise RuntimeError("Off guard changed during LED test")
                report["display_test_observations"].append(status)
                time.sleep(.3)
        for frequency in (0, 5, 20):
            report["issued_commands"].append(f"SET FREQ {frequency}")
            code, response = hmi.request("POST", "/api/cmd", {"cmd": f"SET FREQ {frequency}"})
            if code != 200 or response.get("ok") is not True:
                raise RuntimeError("Setpoint rejected")
            time.sleep(1)
            status = hmi.status()
            if not healthy_off(status) or abs(float(status["freq_cmd"])-frequency) > .1:
                raise RuntimeError("Setpoint/off guard failed")
            command = [str(core.parents[2] / "tools/remoteocd/0.1.1/remoteocd.exe"), "upload",
                       "--adb-path", "adb", "-s", "3880458060", "-f", str(root / "tools/read_unoq_matrix.cfg"),
                       str(core / "firmwares/zephyr-arduino_uno_q_stm32u585xx.elf"),
                       str(image)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            output = result.stdout + result.stderr
            (args.outdir / f"frame_{frequency}.log").write_text(output, encoding="utf-8")
            match = re.search(r"MATRIX_FRAMEBUFFER_BEGIN\s+((?:0x[0-9a-f]+\s+){4})MATRIX_FRAMEBUFFER_END", output, re.I)
            if result.returncode or not match:
                raise RuntimeError("Matrix SRAM read failed")
            scan = re.search(r"MATRIX_SCAN_BEGIN\s+((?:0x[0-9a-f]+\s+){8})MATRIX_SCAN_END", output, re.I)
            if not scan:
                raise RuntimeError("Matrix scan index read failed")
            scan_indices = [int(w, 16) for w in scan[1].split()]
            scan_active = all(0 <= i < 104 for i in scan_indices) and len(set(scan_indices)) > 1
            actual = [int(w, 16) for w in match[1].split()]
            expected = reference["frames"][str(frequency)]
            # matrixWrite copies 104 bits; the following 24 bits are not pixels.
            same = struct.pack("<4I", *actual)[:13] == struct.pack("<4I", *expected)[:13]
            report["samples"].append({"setpoint": frequency, "status": status,
                                      "actual_frame": actual, "expected_frame": expected, "matches": same,
                                      "scan_indices": scan_indices, "scan_active": scan_active})
            print(json.dumps({"setpoint": frequency, "frame_matches": same}), flush=True)
            if args.observe and frequency:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    status = hmi.status()
                    if not healthy_off(status) or abs(float(status["freq_cmd"])-frequency) > .1:
                        raise RuntimeError("Off guard/setpoint changed during digit hold")
                    time.sleep(.3)
        report["pass"] = all(s["matches"] and s["scan_active"] for s in report["samples"])
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        if began:
            try:
                report["issued_commands"].append("STOP sequence (non-emergency)")
                code, response = hmi.fail_safe_stop()
                after = hmi.status()
                report["after"] = after
                report["stop_verified"] = (code == 200 and response.get("ok") is True and healthy_off(after)
                                            and abs(float(after.get("freq_cmd", -999))) <= .1)
                report["pass"] = report["pass"] and report["stop_verified"]
            except Exception as exc:
                report["stop_error"] = str(exc)
                report["pass"] = False
        hmi.close()
        (args.outdir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("pass", "error", "stop_verified")}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

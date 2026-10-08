"""Verify Wi-Fi setpoints and STOP with zero bus; never ARM or START."""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import time

from install_vbus_hmi_fix_remote import precheck
from run_wifi_nucleo_pwm_bench import WifiHmi
from verify_wifi_command_path import get_wifi_logs


def healthy_off(status: dict) -> bool:
    return (precheck(status)[0]
            and (status.get("fw_build"), status.get("mc_fw_build")) in
                ((2026100708, 2026100708), (2026100709, 2026100708))
            and all(status.get(k) == 0 for k in
                    ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--hold-seconds", type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.hold_seconds <= 30:
        parser.error("hold-seconds must be within 0..30")
    args.outdir.mkdir(parents=True, exist_ok=False)
    token = getpass.getpass("Control token (not displayed): ")
    report = {"pass": False, "scope": "USB attached, zero-bus Wi-Fi setpoints and STOP only",
              "pwm_enabled": False, "motor_rotation_tested": False,
              "autonomous_ground_path_verified": False,
              "commands": [], "issued_commands": [], "observations": []}
    hmi = WifiHmi("http://192.168.1.138:8080", token, report["commands"], via_wsl=True)
    began = False
    try:
        before = hmi.status()
        report["before"] = before
        if not healthy_off(before):
            raise RuntimeError("Expected discharged, disarmed, healthy build 708")
        began = True
        for cmd, expected in (("MODE VF", None), ("SET FREQ 5", 5),
                              ("SET FREQ 20", 20), ("SET FREQ 0", 0)):
            report["issued_commands"].append(cmd)
            code, response = hmi.request("POST", "/api/cmd", {"cmd": cmd})
            if code != 200 or response.get("ok") is not True:
                raise RuntimeError(f"Command rejected: {cmd}")
            deadline = time.monotonic() + 4
            while True:
                status = hmi.status()
                report["observations"].append({"after_command": cmd, "status": status})
                if not healthy_off(status):
                    raise RuntimeError("Zero-bus/off/link guard failed")
                if (status.get("mode") == "VF" and (expected is None
                        or abs(float(status.get("freq_cmd", -999)) - expected) <= .1)):
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Setpoint not reflected: {cmd}")
                time.sleep(.2)
            if expected is not None and expected > 0:
                hold_until = time.monotonic() + args.hold_seconds
                while time.monotonic() < hold_until:
                    status = hmi.status()
                    report["observations"].append({"held_command": cmd, "status": status})
                    if (not healthy_off(status)
                            or abs(float(status.get("freq_cmd", -999)) - expected) > .1):
                        raise RuntimeError(f"Setpoint or off/link guard changed during hold: {cmd}")
                    time.sleep(.3)
        report["setpoints_verified"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if began:
            try:
                report["issued_commands"].append("STOP sequence (non-emergency)")
                code, response = hmi.fail_safe_stop()
                after = hmi.status()
                report["after"] = after
                report["stop_verified"] = (code == 200 and response.get("ok") is True
                                            and healthy_off(after)
                                            and abs(float(after.get("freq_cmd", -999))) <= .1)
            except Exception as exc:
                report["stop_error"] = str(exc)
        try:
            logs = get_wifi_logs(hmi, token)
            (args.outdir / "wifi_logs.txt").write_text(logs, encoding="utf-8")
        except Exception as exc:
            report["log_error"] = str(exc)
        hmi.close()
        report["pass"] = (report.get("setpoints_verified") is True
                          and report.get("stop_verified") is True
                          and "error" not in report and "log_error" not in report)
        (args.outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)
                                                 + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in
                      ("pass", "setpoints_verified", "stop_verified", "error", "stop_error",
                       "pwm_enabled", "autonomous_ground_path_verified")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

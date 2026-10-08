"""Capture a measured HV bus point over Wi-Fi without enabling any output."""
from __future__ import annotations

import argparse
import getpass
import json
import math
from pathlib import Path

from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status
from verify_wifi_command_path import get_wifi_logs


def safe_disarmed(status: dict) -> bool:
    try:
        return (
            status["state"] == "SAFE" and status["pwm"] == 0
            and status["hmi_hv_armed"] == 0 and status["estop"] == 0
            and status["mc_fw_build"] == 2026100601
            and not (int(status["bp_status"]) & 0x22)
            and 0 <= float(status["mc_age_ms"]) < 300
            and status["bp_vbus_valid"] == 1
            and 0 <= float(status["bp_vbus_age_ms"]) < 300
            and math.isfinite(float(status["vdc"]))
            and 250 <= float(status["vdc"]) <= 360
            and status["bp_temp_valid"] == 1 and status["bp_temp_fault"] == 0
            and all(status.get(k) == 0 for k in ("precharge", "pfc", "brake", "bp_ext"))
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meter-vdc", type=float, required=True)
    parser.add_argument("--confirm-isolated-no-motor", action="store_true")
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_isolated_no_motor:
        parser.error("Disconnected USB, analyzer including GND, and motor required")
    if not math.isfinite(args.meter_vdc) or not 250 <= args.meter_vdc <= 360:
        parser.error("A measured working point within 250..360 V is required")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    token = getpass.getpass("Control credential (not echoed): ").strip()
    if len(token) < 16:
        raise RuntimeError("Control credential missing")
    report = {"pass": False, "meter_vdc": args.meter_vdc, "commands": [],
              "scope": "HV bus measurement only; no ARM/START or PWM",
              "motor_run_validated": False, "hardware_validated": False}
    hmi = WifiHmi("http://192.168.1.138:8080", token, report["commands"], via_wsl=True)
    try:
        report["before"] = hmi.status()
        if not safe_disarmed(report["before"]):
            raise RuntimeError("Working-point capture requires fresh disarmed SAFE status")
        hmi.post("/api/stop-sequence", {"emergency": False}, "measurement-only STOP")
        hmi.command("CLEAR")
        report["after_clear"] = wait_status(
            hmi, lambda s: safe_disarmed(s) and s.get("bp_fault") == 0
            and s.get("bp_bad") == 0 and s.get("bp_bad_cnt") == 0,
            10, "fault-free working point with outputs off")
        report["capture_response"] = hmi.post(
            "/api/calibration/vbus", {"action": "capture", "meter_vdc": args.meter_vdc},
            "measurement-only Vbus capture")
        report["after_capture"] = hmi.status()
        report["pass"] = (safe_disarmed(report["after_capture"])
                          and report["after_capture"].get("hmi_vbus_hv_calibrated") == 1)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        code, response = hmi.fail_safe_stop()
        report["final_stop"] = {"http": code, "ok": response.get("ok"),
                                "error": response.get("error")}
        try:
            report["final_status"] = hmi.status()
            report["pass"] = (report["pass"] and safe_disarmed(report["final_status"])
                              and code == 200 and response.get("ok") is True)
        except Exception as exc:
            report["final_status_error"] = str(exc)
            report["pass"] = False
        try:
            (out / "wifi_logs.txt").write_text(get_wifi_logs(hmi, token), encoding="utf-8")
        except Exception as exc:
            report["log_error"] = str(exc)
            report["pass"] = False
        hmi.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("pass", "meter_vdc", "error")}, indent=2), flush=True)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

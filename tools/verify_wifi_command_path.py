#!/usr/bin/env python3
"""Verify safe Wi-Fi command routing with a physically disconnected DC bus."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from collect_wifi_telemetry import get_logs, read_token, validate_url
from run_wifi_nucleo_pwm_bench import WifiHmi


def get_wifi_logs(hmi: WifiHmi, token: str) -> str:
    if not getattr(hmi, "via_wsl", False):
        return get_logs(hmi.opener, hmi.base, token, 1.0)
    code, text = hmi._request_via_wsl(
        "GET", "/api/logs?hours=1.000", {"X-UNOQ-Control-Token": token},
        None, response_format="text",
    )
    if code != 200 or not isinstance(text, str):
        raise RuntimeError(f"Wi-Fi log download failed: HTTP {code}")
    return text


def safe_off(status: dict) -> bool:
    try:
        vdc = status["vdc"]
        flags = status["bp_status"]
        age = status["bp_age_ms"]
        return (
            type(vdc) in (int, float) and math.isfinite(vdc) and 0 <= vdc <= 2
            and type(flags) is int and (flags & 0x22) == 0
            and status["state"] == "SAFE" and type(status["pwm"]) is int
            and status["pwm"] == 0 and type(status["hmi_hv_armed"]) is int
            and status["hmi_hv_armed"] == 0 and status["bp_fault"] == 5
            and status["precharge"] == 0 and type(status["bp_ext"]) is int
            and (status["bp_ext"] & 0x08) == 0
            and type(age) in (int, float) and math.isfinite(age) and 0 <= age < 300
        )
    except (KeyError, TypeError, ValueError):
        return False


def verify(hmi: WifiHmi, token: str, outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=False)
    result = {
        "schema": "mic_ai.wifi_safe_command_path.v1",
        "host_utc": datetime.now(timezone.utc).isoformat(),
        "pass": False,
        "checks": {},
        "commands": [],
        "transport": "wsl_nat_wifi_http" if getattr(hmi, "via_wsl", False) else "direct_wifi_http",
    }
    began = False
    before_logs = ""
    try:
        before = hmi.status()
        result["before"] = before
        if not safe_off(before):
            raise RuntimeError("Expected fresh SAFE, zero-bus, fault=5 and disarmed state")
        before_logs = get_wifi_logs(hmi, token)
        began = True
        for command, expected in (("MODE VF", None), ("SET FREQ 5", 5.0),
                                  ("SET FREQ 20", 20.0), ("SET FREQ 0", 0.0)):
            code, response = hmi.request("POST", "/api/cmd", {"cmd": command})
            status = hmi.status()
            result["commands"].append({
                "command": command, "http_status": code, "ok": response.get("ok"),
                "freq_cmd": status.get("freq_cmd"), "safe_off": safe_off(status),
            })
            if code != 200 or response.get("ok") is not True or not safe_off(status):
                raise RuntimeError(f"Safe Wi-Fi command rejected or outputs enabled: {command}")
            if status.get("mode") != "VF":
                raise RuntimeError(f"VF mode was not reflected in telemetry: {command}")
            if expected is not None and abs(float(status.get("freq_cmd", -999)) - expected) > 0.1:
                raise RuntimeError(f"Frequency setpoint not reflected in telemetry: {command}")
        code, response = hmi.request("POST", "/api/start-sequence", {})
        result["start_rejected"] = {"http_status": code, "error": response.get("error")}
        result["checks"]["zero_bus_start_rejected"] = code == 409 and response.get("ok") is False
        if not result["checks"]["zero_bus_start_rejected"]:
            raise RuntimeError("START was not rejected by the live zero-bus guard")
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if began:
            code, response = hmi.fail_safe_stop()
            result["stop"] = {"http_status": code, "ok": response.get("ok")}
            try:
                after = hmi.status()
                result["after"] = after
                result["checks"]["final_stop_confirmed"] = (
                    code == 200 and response.get("ok") is True and safe_off(after)
                    and abs(float(after.get("freq_cmd", -999))) <= 0.1
                )
            except Exception as exc:
                result["final_error"] = f"{type(exc).__name__}: {exc}"
                result["checks"]["final_stop_confirmed"] = False
        try:
            logs = get_wifi_logs(hmi, token)
            (outdir / "logs.txt").write_text(logs, encoding="utf-8")
            result["checks"]["commands_in_wifi_log"] = (
                logs.count("WIFI_START_REJECT") > before_logs.count("WIFI_START_REJECT")
                and logs.count("WIFI_STOP_SEQUENCE") > before_logs.count("WIFI_STOP_SEQUENCE")
                and all(logs.count(f"CMD {command}") > before_logs.count(f"CMD {command}")
                        for command in ("MODE VF", "SET FREQ 5", "SET FREQ 20", "SET FREQ 0"))
            )
        except Exception as exc:
            result["log_error"] = f"{type(exc).__name__}: {exc}"
            result["checks"]["commands_in_wifi_log"] = False
        result["pass"] = (
            len(result["commands"]) == 4 and all(result["checks"].values())
            and "error" not in result and "final_error" not in result
        )
        (outdir / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://192.168.1.138:8080")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--via-wsl", action="store_true", help="Use WSL LAN HTTP, not ADB forwarding")
    parser.add_argument("--confirm-j7-disconnected", action="store_true")
    parser.add_argument("--confirm-motor-disconnected", action="store_true")
    parser.add_argument("--confirm-dc-below-2v", action="store_true")
    args = parser.parse_args()
    if not (args.confirm_j7_disconnected and args.confirm_motor_disconnected and args.confirm_dc_below_2v):
        parser.error("Physical J7, motor and DC-bus confirmations are required")
    try:
        base = validate_url(args.url)
        token = read_token(args.token_file)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    hmi = WifiHmi(base, token, [], via_wsl=args.via_wsl)
    try:
        result = verify(hmi, token, args.outdir.resolve())
    finally:
        hmi.close()
    print(json.dumps({key: result.get(key) for key in ("pass", "checks", "commands", "error")}, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

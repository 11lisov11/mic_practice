"""Check production command guards on an isolated, zero-bus bench; never ARM."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from run_wifi_nucleo_pwm_bench import WifiHmi, read_control_token, wait_status
from verify_wifi_command_path import get_wifi_logs, safe_off


def production_off(status: dict) -> bool:
    return (safe_off(status) and status.get("mode") == "VF"
            and status.get("fw_build") == 2026092901
            and status.get("mc_fw_build") == 2026100601
            and status.get("hmi_arm_profile") == "hv")


def case_pass(code: int, response: dict, status: dict, kind: str,
              expected_freq: float) -> bool:
    if not production_off(status):
        return False
    try:
        freq = float(status["freq_cmd"])
        if not math.isfinite(freq) or abs(freq - expected_freq) > 0.1:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    if kind == "accepted":
        return code == 200 and response.get("ok") is True
    if kind == "auth":
        return code == 401 and response.get("ok") is False
    if kind == "start":
        return (code == 409 and response.get("ok") is False
                and "mc_fault=5" in str(response.get("error", "")))
    if kind == "nonfinite":
        return (400 <= code < 600 and response.get("ok") is False
                and response.get("error") == "rejected")
    return False


def verify(hmi, unauthenticated, token: str, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    report = {"schema": "mic_ai.production_guard_semantics.v1", "pass": False,
              "host_utc": datetime.now(timezone.utc).isoformat(), "cases": [],
              "scope": "production no ARM, no flash, zero bus; not active V/f validation",
              "transport": "wsl_nat_wifi_http" if hmi.via_wsl else "direct_wifi_http"}
    began = False
    try:
        before = hmi.status()
        report["before"] = before
        before_freq = float(before.get("freq_cmd", float("nan")))
        if not production_off(before) or not math.isfinite(before_freq) or abs(before_freq) > 0.1:
            raise RuntimeError("Expected known production images, fresh SAFE/disarmed/VF/zero bus")
        began = True
        cases = [
            ("unauthenticated_frequency", unauthenticated, "/api/cmd", {"cmd": "SET FREQ 5"}, "auth", 0),
            ("FOC_coerced_to_VF", hmi, "/api/cmd", {"cmd": "MODE FOC"}, "accepted", 0),
            ("upper_frequency_clamp", hmi, "/api/cmd", {"cmd": "SET FREQ 100000"}, "accepted", 50),
            ("negative_frequency_clamp", hmi, "/api/cmd", {"cmd": "SET FREQ -1"}, "accepted", 0),
            ("NaN_rejected", hmi, "/api/cmd", {"cmd": "SET FREQ nan"}, "nonfinite", 0),
            ("infinity_rejected", hmi, "/api/cmd", {"cmd": "SET FREQ inf"}, "nonfinite", 0),
            ("zero_bus_START_rejected", hmi, "/api/cmd", {"cmd": "START"}, "start", 0),
            ("zero_bus_sequence_rejected", hmi, "/api/start-sequence", {}, "start", 0),
        ]
        for name, client, path, body, kind, freq in cases:
            code, response = client.request("POST", path, body)
            status = wait_status(hmi, lambda s: production_off(s)
                                 and abs(float(s.get("freq_cmd", -999)) - freq) <= 0.1,
                                 3, name + " telemetry")
            entry = {"name": name, "http_status": code, "response": response,
                     "expected_frequency_hz": freq, "status": status,
                     "pass": case_pass(code, response, status, kind, freq)}
            report["cases"].append(entry)
            if not entry["pass"]:
                raise RuntimeError("Guard semantics failed: " + name)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if began:
            code, response = hmi.fail_safe_stop()
            report["stop"] = {"http_status": code, "ok": response.get("ok")}
            try:
                report["after"] = wait_status(
                    hmi, lambda s: production_off(s) and abs(float(s.get("freq_cmd", -999))) <= 0.1,
                    3, "final production STOP")
                report["final_safe"] = code == 200 and response.get("ok") is True
            except Exception as exc:
                report["stop_error"] = f"{type(exc).__name__}: {exc}"
            try:
                (out / "logs.txt").write_text(get_wifi_logs(hmi, token), encoding="utf-8")
                report["logs_downloaded"] = True
            except Exception as exc:
                report["log_error"] = f"{type(exc).__name__}: {exc}"
        report["pass"] = (len(report["cases"]) == 8 and all(c["pass"] for c in report["cases"])
                          and report.get("final_safe") is True
                          and report.get("logs_downloaded") is True and "error" not in report)
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-isolated-zero-bus", action="store_true")
    parser.add_argument("--via-wsl", action="store_true")
    parser.add_argument("--url", default="http://192.168.1.138:8080")
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_isolated_zero_bus:
        parser.error("Disconnected mains/DC source, motor and J4, measured DC below 2 V required")
    token = read_control_token("adb", "3880458060", "/home/arduino/.config/mic-ai/control_token")
    hmi = WifiHmi(args.url, token, [], via_wsl=args.via_wsl)
    unauthenticated = WifiHmi(args.url, "", [], via_wsl=args.via_wsl)
    try:
        report = verify(hmi, unauthenticated, token, args.outdir.resolve())
    finally:
        hmi.close()
        unauthenticated.close()
    print(json.dumps({"pass": report["pass"], "error": report.get("error"),
                      "cases": [{k: c[k] for k in ("name", "http_status", "pass")}
                                for c in report["cases"]]}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

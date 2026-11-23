"""Concurrent Wi-Fi reads/setpoints/STOP, always disarmed and with PWM off."""
import argparse
import json
import math
from pathlib import Path
import threading
import time

from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi
from verify_wifi_command_path import get_wifi_logs


def off_status(s, uno_build=2026101002):
    try:
        return (s.get("state") == "SAFE" and s.get("pwm") == 0
                and s.get("hmi_hv_armed") == 0
                and (s.get("fw_build"), s.get("mc_fw_build")) == (uno_build, 2026100801)
                and s.get("bp_vbus_valid") == 1
                and math.isfinite(s["vdc"]) and 0 <= s["vdc"] <= 2
                and 0 <= s["bp_vbus_raw"] <= 20
                and 0 <= s["mc_age_ms"] < 300
                and 0 <= s["bp_vbus_age_ms"] < 300
                and not (s["bp_status"] & 0x22)
                and s.get("hmi_vbus_hv_calibrated") == 1
                and all(s.get(k) == 0 for k in ("precharge", "pfc", "brake", "bp_ext")))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-hv-off", action="store_true")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--uno-build", type=int, choices=(2026101001, 2026101002), default=2026101002)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_hv_off or not 5 <= args.rounds <= 50:
        parser.error("physical power-off confirmation and 5..50 rounds required")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"pass": False, "scope": "idle concurrent HTTP/RPC/loop ownership; no powered PWM",
              "arm_commands": 0, "start_commands": 0, "commands": [], "samples": [],
              "observer_errors": [], "hv_release_approved": False}
    token = read_token(args.token_file)
    command_hmi = WifiHmi("http://192.168.1.138:8080", token, report["commands"], via_wsl=True)
    observer_hmi = WifiHmi("http://192.168.1.138:8080", "", [], via_wsl=True)
    stop = threading.Event()
    observer = None

    def observe():
        try:
            while not stop.is_set():
                s = observer_hmi.status()
                report["samples"].append(s)
                if not off_status(s, args.uno_build):
                    raise RuntimeError("idle safety/state gate changed")
                if stop.wait(.1):
                    break
        except Exception as exc:
            report["observer_errors"].append(f"{type(exc).__name__}: {exc}")
            stop.set()

    try:
        before = command_hmi.status()
        report["before"] = before
        if not off_status(before, args.uno_build):
            raise RuntimeError("discharged/disarmed production pair required")
        baseline = {k: before[k] for k in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence")}
        if any(baseline.values()):
            raise RuntimeError("nonzero initial transport counters")
        observer = threading.Thread(target=observe)
        observer.start()
        began = time.monotonic()
        for _ in range(args.rounds):
            for command in ("SET FREQ 5", "SET FREQ 20", "SET FREQ 0", "STOP"):
                if stop.is_set():
                    raise RuntimeError("observer stopped qualification")
                if not off_status(command_hmi.status(), args.uno_build):
                    raise RuntimeError("idle gate failed before command")
                command_hmi.command(command)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if stop.wait(.1):
                raise RuntimeError("observer stopped final window")
        report["duration_s"] = round(time.monotonic() - began, 3)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        stop.set()
        if observer:
            observer.join()
        observer_hmi.close()
        code, response = command_hmi.fail_safe_stop()
        report["final_stop"] = {"http": code, "ok": response.get("ok") is True}
        try:
            after = command_hmi.status()
            report["after"] = after
            rows = [report.get("before", {}), *report["samples"], after]
            report["all_observed_outputs_off"] = all(off_status(s, args.uno_build) for s in rows)
            report["no_new_transport_errors"] = all(
                s.get(k) == 0 for s in rows
                for k in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence"))
            report["new_uno_received_messages"] = after["uno_rx_count"] - report["before"]["uno_rx_count"]
            report["max_observed_uart_age_ms"] = max(s["mc_age_ms"] for s in rows)
            report["pass"] = ("error" not in report and not report["observer_errors"]
                              and len(report["samples"]) >= 10 and report["all_observed_outputs_off"]
                              and report["no_new_transport_errors"] and report["new_uno_received_messages"] > 0
                              and code == 200 and response.get("ok") is True)
            (out / "wifi_logs.txt").write_text(get_wifi_logs(command_hmi, token), encoding="utf-8")
        except Exception as exc:
            report["pass"] = False
            report["final_error"] = f"{type(exc).__name__}: {exc}"
        command_hmi.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in (
        "pass", "error", "final_error", "duration_s", "new_uno_received_messages",
        "max_observed_uart_age_ms", "no_new_transport_errors", "all_observed_outputs_off")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Record read-only UNO Q service checks; never issue a motor command."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--expect-uart", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.samples <= 120:
        parser.error("samples must be between 1 and 120")
    repo = Path(__file__).resolve().parents[1]
    package = repo / "firmware" / "ready_to_flash"

    def shell(command: str) -> str:
        return subprocess.check_output(
            ["adb", "-s", args.device, "shell", command],
            text=True, encoding="utf-8", timeout=15,
        ).strip()

    samples = []
    for i in range(args.samples):
        sample = json.loads(shell("curl -fsS --max-time 8 http://127.0.0.1:8080/api/status"))
        sample["host_utc"] = datetime.now(timezone.utc).isoformat()
        samples.append(sample)
        if i + 1 < args.samples:
            time.sleep(1)
    data = [s.get("data", {}) for s in samples]
    account_status = shell("LC_ALL=C chage -l arduino")
    cron = shell("crontab -l")
    cron_active = shell("systemctl is-active cron 2>/dev/null || true")
    hmi_service_active = shell("systemctl is-active unoq-hmi.service 2>/dev/null || true")
    hmi_service_enabled = shell("systemctl is-enabled unoq-hmi.service 2>/dev/null || true")
    hmi_cron_present = "/home/arduino/bin/start_unoq_hmi.sh" in cron
    systemd_autostart = hmi_service_active == "active" and hmi_service_enabled == "enabled"
    cron_autostart = hmi_cron_present and cron_active == "active"
    checks = {
        "linux_mcu_rpc_all_samples": all(s.get("ok") is True for s in samples),
        "state_safe_all_samples": all(d.get("state") == "SAFE" for d in data),
        "pwm_disabled_all_samples": all(d.get("pwm") == 0 for d in data),
        "mode_vf_all_samples": all(d.get("mode") == "VF" for d in data),
        "rpc_schema_v3_all_samples": all(d.get("rpc_schema_version") == 3 for d in data),
        "nucleo_build_identity_all_samples": all(d.get("mc_fw_build", 0) > 0 for d in data),
        "relay_disabled_all_samples": all(d.get("precharge") == 0 for d in data),
        "hv_unarmed_all_samples": all(d.get("hmi_hv_armed") == 0 for d in data),
        "hmi_auth_enabled_all_samples": all(d.get("hmi_control_auth_required") == 1 for d in data),
        "cron_account_first_setup_complete": "password must be changed" not in account_status.lower(),
        "hmi_autostart_configured": systemd_autostart or cron_autostart,
        "hmi_autostart_not_duplicated": not (systemd_autostart and hmi_cron_present),
    }
    uart_live = all(d.get("mc_good", 0) > 0 and d.get("mc_age_ms", 999999) < 300 for d in data)
    if args.expect_uart:
        checks["uart_live_all_samples"] = uart_live

    hashes = {}
    remote = "/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi"
    for name in ("server.py", "requirements.txt", "static/index.html", "static/app.js", "static/style.css"):
        expected = hashlib.sha256((package / "linux" / "web_hmi" / name).read_bytes()).hexdigest()
        actual = shell(f"sha256sum {remote}/{name}").split()[0]
        hashes[name] = {"expected": expected, "actual": actual, "match": expected == actual}
    checks["deployed_hmi_matches_package"] = all(h["match"] for h in hashes.values())
    report = {
        "schema": "mic_ai.board_bringup_readonly.v1",
        "host_utc": datetime.now(timezone.utc).isoformat(),
        "device": args.device,
        "board_utc": shell("date -u +%Y-%m-%dT%H:%M:%SZ"),
        "board_uptime": shell("cat /proc/uptime"),
        "account_status": account_status,
        "cron": cron,
        "cron_active": cron_active,
        "hmi_service_active": hmi_service_active,
        "hmi_service_enabled": hmi_service_enabled,
        "hmi_autostart_backend": "systemd" if systemd_autostart else ("cron" if cron_autostart else "none"),
        "ip_addresses": shell("hostname -I"),
        "checks": checks,
        "pass": all(checks.values()),
        "uart_expected": args.expect_uart,
        "uart_observed_live": uart_live,
        "hardware_drive_validated": False,
        "motor_commands_sent": [],
        "hmi_hashes": hashes,
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("pass", "checks", "uart_expected", "uart_observed_live", "board_utc", "host_utc")}, indent=2))
    print(f"Report: {args.output.resolve()}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

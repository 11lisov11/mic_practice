"""Install the manual-start UI gate fix without changing the server or MCU firmware."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from collect_wifi_telemetry import get_status

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261017/manual_scalar_hmi_simplified_r1"
CANDIDATE = BASE / "web_hmi/static/app.js"
OUT = ROOT / "artifacts/live_bench_20261017/manual_scalar_start_gate_fix_r1"
REMOTE_ROOT = "/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/static"
REMOTE_APP = REMOTE_ROOT + "/app.js"
REMOTE_STAGE = REMOTE_ROOT + "/manual_start_gate_fix_r1.staged"
REMOTE_BACKUP = REMOTE_ROOT + "/app.js.before_manual_start_gate_fix_r1"
EXPECTED_REMOTE_SHA = "e1ac6d71bc42a3128ba821bba1e5437e9ca673981f8d2ccacee5abd2c39851b3"
BASE_URL = "http://192.168.1.138:8080"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args: list[str], label: str, source: str | None = None) -> str:
    result = subprocess.run(args, input=source, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=40)
    (OUT / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{label} failed; see {OUT / (label + '.log')}")
    return result.stdout


def healthy_idle_status() -> dict:
    status = get_status(build_opener(ProxyHandler({})), BASE_URL)
    checks = {
        "matching_manual_pair": (status.get("fw_build"), status.get("mc_fw_build")) == (2026101507, 2026101506),
        "safe_outputs_off": status.get("state") == "SAFE" and status.get("pwm") == 0 and status.get("estop") == 0,
        "no_driver_or_uart_fault": status.get("mc_fault") == 0 and status.get("bp_fault") == 0
            and status.get("mc_bad_cnt") == 0 and status.get("bp_bad_cnt") == 0
            and status.get("mc_uart_error_flags") == 0 and status.get("bp_uart_error_flags") == 0,
        "fresh_communication": 0 <= status.get("bp_age_ms", 999999) < 300
            and 0 <= status.get("mc_age_ms", 999999) < 300,
        "manual_authenticated_hv_profile": status.get("hmi_manual_scalar_supported") == 1
            and status.get("hmi_control_auth_required") == 1
            and status.get("hmi_hv_enabled") == 1 and status.get("hmi_arm_profile") == "hv",
        "disarmed_and_calibrated": status.get("hmi_hv_armed") == 0 and status.get("hmi_hv_started") == 0
            and status.get("hmi_vbus_hv_calibrated") == 1,
        "normal_dc_and_temperature": 280 <= status.get("vdc", -1) <= 360
            and status.get("mc_temp_valid") == 1 and 0 <= status.get("mc_temp_c", 999) < 70
            and status.get("mc_temp_fault") == 0,
        "no_break_or_transport_fault": not (status.get("bp_status", 0) & 0x22)
            and status.get("bp_transport_fault") == 0,
    }
    if not all(checks.values()):
        raise RuntimeError("Live idle precheck failed: " + json.dumps(checks, sort_keys=True))
    return status


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    candidate = CANDIDATE.read_text(encoding="utf-8")
    assert "return basicStartReady && (!standaloneHv || isHvArmed || manualScalarSupported);" in candidate
    assert "startBtn.disabled = !manualStartAllowed(data, hvArmed);" in candidate
    candidate_sha = sha(CANDIDATE)
    before = healthy_idle_status()
    (OUT / "status_before.json").write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")

    ssh = ["ssh", "-p", "2222", "-i", str(ROOT / ".unoq_ssh/id_ed25519"),
           "-o", "UserKnownHostsFile=" + str(ROOT / ".unoq_ssh/known_hosts"),
           "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
           "arduino@192.168.1.138"]
    scp = ["scp", "-P", "2222", "-i", str(ROOT / ".unoq_ssh/id_ed25519"),
           "-o", "UserKnownHostsFile=" + str(ROOT / ".unoq_ssh/known_hosts"),
           "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes"]
    precheck = f'''from pathlib import Path
import hashlib, os, subprocess
target=Path({REMOTE_APP!r}); stage=Path({REMOTE_STAGE!r}); backup=Path({REMOTE_BACKUP!r})
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert target.is_file() and digest(target)=={EXPECTED_REMOTE_SHA!r}, "live app.js changed; refusing deployment"
assert not stage.exists() and not backup.exists(), "staging or backup path already exists"
st=subprocess.check_output(["systemctl","is-active","unoq-hmi.service"],text=True).strip()
assert st=="active", "HMI service is not active"
print("live HMI source and staging paths verified")
'''
    run(ssh + ["/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -"], "remote_precheck", precheck)
    run(scp + [str(CANDIDATE), "arduino@192.168.1.138:" + REMOTE_STAGE], "stage_app_js")

    # Recheck drive state immediately before the atomic static-asset swap.
    before_swap = healthy_idle_status()
    assert before_swap.get("state") == "SAFE" and before_swap.get("pwm") == 0
    install = f'''from pathlib import Path
import hashlib, os, shutil
target=Path({REMOTE_APP!r}); stage=Path({REMOTE_STAGE!r}); backup=Path({REMOTE_BACKUP!r})
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(target)=={EXPECTED_REMOTE_SHA!r} and digest(stage)=={candidate_sha!r}
shutil.copy2(target,backup)
assert digest(backup)=={EXPECTED_REMOTE_SHA!r}
stage.chmod(target.stat().st_mode)
os.replace(stage,target)
assert digest(target)=={candidate_sha!r}
print("manual-start UI gate installed atomically; server and MCU untouched")
'''
    run(ssh + ["/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -"], "install_app_js", install)
    after = healthy_idle_status()
    assert after.get("state") == "SAFE" and after.get("pwm") == 0 and after.get("hmi_hv_armed") == 0
    (OUT / "status_after.json").write_text(json.dumps(after, indent=2) + "\n", encoding="utf-8")

    report = {
        "pass": True,
        "installed": True,
        "previous_app_js_sha256": EXPECTED_REMOTE_SHA,
        "installed_app_js_sha256": candidate_sha,
        "changed_files": ["web_hmi/static/app.js"],
        "server_changed": False,
        "mcu_firmware_writes": 0,
        "motor_commands": 0,
        "calibration_changed": False,
        "fault_clear_commands": 0,
        "before": {key: before.get(key) for key in ("state", "pwm", "vdc", "mc_temp_c", "mc_fault", "bp_fault", "hmi_hv_armed")},
        "after": {key: after.get(key) for key in ("state", "pwm", "vdc", "mc_temp_c", "mc_fault", "bp_fault", "hmi_hv_armed")},
        "remote_backup": REMOTE_BACKUP,
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

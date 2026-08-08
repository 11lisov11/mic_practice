#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_URL = "http://192.168.1.138:8080"
DEFAULT_REMOTE = "/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi"
VBUS_RAW_MIN_VALID = 1
VBUS_RAW_ZERO_MAX = 400
VBUS_RAW_MAX_VALID = 4094


def log(message: str) -> None:
    print(message, flush=True)


def run(command: list[str]) -> None:
    log("RUN " + " ".join(command))
    subprocess.run(command, check=True)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def fetch_status(base_url: str, timeout: float = 5.0) -> dict:
    request = urllib.request.Request(base_url.rstrip("/") + "/api/status", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("ok") is not True or not isinstance(payload.get("data"), dict):
        raise RuntimeError(payload.get("error") or "UNO Q status is unavailable")
    return payload["data"]


def safe_for_update(status: dict, max_vdc: float) -> tuple[bool, str]:
    if str(status.get("state", "")).upper() != "SAFE":
        return False, f"state={status.get('state')}"
    for key in ("pwm", "estop", "precharge", "pfc", "brake", "bp_fault"):
        try:
            value = int(status.get(key, 0) or 0)
        except (TypeError, ValueError):
            return False, f"{key} telemetry is invalid"
        if value != 0:
            return False, f"{key}={status.get(key)}"
    try:
        bad = max(int(status.get("bp_bad", 0) or 0), int(status.get("bp_bad_cnt", 0) or 0))
    except (TypeError, ValueError):
        return False, "Blue Pill error counter is invalid"
    if bad != 0:
        return False, f"bp_bad={bad}"
    if status.get("link") is False:
        return False, "Blue Pill link is down"
    ages: list[float] = []
    for key in ("bp_rsp_age_ms", "bp_age_ms"):
        try:
            age = float(status[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(age):
            ages.append(age)
    if not ages or min(ages) > 1000.0:
        return False, "Blue Pill link is stale"
    vdc_values: list[float] = []
    for key in ("vdc", "bp_vdc"):
        try:
            value = float(status[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and value >= 0.0:
            vdc_values.append(value)
    if not vdc_values:
        return False, "DC bus telemetry is unavailable"
    vdc = max(vdc_values)
    if vdc > max_vdc:
        return False, f"vdc={vdc:.1f} V exceeds update limit {max_vdc:.1f} V"
    try:
        raw_age_ms = float(status["bp_vbus_age_ms"])
        raw = int(status["bp_vbus_raw"])
    except (KeyError, TypeError, ValueError):
        return False, "raw DC bus telemetry is unavailable"
    if not math.isfinite(raw_age_ms) or raw_age_ms > 1000.0:
        return False, "raw DC bus telemetry is stale"
    if raw < VBUS_RAW_MIN_VALID or raw > VBUS_RAW_MAX_VALID:
        return False, f"raw DC bus telemetry is invalid: raw={raw}"
    if max_vdc <= 10.0 and raw > VBUS_RAW_ZERO_MAX:
        return False, f"raw DC bus is not in the zero-bus range: raw={raw}"
    return True, "ok"


def ssh_base(host: str, port: int, user: str, key: Path) -> list[str]:
    return [
        "ssh",
        "-i",
        str(key),
        "-p",
        str(port),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{user}@{host}",
    ]


def scp_base(host: str, port: int, user: str, key: Path) -> list[str]:
    return [
        "scp",
        "-i",
        str(key),
        "-P",
        str(port),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy UNO Q HMI over key-authenticated Wi-Fi SSH.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--host", default="", help="UNO Q address; defaults to the host from --url")
    parser.add_argument("--user", default="arduino")
    parser.add_argument("--ssh-port", type=int, default=2222)
    parser.add_argument("--key", default=".unoq_ssh/id_ed25519")
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--max-vdc", type=float, default=10.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    parsed = urlparse(args.url)
    host = args.host.strip() or str(parsed.hostname or "")
    if not host:
        raise SystemExit("ERROR: UNO Q host is missing")
    key = Path(args.key)
    if not key.exists():
        raise SystemExit(f"ERROR: SSH key not found: {key}; run the one-time ADB bootstrap first")

    status = fetch_status(args.url)
    safe, reason = safe_for_update(status, args.max_vdc)
    if not safe:
        raise SystemExit(f"ERROR: Wi-Fi deploy refused: {reason}")
    log(f"SAFE update gate: {reason}")
    if args.dry_run:
        log("DRY-RUN complete; no files changed")
        return 0

    repo = Path(__file__).resolve().parents[1]
    local = repo / "web_hmi"
    files = [
        local / "server.py",
        local / "requirements.txt",
        local / "flash_unoq_sketch_090.cfg",
        local / "static" / "index.html",
        local / "static" / "app.js",
        local / "static" / "style.css",
    ]
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise SystemExit("ERROR: missing HMI files: " + ", ".join(missing))

    stamp = int(time.time())
    staging = f"/tmp/unoq_hmi_update_{stamp}"
    ssh = ssh_base(host, args.ssh_port, args.user, key)
    scp = scp_base(host, args.ssh_port, args.user, key)
    run(ssh + [f"mkdir -p {shell_quote(staging + '/static')}"])
    run(
        scp
        + [
            str(local / "server.py"),
            str(local / "requirements.txt"),
            str(local / "flash_unoq_sketch_090.cfg"),
            f"{args.user}@{host}:{staging}/",
        ]
    )
    run(
        scp
        + [
            str(local / "static" / "index.html"),
            str(local / "static" / "app.js"),
            str(local / "static" / "style.css"),
            f"{args.user}@{host}:{staging}/static/",
        ]
    )

    remote = shell_quote(args.remote)
    install = (
        "set -eu; "
        f"cd {shell_quote(staging)}; python3 -m py_compile server.py; "
        f"mkdir -p {remote}/static {remote}/logs; "
        f"install -m 0644 server.py requirements.txt flash_unoq_sketch_090.cfg {remote}/; "
        f"install -m 0644 static/index.html static/app.js static/style.css {remote}/static/; "
        f"rm -rf {shell_quote(staging)}; "
        "if sudo -n systemctl restart unoq-hmi.service >/dev/null 2>&1; then :; "
        "else pid=\"$(ss -ltnp 2>/dev/null | sed -n 's/.*:8080 .*pid=\\([0-9]\\+\\).*/\\1/p' | head -n 1)\"; "
        "test -n \"$pid\" && kill \"$pid\"; fi"
    )
    run(ssh + [install])

    last_error = "server did not return"
    for _ in range(30):
        time.sleep(0.25)
        try:
            final_status = fetch_status(args.url, timeout=2.0)
            final_safe, final_reason = safe_for_update(final_status, args.max_vdc)
            if final_safe:
                log("DONE: HMI updated over Wi-Fi and returned SAFE")
                return 0
            last_error = final_reason
        except Exception as exc:
            last_error = str(exc)
    log(f"ERROR: HMI update verification failed: {last_error}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    raise SystemExit(main())

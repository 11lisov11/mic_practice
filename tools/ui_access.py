#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str]) -> None:
    log("RUN " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def probe_url(url: str, timeout_s: float = 2.0, attempts: int = 10, delay_s: float = 0.25) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(attempts):
        try:
            with opener.open(url, timeout=timeout_s) as resp:
                if 200 <= getattr(resp, "status", 200) < 500:
                    return True
        except Exception:
            pass
        if attempt + 1 < attempts:
            time.sleep(delay_s)
    return False


def start_adb_server() -> None:
    try:
        run(["adb", "start-server"])
    except Exception as exc:
        log(f"WARN: adb start-server failed: {exc}")


def unoq_pnp_rows() -> list[dict]:
    ps = (
        "Get-PnpDevice | "
        "Where-Object { $_.InstanceId -like '*VID_2341&PID_0078*' } | "
        "Select-Object Status,Class,FriendlyName,InstanceId,Present,Problem | "
        "ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return []
    if not out:
        return []
    try:
        data = json.loads(out)
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def report_unoq_pnp() -> None:
    rows = unoq_pnp_rows()
    if not rows:
        log("UNO Q USB: Windows does not currently enumerate VID_2341&PID_0078")
        return
    present_rows = [row for row in rows if row.get("Present")]
    if present_rows:
        log("UNO Q USB: device is present in Windows, but ADB is not ready")
    else:
        log("UNO Q USB: only phantom records are present; board is disconnected or USB enumeration is broken")
    for row in rows:
        log(
            "  "
            + f"{row.get('FriendlyName', '?')} "
            + f"status={row.get('Status')} present={row.get('Present')} "
            + f"problem={row.get('Problem')} id={row.get('InstanceId')}"
        )


def adb_device_ids() -> list[str]:
    try:
        out = subprocess.check_output(["adb", "devices"], text=True)
    except Exception:
        return []
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    devices: list[str] = []
    for ln in lines[1:]:
        if ln.endswith("\tdevice"):
            devices.append(ln.split("\t")[0])
    return devices


def detect_device() -> str | None:
    for device in adb_device_ids():
        # Android emulators are common on dev PCs and are never the UNO Q target.
        if device.startswith("emulator-"):
            continue
        return device
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="ADB forward + optional HTTP bridge for UNOQ UI.")
    ap.add_argument("--device", default="", help="ADB device id (default: auto-detect)")
    ap.add_argument("--forward-port", type=int, default=18080)
    ap.add_argument("--remote-port", type=int, default=8080)
    ap.add_argument("--bridge", action="store_true", help="Expose UI to LAN via HTTP bridge")
    ap.add_argument("--bridge-port", type=int, default=8080)
    ap.add_argument("--probe-timeout", type=float, default=2.0)
    ap.add_argument("--probe-attempts", type=int, default=10)
    args = ap.parse_args()

    start_adb_server()
    device = args.device or detect_device()
    if not device:
        devices = adb_device_ids()
        if devices:
            log("ERROR: no non-emulator ADB device found. Use --device only if this is intentionally the UNO Q.")
            log("ADB devices: " + ", ".join(devices))
        else:
            log("ERROR: ADB device not found. Use --device.")
        report_unoq_pnp()
        return 2

    run(["adb", "-s", device, "forward", f"tcp:{args.forward_port}", f"tcp:{args.remote_port}"])
    target = f"http://127.0.0.1:{args.forward_port}"
    if not probe_url(target + "/api/status", timeout_s=args.probe_timeout, attempts=args.probe_attempts):
        log(f"ERROR: forward is up but {target}/api/status is not responding")
        return 3
    log(f"PC URL: {target}")

    if not args.bridge:
        return 0

    log(f"LAN bridge: http://<IP_PC>:{args.bridge_port} -> {target}")
    cmd = [
        sys.executable,
        "-u",
        "tools/ui_http_bridge.py",
        "--listen-port",
        str(args.bridge_port),
        "--target",
        target,
    ]
    run(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

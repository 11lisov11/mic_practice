#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], check: bool = True) -> None:
    log("RUN " + " ".join(cmd))
    subprocess.run(cmd, check=check)


def detect_device() -> str | None:
    try:
        out = subprocess.check_output(["adb", "devices"], text=True)
    except Exception:
        return None
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    for ln in lines[1:]:
        if ln.endswith("\tdevice"):
            return ln.split("\t")[0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy UNOQ web_hmi to device via ADB.")
    ap.add_argument("--device", default="", help="ADB device id (default: auto-detect)")
    ap.add_argument("--remote", default="/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi")
    ap.add_argument("--restart", action="store_true", help="Restart server after deploy")
    args = ap.parse_args()

    device = args.device or detect_device()
    if not device:
        log("ERROR: ADB device not found. Use --device.")
        return 2

    local_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web_hmi"))
    if not os.path.isdir(local_root):
        log(f"ERROR: local web_hmi not found: {local_root}")
        return 3

    adb = ["adb", "-s", device]
    run(adb + ["push", os.path.join(local_root, "server.py"), f"{args.remote}/server.py"])
    run(adb + ["push", os.path.join(local_root, "requirements.txt"), f"{args.remote}/requirements.txt"])
    static_dir = os.path.join(local_root, "static")
    for name in ("index.html", "app.js", "style.css"):
        run(adb + ["push", os.path.join(static_dir, name), f"{args.remote}/static/{name}"])

    if args.restart:
        log("Restarting server...")
        run(adb + ["shell", "mkdir -p " + args.remote + "/logs"])
        # Kill by port 8080 first (robust and avoids pkill matching the current shell argv).
        kill_and_start = (
            "sh -lc '"
            "pid=\"$(ss -ltnp 2>/dev/null | sed -n \"s/.*:8080 .*pid=\\([0-9]\\+\\).*/\\1/p\" | head -n 1)\"; "
            "if [ -n \"$pid\" ]; then kill $pid || true; fi; "
            # Wait for the port to be released.
            "for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltnp 2>/dev/null | grep -q \":8080\" || break; sleep 0.2; done; "
            f"cd {args.remote} && nohup ./.venv/bin/python server.py --bind 0.0.0.0 --port 8080 --router /var/run/arduino-router.sock "
            "> logs/server.log 2>&1 & "
            # Wait for the new server to bind.
            "for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltnp 2>/dev/null | grep -q \":8080\" && exit 0; sleep 0.2; done; exit 1'"
        )
        run(adb + ["shell", kill_and_start])
    log("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

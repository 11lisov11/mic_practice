#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str]) -> None:
    log("RUN " + " ".join(cmd))
    subprocess.run(cmd, check=True)


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
    ap = argparse.ArgumentParser(description="ADB forward + optional HTTP bridge for UNOQ UI.")
    ap.add_argument("--device", default="", help="ADB device id (default: auto-detect)")
    ap.add_argument("--forward-port", type=int, default=18080)
    ap.add_argument("--remote-port", type=int, default=8080)
    ap.add_argument("--bridge", action="store_true", help="Expose UI to LAN via HTTP bridge")
    ap.add_argument("--bridge-port", type=int, default=8080)
    args = ap.parse_args()

    device = args.device or detect_device()
    if not device:
        log("ERROR: ADB device not found. Use --device.")
        return 2

    run(["adb", "-s", device, "forward", f"tcp:{args.forward_port}", f"tcp:{args.remote_port}"])
    log(f"PC URL: http://127.0.0.1:{args.forward_port}")

    if not args.bridge:
        return 0

    target = f"http://127.0.0.1:{args.forward_port}"
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

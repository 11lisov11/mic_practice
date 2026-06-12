#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], check: bool = True) -> None:
    log("RUN " + " ".join(cmd))
    subprocess.run(cmd, check=check)


def ok(cmd: list[str]) -> bool:
    log("RUN " + " ".join(cmd))
    return subprocess.run(cmd, check=False).returncode == 0


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
        if device.startswith("emulator-"):
            continue
        return device
    return None


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def ensure_msgpack(adb: list[str], remote: str, local_root: str) -> None:
    check_cmd = f"cd {shell_quote(remote)} && ./.venv/bin/python -c 'import msgpack'"
    if ok(adb + ["shell", check_cmd]):
        return

    pip_cmd = f"cd {shell_quote(remote)} && ./.venv/bin/python -m pip install -r requirements.txt"
    if ok(adb + ["shell", pip_cmd]) and ok(adb + ["shell", check_cmd]):
        return

    cache_dir = Path(local_root).parent / ".cache" / "wheels"
    cache_dir.mkdir(parents=True, exist_ok=True)
    wheels = sorted(cache_dir.glob("msgpack-*-cp313-*-aarch64*.whl"))
    if not wheels:
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--dest",
                str(cache_dir),
                "--only-binary=:all:",
                "--platform",
                "manylinux_2_17_aarch64",
                "--implementation",
                "cp",
                "--python-version",
                "313",
                "--abi",
                "cp313",
                "msgpack",
            ]
        )
        wheels = sorted(cache_dir.glob("msgpack-*-cp313-*-aarch64*.whl"))
    if not wheels:
        raise RuntimeError("msgpack wheel was not downloaded")

    run(adb + ["push", str(wheels[-1]), "/tmp/msgpack.whl"])
    install_cmd = (
        f"cd {shell_quote(remote)} && ./.venv/bin/python - <<'PY'\n"
        "import pathlib\n"
        "import zipfile\n"
        "site = pathlib.Path('./.venv/lib/python3.13/site-packages')\n"
        "site.mkdir(parents=True, exist_ok=True)\n"
        "with zipfile.ZipFile('/tmp/msgpack.whl') as wheel:\n"
        "    wheel.extractall(site)\n"
        "import msgpack\n"
        "print('msgpack', msgpack.__version__)\n"
        "PY"
    )
    run(adb + ["shell", install_cmd])


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy UNOQ web_hmi to device via ADB.")
    ap.add_argument("--device", default="", help="ADB device id (default: auto-detect)")
    ap.add_argument("--remote", default="/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi")
    ap.add_argument("--restart", action="store_true", help="Restart server after deploy")
    args = ap.parse_args()

    device = args.device or detect_device()
    if not device:
        devices = adb_device_ids()
        if devices:
            log("ERROR: no non-emulator ADB device found. Use --device only if this is intentionally the UNO Q.")
            log("ADB devices: " + ", ".join(devices))
        else:
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

    ensure_msgpack(adb, args.remote, local_root)

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

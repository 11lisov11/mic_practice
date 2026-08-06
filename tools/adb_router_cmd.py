#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import subprocess
import sys


DEFAULT_REMOTE_PYTHON = "/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python"


ANDROID_SNIPPET = r"""
import base64, msgpack, socket, sys, time


_unpacker = msgpack.Unpacker(raw=False)


def rpc_call(sock, msgid, method, params, timeout_s=1.5):
    sock.sendall(msgpack.packb([0, msgid, method, params], use_bin_type=False))
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            continue
        if not data:
            raise RuntimeError('router closed')
        _unpacker.feed(data)
        for obj in _unpacker:
            if isinstance(obj, list) and len(obj) >= 4 and obj[0] == 1 and obj[1] == msgid:
                return obj
    raise TimeoutError('router timeout')

if len(sys.argv) >= 2 and sys.argv[1] == '--b64':
    cmds = [base64.b64decode(x.encode('ascii')).decode('utf-8') for x in sys.argv[2:]]
else:
    cmds = sys.argv[1:]
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(1.0)
sock.connect('/var/run/arduino-router.sock')
ok = True
for i, cmd in enumerate(cmds, 1):
    try:
        resp = rpc_call(sock, i, 'cmd', [cmd])
        print(cmd, resp)
        if not (isinstance(resp, list) and len(resp) >= 4 and resp[2] is None and resp[3] is True):
            ok = False
    except Exception as exc:
        print(cmd, 'ERR', repr(exc))
        ok = False
    time.sleep(0.05)
sock.close()
raise SystemExit(0 if ok else 2)
"""


def parse_adb_devices(output: str) -> list[str]:
    devices: list[str] = []
    for raw in output.splitlines():
        fields = raw.strip().split()
        if len(fields) >= 2 and fields[1] == "device":
            devices.append(fields[0])
    return devices


def resolve_adb_device(requested: str) -> str:
    if requested.strip():
        return requested.strip()
    proc = subprocess.run(["adb", "devices"], text=True, capture_output=True, timeout=5)
    if proc.returncode != 0:
        raise RuntimeError(f"adb devices failed: {proc.stderr.strip()}")
    devices = parse_adb_devices(proc.stdout)
    if len(devices) != 1:
        raise RuntimeError(f"expected exactly one ADB device, found {devices}")
    return devices[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Send direct cmd RPC to UNO Q via Android arduino-router.")
    ap.add_argument("--device", default="")
    ap.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    ap.add_argument("cmd", nargs="+")
    args = ap.parse_args()

    try:
        device = resolve_adb_device(args.device)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    encoded = [base64.b64encode(cmd.encode("utf-8")).decode("ascii") for cmd in args.cmd]
    remote_cmd = [args.remote_python, "-", "--b64", *encoded]
    proc = subprocess.run(
        ["adb", "-s", device, "shell", *remote_cmd],
        input=ANDROID_SNIPPET,
        text=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
        timeout=10,
    )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

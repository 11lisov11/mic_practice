#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import subprocess
import sys


ANDROID_SNIPPET = r"""
import base64, socket, sys, time
sys.path.insert(0, '/data/local/tmp')
from router_rpc import rpc_call

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


def main() -> int:
    ap = argparse.ArgumentParser(description="Send direct cmd RPC to UNO Q via Android arduino-router.")
    ap.add_argument("--device", default="79204341")
    ap.add_argument("cmd", nargs="+")
    args = ap.parse_args()

    encoded = [base64.b64encode(cmd.encode("utf-8")).decode("ascii") for cmd in args.cmd]
    remote_cmd = ["python3", "-", "--b64", *encoded]
    proc = subprocess.run(
        ["adb", "-s", args.device, "shell", *remote_cmd],
        input=ANDROID_SNIPPET,
        text=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
        timeout=10,
    )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

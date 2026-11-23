"""Scoped Linux HMI-only recovery when RPC is unavailable on a deenergized stand."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import signal
import subprocess
import time
import uuid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--sha256", required=True)
    p.add_argument("--expected-live-sha256", required=True)
    p.add_argument("--confirm-mains-j4-off", action="store_true")
    p.add_argument("--check-only", action="store_true")
    args = p.parse_args()
    if not args.confirm_mains_j4_off:
        p.error("Physical mains/J4-off and discharged-bus confirmation required; not an online HV updater")
    if os.geteuid() != 1000:
        raise RuntimeError("Expected unprivileged arduino UID")
    root = Path("/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi")
    target = root / "server.py"
    calibration = Path("/home/arduino/.config/mic-ai/vbus_calibration.json")
    original = target.read_bytes()
    if hashlib.sha256(original).hexdigest() != args.expected_live_sha256.lower():
        raise RuntimeError("Unexpected live HMI; refuse replacing unrelated code")
    data = args.candidate.resolve(strict=True).read_bytes()
    if hashlib.sha256(data).hexdigest() != args.sha256.lower():
        raise RuntimeError("Candidate hash mismatch")
    py_compile.compile(str(args.candidate), doraise=True)
    spec = importlib.util.spec_from_file_location("candidate_router_recovery", args.candidate)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    # Constructor does not connect to the socket or send an RPC request.
    bridge = module.RpcBridge("/var/run/arduino-router.sock")
    if bridge._router is None or bridge._serial_text is not None:
        raise RuntimeError("Candidate still has competing UART ownership")
    pid = int(subprocess.check_output(["systemctl", "show", "-p", "MainPID", "--value", "unoq-hmi.service"], text=True).strip())
    restart = subprocess.check_output(["systemctl", "show", "-p", "Restart", "--value", "unoq-hmi.service"], text=True).strip()
    proc = Path("/proc") / str(pid)
    if (pid <= 1 or restart != "always" or proc.stat().st_uid != os.geteuid()
            or (proc / "cwd").resolve() != root or "server.py" not in (proc / "cmdline").read_bytes().decode().split("\0")):
        raise RuntimeError("Owned HMI process not identified")
    saved_cal = calibration.read_bytes()
    if args.check_only:
        print(json.dumps({"check_only": True, "actuation_commands": 0, "mcu_flash_commands": 0})); return
    backup = root / "backups" / ("router_recovery_" + uuid.uuid4().hex)
    backup.mkdir(parents=True, exist_ok=False); (backup / "server.py").write_bytes(original)
    pending = root / "server.py.router-pending"
    pending.write_bytes(data); pending.chmod(target.stat().st_mode & 0o777)
    os.replace(pending, target); os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 15
    replacement = pid
    while time.monotonic() < deadline:
        time.sleep(1)
        replacement = int(subprocess.check_output(["systemctl", "show", "-p", "MainPID", "--value", "unoq-hmi.service"], text=True).strip())
        if replacement > 1 and replacement != pid:
            break
    if replacement <= 1 or replacement == pid or target.read_bytes() != data or calibration.read_bytes() != saved_cal:
        raise RuntimeError("HMI process/file/calibration verification failed")
    print(json.dumps({"installed": True, "sha256": args.sha256.lower(), "calibration_unchanged": True,
                      "new_pid": replacement, "backup": str(backup), "actuation_commands": 0,
                      "mcu_flash_commands": 0, "rpc_verified": False}))


if __name__ == "__main__":
    main()

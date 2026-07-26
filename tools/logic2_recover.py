#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from saleae.automation import Manager
except ModuleNotFoundError as exc:
    repo_root = Path(__file__).resolve().parents[1]
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    reexec_flag = "MIC_PRACTICE_LOGIC2_RECOVER_REEXEC"
    if exc.name == "saleae" and venv_python.exists() and os.environ.get(reexec_flag) != "1":
        env = dict(os.environ)
        env[reexec_flag] = "1"
        proc = subprocess.run(
            [str(venv_python), "-u", str(Path(__file__).resolve()), *sys.argv[1:]],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.stdout:
            sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    print(
        "ERROR: Python package 'logic2-automation' is not available. "
        "Install requirements.txt or run with .venv\\Scripts\\python.exe.",
        file=sys.stderr,
    )
    raise


DEFAULT_SHORTCUT = r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Logic\Saleae Logic 2.4.44.lnk"


def log(msg: str) -> None:
    print(msg, flush=True)


def device_snapshot(port: int) -> dict:
    try:
        mgr = Manager.connect(port=port, connect_timeout_seconds=2)
    except Exception as exc:
        return {"app_ok": False, "devices": [], "error": str(exc)}
    try:
        app = mgr.get_app_info()
        devices = mgr.get_devices()
        return {
            "app_ok": True,
            "app_version": app.app_version,
            "devices": [d.device_id for d in devices],
        }
    except Exception as exc:
        return {"app_ok": False, "devices": [], "error": str(exc)}
    finally:
        try:
            mgr.close()
        except Exception:
            pass


def saleae_pnp_rows() -> list[dict]:
    ps = (
        "Get-PnpDevice | "
        "Where-Object { $_.InstanceId -like '*VID_0925&PID_3881*' -or $_.FriendlyName -like '*Saleae*' } | "
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


def resolve_logic_launch(shortcut: str) -> tuple[str, str]:
    if shortcut.lower().endswith(".lnk"):
        ps = (
            "$ws = New-Object -ComObject WScript.Shell; "
            f"$sc = $ws.CreateShortcut('{shortcut}'); "
            "[PSCustomObject]@{TargetPath=$sc.TargetPath;WorkingDirectory=$sc.WorkingDirectory} | ConvertTo-Json -Compress"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        data = json.loads(out)
        target = str(data.get("TargetPath") or "")
        cwd = str(data.get("WorkingDirectory") or "")
        if not target:
            raise RuntimeError(f"Logic2 shortcut target is empty: {shortcut}")
        return target, cwd or str(Path(target).parent)
    return shortcut, str(Path(shortcut).parent)


def stop_logic_processes() -> None:
    subprocess.run(
        ["taskkill", "/IM", "Logic.exe", "/T", "/F"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process Logic -ErrorAction SilentlyContinue | Stop-Process -Force",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_logic_shortcut(shortcut: str) -> None:
    ps = f"Start-Process explorer.exe '{shortcut}'"
    subprocess.check_call(
        ["powershell", "-NoProfile", "-Command", ps],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_logic(target: str, cwd: str, port: int) -> int:
    ps = (
        "$args = @('--automation', '--automationPort', '"
        + str(port)
        + "'); "
        f"$p = Start-Process -FilePath '{target}' -WorkingDirectory '{cwd}' -ArgumentList $args -PassThru; "
        "Start-Sleep -Milliseconds 500; "
        "$p.Id"
    )
    out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps], text=True).strip()
    return int(out.splitlines()[-1])


def logic_process_alive(pid: int) -> bool:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    return str(pid) in (proc.stdout or "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Restart Logic2 and wait for a visible Saleae analyzer device.")
    ap.add_argument("--port", type=int, default=10430)
    ap.add_argument("--shortcut", default=DEFAULT_SHORTCUT)
    ap.add_argument("--wait-app", type=float, default=15.0)
    ap.add_argument("--wait-device", type=float, default=20.0)
    ap.add_argument("--restart", action="store_true")
    args = ap.parse_args()

    snap = device_snapshot(args.port)
    if snap.get("devices") and not args.restart:
        log(f"Logic2 OK devices={snap['devices']}")
        return 0

    if args.restart:
        log("Restarting Logic2")
        stop_logic_processes()
        time.sleep(1.0)
        if not os.path.exists(args.shortcut):
            log(f"ERROR: Logic2 path not found: {args.shortcut}")
            return 2
        try:
            target, cwd = resolve_logic_launch(args.shortcut)
        except Exception as exc:
            log(f"ERROR: failed to resolve Logic2 launch target: {exc}")
            return 2
        if not os.path.exists(target):
            log(f"ERROR: Logic2 executable not found: {target}")
            return 2
        pid = start_logic(target, cwd, args.port)
        time.sleep(1.0)
        if not logic_process_alive(pid):
            log(
                f"ERROR: Logic2 exited immediately after launch pid={pid} "
                f"target={target} port={args.port}"
            )
            return 5

    deadline = time.monotonic() + max(1.0, args.wait_app)
    app_seen = False
    while time.monotonic() < deadline:
        snap = device_snapshot(args.port)
        if snap.get("app_ok"):
            app_seen = True
            break
        time.sleep(0.5)
    if not app_seen:
        log(f"ERROR: Logic2 automation not reachable on port {args.port}")
        return 3

    deadline = time.monotonic() + max(1.0, args.wait_device)
    while time.monotonic() < deadline:
        snap = device_snapshot(args.port)
        if snap.get("devices"):
            log(f"Logic2 device ready devices={snap['devices']}")
            return 0
        time.sleep(0.5)

    log("ERROR: Logic2 is running, but no Saleae analyzer device is visible")
    rows = saleae_pnp_rows()
    if not rows:
        log("Saleae USB: no matching Windows device records")
    else:
        for row in rows:
            log(
                "  "
                + f"{row.get('FriendlyName', '?')} "
                + f"status={row.get('Status')} present={row.get('Present')} "
                + f"problem={row.get('Problem')} id={row.get('InstanceId')}"
            )
    return 4


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())

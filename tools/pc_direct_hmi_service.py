#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


TOOL = "pc_direct_hmi_service"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18080
DEFAULT_SERIAL = "COM3"
DEFAULT_BAUD = 115200
DEFAULT_RX_TIMEOUT = 0.08


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def service_dir(repo: Path) -> Path:
    return repo / "tools" / "_preflight_exports" / "pc_direct_hmi_live"


def http_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(url: str, timeout_s: float = 1.0) -> tuple[bool, dict[str, Any] | None, str]:
    try:
        with http_opener().open(url, timeout=timeout_s) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            data = json.loads(text)
            return True, data if isinstance(data, dict) else None, text
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def http_post_json(url: str, payload: dict[str, Any], timeout_s: float = 1.0) -> tuple[bool, dict[str, Any] | None, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with http_opener().open(req, timeout=timeout_s) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(text)
            return True, parsed if isinstance(parsed, dict) else None, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        return False, parsed, text
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def base_url(host: str, port: int, url: str | None = None) -> str:
    if url:
        return url.rstrip("/")
    return f"http://{host}:{int(port)}"


def powershell_json(command: str, timeout_s: float = 5.0) -> tuple[bool, Any, str]:
    ps = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "$ErrorActionPreference='Stop'; "
        f"{command}"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except FileNotFoundError as exc:
        return False, None, f"{type(exc).__name__}: {exc}"
    except subprocess.TimeoutExpired as exc:
        return False, None, f"{type(exc).__name__}: {exc}"
    text = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, None, (proc.stderr or text or f"powershell rc={proc.returncode}").strip()
    if not text:
        return True, [], ""
    try:
        return True, json.loads(text), text
    except json.JSONDecodeError as exc:
        return False, None, f"JSONDecodeError: {exc}: {text[:500]}"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def list_windows_processes(timeout_s: float = 5.0) -> tuple[bool, list[dict[str, Any]], str]:
    command = (
        "$items=@(Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*unoq_web_server.py*' }); "
        "$rows=@($items | Select-Object @{Name='pid';Expression={$_.ProcessId}},"
        "@{Name='name';Expression={$_.Name}},"
        "@{Name='command_line';Expression={$_.CommandLine}}); "
        "if ($rows.Count -eq 0) { '[]' } else { $rows | ConvertTo-Json -Depth 4 }"
    )
    ok, data, detail = powershell_json(command, timeout_s=timeout_s)
    if not ok:
        return False, [], detail
    rows: list[dict[str, Any]] = []
    for item in as_list(data):
        if isinstance(item, dict):
            rows.append(item)
    return True, rows, detail


def list_windows_listeners(port: int, timeout_s: float = 5.0) -> tuple[bool, list[dict[str, Any]], str]:
    command = (
        f"try {{ $items=@(Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction Stop) }} "
        "catch { $items=@() }; "
        "$rows=@($items | Select-Object @{Name='local_address';Expression={$_.LocalAddress}},"
        "@{Name='local_port';Expression={$_.LocalPort}},"
        "@{Name='state';Expression={$_.State}},"
        "@{Name='pid';Expression={$_.OwningProcess}}); "
        "if ($rows.Count -eq 0) { '[]' } else { $rows | ConvertTo-Json -Depth 4 }"
    )
    ok, data, detail = powershell_json(command, timeout_s=timeout_s)
    if not ok:
        return False, [], detail
    rows: list[dict[str, Any]] = []
    for item in as_list(data):
        if isinstance(item, dict):
            rows.append(item)
    return True, rows, detail


def hmi_commandline_matches(command_line: str, port: int) -> bool:
    text = str(command_line or "")
    if "unoq_web_server.py" not in text.replace("\\", "/"):
        return False
    port_re = re.compile(rf"(?<!\S)--port(?:=|\s+){int(port)}(?!\d)")
    return bool(port_re.search(text))


def filter_hmi_processes(processes: list[dict[str, Any]], port: int) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen: set[int] = set()
    for proc in processes:
        cmd = str(proc.get("command_line", ""))
        if not hmi_commandline_matches(cmd, port):
            continue
        try:
            pid = int(proc.get("pid", 0))
        except Exception:
            pid = 0
        if pid <= 0 or pid in seen:
            continue
        seen.add(pid)
        matches.append(
            {
                "pid": pid,
                "name": str(proc.get("name", "")),
                "command_line": cmd,
            }
        )
    return sorted(matches, key=lambda item: int(item.get("pid", 0)))


def terminate_pids(pids: list[int], timeout_s: float = 5.0) -> tuple[bool, str]:
    clean = sorted({int(pid) for pid in pids if int(pid) > 0})
    if not clean:
        return True, "no matching pids"
    ids = ",".join(str(pid) for pid in clean)
    command = f"$ids=@({ids}); Stop-Process -Id $ids -Force -ErrorAction Stop"
    ok, _data, detail = powershell_json(command, timeout_s=timeout_s)
    return ok, detail


def build_server_cmd(repo: Path, serial: str, baud: int, host: str, port: int, rx_timeout: float) -> list[str]:
    return [
        sys.executable,
        "-u",
        str(repo / "tools" / "unoq_web_server.py"),
        "--serial",
        str(serial),
        "--baud",
        str(int(baud)),
        "--host",
        str(host),
        "--port",
        str(int(port)),
        "--rx-timeout",
        f"{float(rx_timeout):.3f}",
    ]


def launch_server(
    repo: Path,
    serial: str,
    baud: int,
    host: str,
    port: int,
    rx_timeout: float,
    logs_root: Path,
) -> dict[str, Any]:
    logs_root.mkdir(parents=True, exist_ok=True)
    tag = ts_tag()
    stdout_path = logs_root / f"unoq_web_server_{tag}.log"
    stderr_path = logs_root / f"unoq_web_server_{tag}.err.log"
    cmd = build_server_cmd(repo, serial, baud, host, port, rx_timeout)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    stdout_f = stdout_path.open("w", encoding="utf-8", errors="replace")
    stderr_f = stderr_path.open("w", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo),
            stdout=stdout_f,
            stderr=stderr_f,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    finally:
        stdout_f.close()
        stderr_f.close()
    return {
        "pid": int(proc.pid),
        "cmd": cmd,
        "cwd": str(repo),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }


def collect_status(host: str, port: int, url: str | None = None, timeout_s: float = 1.0) -> dict[str, Any]:
    resolved = base_url(host, port, url)
    http_ok, payload, http_detail = http_json(resolved + "/api/status", timeout_s=timeout_s)
    proc_ok, processes, proc_detail = list_windows_processes(timeout_s=timeout_s + 4.0)
    listener_ok, listeners, listener_detail = list_windows_listeners(port, timeout_s=timeout_s + 4.0)
    hmi_processes = filter_hmi_processes(processes, port) if proc_ok else []
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else None
    return {
        "url": resolved,
        "http_reachable": bool(http_ok and payload and payload.get("ok")),
        "http_detail": "" if http_ok else http_detail,
        "status": data,
        "process_query_ok": proc_ok,
        "process_query_detail": "" if proc_ok else proc_detail,
        "hmi_processes": hmi_processes,
        "listener_query_ok": listener_ok,
        "listener_query_detail": "" if listener_ok else listener_detail,
        "listeners": listeners if listener_ok else [],
    }


def write_manifest(logs_root: Path, summary: dict[str, Any]) -> str:
    logs_root.mkdir(parents=True, exist_ok=True)
    latest = logs_root / "pc_direct_hmi_latest.json"
    latest.write_text(json_dumps(summary), encoding="utf-8")
    return str(latest)


def wait_until(predicate, timeout_s: float, interval_s: float = 0.1) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_s)
    while time.monotonic() <= deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return bool(predicate())


def action_status(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    status = collect_status(args.host, args.port, args.url, timeout_s=args.timeout)
    summary = {
        "tool": TOOL,
        "action": "status",
        "pass": True,
        "port": int(args.port),
        **status,
    }
    summary["manifest"] = write_manifest(service_dir(repo), summary)
    return summary


def action_stop(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    logs_root = service_dir(repo)
    resolved = base_url(args.host, args.port, args.url)
    safe_stop_results: list[dict[str, Any]] = []
    if not args.no_http_safe_stop:
        for cmd in ("STOP", "CLEAR"):
            ok, payload, detail = http_post_json(resolved + "/api/cmd", {"cmd": cmd}, timeout_s=args.timeout)
            safe_stop_results.append({"cmd": cmd, "ok": ok, "payload": payload, "detail": detail if not ok else ""})

    before = collect_status(args.host, args.port, args.url, timeout_s=args.timeout)
    pids = [int(item["pid"]) for item in before.get("hmi_processes", [])]
    term_ok, term_detail = terminate_pids(pids, timeout_s=args.timeout + 4.0)

    def stopped() -> bool:
        current = collect_status(args.host, args.port, args.url, timeout_s=max(0.2, args.timeout))
        return len(current.get("hmi_processes", [])) == 0

    stop_ok = term_ok and wait_until(stopped, timeout_s=args.kill_timeout)
    after = collect_status(args.host, args.port, args.url, timeout_s=args.timeout)
    stop_ok = stop_ok and len(after.get("hmi_processes", [])) == 0
    summary = {
        "tool": TOOL,
        "action": "stop",
        "pass": bool(stop_ok),
        "port": int(args.port),
        "url": resolved,
        "safe_stop_results": safe_stop_results,
        "stopped_pids": pids,
        "terminate_ok": bool(term_ok),
        "terminate_detail": "" if term_ok else term_detail,
        "before": before,
        "after": after,
    }
    summary["manifest"] = write_manifest(logs_root, summary)
    return summary


def action_start(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    logs_root = service_dir(repo)
    resolved = base_url(args.host, args.port, args.url)
    before = collect_status(args.host, args.port, args.url, timeout_s=args.timeout)
    if before.get("http_reachable") and not args.force:
        summary = {
            "tool": TOOL,
            "action": "start",
            "pass": True,
            "port": int(args.port),
            "url": resolved,
            "already_running": True,
            "before": before,
            "after": before,
        }
        summary["manifest"] = write_manifest(logs_root, summary)
        return summary
    if before.get("hmi_processes") and not args.force:
        summary = {
            "tool": TOOL,
            "action": "start",
            "pass": False,
            "port": int(args.port),
            "url": resolved,
            "error": "matching HMI process already exists but HTTP status is not reachable; use restart or --force",
            "before": before,
        }
        summary["manifest"] = write_manifest(logs_root, summary)
        return summary
    if args.force and before.get("hmi_processes"):
        stop_args = argparse.Namespace(**vars(args))
        stop_args.no_http_safe_stop = args.no_http_safe_stop
        action_stop(stop_args)
    launch = launch_server(repo, args.serial, args.baud, args.host, args.port, args.rx_timeout, logs_root)

    def reachable() -> bool:
        return bool(collect_status(args.host, args.port, args.url, timeout_s=max(0.2, args.timeout)).get("http_reachable"))

    started = wait_until(reachable, timeout_s=args.start_timeout)
    after = collect_status(args.host, args.port, args.url, timeout_s=args.timeout)
    summary = {
        "tool": TOOL,
        "action": "start",
        "pass": bool(started and after.get("http_reachable")),
        "port": int(args.port),
        "url": resolved,
        "already_running": False,
        "launch": launch,
        "before": before,
        "after": after,
    }
    summary["manifest"] = write_manifest(logs_root, summary)
    return summary


def action_restart(args: argparse.Namespace) -> dict[str, Any]:
    stop_args = argparse.Namespace(**vars(args))
    stop = action_stop(stop_args)
    start_args = argparse.Namespace(**vars(args))
    start_args.force = False
    start = action_start(start_args)
    repo = Path(args.repo).resolve()
    summary = {
        "tool": TOOL,
        "action": "restart",
        "pass": bool(stop.get("pass") and start.get("pass")),
        "port": int(args.port),
        "stop": stop,
        "start": start,
    }
    summary["manifest"] = write_manifest(service_dir(repo), summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Manage the safe PC-direct STM32 HMI process.")
    ap.add_argument("action", choices=["status", "start", "stop", "restart"])
    ap.add_argument("--repo", default=str(repo_root_from_here()))
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--url", default=None)
    ap.add_argument("--serial", default=DEFAULT_SERIAL)
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    ap.add_argument("--rx-timeout", type=float, default=DEFAULT_RX_TIMEOUT)
    ap.add_argument("--timeout", type=float, default=1.0)
    ap.add_argument("--start-timeout", type=float, default=8.0)
    ap.add_argument("--kill-timeout", type=float, default=5.0)
    ap.add_argument("--force", action="store_true", help="Stop existing matching HMI process before start.")
    ap.add_argument("--no-http-safe-stop", action="store_true", help="Do not POST STOP/CLEAR before terminating HMI.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "status":
        summary = action_status(args)
    elif args.action == "start":
        summary = action_start(args)
    elif args.action == "stop":
        summary = action_stop(args)
    elif args.action == "restart":
        summary = action_restart(args)
    else:
        raise AssertionError(args.action)
    print(json_dumps(summary))
    return 0 if summary.get("pass") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    raise SystemExit(main())

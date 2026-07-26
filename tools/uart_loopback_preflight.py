#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


TOOL = "uart_loopback_preflight"
DEFAULT_HMI_PORT = 18080
DEFAULT_PORT = "COM3"
DEFAULT_BAUDS = "460800,115200,230400,921600"


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_json_stdout(stdout: str) -> dict[str, Any] | None:
    for line in reversed((stdout or "").splitlines()):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        return data if isinstance(data, dict) else None
    return None


def run_command(cmd: list[str], cwd: Path, timeout_s: float) -> dict[str, Any]:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "elapsed_s": time.monotonic() - start,
            "stdout_tail": stdout[-6000:],
            "stderr_tail": stderr[-6000:],
            "json": parse_json_stdout(stdout),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "returncode": None,
            "ok": False,
            "elapsed_s": time.monotonic() - start,
            "timeout": True,
            "stdout_tail": (exc.stdout or "")[-6000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-6000:] if isinstance(exc.stderr, str) else "",
            "error": f"TimeoutExpired: {exc}",
        }
    except Exception as exc:
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "returncode": None,
            "ok": False,
            "elapsed_s": time.monotonic() - start,
            "error": f"{type(exc).__name__}: {exc}",
        }


def command_plan(args: argparse.Namespace, repo: Path) -> dict[str, list[str]]:
    stop = [
        sys.executable,
        "-u",
        str(repo / "tools" / "pc_direct_hmi_service.py"),
        "stop",
        "--port",
        str(int(args.hmi_port)),
        "--timeout",
        f"{float(args.hmi_timeout):.3f}",
        "--kill-timeout",
        f"{float(args.hmi_kill_timeout):.3f}",
    ]
    loopback = [
        sys.executable,
        "-u",
        str(repo / "tools" / "bluepill_uart_diagnose.py"),
        "--port",
        str(args.port),
        "--loopback",
        "--confirm-loopback-wired",
        "--bauds",
        str(args.bauds),
        "--timeout",
        f"{float(args.timeout):.3f}",
        "--write-timeout",
        f"{float(args.write_timeout):.3f}",
    ]
    start = [
        sys.executable,
        "-u",
        str(repo / "tools" / "pc_direct_hmi_service.py"),
        "start",
        "--serial",
        str(args.port),
        "--baud",
        str(int(args.hmi_baud)),
        "--port",
        str(int(args.hmi_port)),
        "--timeout",
        f"{float(args.hmi_timeout):.3f}",
        "--start-timeout",
        f"{float(args.hmi_start_timeout):.3f}",
    ]
    return {"stop_hmi": stop, "loopback": loopback, "start_hmi": start}


def write_summary(run_dir: Path, summary: dict[str, Any]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json_dumps(summary), encoding="utf-8")
    return summary_path


def run_preflight(args: argparse.Namespace, runner: Callable[[list[str], Path, float], dict[str, Any]] = run_command) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    run_dir = (repo / args.out_root).resolve() / f"uart_loopback_preflight_{ts_tag()}"
    plan = command_plan(args, repo)
    summary: dict[str, Any] = {
        "tool": TOOL,
        "run_dir": str(run_dir),
        "port": str(args.port),
        "bauds": str(args.bauds),
        "hmi_port": int(args.hmi_port),
        "confirm_loopback_wired": bool(args.confirm_loopback_wired),
        "dry_run": bool(args.dry_run),
        "no_restart_hmi": bool(args.no_restart_hmi),
        "wiring_required": [
            "Disconnect USB-UART TX/RX from STM32.",
            "Short USB-UART TX to USB-UART RX on the isolated adapter side.",
            "Do not connect the TX/RX short while the adapter is still connected to STM32 PA2/PA3.",
            "HV/J7 and active PWM are not required for this test.",
        ],
        "command_plan": plan,
        "steps": [],
        "pass": False,
        "loopback_pass": None,
        "hmi_restored": None,
    }

    if args.dry_run:
        summary["pass"] = True
        summary["reason"] = "dry_run_only_no_commands_executed"
        summary["summary"] = str(write_summary(run_dir, summary))
        return summary

    if not args.confirm_loopback_wired:
        summary["blocked"] = True
        summary["reason"] = "missing --confirm-loopback-wired; refusing to touch COM port until TX/RX are disconnected from STM32 and shorted on adapter side"
        summary["summary"] = str(write_summary(run_dir, summary))
        return summary

    stop = runner(plan["stop_hmi"], repo, float(args.hmi_stop_timeout))
    stop["name"] = "stop_hmi"
    summary["steps"].append(stop)
    stop_json = stop.get("json") if isinstance(stop.get("json"), dict) else {}
    stop_pass = bool(stop.get("ok") and stop_json.get("pass", True))
    summary["hmi_stopped"] = stop_pass
    summary["hmi_stop_summary"] = stop_json
    if not stop_pass:
        summary["pass"] = False
        summary["blocked"] = True
        summary["next_action"] = "stop_or_close_pc_direct_hmi_before_uart_loopback"
        summary["reason"] = "pc_direct_hmi_service stop failed; refusing to open COM port for loopback while HMI may still own the adapter"
        summary["summary"] = str(write_summary(run_dir, summary))
        return summary

    loopback = runner(plan["loopback"], repo, float(args.loopback_timeout))
    loopback["name"] = "bluepill_uart_loopback"
    summary["steps"].append(loopback)

    loop_json = loopback.get("json") if isinstance(loopback.get("json"), dict) else {}
    summary["loopback_summary"] = loop_json
    summary["loopback_pass"] = bool(loop_json.get("loopback_pass") or loop_json.get("pass"))
    summary["bluepill_uart_diagnose_summary"] = loop_json.get("summary")

    start: dict[str, Any] | None = None
    if not args.no_restart_hmi:
        start = runner(plan["start_hmi"], repo, float(args.hmi_start_timeout) + 5.0)
        start["name"] = "start_hmi"
        summary["steps"].append(start)
        start_json = start.get("json") if isinstance(start.get("json"), dict) else {}
        summary["hmi_restored"] = bool(start.get("ok") and start_json.get("pass", True))
        summary["hmi_service_summary"] = start_json
    else:
        summary["hmi_restored"] = None

    summary["pass"] = bool(summary["loopback_pass"] and (args.no_restart_hmi or summary["hmi_restored"] is True))
    if not summary["loopback_pass"]:
        summary["next_action"] = "fix_usb_uart_loopback_or_isolator_before_reconnecting_stm32"
    elif not args.no_restart_hmi and summary["hmi_restored"] is not True:
        summary["next_action"] = "restart_pc_direct_hmi_before_continuing"
    else:
        summary["next_action"] = "remove_tx_rx_short_reconnect_stm32_and_rerun_protocol_diagnose"

    summary["summary"] = str(write_summary(run_dir, summary))
    return summary


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Safe USB-UART loopback preflight with PC-direct HMI stop/start wrapper.")
    ap.add_argument("--repo", default=str(repo_root_from_here()))
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--bauds", default=DEFAULT_BAUDS)
    ap.add_argument("--timeout", type=float, default=0.5)
    ap.add_argument("--write-timeout", type=float, default=2.0)
    ap.add_argument("--loopback-timeout", type=float, default=70.0)
    ap.add_argument("--hmi-port", type=int, default=DEFAULT_HMI_PORT)
    ap.add_argument("--hmi-baud", type=int, default=460800)
    ap.add_argument("--hmi-timeout", type=float, default=1.0)
    ap.add_argument("--hmi-stop-timeout", type=float, default=10.0)
    ap.add_argument("--hmi-start-timeout", type=float, default=8.0)
    ap.add_argument("--hmi-kill-timeout", type=float, default=5.0)
    ap.add_argument("--confirm-loopback-wired", action="store_true", help="Required: TX/RX are disconnected from STM32 and shorted on the USB-UART side.")
    ap.add_argument("--dry-run", action="store_true", help="Write command plan only; do not stop HMI or open COM.")
    ap.add_argument("--no-restart-hmi", action="store_true", help="Leave HMI stopped after loopback.")
    ap.add_argument("--out-root", default="tools/_preflight_exports")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_preflight(args)
    print(json_dumps(summary))
    if summary.get("pass"):
        return 0
    return 2 if summary.get("blocked") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    raise SystemExit(main())

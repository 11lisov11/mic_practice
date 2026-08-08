#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_URL = "http://192.168.1.138:8080"
DEFAULT_FQBN = "arduino:zephyr:unoq:link_mode=static"
DEFAULT_CORE_VERSION = "0.90.0"


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str]) -> None:
    log("RUN " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def installed_core_version_from_json(raw: str, core_id: str = "arduino:zephyr") -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid arduino-cli core list JSON: {exc}") from exc
    for platform in payload.get("platforms", []):
        if platform.get("id") == core_id:
            return str(platform.get("installed_version", "")).strip()
    return ""


def verify_core_version(expected: str) -> None:
    if not expected:
        return
    proc = subprocess.run(
        ["arduino-cli", "core", "list", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    installed = installed_core_version_from_json(proc.stdout)
    if installed != expected:
        raise SystemExit(
            "ERROR: UNO Q core mismatch: "
            f"installed={installed or 'missing'}, required={expected}. "
            f"Run: arduino-cli core install arduino:zephyr@{expected}"
        )
    log(f"CORE_OK arduino:zephyr@{installed}")


def read_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()
    token_file = Path(args.token_file)
    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SystemExit(f"ERROR: token file not readable: {token_file}: {exc}")
    if len(token) < 16:
        raise SystemExit("ERROR: firmware update token is missing or too short")
    return token


def compile_sketch(args: argparse.Namespace) -> Path:
    build_path = Path(args.build_path)
    sketch_dir = Path(args.sketch_dir)
    if not args.no_compile:
        run(
            [
                "arduino-cli",
                "compile",
                "--fqbn",
                args.fqbn,
                "--build-path",
                str(build_path),
                str(sketch_dir),
            ]
        )
    artifact = Path(args.artifact) if args.artifact else build_path / "UNOQ_MOTOR.ino.bin-zsk.bin"
    if artifact.exists():
        return artifact
    fallback = build_path / "UNOQ_MOTOR.ino.bin"
    if fallback.exists():
        return fallback
    matches = sorted(build_path.glob("*.bin-zsk.bin")) + sorted(build_path.glob("*.bin"))
    if matches:
        return matches[0]
    raise SystemExit(f"ERROR: firmware artifact not found in {build_path}")


def read_expected_build_id(sketch_dir: str, explicit: int) -> int:
    if explicit > 0:
        return explicit
    sketch = Path(sketch_dir) / (Path(sketch_dir).name + ".ino")
    try:
        source = sketch.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"ERROR: cannot read firmware build ID from {sketch}: {exc}")
    match = re.search(r"\bFW_BUILD_ID\s*=\s*(\d+)[uUlL]*\s*;", source)
    if not match:
        raise SystemExit(f"ERROR: FW_BUILD_ID is missing in {sketch}")
    return int(match.group(1))


def fetch_status(base_url: str, timeout: float = 3.0) -> dict:
    request = Request(base_url.rstrip("/") + "/api/status", headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data")
    if payload.get("ok") is not True or not isinstance(data, dict):
        raise RuntimeError(payload.get("error") or "status unavailable")
    return data


def post_command(base_url: str, command: str, timeout: float = 3.0) -> tuple[bool, str]:
    body = json.dumps({"cmd": command}).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + "/api/cmd",
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return False, str(exc)
    return bool(payload.get("ok")), str(payload.get("error") or "")


def activation_health_error(status: dict) -> str:
    if str(status.get("state", "")).upper() != "SAFE":
        return f"state={status.get('state')}"
    if int(status.get("pwm", 1) or 0) != 0:
        return f"pwm={status.get('pwm')}"
    if int(status.get("estop", 1) or 0) != 0:
        return f"estop={status.get('estop')}"
    if int(status.get("bp_fault", 255) or 0) != 0:
        return f"bp_fault={status.get('bp_fault')}"
    if max(int(status.get("bp_bad", 0) or 0), int(status.get("bp_bad_cnt", 0) or 0)) != 0:
        return f"bp_bad={status.get('bp_bad')}/{status.get('bp_bad_cnt')}"
    if (int(status.get("bp_status", 0) or 0) & 0x01) == 0:
        return f"bp_status={status.get('bp_status')}"
    if float(status.get("bp_age_ms", 999999)) > 500.0:
        return f"bp_age_ms={status.get('bp_age_ms')}"
    if int(status.get("precharge", 1) or 0) != 0 or (int(status.get("bp_ext", 0x08) or 0) & 0x08) != 0:
        return f"precharge={status.get('precharge')} bp_ext={status.get('bp_ext')}"
    return ""


def wait_for_build(base_url: str, expected: int, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    last_error = "status unavailable"
    while time.monotonic() < deadline:
        try:
            last = fetch_status(base_url)
            actual = int(last.get("fw_build", 0) or 0)
            if actual == expected:
                return last
            last_error = f"fw_build={actual}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"firmware activation not verified: expected fw_build={expected}, {last_error}")


def wait_for_healthy_controller(base_url: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    last_error = "status unavailable"
    timeout_clear_attempted = False
    while time.monotonic() < deadline:
        try:
            last = fetch_status(base_url)
            fault = int(last.get("bp_fault", 255) or 0)
            link_fresh = (
                (int(last.get("bp_status", 0) or 0) & 0x01) != 0
                and float(last.get("bp_age_ms", 999999)) <= 500.0
            )
            if fault == 2 and link_fresh and not timeout_clear_attempted:
                timeout_clear_attempted = True
                ok, error = post_command(base_url, "CLEAR")
                if not ok:
                    last_error = f"planned reboot timeout CLEAR failed: {error or 'rejected'}"
                else:
                    log("RECOVERY_OK cleared expected Blue Pill reboot timeout")
                time.sleep(0.25)
                continue
            last_error = activation_health_error(last)
            if not last_error:
                return last
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"controller health not verified after activation: {last_error}")


def post_binary(url: str, body: bytes, token: str, source_ip: str, timeout: float) -> tuple[int, str]:
    parsed = urlparse(url)
    if parsed.scheme != "http":
        raise SystemExit("ERROR: only http:// URLs are supported")
    host = parsed.hostname
    if not host:
        raise SystemExit("ERROR: URL host is missing")
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if source_ip:
            sock.bind((source_ip, 0))
        sock.settimeout(timeout)
        sock.connect((host, port))
        request = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Connection: close\r\n"
            "Content-Type: application/octet-stream\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"X-UNOQ-Update-Token: {token}\r\n"
            "\r\n"
        ).encode("ascii") + body
        sock.sendall(request)
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        sock.close()

    raw = b"".join(chunks)
    head, _, payload = raw.partition(b"\r\n\r\n")
    status_line = head.splitlines()[0].decode("iso-8859-1", errors="replace") if head else ""
    parts = status_line.split()
    status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    return status, payload.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and send UNO Q MCU firmware through the Wi-Fi HMI.")
    parser.add_argument("--url", default=DEFAULT_URL, help="UNO Q HMI base URL")
    parser.add_argument("--source-ip", default="", help="Optional local source IP, useful when VPN routing interferes")
    parser.add_argument("--token", default="", help="Firmware update token")
    parser.add_argument("--token-file", default=".unoq_firmware_update_token", help="Local token file")
    parser.add_argument("--sketch-dir", default="UNOQ_MOTOR")
    parser.add_argument("--build-path", default="build_unoq_motor_wifi")
    parser.add_argument("--fqbn", default=DEFAULT_FQBN)
    parser.add_argument(
        "--expected-core-version",
        default=DEFAULT_CORE_VERSION,
        help="Require the local UNO Q core to match the Linux-side core before upload",
    )
    parser.add_argument("--artifact", default="", help="Use an existing firmware image instead of auto-detecting")
    parser.add_argument("--expected-build", type=int, default=0, help="Expected FW_BUILD_ID; defaults to the sketch source")
    parser.add_argument("--no-compile", action="store_true", help="Do not run arduino-cli compile")
    parser.add_argument("--flash", action="store_true", help="Actually flash the MCU; default is dry-run upload only")
    parser.add_argument("--confirm-hv-off", action="store_true", help="Required together with --flash")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    if args.flash and not args.confirm_hv_off:
        raise SystemExit("ERROR: --flash requires --confirm-hv-off")

    token = read_token(args)
    verify_core_version(args.expected_core_version.strip())
    expected_build = read_expected_build_id(args.sketch_dir, args.expected_build)
    artifact = compile_sketch(args)
    body = artifact.read_bytes()
    endpoint = args.url.rstrip("/") + "/api/firmware/update"
    if not args.flash:
        endpoint += "?dry_run=1"

    mode = "FLASH" if args.flash else "DRY-RUN"
    log(f"{mode} {artifact} ({len(body)} bytes) -> {endpoint}")
    status, payload = post_binary(endpoint, body, token, args.source_ip, args.timeout)
    try:
        data = json.loads(payload)
        pretty = json.dumps(data, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        pretty = payload
    print(pretty)
    if status < 200 or status >= 300:
        return 1
    if args.flash:
        try:
            verify_timeout = min(max(args.timeout, 10.0), 60.0)
            wait_for_build(args.url, expected_build, verify_timeout)
            final = wait_for_healthy_controller(args.url, verify_timeout)
        except RuntimeError as exc:
            log(f"ERROR: {exc}")
            return 1
        log(
            "ACTIVATION_OK "
            f"fw_build={int(final.get('fw_build', 0) or 0)} "
            f"state={final.get('state')} pwm={int(final.get('pwm', 0) or 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

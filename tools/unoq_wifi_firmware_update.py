#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_URL = "http://192.168.1.138:8080"
DEFAULT_FQBN = "arduino:zephyr:unoq:link_mode=static"


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str]) -> None:
    log("RUN " + " ".join(cmd))
    subprocess.run(cmd, check=True)


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
    parser.add_argument("--artifact", default="", help="Use an existing firmware image instead of auto-detecting")
    parser.add_argument("--no-compile", action="store_true", help="Do not run arduino-cli compile")
    parser.add_argument("--flash", action="store_true", help="Actually flash the MCU; default is dry-run upload only")
    parser.add_argument("--confirm-hv-off", action="store_true", help="Required together with --flash")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    if args.flash and not args.confirm_hv_off:
        raise SystemExit("ERROR: --flash requires --confirm-hv-off")

    token = read_token(args)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

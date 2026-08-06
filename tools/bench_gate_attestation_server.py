#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def parse_gate_output(stdout: str, returncode: int) -> tuple[bool, dict]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            ready = returncode == 0 and payload.get("ready_for_active_pwm") is True
            return ready, payload
    return False, {"error": f"bench_gate_report produced no JSON, rc={returncode}"}


class GateState:
    def __init__(self, repo: Path, hmi_url: str, token: str, ttl_s: float) -> None:
        self.repo = repo
        self.hmi_url = hmi_url
        self.token = token
        self.ttl_s = ttl_s
        self.lock = threading.Lock()

    def attest(self) -> tuple[int, dict]:
        command = [
            sys.executable,
            "-u",
            str(self.repo / "tools" / "bench_gate_report.py"),
            "--url",
            self.hmi_url,
        ]
        with self.lock:
            try:
                proc = subprocess.run(
                    command,
                    cwd=str(self.repo),
                    capture_output=True,
                    text=True,
                    timeout=20.0,
                )
            except Exception as exc:
                return 503, {"ready_for_active_pwm": False, "error": f"{type(exc).__name__}: {exc}"}
        ready, gate = parse_gate_output(proc.stdout, int(proc.returncode))
        now = time.time()
        payload = {
            "ready_for_active_pwm": ready,
            "issued_at": now,
            "expires_at": now + self.ttl_s,
            "gate_summary": gate.get("summary"),
            "failed_checks": gate.get("failed_checks", []),
            "warning_checks": gate.get("warning_checks", []),
        }
        return (200 if ready else 409), payload


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        state: GateState = self.server.gate_state  # type: ignore[attr-defined]
        supplied = parse_qs(parsed.query).get("token", [""])[0]
        if parsed.path != "/api/bench-gate" or not hmac.compare_digest(supplied, state.token):
            self.send_json(404, {"ready_for_active_pwm": False, "error": "not found"})
            return
        status, payload = state.attest()
        self.send_json(status, payload)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve short-lived live bench-gate attestations to UNO Q.")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--token", required=True)
    parser.add_argument("--hmi-url", required=True)
    parser.add_argument("--ttl-s", type=float, default=5.0)
    args = parser.parse_args()
    ttl_s = max(1.0, min(10.0, float(args.ttl_s)))
    repo = Path(__file__).resolve().parents[1]
    server = ThreadingHTTPServer((args.bind, int(args.port)), Handler)
    server.daemon_threads = True
    server.gate_state = GateState(repo, args.hmi_url.rstrip("/"), args.token, ttl_s)  # type: ignore[attr-defined]
    print(f"BENCH_GATE_ATTESTATION_SERVER=http://{args.bind}:{args.port}/api/bench-gate", flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

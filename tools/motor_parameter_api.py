#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from motor_identification.service import identify_motor, validate_capture_payload  # noqa: E402


MAX_REQUEST_BYTES = 32 * 1024 * 1024


def dispatch(action: str, payload: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
    if action == "health":
        return 200, {
            "ok": True,
            "service": "mic_ai.motor_identification.api.v1",
            "hardware_commands_enabled": False,
        }
    capture = payload.get("capture")
    if not isinstance(capture, Mapping):
        return 400, {"ok": False, "error": "capture object is required"}
    if action == "validate":
        return 200, {"ok": True, "result": validate_capture_payload(capture)}
    if action == "identify":
        prior = payload.get("prior")
        if not isinstance(prior, Mapping):
            return 400, {"ok": False, "error": "prior object is required"}
        options = payload.get("options") if isinstance(payload.get("options"), Mapping) else {}
        allowed = {
            "starts",
            "seed",
            "bound_factor",
            "max_nfev",
            "rank_tolerance",
            "condition_limit",
            "max_fit_nrmse",
            "max_validation_nrmse",
            "max_relative_ci_half_width",
        }
        kwargs = {key: options[key] for key in allowed if key in options}
        result = identify_motor(capture, prior, **kwargs)
        return 200, {"ok": True, "result": result}
    return 404, {"ok": False, "error": "not found"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            status, payload = dispatch("health", {})
            self._send(status, payload)
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        actions = {
            "/api/validate": "validate",
            "/api/identify": "identify",
        }
        action = actions.get(self.path)
        if action is None:
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, {"ok": False, "error": "invalid Content-Length"})
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._send(413, {"ok": False, "error": "request body size is invalid"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("request root must be an object")
            status, response = dispatch(action, payload)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            status, response = 400, {"ok": False, "error": str(exc)}
        self._send(status, response)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only motor identification HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18110)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        json.dumps(
            {
                "service": "mic_ai.motor_identification.api.v1",
                "listen": f"http://{args.host}:{args.port}",
                "hardware_commands_enabled": False,
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

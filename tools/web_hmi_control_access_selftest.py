#!/usr/bin/env python3
from __future__ import annotations

import http.client
import importlib.util
import json
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any


def load_server(repo: Path) -> Any:
    path = repo / "web_hmi" / "server.py"
    spec = importlib.util.spec_from_file_location("unoq_hmi_server", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRpc:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def cmd(self, command: str) -> tuple[bool, str]:
        self.commands.append(command)
        return True, ""

    def get(self) -> tuple[bool, dict, str]:
        return True, {
            "state": "SAFE",
            "state_code": 0,
            "mode": "VF",
            "pwm": 0,
            "precharge": 0,
            "bp_ext": 0,
            "estop": 0,
            "bp_fault": 0,
            "bp_bad": 0,
            "bp_bad_cnt": 0,
            "freq": 0.0,
            "speed": 0.0,
            "vdc": 0.0,
            "bp_vdc": 0.0,
            "bp_temp_c": 25.0,
            "bp_temp_fault": 0,
            "bp_phase_c_v": 0.0,
            "bp_phase_c_virtual": 0,
            "fan_duty": 0.0,
            "bp_fan_rpm": 0.0,
            "bp_cmd_mode": 0,
            "bp_foc_backend": 0,
        }, ""


def request(port: int, method: str, path: str, token: str = "", body: dict | None = None) -> tuple[int, bytes]:
    headers = {}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-UNOQ-Control-Token"] = token
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3.0)
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    mod = load_server(repo)
    token = "autonomous-control-token-32-chars"
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / "control.token"
        token_path.write_text(token + "\n", encoding="utf-8")
        logs = mod.LogStore(1024 * 1024, None, 0)
        logs.add("SELFTEST")
        rpc = FakeRpc()
        app = mod.AppState(
            rpc,
            logs,
            3600.0,
            control_access=mod.ControlAccessConfig(str(token_path)),
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
        server.app = app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = int(server.server_address[1])
        try:
            cases = {
                "status_is_read_only_public": request(port, "GET", "/api/status")[0] == 200,
                "logs_reject_missing_token": request(port, "GET", "/api/logs?hours=1")[0] == 401,
                "logs_accept_valid_token": request(port, "GET", "/api/logs?hours=1", token)[0] == 200,
                "start_rejects_missing_token": request(port, "POST", "/api/start-sequence", body={})[0] == 401,
                "command_rejects_bad_token": request(port, "POST", "/api/cmd", "wrong-token-value", {"cmd": "MODE VF"})[0] == 401,
                "command_accepts_valid_token": request(port, "POST", "/api/cmd", token, {"cmd": "MODE VF"})[0] == 200,
                "heartbeat_accepts_valid_token": request(port, "POST", "/api/operator-heartbeat", token, {})[0] == 200,
                "stop_remains_fail_safe_without_token": request(port, "POST", "/api/stop-sequence", body={})[0] == 200,
            }
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

        with app.hv_arm._lock:
            app.hv_arm._started = True
            app.hv_arm._expires_at = time.time() + 30.0
        with app._lock:
            app._operator_heartbeat_ts = time.monotonic() - 10.0
        rpc.commands.clear()
        app.start_safety_watchdog()
        time.sleep(0.5)
        app.stop_safety_watchdog()
        cases["lost_heartbeat_forces_stop_and_estop"] = "STOP" in rpc.commands and "ESTOP" in rpc.commands

    failed = [name for name, ok in cases.items() if not ok]
    print(json.dumps({"tool": "web_hmi_control_access_selftest", "pass": not failed, "cases": cases}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

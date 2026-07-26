#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import types
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def install_import_stubs() -> None:
    if "grpc" not in sys.modules:
        grpc = types.ModuleType("grpc")
        grpc.RpcError = RuntimeError
        grpc.StatusCode = types.SimpleNamespace(
            DEADLINE_EXCEEDED=object(),
            UNAVAILABLE=object(),
            INTERNAL=object(),
            UNKNOWN=object(),
            ABORTED=object(),
        )
        sys.modules["grpc"] = grpc
    if "saleae" not in sys.modules:
        saleae = types.ModuleType("saleae")
        automation = types.ModuleType("saleae.automation")
        capture = types.ModuleType("saleae.automation.capture")
        grpc_pkg = types.ModuleType("saleae.grpc")
        saleae_pb2 = types.ModuleType("saleae.grpc.saleae_pb2")

        class _DummyManager:
            pass

        class _DummyCapture:
            pass

        automation.Manager = _DummyManager
        capture.Capture = _DummyCapture
        grpc_pkg.saleae_pb2 = saleae_pb2
        sys.modules["saleae"] = saleae
        sys.modules["saleae.automation"] = automation
        sys.modules["saleae.automation.capture"] = capture
        sys.modules["saleae.grpc"] = grpc_pkg
        sys.modules["saleae.grpc.saleae_pb2"] = saleae_pb2


install_import_stubs()

import ui_pwm_case as case
import active_pwm_guard as active_guard


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


class TestState:
    def __init__(self) -> None:
        self.vdc = 0.0
        self.include_vbus = True
        self.bp_bad = 0
        self.bp_bad_cnt = 0
        self.cmd_status = 200
        self.cmd_payload: dict[str, Any] = {"ok": True}
        self.commands: list[str] = []


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.startswith("/api/status"):
            st: TestState = self.server.test_state  # type: ignore[attr-defined]
            data = {
                "state": "SAFE",
                "pwm": 0,
                "estop": 0,
                "bp_fault": 0,
                "bp_bad": int(st.bp_bad),
                "bp_bad_cnt": int(st.bp_bad_cnt),
                "link": True,
                "bp_rsp_age_ms": 1,
            }
            if st.include_vbus:
                data["vdc"] = float(st.vdc)
                data["bp_vdc"] = float(st.vdc)
            self._send_json(
                200,
                {
                    "ok": True,
                    "data": data,
                },
            )
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path.startswith("/api/cmd"):
            st: TestState = self.server.test_state  # type: ignore[attr-defined]
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            st.commands.append(str(body.get("cmd", "")))
            self._send_json(st.cmd_status, st.cmd_payload)
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        return


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def add_case(results: list[CaseResult], name: str, ok: bool, detail: str = "", evidence: Any = None) -> None:
    results.append(CaseResult(name=name, ok=bool(ok), detail=detail, evidence=evidence))


def main() -> int:
    port = free_tcp_port()
    state = TestState()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.test_state = state  # type: ignore[attr-defined]
    th = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{port}"

    old_env = {
        name: os.environ.get(name)
        for name in (
            "UNOQ_ADB_ROUTER_FALLBACK",
            "UNOQ_ALLOW_HV",
            "UNOQ_MAX_START_VDC",
            "UNOQ_START_VDC_SAMPLES",
        )
    }
    fallback_calls: list[str] = []
    original_fallback = case.post_cmd_adb_router
    original_start_allowed = case.start_allowed_by_bench_gate
    bench_gate_allowed = {"value": True}

    def fake_fallback(cmd: str) -> bool:
        fallback_calls.append(cmd)
        return True

    def fake_start_allowed(log_fn, url: str | None = None) -> bool:
        return bool(bench_gate_allowed["value"])

    results: list[CaseResult] = []
    try:
        case.post_cmd_adb_router = fake_fallback
        case.start_allowed_by_bench_gate = fake_start_allowed
        os.environ["UNOQ_ADB_ROUTER_FALLBACK"] = "1"
        os.environ.pop("UNOQ_ALLOW_HV", None)
        os.environ["UNOQ_MAX_START_VDC"] = "60.0"
        os.environ["UNOQ_START_VDC_SAMPLES"] = "1"

        inserted = case.commands_with_runlimit(["CLEAR", "MODE VF", "START"], default_s=1.2)
        add_case(
            results,
            "commands_with_runlimit_inserts_before_start",
            inserted == ["CLEAR", "MODE VF", "SET RUNLIMIT 1.200", "START"],
            evidence={"commands": inserted},
        )

        preserved = case.commands_with_runlimit(["CLEAR", "SET RUNLIMIT 2.500", "START"], default_s=1.2)
        add_case(
            results,
            "commands_with_runlimit_preserves_existing",
            preserved == ["CLEAR", "SET RUNLIMIT 2.500", "START"],
            evidence={"commands": preserved},
        )

        state.vdc = 0.0
        state.cmd_status = 400
        state.cmd_payload = {"ok": False, "error": "bluepill link not ready"}
        state.commands.clear()
        fallback_calls.clear()
        ok = case.post_cmd(base, "START")
        add_case(
            results,
            "start_4xx_rejection_does_not_fallback",
            (not ok) and fallback_calls == [] and state.commands == ["START"],
            evidence={"ok": ok, "fallback_calls": list(fallback_calls), "commands": list(state.commands)},
        )

        state.vdc = 0.0
        state.cmd_status = 503
        state.cmd_payload = {"ok": False, "error": "temporary server error"}
        state.commands.clear()
        fallback_calls.clear()
        ok = case.post_cmd(base, "STOP")
        add_case(
            results,
            "server_5xx_allows_fallback",
            ok and fallback_calls == ["STOP"] and state.commands == ["STOP"],
            evidence={"ok": ok, "fallback_calls": list(fallback_calls), "commands": list(state.commands)},
        )

        state.vdc = 315.0
        state.cmd_status = 200
        state.cmd_payload = {"ok": True}
        state.commands.clear()
        fallback_calls.clear()
        ok = case.post_cmd(base, "START")
        add_case(
            results,
            "start_vdc_guard_blocks_before_http_or_fallback",
            (not ok) and fallback_calls == [] and state.commands == [],
            evidence={"ok": ok, "fallback_calls": list(fallback_calls), "commands": list(state.commands)},
        )

        state.vdc = 315.0
        state.include_vbus = True
        state.cmd_status = 200
        state.cmd_payload = {"ok": True}
        state.commands.clear()
        fallback_calls.clear()
        bench_gate_allowed["value"] = True
        os.environ["UNOQ_ALLOW_HV"] = "1"
        ok = case.post_cmd(base, "START")
        add_case(
            results,
            "allow_hv_allows_high_readable_vbus",
            ok and fallback_calls == [] and state.commands == ["START"],
            evidence={"ok": ok, "fallback_calls": list(fallback_calls), "commands": list(state.commands)},
        )

        state.include_vbus = False
        state.commands.clear()
        fallback_calls.clear()
        ok = case.post_cmd(base, "START")
        add_case(
            results,
            "allow_hv_does_not_bypass_missing_vbus",
            (not ok) and fallback_calls == [] and state.commands == [],
            evidence={"ok": ok, "fallback_calls": list(fallback_calls), "commands": list(state.commands)},
        )
        state.include_vbus = True
        os.environ.pop("UNOQ_ALLOW_HV", None)

        state.vdc = 0.0
        state.bp_bad = 1
        state.bp_bad_cnt = 0
        state.cmd_status = 200
        state.cmd_payload = {"ok": True}
        state.commands.clear()
        fallback_calls.clear()
        ok = case.post_cmd(base, "START")
        add_case(
            results,
            "legacy_bad_counter_blocks_before_http_or_fallback",
            (not ok) and fallback_calls == [] and state.commands == [],
            evidence={"ok": ok, "fallback_calls": list(fallback_calls), "commands": list(state.commands)},
        )
        state.bp_bad = 0
        state.bp_bad_cnt = 0

        state.vdc = 0.0
        state.cmd_status = 200
        state.cmd_payload = {"ok": True}
        state.commands.clear()
        fallback_calls.clear()
        active_guard.reset_cache()
        bench_gate_allowed["value"] = False
        ok = case.post_cmd(base, "START")
        add_case(
            results,
            "start_bench_gate_blocks_before_http_or_fallback",
            (not ok) and fallback_calls == [] and state.commands == [],
            evidence={"ok": ok, "fallback_calls": list(fallback_calls), "commands": list(state.commands)},
        )
    finally:
        case.post_cmd_adb_router = original_fallback
        case.start_allowed_by_bench_gate = original_start_allowed
        for name, value in old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        server.shutdown()
        server.server_close()

    failed = [r for r in results if not r.ok]
    summary = {
        "tool": "ui_pwm_case_selftest",
        "pass": len(failed) == 0,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [r.__dict__ for r in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class BenchGateResult:
    ok: bool
    ready: bool
    summary: str | None = None
    next_actions: list[str] | None = None
    detail: str = ""


_CACHE: dict[str, Any] = {"ts": 0.0, "result": None, "key": None}
UNGATED_START_ACK = "I_UNDERSTAND_ACTIVE_PWM_RISK"


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def cache_ttl_s() -> float:
    raw = os.environ.get("UNOQ_BENCH_GATE_CACHE_S", "5.0").strip()
    try:
        return max(0.0, float(raw))
    except Exception:
        return 5.0


def reset_cache() -> None:
    _CACHE["ts"] = 0.0
    _CACHE["result"] = None
    _CACHE["key"] = None


def cacheable_result(result: BenchGateResult) -> bool:
    # Never cache a green gate: every START attempt must prove the live bench
    # is still safe. Caching red results is fail-closed and only avoids log spam.
    return not (result.ok and result.ready)


def parse_bench_gate_stdout(stdout: str, returncode: int) -> BenchGateResult:
    payload = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
            break
        except Exception:
            continue
    if not isinstance(payload, dict):
        return BenchGateResult(ok=False, ready=False, detail=f"bench_gate_report produced no JSON, rc={returncode}")
    ready = bool(payload.get("ready_for_active_pwm"))
    next_actions = [str(item) for item in payload.get("next_actions", [])]
    summary = str(payload.get("summary")) if payload.get("summary") else None
    if ready and returncode == 0:
        return BenchGateResult(ok=True, ready=True, summary=summary, next_actions=next_actions)
    return BenchGateResult(
        ok=False,
        ready=ready,
        summary=summary,
        next_actions=next_actions,
        detail=f"bench gate not ready: ready_for_active_pwm={ready} rc={returncode} next_actions={next_actions}",
    )


def missing_live_url_result() -> BenchGateResult:
    return BenchGateResult(
        ok=False,
        ready=False,
        next_actions=["restore_hmi_safe_status"],
        detail=(
            "live bench-gate URL is required for START; "
            "pass url=... or set UNOQ_BENCH_GATE_URL"
        ),
    )


def run_bench_gate(timeout_s: float = 10.0, url: str | None = None) -> BenchGateResult:
    script = Path(__file__).resolve().with_name("bench_gate_report.py")
    gate_url = (url or os.environ.get("UNOQ_BENCH_GATE_URL", "")).strip()
    if not gate_url:
        return missing_live_url_result()
    cmd = [sys.executable, "-u", str(script)]
    cmd.extend(["--url", gate_url])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except Exception as exc:
        return BenchGateResult(ok=False, ready=False, detail=f"{type(exc).__name__}: {exc}")
    result = parse_bench_gate_stdout(proc.stdout, int(proc.returncode))
    if not result.ok and proc.stderr.strip():
        result.detail = (result.detail + "; stderr=" + proc.stderr.strip())[:1000]
    return result


def start_allowed_by_bench_gate(
    log_fn: Callable[[str], None] | None = print,
    runner: Callable[[], BenchGateResult] | None = None,
    url: str | None = None,
) -> bool:
    if truthy_env("UNOQ_ALLOW_UNGATED_START"):
        ack = os.environ.get("UNOQ_ALLOW_UNGATED_START_ACK", "").strip()
        if log_fn:
            if ack == UNGATED_START_ACK:
                log_fn(
                    "ERROR: START bench-gate bypass is disabled; "
                    "clear UNOQ_ALLOW_UNGATED_START and make bench_gate_report.py green instead"
                )
            else:
                log_fn(
                    "ERROR: START bench-gate bypass requested but this legacy override is disabled; "
                    "make bench_gate_report.py green instead"
                )
        return False

    ttl = cache_ttl_s()
    now = time.monotonic()
    gate_url = (url or os.environ.get("UNOQ_BENCH_GATE_URL", "")).strip()
    cache_key = ("runner", id(runner)) if runner is not None else ("url", gate_url or "offline")
    cached = _CACHE.get("result")
    if (
        isinstance(cached, BenchGateResult)
        and cacheable_result(cached)
        and _CACHE.get("key") == cache_key
        and ttl > 0.0
        and now - float(_CACHE.get("ts", 0.0)) <= ttl
    ):
        result = cached
    else:
        result = runner() if runner is not None else run_bench_gate(url=gate_url or None)
        if cacheable_result(result):
            _CACHE["result"] = result
            _CACHE["ts"] = now
            _CACHE["key"] = cache_key
        else:
            reset_cache()

    if result.ok and result.ready:
        return True
    if log_fn:
        msg = "ERROR: START blocked by bench gate"
        if result.summary:
            msg += f"; summary={result.summary}"
        if result.next_actions:
            msg += f"; next_actions={','.join(result.next_actions)}"
        if result.detail:
            msg += f"; detail={result.detail}"
        log_fn(msg)
    return False

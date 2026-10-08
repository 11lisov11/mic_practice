#!/usr/bin/env python3
"""Collect UNO Q status and authenticated logs over direct Wi-Fi HTTP only."""
from __future__ import annotations

import argparse
import json
import math
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/"):
        raise ValueError("Use an explicit http://host:port base URL without credentials or path")
    address = socket.gethostbyname(parsed.hostname)
    if address.startswith("127.") or address == "0.0.0.0":
        raise ValueError("Loopback/ADB-forward URLs are not Wi-Fi evidence")
    return raw.rstrip("/")


def read_token(path: str) -> str:
    token = Path(path).read_text(encoding="utf-8").strip() if path else os.environ.get("UNOQ_CONTROL_TOKEN", "").strip()
    if len(token) < 16 or "\r" in token or "\n" in token:
        raise ValueError("A separate UNO Q control token file or UNOQ_CONTROL_TOKEN is required")
    return token


def get_status(opener, base_url: str) -> dict:
    request = Request(base_url + "/api/status", headers={"Accept": "application/json"})
    with opener.open(request, timeout=8) as response:
        payload = json.load(response)
    if payload.get("ok") is not True or not isinstance(payload.get("data"), dict):
        raise RuntimeError("Wi-Fi status unavailable")
    return payload["data"]


def get_logs(opener, base_url: str, token: str, hours: float) -> str:
    request = Request(
        base_url + f"/api/logs?hours={hours:.3f}",
        headers={"X-UNOQ-Control-Token": token},
    )
    with opener.open(request, timeout=15) as response:
        return response.read().decode("utf-8")


def finite_number(status: dict, key: str) -> float | None:
    value = status.get(key)
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value)


def summarize(rows: list[dict], errors: list[str], logs: str, expect_idle: bool,
              max_vdc: float | None = None) -> dict:
    statuses = [row["status"] for row in rows if "status" in row]
    checks = {
        "wifi_status_received": len(statuses) > 0,
        "no_http_errors": not errors,
        "build_identity_stable": bool(statuses) and all(
            s.get("fw_build") == statuses[0].get("fw_build")
            and s.get("mc_fw_build") == statuses[0].get("mc_fw_build")
            for s in statuses
        ),
        "uart_fresh": bool(statuses) and all(
            (age := finite_number(s, "bp_age_ms")) is not None and 0 <= age < 300
            for s in statuses
        ),
    }
    first, last = (statuses[0], statuses[-1]) if statuses else ({}, {})
    for key in ("bp_good", "bp_bad", "bp_bad_cnt"):
        values = [finite_number(s, key) for s in statuses]
        checks[f"{key}_valid"] = bool(values) and all(
            value is not None and value >= 0 and (index == 0 or value >= values[index - 1])
            for index, value in enumerate(values)
        )
    if expect_idle:
        checks["idle_outputs_off"] = bool(statuses) and all(
            s.get("state") == "SAFE" and s.get("pwm") == 0
            and s.get("hmi_hv_armed") == 0
            and (flag := finite_number(s, "bp_status")) is not None
            and flag == int(flag) and (int(flag) & 0x22) == 0
            for s in statuses
        )
        checks["no_new_uart_errors"] = all(
            checks[f"{key}_valid"] and all(s[key] == first[key] for s in statuses)
            for key in ("bp_bad", "bp_bad_cnt")
        )
    if max_vdc is not None:
        checks["vdc_within_limit"] = bool(statuses) and all(
            (vdc := finite_number(s, "vdc")) is not None and 0 <= vdc <= max_vdc
            for s in statuses
        )
    detailed_keys = ("bp_bad_integrity", "bp_bad_sequence", "bp_superseded", "bp_clear_pending")
    detailed_available = bool(statuses) and all(
        finite_number(s, key) is not None for s in statuses for key in detailed_keys
    )
    return {
        "schema": "mic_ai.wifi_telemetry.v1",
        "pass": all(checks.values()),
        "checks": checks,
        "samples": len(statuses),
        "http_errors": errors,
        "first_builds": {key: first.get(key) for key in ("fw_build", "mc_fw_build")},
        "counters": {key: {"first": first.get(key), "last": last.get(key)} for key in ("bp_good", "bp_bad", "bp_bad_cnt")},
        "detailed_uart_counters_available": detailed_available,
        "detailed_uart_counters": {
            key: {"first": first.get(key), "last": last.get(key)} for key in detailed_keys
        } if detailed_available else None,
        "log_lines": len(logs.splitlines()),
        "max_vdc": max_vdc,
    }


def collect(base_url: str, token: str, seconds: float, interval: float, outdir: Path,
            expect_idle: bool, max_vdc: float | None = None) -> dict:
    outdir.mkdir(parents=True, exist_ok=False)
    opener = build_opener(ProxyHandler({}))
    rows: list[dict] = []
    errors: list[str] = []
    deadline = time.monotonic() + seconds
    with (outdir / "status.jsonl").open("w", encoding="utf-8") as stream:
        while True:
            row: dict = {"host_utc": utc_now()}
            try:
                row["status"] = get_status(opener, base_url)
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                errors.append(row["error"])
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
    logs = ""
    try:
        logs = get_logs(opener, base_url, token, min(24.0, seconds / 3600 + 1.0))
    except Exception as exc:
        errors.append(f"logs: {type(exc).__name__}: {exc}")
    (outdir / "logs.txt").write_text(logs, encoding="utf-8")
    summary = summarize(rows, errors, logs, expect_idle, max_vdc)
    summary["host_utc"] = utc_now()
    summary["duration_requested_s"] = seconds
    summary["transport"] = "direct_wifi_http_get_only"
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://192.168.1.138:8080")
    parser.add_argument("--token-file", default="", help="Local control-token file; or use UNOQ_CONTROL_TOKEN")
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--expect-idle", action="store_true", help="Fail if outputs enable or UART counters increase")
    parser.add_argument("--max-vdc", type=float, help="Fail if any reported DC-bus voltage exceeds this limit")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or not math.isfinite(args.interval) or not 1 <= args.seconds <= 3600 or not 0.1 <= args.interval <= 10:
        parser.error("seconds must be 1..3600 and interval 0.1..10")
    if args.max_vdc is not None and (not math.isfinite(args.max_vdc) or not 0 <= args.max_vdc <= 400):
        parser.error("max-vdc must be a finite value from 0 to 400 V")
    try:
        summary = collect(validate_url(args.url), read_token(args.token_file), args.seconds,
                          args.interval, args.outdir.resolve(), args.expect_idle, args.max_vdc)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

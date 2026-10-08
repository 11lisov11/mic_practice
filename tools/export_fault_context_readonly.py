#!/usr/bin/env python3
"""Download fault evidence over Wi-Fi without issuing controller commands."""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from run_wifi_nucleo_pwm_bench import WifiHmi
from verify_wifi_command_path import get_wifi_logs


def extract_events(logs: str, event_id: str) -> list[dict]:
    events = []
    marker = "MC_FAULT_CONTEXT "
    for line in logs.splitlines():
        if marker not in line:
            continue
        payload = line.split(marker, 1)[1]
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event_id") == event_id:
            events.append(event)
    return events


def summarize(events: list[dict]) -> dict:
    faults = [e for e in events if e.get("phase") == "fault"]
    after = [e["at"] for e in events if e.get("phase") == "after"]
    if len(faults) != 1:
        raise ValueError(f"Expected one fault event, got {len(faults)}")
    event = faults[0]
    at = event["at"]
    origin = at["observed_monotonic_s"]
    fields = ("state", "pwm", "vdc", "mc_fault", "mc_bad_cnt",
              "mc_fault_reason", "mc_last_bad_reason", "mc_last_uart_error_flags",
              "enc_bus_ok", "enc_errors", "enc_io_error", "mc_seq", "mc_age_ms")
    samples = event.get("before", []) + [at] + after
    return {
        "event_id": event["event_id"], "summary": event["summary"],
        "physical_source_identified": event["physical_source_identified"],
        "time_basis": event["time_basis"], "detail": event["detail"],
        "before_samples": len(event.get("before", [])), "after_samples": len(after),
        "after_span_s": round(max((s["observed_monotonic_s"] - origin
                                   for s in after), default=0), 3),
        "timeline": [{"relative_to_fault_s": round(s["observed_monotonic_s"] - origin, 3),
                      **{k: s.get(k) for k in fields}} for s in samples],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://192.168.1.138:8080")
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    token = getpass.getpass("Control token (not displayed): ")
    hmi = WifiHmi(args.url, token, [], via_wsl=True)
    try:
        status = hmi.status()
        logs = get_wifi_logs(hmi, token)
    finally:
        hmi.close()
    events = extract_events(logs, args.event_id)
    summary = summarize(events)
    args.outdir.mkdir(parents=True, exist_ok=True)
    for name, content in (("fault_context_complete.json", events),
                          ("fault_timeline.json", summary),
                          ("readonly_status.json", status)):
        (args.outdir / name).write_text(json.dumps(content, ensure_ascii=False, indent=2)
                                      + "\n", encoding="utf-8")
    (args.outdir / "wifi_logs_complete.txt").write_text(logs, encoding="utf-8")
    print(json.dumps({"summary": summary, "current_status": {
        k: status.get(k) for k in ("state", "pwm", "vdc", "hmi_hv_armed",
                                  "mc_bad_cnt", "mc_last_bad_reason")
    }}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

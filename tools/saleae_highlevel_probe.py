#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from saleae import automation


def append_log(path: Path, msg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='milliseconds')} {msg}\n")


def post_cmd(base: str, cmd: str, timeout_s: float = 2.0) -> str:
    data = json.dumps({"cmd": cmd}).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/api/cmd",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return resp.read().decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description="Minimal Saleae high-level Automation API probe.")
    ap.add_argument("--port", type=int, default=10430)
    ap.add_argument("--channels", default="0,1")
    ap.add_argument("--rate", type=int, default=6_000_000)
    ap.add_argument("--duration", type=float, default=0.12)
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--url", default="http://127.0.0.1:18080")
    ap.add_argument("--cmd", action="append", default=[])
    ap.add_argument(
        "--outdir",
        default=str(Path(__file__).resolve().parent / "_preflight_exports"),
    )
    args = ap.parse_args()

    channels = [int(x) for x in args.channels.split(",") if x.strip()]
    run_dir = Path(args.outdir) / ("saleae_highlevel_probe_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    log_path = run_dir / "probe.log"
    append_log(log_path, f"START channels={channels} rate={args.rate} duration={args.duration}")

    try:
        append_log(log_path, "connect_begin")
        with automation.Manager.connect(port=args.port) as manager:
            append_log(log_path, f"connect_ok app={manager.get_app_info()}")
            devices = manager.get_devices()
            append_log(log_path, f"devices={devices}")

            device_kwargs = {
                "enabled_digital_channels": channels,
                "digital_sample_rate": args.rate,
            }
            if args.threshold is not None:
                device_kwargs["digital_threshold_volts"] = args.threshold
            device_configuration = automation.LogicDeviceConfiguration(**device_kwargs)
            capture_configuration = automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=args.duration)
            )

            append_log(log_path, "start_capture_begin")
            with manager.start_capture(
                device_configuration=device_configuration,
                capture_configuration=capture_configuration,
            ) as capture:
                append_log(log_path, "start_capture_ok")
                time.sleep(min(0.03, max(0.0, args.duration / 4.0)))
                for cmd in args.cmd:
                    append_log(log_path, f"cmd_begin {cmd}")
                    try:
                        resp = post_cmd(args.url, cmd)
                        append_log(log_path, f"cmd_ok {cmd} {resp}")
                    except Exception as exc:
                        append_log(log_path, f"cmd_err {cmd} {exc!r}")
                append_log(log_path, "wait_begin")
                capture.wait()
                append_log(log_path, "wait_ok")
                append_log(log_path, "export_begin")
                capture.export_raw_data_csv(directory=str(run_dir), digital_channels=channels)
                append_log(log_path, "export_ok")
    except Exception as exc:
        append_log(log_path, f"ERROR {type(exc).__name__}: {exc}")
        print(f"PROBE_LOG={log_path}")
        raise

    csv_path = run_dir / "digital.csv"
    summary = {"run_dir": str(run_dir), "csv": str(csv_path), "channels": channels, "edges": {}}
    if csv_path.exists():
        prev = {ch: None for ch in channels}
        rows = 0
        with csv_path.open(newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                rows += 1
                for idx, ch in enumerate(channels, start=1):
                    if idx >= len(row):
                        continue
                    val = 1 if row[idx] == "1" else 0
                    if prev[ch] is None:
                        summary["edges"][str(ch)] = 0
                    elif val != prev[ch]:
                        summary["edges"][str(ch)] = summary["edges"].get(str(ch), 0) + 1
                    prev[ch] = val
        summary["rows"] = rows
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    append_log(log_path, f"DONE summary={summary_path}")
    print(f"PROBE_LOG={log_path}")
    print(f"SUMMARY={summary_path}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Capture G431 TIM1 pins using Saleae; never send commands to either MCU."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from saleae_pwm_analyze import analyze_csv


CHANNEL_MAP = {
    0: {"signal": "UH", "gpio": "PA8", "connector": "CN10-23"},
    1: {"signal": "UL", "gpio": "PA7", "connector": "CN10-15"},
    2: {"signal": "VH", "gpio": "PA9", "connector": "CN10-21"},
    3: {"signal": "VL", "gpio": "PB0", "connector": "CN7-34"},
    4: {"signal": "WH", "gpio": "PA10", "connector": "CN10-33"},
    5: {"signal": "WL", "gpio": "PB1", "connector": "CN10-24"},
}


def capture_checks(analysis: dict, expect_pwm: bool) -> dict:
    channels = analysis["channels"]
    all_present = all(str(ch) in channels for ch in CHANNEL_MAP)
    all_low = all_present and all(
        channels[str(ch)]["initial"] == 0
        and channels[str(ch)]["final"] == 0
        and channels[str(ch)]["edges"] == 0 for ch in CHANNEL_MAP
    )
    all_active = all_present and all(channels[str(ch)]["edges"] >= 4 for ch in CHANNEL_MAP)
    checks = {
        "all_six_channels_present": all_present,
        "no_overlap": analysis["no_overlap_pass"],
        "timing_resolution": analysis["timing_resolution_pass"],
        "all_six_active" if expect_pwm else "all_six_static_low": all_active if expect_pwm else all_low,
    }
    return {"checks": checks, "pass": all(checks.values())}


def main() -> int:
    from saleae import automation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, help="Exact Saleae device ID")
    parser.add_argument("--port", type=int, default=10430)
    parser.add_argument("--rate", type=int, default=24_000_000)
    parser.add_argument("--duration", type=float, default=0.2)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--expect-pwm", action="store_true", help="Analysis only; does not enable PWM")
    args = parser.parse_args()
    if not 0 < args.duration <= 10 or args.rate <= 0:
        parser.error("duration must be in (0, 10] seconds and rate must be positive")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with automation.Manager.connect(port=args.port) as manager:
        matches = [d for d in manager.get_devices() if d.device_id == args.device and not d.is_simulation]
        if len(matches) != 1:
            raise RuntimeError("Expected exactly one matching physical Saleae analyzer")
        app = manager.get_app_info()
        with manager.start_capture(
            device_id=args.device,
            device_configuration=automation.LogicDeviceConfiguration(
                enabled_digital_channels=list(CHANNEL_MAP), digital_sample_rate=args.rate,
            ),
            capture_configuration=automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=args.duration),
            ),
        ) as capture:
            capture.wait()
            capture.save_capture(str(out / "nucleo_pwm.sal"))
            capture.export_raw_data_csv(directory=str(out / "csv"), digital_channels=list(CHANNEL_MAP))
    analysis = analyze_csv(out / "csv" / "digital.csv", expect_pwm=args.expect_pwm,
                           selected_sample_rate_hz=args.rate, max_sample_period_ns=100)
    report = {
        "host_utc": datetime.now(timezone.utc).isoformat(),
        "device_id": args.device,
        "is_simulation": False,
        "logic_version": app.app_version,
        "sample_rate_hz": args.rate,
        "requested_duration_s": args.duration,
        "channel_map": CHANNEL_MAP,
        "motor_commands_sent": [],
        "scope": "observed_pin_levels_only_not_power_stage_validation",
        "expect_pwm": args.expect_pwm,
        **capture_checks(analysis, args.expect_pwm),
        "analysis": analysis,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

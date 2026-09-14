#!/usr/bin/env python3
"""Passive capture of both ends of the UNO Q TX -> Nucleo RX wire."""
import argparse
import json
from pathlib import Path

from saleae_pwm_analyze import channel_summary, load_csv


def main():
    from saleae import automation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--confirm-probes", action="store_true",
                        help="CH6=UNO Q D1/TX, CH7=Nucleo PB7/CN7-21; power stage disconnected")
    args = parser.parse_args()
    if not args.confirm_probes:
        parser.error("Confirm probe placement and a disconnected power stage")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with automation.Manager.connect(port=10430) as manager:
        if not any(d.device_id == args.device and not d.is_simulation for d in manager.get_devices()):
            raise RuntimeError("Requested physical analyzer not available")
        with manager.start_capture(
            device_id=args.device,
            device_configuration=automation.LogicDeviceConfiguration(
                enabled_digital_channels=list(range(8)), digital_sample_rate=24000000),
            capture_configuration=automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=1.0)),
        ) as capture:
            capture.wait()
            exports = []
            for ch, label in ((6, "UNO_Q_TX_source"), (7, "Nucleo_RX_destination")):
                analyzer = capture.add_analyzer("Async Serial", label=label, settings={
                    "Input Channel": ch,
                    "Bit Rate (Bits/s)": 115200,
                    "Bits per Frame": "8 Bits per Transfer (Standard)",
                    "Stop Bits": "1 Stop Bit (Standard)",
                    "Parity Bit": "No Parity Bit (Standard)",
                    "Significant Bit": "Least Significant Bit Sent First (Standard)",
                    "Signal inversion": "Non Inverted (Standard)",
                    "Mode": "Normal",
                })
                exports.append(automation.DataTableExportConfiguration(analyzer, automation.RadixType.HEXADECIMAL))
            capture.save_capture(str(out / "uart_wire.sal"))
            capture.export_raw_data_csv(directory=str(out / "csv"), digital_channels=list(range(8)))
            capture.export_data_table(filepath=str(out / "decoded_uart.csv"), analyzers=exports)
    times, values = load_csv(out / "csv/digital.csv", list(range(8)))
    stats = {str(ch): channel_summary(times, values[ch]) for ch in range(8)}
    mismatch = sum(times[i + 1] - times[i] for i in range(len(times) - 1) if values[6][i] != values[7][i])
    report = {
        "scope": "passive_same_wire_capture_not_bidirectional_link_validation",
        "sample_rate_hz": 24000000,
        "probes": {"6": "UNO Q D1/TX", "7": "Nucleo PB7/CN7-21"},
        "motor_commands_sent": [],
        "channels": stats,
        "source_active": stats["6"]["edges"] >= 4,
        "destination_active": stats["7"]["edges"] >= 4,
        "different_level_time_s": mismatch,
        "pwm_all_low": all(stats[str(ch)]["edges"] == 0 and stats[str(ch)]["initial"] == 0 for ch in range(6)),
        "note": "Inspect decoded_uart.csv for frame bytes/errors; matching idle levels do not prove continuity.",
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

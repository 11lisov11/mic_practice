"""Observe direct AS5600 and UART telemetry; never issue a motor command."""
import argparse
import json
import time
from pathlib import Path

from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status


def controller_link_evidence(rows, expected_build):
    """A saturated 16-bit counter needs independent, changing ACK sequences."""
    result = {"controller_link_pass": False, "counter_saturated": False,
              "new_uart_messages": None, "observed_sequence_changes": 0}
    try:
        if len(rows) < 2:
            return result
        counts = [r["mc_good"] for r in rows]
        if any(not isinstance(c, int) or not 0 <= c <= 65535 for c in counts):
            return result
        if any(b < a for a, b in zip(counts, counts[1:])):
            return result
        saturated = counts[-1] == 65535
        sequences = [r.get("mc_seq") for r in rows]
        valid_sequences = all(isinstance(s, int) and 0 <= s <= 255 for s in sequences)
        changes = sum(a != b for a, b in zip(sequences, sequences[1:])) if valid_sequences else 0
        progress = counts[-1] > counts[0] or (saturated and changes > 0)
        result.update(counter_saturated=saturated,
                      new_uart_messages=None if saturated else counts[-1] - counts[0],
                      counter_increment_lower_bound=counts[-1] - counts[0],
                      observed_sequence_changes=changes,
                      controller_link_pass=(progress
                          and all(r["mc_fw_build"] == expected_build and 0 <= r["mc_age_ms"] < 300 for r in rows)
                          and all(r[k] == rows[0][k] for r in rows
                                  for k in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence"))))
    except (KeyError, TypeError, ValueError):
        pass
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--fw-build", type=int, default=2026100704)
    parser.add_argument("--mc-fw-build", type=int, default=2026100704)
    args = parser.parse_args()
    if not 1 <= args.duration <= 120:
        parser.error("duration must be within 1..120 seconds")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    hmi = WifiHmi("http://192.168.1.138:8080", "", [], via_wsl=True)
    keys = ("state", "pwm", "fw_build", "mc_fw_build", "vdc", "bp_fault",
            "enc_source", "enc_bus_ok", "enc_status", "enc_ok", "enc_raw", "enc_deg",
            "enc_rpm", "enc_speed_ok", "enc_reads", "enc_errors", "enc_io_error",
            "enc_init_error", "enc_scl", "enc_sda", "enc_age_ms", "mc_age_ms",
            "mc_good", "mc_seq", "mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence",
            "mc_last_bad_reason", "mc_last_uart_error_flags", "hmi_hv_armed",
            "hmi_vbus_hv_calibrated", "hmi_vbus_calibration_reason")
    rows = []
    report = {"scope": "read-only Wi-Fi; no ARM/START, no motor rotation test",
              "actuation_commands_sent": 0, "hardware_validated": False}
    try:
        wait_status(hmi, lambda s: s.get("fw_build") == args.fw_build, 25, "AS5600 image boot")
        started = time.monotonic()
        while time.monotonic() - started < args.duration:
            status = hmi.status()
            rows.append({"host_monotonic_s": time.monotonic(), **{k: status.get(k) for k in keys}})
            if status.get("state") != "SAFE" or status.get("pwm") != 0 or status.get("hmi_hv_armed") != 0:
                raise RuntimeError("Read-only probe stopped: drive is not disarmed SAFE")
            time.sleep(.2)
        first, last = rows[0], rows[-1]
        report.update(controller_link_evidence(rows, args.mc_fw_build))
        report["sensor_link_pass"] = all(
            r["enc_source"] == "uno_q_i2c2" and r["enc_bus_ok"] == 1
            and r["enc_init_error"] == 0 and 0 <= r["enc_age_ms"] < 100
            and r["enc_errors"] == first["enc_errors"] for r in rows)
        report["magnet_angle_valid"] = all(r["enc_ok"] == 1 for r in rows)
        report["first"] = first
        report["last"] = last
        report["samples"] = len(rows)
        report["max_uart_age_ms"] = max(r["mc_age_ms"] for r in rows)
        report["pass"] = report["controller_link_pass"] and report["sensor_link_pass"]
    except Exception as exc:
        report["error"] = str(exc)
        report["pass"] = False
    finally:
        hmi.close()
        (out / "samples.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in (
        "pass", "controller_link_pass", "sensor_link_pass", "magnet_angle_valid",
        "new_uart_messages", "counter_saturated", "observed_sequence_changes",
        "max_uart_age_ms", "last", "error")}, indent=2))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

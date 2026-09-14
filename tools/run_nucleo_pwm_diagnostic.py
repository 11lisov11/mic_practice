#!/usr/bin/env python3
"""Isolated-board PWM test with unconditional restoration of the MCSDK image."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from nucleo_logic_capture import CHANNEL_MAP, capture_checks
from saleae_pwm_analyze import analyze_csv, channel_summary, load_csv, transitions


def analyze_burst(csv: Path, rate: int) -> dict:
    analysis = analyze_csv(csv, expect_pwm=True, selected_sample_rate_hz=rate, max_sample_period_ns=100)
    checks = capture_checks(analysis, True)["checks"]
    checks["initial_and_final_low"] = all(c["initial"] == c["final"] == 0 for c in analysis["channels"].values())
    checks["carrier_16khz"] = all(abs(c["freq_hz_from_rising"] - 16000) <= 160 for c in analysis["channels"].values())
    checks["deadtime_1_2_to_1_5_us"] = all(
        p["min_gap_s"] is not None and 1.2e-6 <= p["min_gap_s"] <= 1.5e-6
        for p in analysis["pairs"].values())
    times, values = load_csv(csv, list(CHANNEL_MAP))
    edges = {ch: transitions(times, values[ch]) for ch in CHANNEL_MAP}
    duration = None
    active_duty = {}
    if all(edges.values()):
        first = min(e[0]["time"] for e in edges.values())
        last = max(e[-1]["time"] for e in edges.values())
        duration = last - first
        start = max(e[0]["time"] for e in edges.values()) + 2 / 16000
        end = min(e[-1]["time"] for e in edges.values()) - 2 / 16000
        indexes = [i for i, t in enumerate(times) if start <= t <= end]
        if len(indexes) >= 2:
            for ch in CHANNEL_MAP:
                stats = channel_summary([times[i] for i in indexes], [values[ch][i] for i in indexes])
                active_duty[str(ch)] = stats["duty_ratio"]
    checks["burst_290_to_310_ms"] = duration is not None and 0.290 <= duration <= 0.310
    loss = (228 / 170000000) * 16000
    expected = [0.2 - loss, 0.8 - loss, 0.5 - loss, 0.5 - loss, 0.8 - loss, 0.2 - loss]
    checks["duty_identifies_phase_pairs"] = len(active_duty) == 6 and all(
        abs(active_duty[str(ch)] - expected[ch]) <= 0.006 for ch in CHANNEL_MAP)
    return {"checks": checks, "pass": all(checks.values()), "burst_duration_s": duration,
            "active_duty": active_duty, "expected_active_duty": expected, "analysis": analysis}


def main() -> int:
    from saleae import automation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-isolated-nucleo", action="store_true")
    parser.add_argument("--stlink", required=True)
    parser.add_argument("--logic-device", required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_isolated_nucleo:
        parser.error("Physically disconnect the IPM/power stage and confirm the isolated Nucleo first")
    root = Path(__file__).resolve().parents[1]
    image = root / "nucleo_g431_pwm_diag_pio/.pio/build/isolated_logic_only/firmware.bin"
    elf = image.with_suffix(".elf")
    production = root / "firmware/ready_to_flash/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"
    programmer = Path("C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe")
    nm = Path.home() / ".platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-nm.exe"
    subprocess.run([sys.executable, str(root / "tools/verify_board_flash_package.py"), str(production.parents[1])], check=True)
    for path in (image, elf, production, programmer, nm):
        if not path.is_file():
            raise FileNotFoundError(path)
    symbols = {}
    for line in subprocess.check_output([str(nm), str(elf)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].startswith("diag_"):
            symbols[parts[2]] = int(parts[0], 16)
    for name in ("diag_identity", "diag_request", "diag_state", "diag_timer_hz", "diag_arr", "diag_dtg"):
        if name not in symbols or not 0x20000000 <= symbols[name] <= 0x20007FFC or symbols[name] % 4:
            raise RuntimeError(f"Invalid SRAM symbol: {name}")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"host_utc": datetime.now(timezone.utc).isoformat(), "stlink": args.stlink,
              "logic_device": args.logic_device, "channel_map": CHANNEL_MAP, "symbols": symbols,
              "diagnostic_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
              "production_hex_sha256": hashlib.sha256(production.read_bytes()).hexdigest(),
              "restored_production": False, "hardware_drive_validated": False}
    counter = 0

    def program(arguments: list[str], hotplug: bool = False) -> str:
        nonlocal counter
        counter += 1
        connect = ["-c", "port=SWD", "mode=HOTPLUG" if hotplug else "mode=UR", "sn=" + args.stlink]
        if not hotplug:
            connect.append("reset=HWrst")
        command = [str(programmer), *connect, *arguments]
        result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=45)
        (out / f"programmer_{counter:02d}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Programmer failed; see programmer_{counter:02d}.log")
        return result.stdout

    def word(name: str) -> int:
        target = out / f"read_{counter + 1:02d}_{name}.bin"
        program(["-u", hex(symbols[name]), "4", str(target)], hotplug=True)
        raw = target.read_bytes()
        if len(raw) != 4:
            raise RuntimeError("Short memory read")
        return int.from_bytes(raw, "little")

    def capture(manager, name: str, trigger: bool = False) -> Path:
        folder = out / name
        folder.mkdir()
        with manager.start_capture(
            device_id=args.logic_device,
            device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(CHANNEL_MAP), digital_sample_rate=24000000),
            capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=1.2 if trigger else 0.2)),
        ) as cap:
            if trigger:
                time.sleep(0.1)
                # The request is consumed immediately, so RAM write verification is not applicable.
                program(["-w32", hex(symbols["diag_request"]), "0x504D5744", "-nv"], hotplug=True)
            cap.wait()
            cap.save_capture(str(folder / "capture.sal"))
            cap.export_raw_data_csv(directory=str(folder / "csv"), digital_channels=list(CHANNEL_MAP))
        return folder / "csv/digital.csv"

    error = None
    with automation.Manager.connect(port=10430) as manager:
        devices = [d for d in manager.get_devices() if d.device_id == args.logic_device and not d.is_simulation]
        if len(devices) != 1:
            raise RuntimeError("Physical analyzer unavailable; no flash changes made")
        try:
            print("Writing isolated diagnostic; outputs remain off until the explicit SRAM request.", flush=True)
            program(["-w", str(image), "0x08000000", "-v", "-rst"])
            time.sleep(0.5)
            report["boot_state"] = {name: word(name) for name in symbols}
            expected = {"diag_identity": 0x47343144, "diag_state": 1, "diag_request": 0,
                        "diag_timer_hz": 170000000, "diag_arr": 5312, "diag_dtg": 114}
            if any(report["boot_state"].get(k) != v for k, v in expected.items()):
                raise RuntimeError("Diagnostic not ready; will not enable PWM")
            baseline = analyze_csv(capture(manager, "diagnostic_boot"), selected_sample_rate_hz=24000000)
            report["diagnostic_boot"] = capture_checks(baseline, False)
            if not report["diagnostic_boot"]["pass"]:
                raise RuntimeError("Unexpected activity before diagnostic request")
            print("Capturing one 300 ms PWM burst.", flush=True)
            report["burst"] = analyze_burst(capture(manager, "burst", trigger=True), 24000000)
            report["state_after_burst"] = word("diag_state")
            # A second request without reset must not produce a second burst.
            repeat = analyze_csv(capture(manager, "second_request_rejected", trigger=True), selected_sample_rate_hz=24000000)
            report["second_request_rejected"] = capture_checks(repeat, False)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            report["error"] = error
        finally:
            print("Restoring and verifying the production MCSDK image.", flush=True)
            try:
                program(["-w", str(production), "-v", "-rst"])
                report["restored_production"] = True
            except Exception as exc:
                report["restore_error"] = str(exc)
                error = "Production restore failed; do not attach a power stage"
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if report["restored_production"]:
            try:
                time.sleep(0.5)
                final = analyze_csv(capture(manager, "production_restored"), selected_sample_rate_hz=24000000)
                report["production_outputs_low"] = capture_checks(final, False)
            except Exception as exc:
                error = f"Post-restoration capture failed: {type(exc).__name__}: {exc}"
                report["final_capture_error"] = error
    report["pass"] = not error and all((report.get("burst", {}).get("pass", False),
        report.get("state_after_burst") == 3, report.get("second_request_rejected", {}).get("pass", False),
        report.get("production_outputs_low", {}).get("pass", False), report["restored_production"]))
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

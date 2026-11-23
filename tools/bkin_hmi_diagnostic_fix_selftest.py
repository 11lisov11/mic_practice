"""Regression checks for retained BKIN diagnostics and honest sample validity."""
import argparse
import importlib.util
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWN_CAPTURE = ROOT / "artifacts/live_bench_20261017/manual_scalar_5hz_to_25_ipm_trip_run1/bkin_trace_readback.json"


def load_server(path: Path):
    spec = importlib.util.spec_from_file_location("bkin_hmi_fix_candidate", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def d1_hex(module, *, age_ms=60000, state=6, start_window=1):
    values = {name: 0 for name in module._BREAK_FIELDS}
    values.update(magic=0x314B5242, schema=2, bytes=92, tick_ms=65000,
                  tim_sr=0x80, tim_bdtr=0x9000, gpioa_idr=0x40,
                  context_valid=1, context_tick_ms=64967, motor_state=state,
                  reference_speed_unit=227, vbus_v=318, temperature_deci_c=600,
                  start_window=start_window)
    raw = struct.pack("<23I", *(values[name] & 0xFFFFFFFF for name in module._BREAK_FIELDS))
    return raw.hex()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    module = load_server(candidate / "server.py")
    checks = []

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)

    saved = json.loads(KNOWN_CAPTURE.read_text(encoding="utf-8"))
    d1 = {"kind": "first_since_boot", "captured": True,
          "event": {"pa6_high_at_irq": True}}
    status = module.bkin_wave_status({
        "mc_fw_build": 2026101506, "mc_age_ms": 22,
        "mc_break_wave_hex": saved["raw_record_hex"],
        "mc_break_wave_age_ms": 586228, "mc_break_snapshots": [d1],
    })
    check("real saved 586-second trace remains readable", status["available"] and status["age_ms"] == 586228)
    check("combined BKINP/BKP polarity is decoded active-low",
          status["active_level"] == 0 and status["active_polarity"] == "LOW")
    check("saved low-only window is shown as active-level samples", status["active_sample_count"] == 1024)
    check("legacy firmware sample completeness is marked unverified",
          status["pa6_dma_count_verified"] is False and status["sample_validity"] == "unverified_elapsed_time_only_no_dma_count")
    check("IRQ high is shown alongside the saved window", status["irq_pa6_high"] is True)
    check("sample window remains explicitly 1024 samples", status["valid_sample_count"] == 1024)

    raw = bytearray.fromhex(saved["raw_record_hex"])
    for index in range(128): raw[32 + index] = 0xFF
    for index in (1021, 1022, 1023):
        raw[32 + index // 8] &= ~(1 << (index & 7))
    pulse = module.bkin_wave_status({
        "mc_fw_build": 2026101506, "mc_age_ms": 10,
        "mc_break_wave_hex": raw.hex(), "mc_break_wave_age_ms": 600000,
        "mc_break_snapshots": [d1],
    })
    check("active-low pulse at capture edge is decoded", pulse["active_sample_count"] == 3)
    check("boundary is labeled instead of claiming exact pulse width",
          pulse["active_intervals"] == [{"from_us": -2, "to_us": 1, "includes_capture_boundary": True}])
    check("stale current Nucleo link still blocks passive trace display",
          module.bkin_wave_status({"mc_fw_build": 2026101506, "mc_age_ms": 300,
              "mc_break_wave_hex": saved["raw_record_hex"], "mc_break_wave_age_ms": 600000})["reason"] == "stale_peer")

    kv = {"bp_fw_build": "2026101506", "bp_age_ms": "20",
          "mc_break0_hex": d1_hex(module), "mc_break0_age_ms": "60000"}
    decoded = module.break_wire_status(kv)["mc_break_snapshots"][0]
    check("retained D1 event stays available after five seconds", decoded["captured"] and decoded["age_ms"] == 60000)
    check("RUN context overrides the stuck start-window marker", not decoded["event"]["during_start_request_window"])
    check("raw marker defect stays visible for diagnosis", decoded["event"]["start_window_flag_raw"] and
          decoded["event"]["start_window_flag_stale_after_run"])
    pre_run = module.break_wire_status({"bp_fw_build": "2026101506", "bp_age_ms": "20",
        "mc_break0_hex": d1_hex(module, age_ms=60000, state=1), "mc_break0_age_ms": "60000"})["mc_break_snapshots"][0]
    check("non-RUN startup context remains classified as startup", pre_run["event"]["during_start_request_window"])

    js = (candidate / "static/app.js").read_text(encoding="utf-8")
    check("browser text names active-low PA6", "Активный PA6 LOW" in js)
    check("browser text reports snapshot age and pulse limitation",
          "снимок ${ageText}" in js and "не подтверждены счётчиком DMA" in js)
    report = {"pass": True, "checks": checks, "check_count": len(checks),
              "hardware_commands": 0, "mcu_flash_commands": 0, "actuation_commands": 0,
              "scope": "Saved-event decoder and candidate browser text; no device access"}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pass": True, "check_count": len(checks)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

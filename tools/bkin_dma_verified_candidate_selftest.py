"""Host-side checks for the DMA-count-verified BKIN candidate."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "artifacts/live_bench_20261017/bkin_dma_verified_pair_r1"
SERVER = CANDIDATE / "web_hmi/server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("bkin_dma_candidate_server", SERVER)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load candidate HMI parser")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def record(valid_count: int, remaining: int, flags: int, low_index: int | None = None) -> str:
    raw = bytearray(160)
    struct.pack_into("<8I", raw, 0, 0x314E4B42, 2, 160, 1234, 1000,
                     valid_count, remaining, flags)
    raw[32:160] = b"\xff" * 128
    if low_index is not None:
        raw[32 + low_index // 8] &= ~(1 << (low_index & 7))
    return raw.hex()


def check(condition: bool, name: str, failures: list[str]) -> None:
    if not condition:
        failures.append(name)


def main() -> int:
    failures: list[str] = []
    server = load_server()
    decode = lambda hex_record, build=2026101702: server.bkin_wave_status({
        "mc_fw_build": build, "mc_break_wave_hex": hex_record,
        "mc_break_wave_age_ms": 25,
    })

    partial = decode(record(4, 1020, 0x10, 1022))
    check(partial.get("available") is True and partial.get("dma_count_verified") is True,
          "partial transfer accepted only with recorded CNDTR", failures)
    check(partial.get("valid_sample_count") == 4 and partial.get("unknown_prefix_samples") == 1020,
          "CNDTR derives valid partial count", failures)
    check(partial.get("active_intervals") == [{"from_us": -1, "to_us": 0,
          "includes_capture_boundary": False}], "active-low pulse decoded at recorded index", failures)

    full = decode(record(1024, 1018, 0x16, 1023))
    check(full.get("available") is True and full.get("sample_validity") == "dma_verified_full",
          "TCIF certifies a complete circular buffer", failures)
    check(full.get("dma_htif") is True and full.get("dma_tcif") is True,
          "raw half-transfer and transfer-complete flags are exposed", failures)

    none = decode(record(0, 1024, 0x10))
    check(none.get("available") is True and none.get("sample_validity") == "dma_no_transfers",
          "elapsed time cannot invent samples when DMA made no transfers", failures)
    err = decode(record(0, 1020, 0x18))
    check(err.get("available") is True and err.get("sample_validity") == "dma_transfer_error"
          and err.get("valid_sample_count") == 0, "DMA error invalidates the trace", failures)
    mismatch = decode(record(1, 1020, 0x10))
    check(mismatch.get("reason") == "dma_count_mismatch",
          "inconsistent count/remaining pair is rejected", failures)
    wrong_build = decode(record(4, 1020, 0x10), 2026101506)
    check(wrong_build.get("reason") == "wrong_peer_build", "wrong peer is rejected", failures)

    main_c = (CANDIDATE / "nucleo/Src/main.c").read_text(encoding="utf-8-sig")
    wire = (CANDIDATE / "UNOQ_MOTOR/bkin_wave_wire.h").read_text(encoding="utf-8-sig")
    app = (CANDIDATE / "web_hmi/static/app.js").read_text(encoding="utf-8-sig")
    manifest = json.loads((CANDIDATE / "manifest.json").read_text(encoding="utf-8"))
    check("mic_bkin_start_tick_ms" not in main_c and "mic_bkin_filled_at_event" not in main_c,
          "elapsed-time completeness heuristic removed", failures)
    check("DMA2_Channel1->CNDTR" in main_c and "DMA2->ISR & 0x0FU" in main_c,
          "DMA count and channel flags are captured at freeze", failures)
    check("bw_u32(rx->data+4)!=2U" in wire and "bw_u32(rx->data+24)>1024U" in wire,
          "Uno accepts only schema 2 and validates CNDTR", failures)
    check("счётчик DMA подтверждает" in app and "start_window_flag_stale_after_run" in app,
          "simplified UI reports capture quality and stale start marker", failures)
    check(manifest.get("pair") == [2026101703, 2026101702] and
          manifest.get("mcu_flash_commands") == 0 and manifest.get("hv_release_approved") is False,
          "candidate manifest keeps flash and HV release disabled", failures)
    check(server.manual_scalar_supported({"fw_build": 2026101703, "mc_fw_build": 2026101702,
          "manual_scalar_capable": 1}), "exact diagnostic pair passes the manual V/f identity gate", failures)
    check(not server.manual_scalar_supported({"fw_build": 2026101703, "mc_fw_build": 2026101506,
          "manual_scalar_capable": 1}), "mixed diagnostic/production pair remains rejected", failures)
    server_text = SERVER.read_text(encoding="utf-8-sig")
    check("in (2026101502,2026101504,2026101506,2026101702) and" in server_text,
          "HV identity guard covers the new Nucleo build", failures)

    report = {"pass": not failures, "checks": 17 - len(failures),
              "failures": failures, "hardware_commands": 0,
              "mcu_flash_commands": 0, "motor_commands": 0,
              "scope": "Host parser and source invariants only; no device access"}
    out = CANDIDATE / "selftest/report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

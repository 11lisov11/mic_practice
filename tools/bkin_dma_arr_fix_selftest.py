"""Offline validation for the nonzero-ARR BKIN DMA capture fix."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "artifacts/live_bench_20261017/bkin_dma_arr_fix_r1"
PREDECESSOR = ROOT / "artifacts/live_bench_20261017/bkin_dma_boot_armed_r1"
SAMPLE_HZ = 1_000_000


def load_server():
    path = CANDIDATE / "web_hmi/server.py"
    spec = importlib.util.spec_from_file_location("bkin_dma_arr_fix_hmi", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load HMI parser")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_record(count: int, remaining: int, flags: int, low_index: int | None = None) -> str:
    raw = bytearray(160)
    struct.pack_into("<8I", raw, 0, 0x314E4B42, 2, 160, 1234, 1000,
                     count, remaining, flags)
    raw[32:160] = b"\xff" * 128
    valid_from = 1024 - count
    if low_index is not None:
        if not valid_from <= low_index < 1024:
            raise ValueError("low sample must be in the recorded portion")
        byte_index = 32 + low_index // 8
        raw[byte_index] &= ~(1 << (low_index & 7))
    return raw.hex()


def main() -> int:
    failures: list[str] = []
    def check(ok: bool, label: str) -> None:
        if not ok:
            failures.append(label)

    source = (CANDIDATE / "nucleo/Src/main.c").read_text(encoding="utf-8-sig")
    old_source = (PREDECESSOR / "nucleo/Src/main.c").read_text(encoding="utf-8-sig")
    capture = source.split("static void mic_bkin_capture_start(void) {", 1)[1].split(
        "static void mic_bkin_capture_stop(", 1)[0]
    check("TIM2->PSC = 0U;" in capture and "TIM2->ARR = period_cycles - 1U;" in capture,
          "TIM2 is programmed with a nonzero autoreload period")
    check("TIM2->ARR = 0U;" not in capture and "period_cycles < 2U" in capture,
          "zero ARR is rejected before timer start")

    for timer_hz in (80_000_000, 120_000_000, 160_000_000, 170_000_000):
        cycles = timer_hz // SAMPLE_HZ
        check(timer_hz % SAMPLE_HZ == 0 and cycles >= 2 and
              timer_hz // (cycles) == SAMPLE_HZ,
              f"1-MHz period is exact for timer clock {timer_hz}")

    old_calc = (
        "  uint32_t timer_hz = HAL_RCC_GetPCLK1Freq();\n"
        "  if (clocks.APB1CLKDivider != RCC_HCLK_DIV1) timer_hz *= 2U;\n"
        "  if (timer_hz < MIC_BKIN_SAMPLE_HZ || timer_hz % MIC_BKIN_SAMPLE_HZ != 0U) {\n"
        "    mic_bkin_capture_state = MIC_BKIN_CAPTURE_ERROR;\n"
        "    return;\n"
        "  }\n"
        "  const uint32_t prescaler = timer_hz / MIC_BKIN_SAMPLE_HZ;\n"
        "  if (prescaler == 0U || prescaler > 65536U) {\n"
        "    mic_bkin_capture_state = MIC_BKIN_CAPTURE_ERROR;\n"
        "    return;\n"
        "  }\n"
    )
    new_calc = (
        "  uint32_t timer_hz = HAL_RCC_GetPCLK1Freq();\n"
        "  if (clocks.APB1CLKDivider != RCC_HCLK_DIV1) timer_hz *= 2U;\n"
        "  if (timer_hz < (2U * MIC_BKIN_SAMPLE_HZ) ||\n"
        "      timer_hz % MIC_BKIN_SAMPLE_HZ != 0U) {\n"
        "    mic_bkin_capture_state = MIC_BKIN_CAPTURE_ERROR;\n"
        "    return;\n"
        "  }\n"
        "  const uint32_t period_cycles = timer_hz / MIC_BKIN_SAMPLE_HZ;\n"
        "  if (period_cycles < 2U) {\n"
        "    mic_bkin_capture_state = MIC_BKIN_CAPTURE_ERROR;\n"
        "    return;\n"
        "  }\n"
    )
    restored = source.replace(new_calc, old_calc, 1).replace(
        "  /* RM0440: an auto-reload value of zero blocks the timer counter. */\n"
        "  TIM2->PSC = 0U;\n"
        "  TIM2->ARR = period_cycles - 1U;\n",
        "  TIM2->PSC = prescaler - 1U;\n"
        "  TIM2->ARR = 0U;\n", 1)
    check(restored == old_source,
          "the only Nucleo source change is the BKIN recorder timer period")

    previous_uno = (PREDECESSOR / "UNOQ_MOTOR/UNOQ_MOTOR.ino").read_bytes()
    candidate_uno = (CANDIDATE / "UNOQ_MOTOR/UNOQ_MOTOR.ino").read_bytes()
    previous_hmi = (PREDECESSOR / "web_hmi/server.py").read_bytes()
    candidate_hmi = (CANDIDATE / "web_hmi/server.py").read_bytes()
    check(previous_uno == candidate_uno and previous_hmi == candidate_hmi,
          "Uno and HMI sources are unchanged")

    debug = CANDIDATE / "nucleo/STM32CubeIDE/Debug"
    build_manifest_path = debug / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json"
    build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8-sig")) if build_manifest_path.is_file() else {}
    hex_path = debug / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"
    check(build_manifest.get("firmware_build_id") == 2026101710 and
          build_manifest.get("build_exit_code") == 0 and
          build_manifest.get("build_errors") == 0 and
          build_manifest.get("build_warnings") == 0 and
          hex_path.is_file(),
          "Nucleo image builds cleanly with the existing protocol identity")

    hmi = load_server()
    empty = hmi.bkin_wave_status({"mc_fw_build": 2026101710,
        "mc_break_wave_hex": make_record(0, 1024, 0x10),
        "mc_break_wave_age_ms": 25})
    check(empty.get("available") is True and empty.get("valid_sample_count") == 0 and
          empty.get("sample_validity") == "dma_no_transfers",
          "HMI explicitly identifies the observed zero-transfer DMA record")
    full = hmi.bkin_wave_status({"mc_fw_build": 2026101710,
        "mc_break_wave_hex": make_record(1024, 0, 0x12, 1023),
        "mc_break_wave_age_ms": 25})
    check(full.get("available") is True and full.get("valid_sample_count") == 1024 and
          full.get("active_intervals") == [{"from_us": 0, "to_us": 1,
                                             "includes_capture_boundary": True}],
          "HMI decodes a full DMA trace and active-low PA6 sample")

    report = {"pass": not failures, "checks": 10 - len(failures),
              "failures": failures, "hardware_commands": 0,
              "mcu_flash_commands": 0, "motor_commands": 0,
              "scope": "Offline source, timer-period, and HMI parser checks only"}
    (CANDIDATE / "selftest/report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    manifest_path = CANDIDATE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["selftest_pass"] = report["pass"]
    manifest["selftest"] = report
    manifest["built"] = hex_path.is_file()
    if manifest["built"]:
        item = next((x for x in build_manifest.get("artifacts", [])
                     if x.get("file") == hex_path.name), {})
        manifest["nucleo_hex"] = {"path": str(hex_path), "sha256": hashlib.sha256(hex_path.read_bytes()).hexdigest(),
                                  "bytes": hex_path.stat().st_size,
                                  "manifest_sha256": item.get("sha256"),
                                  "build_id": build_manifest.get("firmware_build_id"),
                                  "build_errors": build_manifest.get("build_errors"),
                                  "build_warnings": build_manifest.get("build_warnings")}
        preflight_path = debug / "mcsdk_release_preflight.json"
        manifest["release_preflight"] = json.loads(preflight_path.read_text(encoding="utf-8-sig")) if preflight_path.is_file() else None
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

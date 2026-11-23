"""Prepare an offline Nucleo-only BKIN DMA timer fix from the installed diagnostic pair."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261017/bkin_dma_boot_armed_r1"
OUT = ROOT / "artifacts/live_bench_20261017/bkin_dma_arr_fix_r1"
PAIR = [2026101711, 2026101710]  # retain the existing UART-compatible pair


def replace_once(text: str, before: str, after: str, label: str) -> str:
    count = text.count(before)
    if count != 1:
        raise RuntimeError(f"{label}: expected one source anchor, found {count}")
    return text.replace(before, after, 1)


def main() -> int:
    if not (BASE / "manifest.json").is_file():
        raise RuntimeError(f"base candidate is missing: {BASE}")
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite candidate: {OUT}")

    ignore = shutil.ignore_patterns("build", "Debug", "Release", ".metadata", ".settings", "__pycache__", ".lock")
    for name in ("nucleo", "UNOQ_MOTOR", "web_hmi"):
        shutil.copytree(BASE / name, OUT / name, ignore=ignore)
    (OUT / "build/nucleo").mkdir(parents=True)
    (OUT / "build/uno").mkdir(parents=True)
    (OUT / "selftest").mkdir(parents=True)
    shutil.copytree(BASE / "build/uno", OUT / "build/uno", dirs_exist_ok=True)

    path = OUT / "nucleo/Src/main.c"
    source = path.read_text(encoding="utf-8-sig")
    old = (
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
    new = (
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
    source = replace_once(source, old, new, "Nonzero timer period calculation")
    source = replace_once(source,
        "  TIM2->PSC = prescaler - 1U;\n"
        "  TIM2->ARR = 0U;\n",
        "  /* RM0440: an auto-reload value of zero blocks the timer counter. */\n"
        "  TIM2->PSC = 0U;\n"
        "  TIM2->ARR = period_cycles - 1U;\n",
        "Use a nonzero TIM2 auto-reload period")
    path.write_text(source, encoding="utf-8", newline="\n")

    files = (
        "nucleo/Src/main.c", "nucleo/Inc/bkin_wave_capture.h",
        "nucleo/Inc/break_wire.h", "UNOQ_MOTOR/UNOQ_MOTOR.ino",
        "UNOQ_MOTOR/break_wire.h", "UNOQ_MOTOR/nucleo_fault_diagnostics.h",
        "web_hmi/server.py",
    )
    hashes = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in files}
    base_manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8-sig"))
    manifest = {
        "schema": "mic_ai.bkin_dma_arr_fix_candidate.v1",
        "candidate": str(OUT),
        "predecessor": str(BASE),
        "pair_compatibility_ids": PAIR,
        "nucleo_only_update": True,
        "uno_image_changed": False,
        "hmi_changed": False,
        "change": "Set TIM2 PSC=0 and ARR=(TIM2 clock / 1 MHz)-1; the prior ARR=0 blocked the counter, leaving DMA CNDTR at 1024 and zero captured PA6 samples.",
        "evidence_input": "artifacts/live_bench_20261017/bkin_dma_boot_armed_install_r1/live_j1_ramp_snapshot.json",
        "previous_nucleo_hex_sha256": base_manifest.get("flash_readback_verification", {}).get("nucleo", {}).get("sha256"),
        "source_sha256": hashes,
        "calibration_changed": False,
        "control_protocol_changed": False,
        "pwm_or_motor_control_changed": False,
        "hardware_commands": 0,
        "motor_commands": 0,
        "mcu_flash_commands": 0,
        "operationally_qualified": False,
        "hv_release_approved": False,
        "built": False,
        "selftest_pass": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (OUT / "README_RU.md").write_text(
        "# Исправление DMA-захвата BKIN\n\n"
        "В установленной диагностике TIM2 задавался ARR=0. Справочник ST RM0440 указывает, "
        "что при нулевом ARR счётчик заблокирован; фактическая запись подтвердила CNDTR=1024 "
        "и 0 валидных отсчётов. Кандидат использует PSC=0 и ненулевой ARR для периода 1 мкс.\n\n"
        "Меняется только диагностическая настройка таймера в Nucleo. Uno, HMI, UART, ШИМ, "
        "управление двигателем и калибровка остаются прежними. Идентификаторы пары сохранены "
        "для совместимости протокола; точный новый Nucleo HEX отслеживается SHA-256. "
        "Это диагностическая прошивка, она не разрешает силовой пуск.\n",
        encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

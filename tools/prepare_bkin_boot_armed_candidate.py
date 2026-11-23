"""Prepare a boot-armed BKIN waveform diagnostic candidate without device I/O."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261017/bkin_dma_verified_pair_r1"
OUT = ROOT / "artifacts/live_bench_20261017/bkin_dma_boot_armed_r1"
UNO_BUILD = 2026101711
MC_BUILD = 2026101710


def replace_once(text: str, before: str, after: str, label: str) -> str:
    count = text.count(before)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}: {before[:90]!r}")
    return text.replace(before, after, 1)


def replace_all(text: str, before: str, after: str, expected: int, label: str) -> str:
    count = text.count(before)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} anchors, found {count}: {before[:90]!r}")
    return text.replace(before, after)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    if not (BASE / "manifest.json").is_file():
        raise RuntimeError(f"base candidate is missing: {BASE}")
    if OUT.exists() and (OUT / "manifest.json").exists():
        raise RuntimeError(f"refusing to overwrite candidate: {OUT}")

    ignore = shutil.ignore_patterns(
        "build", "Debug", "Release", ".metadata", ".settings", "__pycache__", ".lock"
    )
    shutil.copytree(BASE / "nucleo", OUT / "nucleo", ignore=ignore, dirs_exist_ok=True)
    shutil.copytree(BASE / "UNOQ_MOTOR", OUT / "UNOQ_MOTOR", ignore=ignore, dirs_exist_ok=True)
    shutil.copytree(BASE / "web_hmi", OUT / "web_hmi", ignore=ignore, dirs_exist_ok=True)
    (OUT / "build/nucleo").mkdir(parents=True, exist_ok=True)
    (OUT / "build/uno").mkdir(parents=True, exist_ok=True)
    (OUT / "selftest").mkdir(parents=True, exist_ok=True)

    main_path = OUT / "nucleo/Src/main.c"
    main = read(main_path)
    main = replace_once(main, "#define MIC_NUCLEO_FW_BUILD_ID 2026101702UL",
                        f"#define MIC_NUCLEO_FW_BUILD_ID {MC_BUILD}UL", "Nucleo identity")
    main = replace_once(main,
        "static void mic_bkin_capture_start(void) {\n"
        "  if (mic_bkin_capture_state == MIC_BKIN_CAPTURED ||\n",
        "static void mic_bkin_capture_start(void) {\n"
        "  if (mic_bkin_capture_state == MIC_BKIN_RUNNING) return;\n"
        "  if (mic_bkin_capture_state == MIC_BKIN_CAPTURED ||\n",
        "Keep an already armed passive capture running")
    main = replace_once(main,
        "  /* Reuse TIM2 for passive BKIN trace after MCSDK's boot synchronization. */\n"
        "  mic_bkin_capture_init();",
        "  /* Arm the passive BKIN trace after MCSDK boot synchronization, before any START. */\n"
        "  mic_bkin_capture_start();",
        "Arm before START so power-up breaks have a trace")
    main = replace_once(main,
        "static void mic_bkin_capture_stop_software(void) {\n"
        "  mic_bkin_capture_stop(HAL_GetTick(), false);\n"
        "}\n\n",
        "",
        "Keep diagnostic capture active through normal STOP")
    main = replace_once(main,
        "static void uno_stop_motor(void) {\n"
        "  mic_bkin_capture_stop_software();\n",
        "static void uno_stop_motor(void) {\n",
        "Normal STOP does not cancel the boot-armed capture")
    write(main_path, main)

    for relative in ("nucleo/Inc/break_wire.h", "UNOQ_MOTOR/break_wire.h"):
        path = OUT / relative
        text = replace_once(read(path), "#define BW_NUCLEO_BUILD 2026101702UL",
                            f"#define BW_NUCLEO_BUILD {MC_BUILD}UL", relative)
        write(path, text)

    uno_path = OUT / "UNOQ_MOTOR/UNOQ_MOTOR.ino"
    uno = read(uno_path)
    uno = replace_once(uno, "static const uint32_t FW_BUILD_ID = 2026101703U;",
                       f"static const uint32_t FW_BUILD_ID = {UNO_BUILD}U;", "Uno identity")
    uno = replace_once(uno, "g_bp_fw_build==2026101702U",
                       f"g_bp_fw_build=={MC_BUILD}U", "Uno peer build check")
    write(uno_path, uno)

    diag_path = OUT / "UNOQ_MOTOR/nucleo_fault_diagnostics.h"
    diag = read(diag_path)
    diag = replace_once(diag, "build==2026101702U", f"build==2026101702U || build=={MC_BUILD}U",
                        "MCSDK status signature peer allowlist")
    diag = replace_once(diag, "build == 2026101702U;",
                        f"build == 2026101702U || build == {MC_BUILD}U;",
                        "MCSDK diagnostic peer allowlist")
    write(diag_path, diag)

    server_path = OUT / "web_hmi/server.py"
    server = read(server_path)
    server = replace_once(server,
        "2026101502, 2026101504, 2026101506, 2026101702)",
        f"2026101502, 2026101504, 2026101506, 2026101702, {MC_BUILD})",
        "MC telemetry identity allowlist")
    server = replace_once(server,
        'if _as_int(data or {}, "mc_fw_build", 0) != 2026101702:',
        f'if _as_int(data or {{}}, "mc_fw_build", 0) not in (2026101702, {MC_BUILD}):',
        "Wave trace peer identity")
    server = replace_once(server,
        "        (2026101703, 2026101702),",
        f"        (2026101703, 2026101702),\n        ({UNO_BUILD}, {MC_BUILD}),",
        "Manual scalar pair allowlist")
    server = replace_once(server,
        "(2026101502,2026101504,2026101506,2026101702)",
        f"(2026101502,2026101504,2026101506,2026101702,{MC_BUILD})",
        "HV profile MC identity allowlist")
    server = replace_all(server,
        "((2026101505,2026101504),(2026101507,2026101506),(2026101703,2026101702))",
        f"((2026101505,2026101504),(2026101507,2026101506),(2026101703,2026101702),({UNO_BUILD},{MC_BUILD}))",
        2, "HV/manual scalar pair allowlists")
    write(server_path, server)

    readme = """# BKIN-захват до команды «Пуск»

Кандидат исправляет конкретный пробел диагностики события 17.10.2026: DMA
запускалась только после принятой команды START, поэтому авария до START не
оставляла трассу PA6. Новая прошивка Nucleo запускает прежний кольцевой DMA-захват
1 МГц после синхронизации MCSDK при загрузке и замораживает его при первом
обработанном Break. Если команда START приходит, уже запущенный захват остаётся
работать.

Логика двигателя, разгон/замедление V/f, ШИМ, калибровка и формат UART-команд не
меняются. Та же низкоприоритетная передача GPIO через DMA уже использовалась
предыдущей диагностикой во время работы двигателя; теперь она запускается раньше,
чтобы видеть события до START.

Пара кандидата: Uno Q %d / Nucleo %d. Кандидат пока собран и проверен только
офлайн; прошивка и работа на стенде не подтверждены.
""" % (UNO_BUILD, MC_BUILD)
    write(OUT / "README_RU.md", readme)

    files = (
        "nucleo/Src/main.c", "nucleo/Inc/break_wire.h", "UNOQ_MOTOR/UNOQ_MOTOR.ino",
        "UNOQ_MOTOR/break_wire.h", "UNOQ_MOTOR/nucleo_fault_diagnostics.h",
        "UNOQ_MOTOR/bkin_wave_wire.h", "web_hmi/server.py", "README_RU.md",
    )
    hashes = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in files}
    manifest = {
        "schema": "mic_ai.bkin_boot_armed_candidate.v1",
        "candidate": str(OUT),
        "predecessor": str(BASE),
        "pair": [UNO_BUILD, MC_BUILD],
        "predecessor_pair": [2026101703, 2026101702],
        "prepared": True,
        "built": False,
        "installed": False,
        "operationally_qualified": False,
        "hv_release_approved": False,
        "calibration_changed": False,
        "control_protocol_changed": False,
        "pwm_or_motor_control_changed": False,
        "hardware_commands": 0,
        "motor_commands": 0,
        "mcu_flash_commands": 0,
        "change": "Arm the existing DMA PA6 circular trace after MCSDK boot synchronization so a BKIN event before START freezes a waveform; normal STOP does not cancel it.",
        "files_sha256": hashes,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

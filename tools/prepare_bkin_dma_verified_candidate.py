"""Prepare a diagnostic-only BKIN candidate with DMA-count-verified traces.

Creates a new source/artifact package from the installed manual scalar pair.
No device access, deployment, motor command, or programming is performed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261015/manual_scalar_bkin_trace_r3"
DIAG_HMI = ROOT / "artifacts/live_bench_20261017/bkin_hmi_diagnostic_fix_r3"
SIMPLE_HMI = ROOT / "artifacts/live_bench_20261017/manual_scalar_hmi_simplified_r1/web_hmi/static"
OUT = ROOT / "artifacts/live_bench_20261017/bkin_dma_verified_pair_r1"
UNO_BUILD = 2026101703
MC_BUILD = 2026101702


def replace_once(text: str, before: str, after: str, label: str) -> str:
    count = text.count(before)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}: {before[:90]!r}")
    return text.replace(before, after, 1)


def replace_span(text: str, start: str, end: str, replacement: str, label: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError(f"{label}: expected unique start/end anchors")
    a = text.index(start)
    b = text.index(end, a)
    if b <= a:
        raise RuntimeError(f"{label}: invalid replacement span")
    return text[:a] + replacement + text[b:]


def write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare() -> dict:
    if not (BASE / "manifest.json").is_file() or not (DIAG_HMI / "server.py").is_file():
        raise RuntimeError("Frozen MCU pair or diagnostic HMI base is missing")
    base_manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    if base_manifest.get("pair") != [2026101507, 2026101506]:
        raise RuntimeError("Unexpected installed MCU pair")
    if OUT.exists() and (OUT / "manifest.json").exists():
        raise RuntimeError(f"Refusing to overwrite existing candidate: {OUT}")

    ignore = shutil.ignore_patterns("Debug", "Release", ".settings", "__pycache__", ".metadata")
    OUT.mkdir(parents=True, exist_ok=True)
    for tree in ("nucleo", "UNOQ_MOTOR"):
        shutil.copytree(BASE / tree, OUT / tree, ignore=ignore, dirs_exist_ok=True)
    (OUT / "web_hmi/static").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DIAG_HMI / "server.py", OUT / "web_hmi/server.py")
    for name in ("app.js", "index.html", "style.css"):
        shutil.copyfile(SIMPLE_HMI / name, OUT / "web_hmi/static" / name)

    main_path = OUT / "nucleo/Src/main.c"
    main = main_path.read_text(encoding="utf-8-sig")
    main = replace_once(main, "#define MIC_NUCLEO_FW_BUILD_ID 2026101506UL",
                        f"#define MIC_NUCLEO_FW_BUILD_ID {MC_BUILD}UL", "Nucleo identity")
    main = replace_once(main,
        "volatile uint32_t mic_bkin_remaining;\n"
        "volatile uint32_t mic_bkin_start_tick_ms;\n"
        "volatile uint32_t mic_bkin_event_tick_ms;\n"
        "volatile uint32_t mic_bkin_filled_at_event;",
        "volatile uint32_t mic_bkin_remaining;\n"
        "volatile uint32_t mic_bkin_dma_flags;\n"
        "volatile uint32_t mic_bkin_event_tick_ms;",
        "DMA snapshot storage")
    main = replace_once(main,
        "  if (HAL_DMA_Start(&hdma_mic_bkin, (uint32_t)(uintptr_t)&GPIOA->IDR,\n",
        "  DMA2->IFCR = 0x0FU; /* clear channel 1 GIF/TC/HT/TE flags */\n"
        "  __DSB();\n"
        "  if (HAL_DMA_Start(&hdma_mic_bkin, (uint32_t)(uintptr_t)&GPIOA->IDR,\n",
        "Clear DMA status before capture")
    main = replace_once(main,
        "  mic_bkin_start_tick_ms = HAL_GetTick();\n"
        "  mic_bkin_remaining = MIC_BKIN_SAMPLE_COUNT;\n"
        "  mic_bkin_filled_at_event = 0U;\n",
        "  mic_bkin_remaining = MIC_BKIN_SAMPLE_COUNT;\n"
        "  mic_bkin_dma_flags = 0U;\n",
        "Remove elapsed-time completeness marker")
    main = replace_once(main,
        "  __HAL_DMA_DISABLE(&hdma_mic_bkin);\n"
        "  __DSB();\n"
        "  mic_bkin_remaining = DMA2_Channel1->CNDTR;\n"
        "  mic_bkin_event_tick_ms = tick_ms;\n"
        "  mic_bkin_filled_at_event = (uint32_t)(tick_ms - mic_bkin_start_tick_ms) >= 2U;\n",
        "  __HAL_DMA_DISABLE(&hdma_mic_bkin);\n"
        "  __DSB();\n"
        "  mic_bkin_remaining = DMA2_Channel1->CNDTR;\n"
        "  mic_bkin_dma_flags = DMA2->ISR & 0x0FU;\n"
        "  mic_bkin_event_tick_ms = tick_ms;\n",
        "Freeze actual DMA count and status")
    record_fn = r'''static void mic_bkin_prepare_record(void) {
  if (mic_bkin_capture_state != MIC_BKIN_CAPTURED || mic_bkin_record_ready != 0U) return;
  const uint32_t remaining = mic_bkin_remaining;
  const uint32_t dma_flags = mic_bkin_dma_flags & 0x0FU;
  const bool dma_error = (dma_flags & 0x08U) != 0U; /* DMA2 channel 1 TEIF */
  const bool dma_wrapped = (dma_flags & 0x02U) != 0U; /* DMA2 channel 1 TCIF */
  uint32_t valid_count = 0U;
  if (!dma_error && remaining <= MIC_BKIN_SAMPLE_COUNT)
    valid_count = dma_wrapped ? MIC_BKIN_SAMPLE_COUNT : MIC_BKIN_SAMPLE_COUNT - remaining;
  const uint32_t next = (MIC_BKIN_SAMPLE_COUNT -
      (remaining <= MIC_BKIN_SAMPLE_COUNT ? remaining : MIC_BKIN_SAMPLE_COUNT)) &
      (MIC_BKIN_SAMPLE_COUNT - 1U);
  const uint32_t first_valid = MIC_BKIN_SAMPLE_COUNT - valid_count;
  memset(mic_bkin_record, 0, sizeof(mic_bkin_record));
  mic_bkin_put32(mic_bkin_record + 0U, MIC_BKIN_RECORD_MAGIC);
  mic_bkin_put32(mic_bkin_record + 4U, MIC_BKIN_RECORD_SCHEMA);
  mic_bkin_put32(mic_bkin_record + 8U, MIC_BKIN_RECORD_BYTES);
  mic_bkin_put32(mic_bkin_record + 12U, mic_bkin_event_tick_ms);
  mic_bkin_put32(mic_bkin_record + 16U, 1000U); /* sample period, nanoseconds */
  mic_bkin_put32(mic_bkin_record + 20U, valid_count);
  mic_bkin_put32(mic_bkin_record + 24U, remaining); /* actual DMA CNDTR at freeze */
  mic_bkin_put32(mic_bkin_record + 28U, dma_flags | 0x10U); /* bit 4: DMA frozen */
  for (uint32_t i = 0U; i < valid_count; ++i) {
    const uint32_t source = dma_wrapped ?
        ((next + i) & (MIC_BKIN_SAMPLE_COUNT - 1U)) : i;
    const uint32_t destination = first_valid + i;
    if ((mic_bkin_ring[source] & GPIO_PIN_6) != 0U)
      mic_bkin_record[32U + destination / 8U] |= (uint8_t)(1U << (destination & 7U));
  }
  mic_bkin_record_crc = uv3_crc32c(mic_bkin_record, MIC_BKIN_RECORD_BYTES);
  __DMB();
  mic_bkin_record_ready = 1U;
}

'''
    main = replace_span(main, "static void mic_bkin_prepare_record(void) {",
                        "static void mic_bkin_wave_packet(", record_fn,
                        "DMA-count-derived record builder")
    write(main_path, main)

    capture_header = OUT / "nucleo/Inc/bkin_wave_capture.h"
    header = capture_header.read_text(encoding="utf-8-sig")
    header = replace_once(header, "#define MIC_BKIN_RECORD_SCHEMA 1U",
                          "#define MIC_BKIN_RECORD_SCHEMA 2U", "Trace record schema")
    write(capture_header, header)

    # Both ordinary diagnostic transport and trace transport must identify the
    # new peer exactly; the normal 43-byte command/reply format is untouched.
    for rel in ("nucleo/Inc/break_wire.h", "UNOQ_MOTOR/break_wire.h"):
        path = OUT / rel
        text = path.read_text(encoding="utf-8-sig")
        text = replace_once(text, "#define BW_NUCLEO_BUILD 2026101506UL",
                            f"#define BW_NUCLEO_BUILD {MC_BUILD}UL", rel)
        write(path, text)
    uno_path = OUT / "UNOQ_MOTOR/UNOQ_MOTOR.ino"
    uno = uno_path.read_text(encoding="utf-8-sig")
    uno = replace_once(uno, "static const uint32_t FW_BUILD_ID = 2026101507U;",
                       f"static const uint32_t FW_BUILD_ID = {UNO_BUILD}U;", "Uno identity")
    uno = replace_once(uno, "g_bp_fw_build==2026101506U", f"g_bp_fw_build=={MC_BUILD}U",
                       "Uno peer reference identity")
    write(uno_path, uno)

    wave_header_path = OUT / "UNOQ_MOTOR/bkin_wave_wire.h"
    wave = wave_header_path.read_text(encoding="utf-8-sig")
    wave = replace_once(wave, "bw_u32(rx->data+4)!=1U", "bw_u32(rx->data+4)!=2U", "Trace schema")
    wave = replace_once(wave,
        "bw_u32(rx->data+20)==0U || bw_u32(rx->data+20)>1024U ||\n"
        "        bw_u32(rx->data+24)!=1023U || !(bw_u32(rx->data+28)&2U) ||\n"
        "        (bw_u32(rx->data+28)&~3U)",
        "bw_u32(rx->data+20)>1024U || bw_u32(rx->data+24)>1024U ||\n"
        "        !(bw_u32(rx->data+28)&0x10U) || (bw_u32(rx->data+28)&~0x1FU) ||\n"
        "        bw_u32(rx->data+20)!=((bw_u32(rx->data+28)&0x08U)?0U:\n"
        "          ((bw_u32(rx->data+28)&0x02U)?1024U:1024U-bw_u32(rx->data+24)))",
        "Validate DMA counter/status consistency")
    write(wave_header_path, wave)

    fault_path = OUT / "UNOQ_MOTOR/nucleo_fault_diagnostics.h"
    fault = fault_path.read_text(encoding="utf-8-sig")
    fault = replace_once(fault, "build==2026101506U", f"build==2026101506U || build=={MC_BUILD}U",
                         "Extended MCSDK diagnostic peer identity")
    fault = replace_once(fault, "build == 2026101506U;",
                         f"build == 2026101506U || build == {MC_BUILD}U;",
                         "V2 MCSDK diagnostic peer identity")
    write(fault_path, fault)

    # Use the current simplified operator panel assets; only its diagnostic
    # interpretation text is updated. Control layout and key/ARM flow stay intact.
    server_path = OUT / "web_hmi/server.py"
    server = server_path.read_text(encoding="utf-8-sig")
    server = replace_once(server,
        "2026101504, 2026101506) or not 0 <= peer_age < 300",
        f"2026101504, 2026101506, {MC_BUILD}) or not 0 <= peer_age < 300",
        "D1 peer allowlist")
    server = replace_once(server,
        'if _as_int(data or {}, "mc_fw_build", 0) != 2026101506:',
        f'if _as_int(data or {{}}, "mc_fw_build", 0) != {MC_BUILD}:',
        "D2 peer identity")
    server = replace_once(server,
        '2026101507, 2026101506),',
        f'2026101507, 2026101506),\n        ({UNO_BUILD}, {MC_BUILD}),',
        "Manual scalar pair allowlist")
    server = replace_once(server,
        'in (2026101502,2026101504,2026101506) and',
        f'in (2026101502,2026101504,2026101506,{MC_BUILD}) and',
        "HV guard recognizes the candidate peer build")
    server = replace_once(server,
        '((2026101505,2026101504),(2026101507,2026101506)):',
        f'((2026101505,2026101504),(2026101507,2026101506),({UNO_BUILD},{MC_BUILD})):',
        "HV profile pair guard")
    server = replace_once(server,
        '((2026101505,2026101504),(2026101507,2026101506)) and _as_int(data,"manual_scalar_capable",0)==1)',
        f'((2026101505,2026101504),(2026101507,2026101506),({UNO_BUILD},{MC_BUILD})) and _as_int(data,"manual_scalar_capable",0)==1)',
        "Manual control pair gate")
    parser = r'''def bkin_wave_status(data):
    """Decode schema-2 PA6 trace only when DMA count and flags agree."""
    unavailable = {"available": False, "reason": "not_received"}
    try:
        if _as_int(data or {}, "mc_fw_build", 0) != 2026101702:
            return {"available": False, "reason": "wrong_peer_build"}
        text = data.get("mc_break_wave_hex", "")
        age = _as_int(data, "mc_break_wave_age_ms", 999999)
        if not text or text == "-": return unavailable
        if len(text) != 320 or any(c not in "0123456789abcdefABCDEF" for c in text):
            return {"available": False, "reason": "invalid_hex"}
        if not 0 <= age <= 5000: return {"available": False, "reason": "stale"}
        raw = bytes.fromhex(text)
        u32 = lambda offset: int.from_bytes(raw[offset:offset+4], "little")
        valid_count, remaining, flags = u32(20), u32(24), u32(28)
        if (u32(0) != 0x314E4B42 or u32(4) != 2 or u32(8) != 160 or
                u32(16) != 1000 or valid_count > 1024 or remaining > 1024 or
                not (flags & 0x10) or (flags & ~0x1F)):
            return {"available": False, "reason": "invalid_record"}
        dma_error = bool(flags & 0x08)
        dma_complete = bool(flags & 0x02)
        expected = 0 if dma_error else (1024 if dma_complete else 1024 - remaining)
        if valid_count != expected:
            return {"available": False, "reason": "dma_count_mismatch"}
        valid_from = 1024 - valid_count
        bits = raw[32:160]
        samples = [None if i < valid_from else int(bool(bits[i // 8] & (1 << (i & 7))))
                   for i in range(1024)]
        active_intervals = []
        start = None
        for i in range(valid_from, 1025):
            low = i < 1024 and samples[i] == 0
            if low and start is None: start = i
            elif not low and start is not None:
                active_intervals.append({"from_us": start - 1023, "to_us": i - 1023,
                                         "includes_capture_boundary": i == 1024})
                start = None
        validity = ("dma_transfer_error" if dma_error else
                    "dma_verified_full" if dma_complete else
                    "dma_verified_partial" if valid_count else "dma_no_transfers")
        return {"available": True, "reason": "recorded", "age_ms": age,
            "schema": 2, "sample_rate_hz": 1000000, "sample_period_us": 1,
            "sample_count": 1024, "valid_sample_count": valid_count,
            "unknown_prefix_samples": valid_from, "trigger_index": 1023,
            "dma_count_verified": True, "dma_remaining": remaining,
            "dma_flags_raw": flags & 0x0F, "dma_tcif": dma_complete,
            "dma_htif": bool(flags & 0x04), "dma_teif": dma_error,
            "dma_complete": dma_complete, "dma_error": dma_error,
            "sample_validity": validity,
            "trace_reference": "last DMA sample before BKIN interrupt handling; exact edge offset includes IRQ latency",
            "pa6_samples": samples, "active_intervals": active_intervals,
            "pa6_low_intervals": active_intervals, "pa6_low_is_active": True,
            "limitations": ["Digital BKIN/SD input only; no current, J4 rail, or phase voltage is measured",
                "Sub-microsecond pulse widths are below this recorder's resolution",
                "Trace alone cannot identify overcurrent, driver undervoltage, or interference"]}
    except (ValueError, TypeError, OverflowError):
        return {"available": False, "reason": "invalid_metadata"}


'''
    server = replace_span(server, "def bkin_wave_status(data):", "STATE_NAMES = {", parser,
                          "Schema-2 DMA-verified HMI decoder")
    write(server_path, server)

    app_path = OUT / "web_hmi/static/app.js"
    app = app_path.read_text(encoding="utf-8-sig")
    app = replace_once(app,
        '    bkinTraceStatus.textContent = `PA6 LOW: ${pulses || "не обнаружен"}; ` +\n'
        '      `${trace.valid_sample_count}/1024 отсчётов, шаг 1 мкс`;',
        '      const dmaText = trace.dma_error ? "DMA сообщил ошибку; отсчёты отброшены" :\n'
        '        trace.valid_sample_count === 0 ? "DMA не успел записать отсчёты" :\n'
        '        `счётчик DMA подтверждает ${trace.valid_sample_count}/1024 отсчётов`;\n'
        '    bkinTraceStatus.textContent = `Активный PA6 LOW: ${pulses || "не обнаружен"}; ` +\n'
        '      `${dmaText}, шаг 1 мкс; снимок ${(Number(trace.age_ms) / 1000).toFixed(1)} с.`;',
        "Simplified HMI trace explanation")
    app = replace_once(app,
        '      writeDriveSnapshotUnavailable(`${record.kind === "first_start_window" ? "Во время запроса пуска" : "При запуске контроллера"} (${at}): ${flags}${hz}${bus}${temp}${contextAge}. PA6 снят один раз при входе в обработчик: длительность импульса и точную физическую причину этот снимок не устанавливает.`);',
        '      const origin = event.start_window_flag_stale_after_run ? "Уже после перехода в RUN (флаг окна пуска не сброшен)" :\n'
        '        event.during_start_request_window ? "Во время запроса пуска" : "При останове";\n'
        '      writeDriveSnapshotUnavailable(`${origin} (${at}): ${flags}${hz}${bus}${temp}${contextAge}. PA6 снят один раз при входе в обработчик: длительность импульса и точную физическую причину этот снимок не устанавливает.`);',
        "Use corrected runtime/start-window interpretation")
    write(app_path, app)

    # Store a small reproducible record of scope and hashes; this is a build
    # candidate, not a release or hardware authorization.
    tracked = [
        "nucleo/Src/main.c", "nucleo/Inc/bkin_wave_capture.h",
        "UNOQ_MOTOR/UNOQ_MOTOR.ino", "UNOQ_MOTOR/bkin_wave_wire.h",
        "UNOQ_MOTOR/nucleo_fault_diagnostics.h", "web_hmi/server.py",
        "web_hmi/static/app.js", "web_hmi/static/index.html", "web_hmi/static/style.css",
    ]
    manifest = {
        "schema": "mic_ai.bkin_dma_verified_candidate.v1",
        "candidate": str(OUT), "predecessor": str(BASE),
        "pair": [UNO_BUILD, MC_BUILD], "predecessor_pair": base_manifest["pair"],
        "prepared": True, "installed": False, "operationally_qualified": False,
        "hv_release_approved": False, "calibration_changed": False,
        "control_protocol_changed": False, "pwm_or_motor_control_changed": False,
        "hardware_commands": 0, "motor_commands": 0, "mcu_flash_commands": 0,
        "change": "Use actual DMA CNDTR and DMA2 channel 1 ISR flags to derive valid samples; expose verified count and transfer errors in the simplified HMI.",
        "files_sha256": {name: sha(OUT / name) for name in tracked},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"prepared": True, "candidate": str(OUT), "pair": [UNO_BUILD, MC_BUILD],
            "hardware_commands": 0, "mcu_flash_commands": 0}


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))

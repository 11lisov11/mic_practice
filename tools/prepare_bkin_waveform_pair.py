"""Prepare a separate BKIN trace firmware pair from the last working pair.

This only creates source/artifact directories. It never connects to hardware,
deploys the HMI, or programs a board.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261015/manual_scalar_working_pair_r3"
OUT = ROOT / "artifacts/live_bench_20261015/manual_scalar_bkin_trace_r3"
UNO_BUILD = 2026101507
MC_BUILD = 2026101506


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): sha(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and not any(x in {"Debug", "Release", ".settings", "__pycache__"}
                                    for x in p.relative_to(folder).parts)
    }


def replace_once(text: str, before: str, after: str, name: str) -> str:
    count = text.count(before)
    if count != 1:
        raise RuntimeError(f"{name}: expected one anchor, found {count}: {before[:100]!r}")
    return text.replace(before, after, 1)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def prepare() -> dict:
    if not BASE.is_dir() or not (BASE / "manifest.json").is_file():
        raise RuntimeError(f"Frozen predecessor pair is missing: {BASE}")
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing candidate: {OUT}")
    predecessor = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    if predecessor.get("pair") != [2026101505, 2026101504]:
        raise RuntimeError("Unexpected predecessor identity")
    before = {tree: tree_hashes(BASE / tree) for tree in ("nucleo", "UNOQ_MOTOR", "web_hmi")}

    OUT.mkdir(parents=True)
    ignore = shutil.ignore_patterns("Debug", "Release", ".settings", "__pycache__")
    for tree in ("nucleo", "UNOQ_MOTOR", "web_hmi"):
        shutil.copytree(BASE / tree, OUT / tree, ignore=ignore)

    # Nucleo capture firmware: reserve DMA2 channel 1 and TIM2, both unused by
    # the predecessor; sample PA6 at 1 MHz into a 1 ms ring during START/RUN.
    main_path = OUT / "nucleo/Src/main.c"
    main = main_path.read_text(encoding="utf-8-sig")
    main = replace_once(main, '#include "stm32g4xx_ll_tim.h"',
        '#include "stm32g4xx_ll_tim.h"\n#include "bkin_wave_capture.h"', "Nucleo includes")
    main = replace_once(main, "DMA_HandleTypeDef hdma_usart2_tx;", "DMA_HandleTypeDef hdma_usart2_tx;\n"
        "static DMA_HandleTypeDef hdma_mic_bkin;\n"
        "volatile uint32_t mic_bkin_ring[MIC_BKIN_SAMPLE_COUNT];\n"
        "volatile uint32_t mic_bkin_capture_state;\n"
        "volatile uint32_t mic_bkin_remaining;\n"
        "volatile uint32_t mic_bkin_start_tick_ms;\n"
        "volatile uint32_t mic_bkin_event_tick_ms;\n"
        "volatile uint32_t mic_bkin_filled_at_event;\n"
        "volatile uint32_t mic_bkin_record_ready;\n"
        "uint8_t mic_bkin_record[MIC_BKIN_RECORD_BYTES];\n"
        "uint32_t mic_bkin_record_crc;", "Nucleo capture storage")
    main = replace_once(main, "#define MIC_NUCLEO_FW_BUILD_ID 2026101504UL",
                        f"#define MIC_NUCLEO_FW_BUILD_ID {MC_BUILD}UL", "Nucleo build id")

    insert_after = "#define MIC_EXTERNAL_SOFTSTART_SETTLE_MS 3500U\n"
    capture_impl = r'''

static bool mic_bkin_dma_initialized;

static void mic_bkin_capture_init(void) {
  if (mic_bkin_dma_initialized || mic_bkin_capture_state == MIC_BKIN_CAPTURE_ERROR) return;
  __HAL_RCC_TIM2_CLK_ENABLE();
  memset(&hdma_mic_bkin, 0, sizeof(hdma_mic_bkin));
  hdma_mic_bkin.Instance = DMA2_Channel1;
  hdma_mic_bkin.Init.Request = DMA_REQUEST_TIM2_UP;
  hdma_mic_bkin.Init.Direction = DMA_PERIPH_TO_MEMORY;
  hdma_mic_bkin.Init.PeriphInc = DMA_PINC_DISABLE;
  hdma_mic_bkin.Init.MemInc = DMA_MINC_ENABLE;
  hdma_mic_bkin.Init.PeriphDataAlignment = DMA_PDATAALIGN_WORD;
  hdma_mic_bkin.Init.MemDataAlignment = DMA_MDATAALIGN_WORD;
  hdma_mic_bkin.Init.Mode = DMA_CIRCULAR;
  hdma_mic_bkin.Init.Priority = DMA_PRIORITY_LOW;
  if (HAL_DMA_Init(&hdma_mic_bkin) != HAL_OK) {
    mic_bkin_capture_state = MIC_BKIN_CAPTURE_ERROR;
    return;
  }
  mic_bkin_dma_initialized = true;
}

static void mic_bkin_capture_start(void) {
  if (mic_bkin_capture_state == MIC_BKIN_CAPTURED ||
      mic_bkin_capture_state == MIC_BKIN_CAPTURE_ERROR) return;
  mic_bkin_capture_init();
  if (!mic_bkin_dma_initialized) return;
  if (mic_bkin_capture_state == MIC_BKIN_STOPPED &&
      HAL_DMA_Abort(&hdma_mic_bkin) != HAL_OK) {
    mic_bkin_capture_state = MIC_BKIN_CAPTURE_ERROR;
    return;
  }

  RCC_ClkInitTypeDef clocks = {0};
  uint32_t flash_latency = 0U;
  HAL_RCC_GetClockConfig(&clocks, &flash_latency);
  uint32_t timer_hz = HAL_RCC_GetPCLK1Freq();
  if (clocks.APB1CLKDivider != RCC_HCLK_DIV1) timer_hz *= 2U;
  if (timer_hz < MIC_BKIN_SAMPLE_HZ || timer_hz % MIC_BKIN_SAMPLE_HZ != 0U) {
    mic_bkin_capture_state = MIC_BKIN_CAPTURE_ERROR;
    return;
  }
  const uint32_t prescaler = timer_hz / MIC_BKIN_SAMPLE_HZ;
  if (prescaler == 0U || prescaler > 65536U) {
    mic_bkin_capture_state = MIC_BKIN_CAPTURE_ERROR;
    return;
  }
  /* MCSDK used TIM2 for the one-shot TIM1 synchronization during boot.
     Its initialization is complete before any START; keep TRGO reset while
     this timer is repurposed as a DMA sampling clock. */
  TIM2->CR2 &= ~TIM_CR2_MMS;
  TIM2->CR1 = 0U;
  TIM2->DIER = 0U;
  TIM2->PSC = prescaler - 1U;
  TIM2->ARR = 0U;
  TIM2->CNT = 0U;
  TIM2->EGR = TIM_EGR_UG;
  TIM2->SR = 0U;
  if (HAL_DMA_Start(&hdma_mic_bkin, (uint32_t)(uintptr_t)&GPIOA->IDR,
                    (uint32_t)(uintptr_t)mic_bkin_ring, MIC_BKIN_SAMPLE_COUNT) != HAL_OK) {
    mic_bkin_capture_state = MIC_BKIN_CAPTURE_ERROR;
    return;
  }
  mic_bkin_start_tick_ms = HAL_GetTick();
  mic_bkin_remaining = MIC_BKIN_SAMPLE_COUNT;
  mic_bkin_filled_at_event = 0U;
  mic_bkin_record_ready = 0U;
  mic_bkin_capture_state = MIC_BKIN_RUNNING;
  TIM2->DIER = TIM_DIER_UDE;
  TIM2->CR1 = TIM_CR1_CEN;
}

static void mic_bkin_capture_stop(uint32_t tick_ms, bool by_break) {
  if (mic_bkin_capture_state != MIC_BKIN_RUNNING) return;
  TIM2->DIER &= ~TIM_DIER_UDE;
  TIM2->CR1 &= ~TIM_CR1_CEN;
  __HAL_DMA_DISABLE(&hdma_mic_bkin);
  __DSB();
  mic_bkin_remaining = DMA2_Channel1->CNDTR;
  mic_bkin_event_tick_ms = tick_ms;
  mic_bkin_filled_at_event = (uint32_t)(tick_ms - mic_bkin_start_tick_ms) >= 2U;
  mic_bkin_capture_state = by_break ? MIC_BKIN_CAPTURED : MIC_BKIN_STOPPED;
}

void mic_bkin_capture_stop_from_break(uint32_t tick_ms) {
  mic_bkin_capture_stop(tick_ms, true);
}

static void mic_bkin_capture_stop_software(void) {
  mic_bkin_capture_stop(HAL_GetTick(), false);
}

static void mic_bkin_put32(uint8_t *p, uint32_t value) {
  p[0] = (uint8_t)value;
  p[1] = (uint8_t)(value >> 8U);
  p[2] = (uint8_t)(value >> 16U);
  p[3] = (uint8_t)(value >> 24U);
}

static void mic_bkin_prepare_record(void) {
  if (mic_bkin_capture_state != MIC_BKIN_CAPTURED || mic_bkin_record_ready != 0U) return;
  uint32_t remaining = mic_bkin_remaining;
  if (remaining > MIC_BKIN_SAMPLE_COUNT) remaining = MIC_BKIN_SAMPLE_COUNT;
  const uint32_t next = (MIC_BKIN_SAMPLE_COUNT - remaining) & (MIC_BKIN_SAMPLE_COUNT - 1U);
  const uint32_t valid_count = mic_bkin_filled_at_event ? MIC_BKIN_SAMPLE_COUNT :
      MIC_BKIN_SAMPLE_COUNT - remaining;
  const uint32_t first_valid = MIC_BKIN_SAMPLE_COUNT - valid_count;
  memset(mic_bkin_record, 0, sizeof(mic_bkin_record));
  mic_bkin_put32(mic_bkin_record + 0U, MIC_BKIN_RECORD_MAGIC);
  mic_bkin_put32(mic_bkin_record + 4U, MIC_BKIN_RECORD_SCHEMA);
  mic_bkin_put32(mic_bkin_record + 8U, MIC_BKIN_RECORD_BYTES);
  mic_bkin_put32(mic_bkin_record + 12U, mic_bkin_event_tick_ms);
  mic_bkin_put32(mic_bkin_record + 16U, 1000U); /* sample period, nanoseconds */
  mic_bkin_put32(mic_bkin_record + 20U, valid_count);
  mic_bkin_put32(mic_bkin_record + 24U, MIC_BKIN_SAMPLE_COUNT - 1U);
  mic_bkin_put32(mic_bkin_record + 28U,
      (mic_bkin_filled_at_event ? 1U : 0U) | 2U); /* bit 1: DMA trace frozen */
  for (uint32_t i = 0U; i < valid_count; ++i) {
    const uint32_t source = mic_bkin_filled_at_event ?
        ((next + i) & (MIC_BKIN_SAMPLE_COUNT - 1U)) : i;
    const uint32_t destination = first_valid + i;
    if ((mic_bkin_ring[source] & GPIO_PIN_6) != 0U)
      mic_bkin_record[32U + destination / 8U] |= (uint8_t)(1U << (destination & 7U));
  }
  mic_bkin_record_crc = uv3_crc32c(mic_bkin_record, MIC_BKIN_RECORD_BYTES);
  __DMB();
  mic_bkin_record_ready = 1U;
}

static void mic_bkin_wave_packet(uint8_t *packet, unsigned page) {
  memset(packet, 0, UV3_FRAME);
  packet[0] = 0x55U;
  packet[1] = 0xAAU;
  packet[2] = MIC_BKIN_WIRE_VERSION;
  packet[3] = (uint8_t)page;
  packet[4] = MIC_BKIN_WIRE_PAGES;
  bw_put32(packet + 6U, MIC_NUCLEO_FW_BUILD_ID);
  bw_put32(packet + 10U, mic_bkin_record_crc);
  const unsigned offset = page * MIC_BKIN_WIRE_CHUNK;
  unsigned length = MIC_BKIN_RECORD_BYTES - offset;
  if (length > MIC_BKIN_WIRE_CHUNK) length = MIC_BKIN_WIRE_CHUNK;
  memcpy(packet + 14U, mic_bkin_record + offset, length);
  uv3_seal(packet);
}
'''
    main = replace_once(main, insert_after, insert_after + capture_impl, "Nucleo capture implementation")

    # Keep the existing first-break record and hardware-BKIN handler order;
    # freeze only the extra recorder before the existing snapshot is committed.
    first_path = OUT / "nucleo/Inc/first_break_snapshot.h"
    first = first_path.read_text(encoding="utf-8-sig")
    first = replace_once(first, "extern volatile mic_break_snapshot_t mic_first_break;",
        "void mic_bkin_capture_stop_from_break(uint32_t tick_ms);\n"
        "extern volatile mic_break_snapshot_t mic_first_break;", "Break recorder declaration")
    first = replace_once(first, "  if ((sr & (TIM_SR_BIF | TIM_SR_B2IF)) == 0U) return;\n",
        "  if ((sr & (TIM_SR_BIF | TIM_SR_B2IF)) == 0U) return;\n"
        "  mic_bkin_capture_stop_from_break(tick_ms);\n", "Break freeze hook")
    write(first_path, first)

    main = replace_once(main, "static void uno_stop_motor(void) {\n  (void)MC_StopMotor1();",
        "static void uno_stop_motor(void) {\n  mic_bkin_capture_stop_software();\n  (void)MC_StopMotor1();", "Software stop hook")
    main = replace_once(main, "    if (start_state == IDLE) {\n      mic_break_start_window = 1U;",
        "    if (start_state == IDLE) {\n      mic_bkin_capture_start();\n      mic_break_start_window = 1U;", "START capture hook")
    main = replace_once(main, "  /* Keep the external UNO Q transport outside generated peripheral lists. */\n  uno_link_init();",
        "  /* Reuse TIM2 for passive BKIN trace after MCSDK's boot synchronization. */\n"
        "  mic_bkin_capture_init();\n\n"
        "  /* Keep the external UNO Q transport outside generated peripheral lists. */\n  uno_link_init();", "Capture initialization")
    main = replace_once(main, "static void mic_send_break_page(uint32_t now_ms) {\n  static uint32_t last_ms;\n  static uint8_t slot;",
        "static void mic_send_break_page(uint32_t now_ms) {\n  static uint32_t last_ms;\n  static uint8_t slot;\n  mic_bkin_prepare_record();", "Passive sender setup")
    main = replace_once(main, "  const unsigned kind = slot / BW_PAGES;\n  const unsigned page = slot % BW_PAGES;\n  const volatile mic_break_snapshot_t *record = kind == 0U ? &mic_first_break : &mic_first_start_break;\n",
        "  if (slot >= 2U * BW_PAGES) {\n"
        "    if (mic_bkin_record_ready != 0U) {\n"
        "      uint8_t packet[UV3_FRAME];\n"
        "      mic_bkin_wave_packet(packet, slot - 2U * BW_PAGES);\n"
        "      if (HAL_UART_Transmit(&huart1,packet,UV3_FRAME,UNO_REPLY_TIMEOUT_MS) != HAL_OK)\n"
        "        bw_increment(&mic_break_diag_tx_errors);\n"
        "    }\n"
        "    slot = (uint8_t)((slot + 1U) % (2U * BW_PAGES + MIC_BKIN_WIRE_PAGES));\n"
        "    return;\n"
        "  }\n"
        "  const unsigned kind = slot / BW_PAGES;\n  const unsigned page = slot % BW_PAGES;\n"
        "  const volatile mic_break_snapshot_t *record = kind == 0U ? &mic_first_break : &mic_first_start_break;\n", "Passive wave pages")
    main = replace_once(main, "  slot=(uint8_t)((slot+1U)%(2U*BW_PAGES));",
        "  slot=(uint8_t)((slot+1U)%(2U*BW_PAGES + MIC_BKIN_WIRE_PAGES));", "Passive page schedule")
    write(main_path, main)

    # Matched Uno receiver and low-rate text export; D2 pages are ignored unless
    # the peer is fresh and both PWM/output status bits are clear.
    uno_path = OUT / "UNOQ_MOTOR/UNOQ_MOTOR.ino"
    uno = uno_path.read_text(encoding="utf-8-sig")
    uno = replace_once(uno, '#include "break_wire.h"\nstatic bw_receiver g_break_wire;',
        '#include "break_wire.h"\n#include "bkin_wave_wire.h"\n'
        'static bw_receiver g_break_wire;\nstatic bkw_receiver g_bkin_wave;', "Uno wire receiver include")
    uno = replace_once(uno, "FW_BUILD_ID = 2026101505U", f"FW_BUILD_ID = {UNO_BUILD}U", "Uno build id")
    uno = replace_once(uno, "g_bp_fw_build==2026101504U", "g_bp_fw_build==2026101506U", "Uno peer identity")
    uno = replace_once(uno, "  for (unsigned kind=0;kind<2;++kind) {\n    s += kind == 0 ? \" mc_break0_hex=\" : \" mc_break1_hex=\";",
        "  s += \" mc_break_wave_hex=\";\n"
        "  if (g_bkin_wave.complete) {\n"
        "    for (unsigned i=0;i<BKW_RECORD_BYTES;++i) {\n"
        "      const uint8_t byte=g_bkin_wave.data[i];\n"
        "      s += break_hex[byte>>4]; s += break_hex[byte&15];\n"
        "    }\n"
        "  } else s += \"-\";\n"
        "  s += \" mc_break_wave_age_ms=\"; s += String((unsigned long)(g_bkin_wave.complete ?\n"
        "      (uint32_t)(millis()-g_bkin_wave.received_ms) : 999999U));\n"
        "  s += \" mc_break_wave_good_pages=\"; s += String((unsigned long)g_bkin_wave.good_pages);\n"
        "  s += \" mc_break_wave_bad_pages=\"; s += String((unsigned long)g_bkin_wave.bad_pages);\n"
        "\n  for (unsigned kind=0;kind<2;++kind) {\n    s += kind == 0 ? \" mc_break0_hex=\" : \" mc_break1_hex=\";", "Uno waveform status export")
    uno = replace_once(uno, "      if (buf[2] == BW_VERSION) {",
        "      if (buf[2] == BKW_VERSION) {\n"
        "        const uint32_t observed_ms=millis();\n"
        "        const uint32_t observed_age=(uint32_t)(observed_ms-g_bp_last_rsp_ms);\n"
        "        const bool fresh_off = g_bp_mcsdk_telemetry && !g_pwm_enabled &&\n"
        "            (g_bp_status & 0x22U) == 0U && observed_age < 300U;\n"
        "        (void)bkw_receive(&g_bkin_wave,buf,g_bp_fw_build,fresh_off,observed_ms);\n"
        "        continue;\n"
        "      }\n"
        "      if (buf[2] == BW_VERSION) {", "Uno D2 receive path")
    write(uno_path, uno)

    # Existing D1 event snapshots remain byte-for-byte ABI compatible.
    for rel in ("nucleo/Inc/break_wire.h", "UNOQ_MOTOR/break_wire.h"):
        p = OUT / rel
        write(p, replace_once(p.read_text(encoding="utf-8-sig"),
            "BW_NUCLEO_BUILD 2026101504UL", f"BW_NUCLEO_BUILD {MC_BUILD}UL", rel))
    diag = OUT / "UNOQ_MOTOR/nucleo_fault_diagnostics.h"
    d = diag.read_text(encoding="utf-8-sig")
    d = replace_once(d, "build==2026101504U", "(build==2026101504U || build==2026101506U)", "Fault diagnostic identity")
    d = replace_once(d, "build == 2026101414U || build == 2026101504U;",
        "build == 2026101414U || build == 2026101504U || build == 2026101506U;",
        "Fault diagnostic build allowlist")
    write(diag, d)

    # HMI recognizes only the new matched pair for manual control and exposes
    # the trace through a read-only endpoint after a trip.
    hmi_path = OUT / "web_hmi/server.py"
    hmi = hmi_path.read_text(encoding="utf-8-sig")
    hmi = replace_once(hmi, "2026101412, 2026101414, 2026101502, 2026101504)",
        "2026101412, 2026101414, 2026101502, 2026101504, 2026101506)", "HMI snapshot peer allowlist")
    hmi = replace_once(hmi, "        (2026101505, 2026101504),",
        "        (2026101505, 2026101504),\n        (2026101507, 2026101506),", "HMI firmware pair allowlist")
    hmi = replace_once(hmi,
        'if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) in (2026101502,2026101504) and (_as_int(data or {}, "fw_build", -1),_as_int(data or {}, "mc_fw_build", -1)) != (2026101505,2026101504):',
        'if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) in (2026101502,2026101504,2026101506) and (_as_int(data or {}, "fw_build", -1),_as_int(data or {}, "mc_fw_build", -1)) not in ((2026101505,2026101504),(2026101507,2026101506)):',
        "HMI matched-pair arm guard")
    hmi = replace_once(hmi,
        'return bool(data and _as_int(data,"fw_build",0)==2026101505 and\n        _as_int(data,"mc_fw_build",0)==2026101504 and _as_int(data,"manual_scalar_capable",0)==1)',
        'return bool(data and (_as_int(data,"fw_build",0),_as_int(data,"mc_fw_build",0)) in ((2026101505,2026101504),(2026101507,2026101506)) and _as_int(data,"manual_scalar_capable",0)==1)',
        "HMI manual pair support")
    hmi = replace_once(hmi, '"uno_rx_rejected_hex": kv.get("uno_rx_rejected_hex", "-"),',
        '"uno_rx_rejected_hex": kv.get("uno_rx_rejected_hex", "-"),\n'
        '                "mc_break_wave_hex": kv.get("mc_break_wave_hex", "-"),\n'
        '                "mc_break_wave_age_ms": int(kv.get("mc_break_wave_age_ms", "999999")),\n'
        '                "mc_break_wave_good_pages": int(kv.get("mc_break_wave_good_pages", "0")),\n'
        '                "mc_break_wave_bad_pages": int(kv.get("mc_break_wave_bad_pages", "0")),', "HMI waveform raw fields")
    wave_function = r'''

def bkin_wave_status(data):
    """Decode the frozen 1 MHz PA6 trace; never infer current or fault cause."""
    unavailable = {"available": False, "reason": "not_received"}
    try:
        if _as_int(data or {}, "mc_fw_build", 0) != 2026101506:
            return {"available": False, "reason": "wrong_peer_build"}
        text = data.get("mc_break_wave_hex", "")
        age = _as_int(data, "mc_break_wave_age_ms", 999999)
        if not text or text == "-": return unavailable
        if len(text) != 320 or any(c not in "0123456789abcdefABCDEF" for c in text):
            return {"available": False, "reason": "invalid_hex"}
        if not 0 <= age <= 5000: return {"available": False, "reason": "stale"}
        raw = bytes.fromhex(text)
        u32 = lambda offset: int.from_bytes(raw[offset:offset+4], "little")
        if (u32(0) != 0x314E4B42 or u32(4) != 1 or u32(8) != 160 or
                u32(16) != 1000 or not 1 <= u32(20) <= 1024 or
                u32(24) != 1023 or not (u32(28) & 2) or (u32(28) & ~3)):
            return {"available": False, "reason": "invalid_record"}
        valid_count = u32(20)
        valid_from = 1024 - valid_count
        bits = raw[32:160]
        samples = [None if i < valid_from else int(bool(bits[i // 8] & (1 << (i & 7))))
                   for i in range(1024)]
        low_intervals = []
        start = None
        for i in range(valid_from, 1025):
            low = i < 1024 and samples[i] == 0
            if low and start is None: start = i
            elif not low and start is not None:
                low_intervals.append({"from_us": start - 1023, "to_us": i - 1023,
                                      "includes_capture_boundary": i == 1024})
                start = None
        return {"available": True, "reason": "recorded", "age_ms": age,
            "sample_rate_hz": 1000000, "sample_period_us": 1,
            "sample_count": 1024, "valid_sample_count": valid_count,
            "unknown_prefix_samples": valid_from, "trigger_index": 1023,
            "trace_reference": "last DMA sample before BKIN interrupt handling; exact edge offset includes IRQ latency",
            "pa6_samples": samples, "pa6_low_intervals": low_intervals,
            "pa6_low_is_active": True,
            "limitations": ["Digital BKIN/SD input only; no current, J4 rail, or phase voltage is measured",
                "Sub-microsecond pulse widths are below this recorder's resolution",
                "Trace alone cannot identify overcurrent, driver undervoltage, or interference"]}
    except (ValueError, TypeError, OverflowError):
        return {"available": False, "reason": "invalid_metadata"}
'''
    hmi = replace_once(hmi, "\n\nSTATE_NAMES = {", wave_function + "\n\nSTATE_NAMES = {", "HMI waveform decoder")
    hmi = replace_once(hmi, '        if parsed.path == "/api/break-snapshot":',
        '        if parsed.path == "/api/bkin-trace":\n'
        '            if not self._require_control_access(mark_heartbeat=False):\n'
        '                return\n'
        '            ok, data, err = self.server.app.rpc.get()\n'
        '            if not ok or data is None:\n'
        '                self._send_json({"ok": False, "error": err or "no response"}, 503)\n'
        '                return\n'
        '            self.server.app.maybe_log_status(data)\n'
        '            self._send_json({"ok": True, "data": bkin_wave_status(data)})\n'
        '            return\n'
        '        if parsed.path == "/api/break-snapshot":', "HMI waveform endpoint")
    write(hmi_path, hmi)

    html_path = OUT / "web_hmi/static/index.html"
    html = html_path.read_text(encoding="utf-8-sig")
    html = replace_once(html,
        '        <div class="status-footer">\n          <span id="lastUpdate">Нет данных</span>\n        </div>',
        '        <div class="status-footer">\n          <span id="lastUpdate">Нет данных</span>\n'
        '          <button id="bkinTraceLoad" class="btn ghost" type="button">Считать снимок BKIN</button>\n'
        '          <span id="bkinTraceStatus">Снимок появится после срабатывания защиты.</span>\n'
        '        </div>', "HMI waveform control")
    write(html_path, html)

    js_path = OUT / "web_hmi/static/app.js"
    js = js_path.read_text(encoding="utf-8-sig")
    js = replace_once(js, 'const lastUpdate = document.getElementById("lastUpdate");',
        'const lastUpdate = document.getElementById("lastUpdate");\n'
        'const bkinTraceLoad = document.getElementById("bkinTraceLoad");\n'
        'const bkinTraceStatus = document.getElementById("bkinTraceStatus");', "HMI waveform controls")
    js = replace_once(js, "async function apiStatus() {", r'''async function loadBkinTrace() {
  if (!bkinTraceLoad || !bkinTraceStatus) return;
  bkinTraceLoad.disabled = true;
  bkinTraceStatus.textContent = "Читаю сохранённый снимок…";
  try {
    const res = await fetch("/api/bkin-trace", {
      headers: controlHeaders(false), cache: "no-store",
    });
    const envelope = await res.json().catch(() => ({ ok: false }));
    noteApiAccess(envelope);
    if (!res.ok || envelope.ok !== true) throw new Error(envelope.error || "Снимок недоступен");
    const trace = envelope.data || {};
    if (!trace.available) {
      const reasons = { not_received: "снимок ещё не получен", wrong_peer_build: "не совпадает версия Nucleo",
        invalid_hex: "повреждён ответ", invalid_record: "неверный формат снимка", stale: "снимок устарел" };
      bkinTraceStatus.textContent = reasons[trace.reason] || "снимок пока недоступен";
      return;
    }
    const pulses = (trace.pa6_low_intervals || []).map((p) =>
      `${p.from_us}…${p.to_us} мкс`).join(", ");
    bkinTraceStatus.textContent = `PA6 LOW: ${pulses || "не обнаружен"}; ` +
      `${trace.valid_sample_count}/1024 отсчётов, шаг 1 мкс`;
  } catch (error) {
    bkinTraceStatus.textContent = error.message || "ошибка чтения снимка";
  } finally {
    bkinTraceLoad.disabled = false;
  }
}

if (bkinTraceLoad) bkinTraceLoad.addEventListener("click", loadBkinTrace);

async function apiStatus() {''', "HMI waveform reader")
    write(js_path, js)

    css_path = OUT / "web_hmi/static/style.css"
    css = css_path.read_text(encoding="utf-8-sig")
    css += '\n.status-footer #bkinTraceStatus { flex-basis: 100%; }\n'
    write(css_path, css)

    # Candidate-specific protocol header.
    wire = r'''#ifndef MIC_BKIN_WAVE_WIRE_H
#define MIC_BKIN_WAVE_WIRE_H
#include "break_wire.h"

enum { BKW_VERSION=0xD2, BKW_RECORD_BYTES=160, BKW_CHUNK=24, BKW_PAGES=7, BKW_TIMEOUT_MS=5000 };
#define BKW_RECORD_MAGIC UINT32_C(0x314e4b42)

typedef struct {
  uint8_t data[BKW_RECORD_BYTES];
  uint8_t mask;
  uint32_t crc;
  uint32_t started_ms;
  uint32_t received_ms;
  uint32_t good_pages;
  uint32_t bad_pages;
  bool complete;
} bkw_receiver;

static inline bool bkw_receive(bkw_receiver *rx, const uint8_t *packet,
    uint32_t peer_build, bool peer_fresh_off, uint32_t now_ms) {
  if (rx->complete) return true; /* immutable first BKIN trace per boot */
  unsigned page=packet[3];
  if (packet[0]!=0x55 || packet[1]!=0xaa || packet[2]!=BKW_VERSION ||
      !uv3_crc_ok(packet) || page>=BKW_PAGES || packet[4]!=BKW_PAGES || packet[5]!=0 ||
      bw_u32(packet+6)!=BW_NUCLEO_BUILD || peer_build!=BW_NUCLEO_BUILD ||
      !peer_fresh_off || packet[38]!=0) { bw_increment(&rx->bad_pages); return false; }
  const unsigned offset=page*BKW_CHUNK;
  unsigned length=BKW_RECORD_BYTES-offset;
  if (length>BKW_CHUNK) length=BKW_CHUNK;
  for (unsigned i=length;i<BKW_CHUNK;++i) if (packet[14+i]!=0) {
    bw_increment(&rx->bad_pages); return false;
  }
  const uint32_t crc=bw_u32(packet+10);
  if (!rx->mask || rx->crc!=crc || (uint32_t)(now_ms-rx->started_ms)>BKW_TIMEOUT_MS) {
    memset(rx->data,0,sizeof(rx->data)); rx->mask=0; rx->crc=crc; rx->started_ms=now_ms;
  }
  const uint8_t bit=(uint8_t)(1U<<page);
  if ((rx->mask&bit) && memcmp(rx->data+offset,packet+14,length)!=0) {
    rx->mask=0; bw_increment(&rx->bad_pages); return false;
  }
  memcpy(rx->data+offset,packet+14,length); rx->mask|=bit; bw_increment(&rx->good_pages);
  if (rx->mask==(uint8_t)((1U<<BKW_PAGES)-1U)) {
    if (uv3_crc32c(rx->data,BKW_RECORD_BYTES)!=rx->crc ||
        bw_u32(rx->data)!=BKW_RECORD_MAGIC || bw_u32(rx->data+4)!=1U ||
        bw_u32(rx->data+8)!=BKW_RECORD_BYTES || bw_u32(rx->data+16)!=1000U ||
        bw_u32(rx->data+20)==0U || bw_u32(rx->data+20)>1024U ||
        bw_u32(rx->data+24)!=1023U || !(bw_u32(rx->data+28)&2U) ||
        (bw_u32(rx->data+28)&~3U)) { rx->mask=0; bw_increment(&rx->bad_pages); return false; }
    rx->received_ms=now_ms; rx->complete=true; rx->mask=0;
  }
  return true;
}
#endif
'''
    write(OUT / "UNOQ_MOTOR/bkin_wave_wire.h", wire)

    capture_header = r'''#ifndef MIC_BKIN_WAVE_CAPTURE_H
#define MIC_BKIN_WAVE_CAPTURE_H
#include <stdint.h>

enum {
  MIC_BKIN_SAMPLE_HZ = 1000000U,
  MIC_BKIN_SAMPLE_COUNT = 1024U,
  MIC_BKIN_RECORD_BYTES = 160U,
  MIC_BKIN_WIRE_CHUNK = 24U,
  MIC_BKIN_WIRE_PAGES = 7U,
  MIC_BKIN_WIRE_VERSION = 0xD2U,
  MIC_BKIN_CAPTURE_IDLE = 0U,
  MIC_BKIN_RUNNING = 1U,
  MIC_BKIN_STOPPED = 2U,
  MIC_BKIN_CAPTURED = 3U,
  MIC_BKIN_CAPTURE_ERROR = 4U
};
#define MIC_BKIN_RECORD_MAGIC 0x314E4B42UL
#define MIC_BKIN_RECORD_SCHEMA 1U

void mic_bkin_capture_stop_from_break(uint32_t tick_ms);
#endif
'''
    write(OUT / "nucleo/Inc/bkin_wave_capture.h", capture_header)

    # Keep the active predecessor and its frozen qualification evidence intact.
    after = {tree: tree_hashes(OUT / tree) for tree in ("nucleo", "UNOQ_MOTOR", "web_hmi")}
    changed = {
        tree: sorted(k for k in (set(before[tree]) | set(after[tree]))
                     if before[tree].get(k) != after[tree].get(k))
        for tree in before
    }
    expected = {
        "nucleo": ["Inc/bkin_wave_capture.h", "Inc/break_wire.h", "Inc/first_break_snapshot.h", "Src/main.c"],
        "UNOQ_MOTOR": ["UNOQ_MOTOR.ino", "bkin_wave_wire.h", "break_wire.h", "nucleo_fault_diagnostics.h"],
        "web_hmi": ["server.py", "static/app.js", "static/index.html", "static/style.css"],
    }
    if changed != expected:
        raise RuntimeError(f"Unexpected candidate source changes: {changed}")
    if before != {tree: tree_hashes(BASE / tree) for tree in before}:
        raise RuntimeError("Frozen predecessor changed during preparation")

    docs = f'''# BKIN trace candidate {UNO_BUILD} / {MC_BUILD}

This is a separate, uninstalled diagnostic pair derived from the working pair
{predecessor['pair'][0]} / {predecessor['pair'][1]}. The installed firmware,
live HMI, calibration, and archived run results were not changed.

## What it records

On each START, Nucleo uses the previously unused DMA2 channel 1 and repurposes
TIM2 after MCSDK has completed its one-time boot synchronization. The recorder
holds TIM2 TRGO at reset and triggers one GPIOA IDR read each microsecond into a
1024-word circular buffer. PA6 is the BKIN/SD digital input. When TIM1 reports BKIN/BK2, the new
recorder stops only its own timer and DMA before the existing first-break
snapshot and MCSDK handler continue. It preserves the most recent 1.024 ms,
packs PA6 into a 128-byte bit trace, and sends seven CRC-protected D2 pages
through the existing UART only after outputs are confirmed off. Uno exposes the
decoded trace at `GET /api/bkin-trace`; no Saleae lead or PC ground is involved.

The existing D1 first-break snapshots keep their 92-byte format. UART control
frames, PWM generation, ADC setup, TIM1 break configuration, and V/f profile are
not modified. The HMI enables only the matched pair above.

## Limits and status

The trace measures one digital PA6 signal at 1 MHz. It does not measure J4,
phase voltage, or qualified motor current, and by itself cannot identify the
physical cause of the IPM trip. Its time zero is the final DMA sample before
BKIN interrupt handling, not a hardware timestamp of the electrical edge;
sub-microsecond pulses are not resolved. If fewer than 1024 valid samples were
collected after START, the returned prefix is marked unknown.

`installed=false`, `hardware_commands=0`, and `hv_release_approved=false` are
intentional. The candidate has not been programmed or electrically qualified.
Do not use the predecessor pair's results as qualification for this new image.
The next bench step is a controlled low-voltage compile/readback and then a
single supervised trip capture; no powered trial is authorized by this package.
'''
    write(OUT / "BKIN_TRACE_RU.md", docs)

    manifest = {
        "schema": "mic_ai.bkin_waveform_pair_candidate.v1",
        "pair": [UNO_BUILD, MC_BUILD],
        "predecessor_pair": predecessor["pair"],
        "predecessor_candidate": str(BASE),
        "candidate": str(OUT),
        "prepared": True,
        "installed": False,
        "qualification_pending": True,
        "hardware_commands": 0,
        "hv_release_approved": False,
        "capture": {"signal": "Nucleo PA6 / TIM1 BKIN-SD", "sampling_hz": 1000000,
            "sample_count": 1024, "window_us": 1024, "storage": "DMA2 channel 1 circular ring, 32-bit GPIOA IDR samples",
            "trigger": "first TIM1 BIF/B2IF interrupt", "transport": "passive D2 pages over existing UART after outputs-off confirmation",
            "retention": "one trace per Nucleo boot; software STOP and CLEAR preserve captured event"},
        "changed_files": changed,
        "predecessor_sha256": {tree: before[tree] for tree in before},
        "candidate_sha256": after,
        "calibration_changed": False,
        "protection_configuration_changed": False,
        "uart_control_layout_changed": False,
        "d1_snapshot_layout_changed": False,
        "saleae_connection_required": False,
        "test_runs": 0,
    }
    write(OUT / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    result = prepare()
    print(json.dumps({"prepared": result["prepared"], "pair": result["pair"],
                      "candidate": result["candidate"], "installed": result["installed"]}))

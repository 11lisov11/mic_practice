"""Prepare isolated UART-v3 firmware candidates; never connect or upload."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_mcsdk_logic_bench import function_span, replace_once


PROJECT = "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
NUCLEO_BUILD = 2026101006
UNO_BUILD = 2026101007


def span(text: str, start: str, end: str, replacement: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError("Nonunique candidate section")
    a = text.index(start)
    b = text.index(end, a)
    return text[:a] + replacement + "\n\n" + text[b:]


def nucleo_source(root: Path) -> str:
    text = (root / PROJECT / "Src/main.c").read_text(encoding="utf-8-sig")
    text = replace_once(text, "UNO_FRAME_LEN = 32U,", "UNO_FRAME_LEN = UV3_FRAME,")
    text = replace_once(text, "UNO_PROTOCOL_VERSION = 0x02U,", "UNO_PROTOCOL_VERSION = UV3_VERSION,")
    text = replace_once(text, "#define MIC_NUCLEO_FW_BUILD_ID 2026100801UL",
                        f"#define MIC_NUCLEO_FW_BUILD_ID {NUCLEO_BUILD}UL")
    text = replace_once(text, "enum {\n  UNO_FRAME_LEN", '#include "uart_v3_transport.h"\n\nenum {\n  UNO_FRAME_LEN')
    fifo = (root / "research/uart_v3/nucleo_fifo.c.inc").read_text(encoding="utf-8")
    text = span(text, "/* Single ISR producer,", "static uint32_t uno_u32le", fifo)
    # Reserved/service checks stop at the payload boundary, not the new CRC.
    text = text.replace("(UNO_FRAME_LEN - 1U)", "UV3_PAYLOAD")
    text = replace_once(text, "reply[UNO_FRAME_LEN - 1U] = uno_crc_xor(reply);",
                        "uv3_reply_diagnostics(reply, &uno_transport);\n  uv3_seal(reply);")
    parser = (root / "research/uart_v3/nucleo_parser.c.inc").read_text(encoding="utf-8")
    a, b = function_span(text, "uno_consume_byte")
    text = text[:a] + parser + text[b:]
    text = replace_once(text, "uno_rx_errors = uno_rx_overflow = 0U;\n}",
                        "uno_rx_errors = uno_rx_overflow = 0U;\n  uv3_init(&uno_transport, true);\n}")
    text = replace_once(text, "uno_link.parser_state = 0U;\n      uno_link.parser_index = 0U;",
                        "uno_link.parser_state = 0U;\n      uno_link.parser_index = 0U;\n"
                        "      uno_transport.last_uart_flags = errors;\n"
                        "      uv3_trip(&uno_transport, UV3_HARD_UART);")
    text = replace_once(text, "uint8_t byte;\n  while (uno_rx_pop(&byte)) {",
                        "uno_transport_result(uv3_tick(&uno_transport, HAL_GetTick()));\n"
                        "  uint8_t byte, flags;\n  while (uno_rx_pop(&byte, &flags)) {")
    text = replace_once(text, "uno_consume_byte(byte);", "uno_consume_sample(byte, flags);")
    text = replace_once(text, "HAL_UARTEx_EnableFifoMode(&huart1)", "HAL_UARTEx_DisableFifoMode(&huart1)")
    if "uno_crc_xor" in text or "uno_consume_byte" in text:
        raise RuntimeError("Obsolete v2 parser retained")
    return text


def uno_source(root: Path) -> str:
    text = (root / "UNOQ_MOTOR/UNOQ_MOTOR.ino").read_text(encoding="utf-8-sig")
    text = replace_once(text, '#include "scoped_control_lock.h"',
                        '#include "scoped_control_lock.h"\n#include "uart_v3_transport.h"')
    text = replace_once(text, "FW_BUILD_ID = 2026101002U", f"FW_BUILD_ID = {UNO_BUILD}U")
    text = replace_once(text, "BP_FRAME_LEN = 32;", "BP_FRAME_LEN = UV3_FRAME;")
    text = replace_once(text, "BP_CRC_OFF = BP_FRAME_LEN - 1;", "BP_CRC_OFF = UV3_PAYLOAD;")
    text = replace_once(text, "BP_VER = 0x02;", "BP_VER = UV3_VERSION;")
    # Function content is matched exactly; remove misleading crc8/XOR API.
    start = text.index("static uint8_t nucleo_crc8(")
    end = text.index("static float bp_temp_voltage_from_raw", start)
    text = text[:start] + text[end:]
    text = replace_once(text, "uint8_t crc = nucleo_crc8(rx, BP_CRC_OFF);\n  if (crc != rx[BP_CRC_OFF]) return false;",
                        "if (!uv3_crc_ok(rx)) return false;")
    text = replace_once(text, "nucleo_crc8(buf, BP_CRC_OFF) == buf[BP_CRC_OFF]", "uv3_crc_ok(buf)")
    text = replace_once(text, "pkt[BP_CRC_OFF] = nucleo_crc8(pkt, BP_CRC_OFF);", "uv3_seal(pkt);")
    text = replace_once(text, "static uint16_t g_bp_good_cnt = 0;",
                        "static uint16_t g_bp_ne_accepted = 0;\nstatic uint16_t g_bp_ne_observed = 0;\n"
                        "static uint8_t g_bp_ne_flags = 0;\nstatic uint8_t g_bp_transport_fault = 0;\n"
                        "static uint16_t g_bp_good_cnt = 0;")
    text = replace_once(text, "g_bp_status = rx[3];",
                        "g_bp_ne_accepted = (uint16_t)rx[31] | ((uint16_t)rx[32] << 8);\n"
                        "  g_bp_ne_observed = (uint16_t)rx[33] | ((uint16_t)rx[34] << 8);\n"
                        "  g_bp_ne_flags = rx[37];\n  g_bp_transport_fault = rx[38];\n  g_bp_status = rx[3];")
    text = replace_once(text, 's += " bp_good_cnt=";',
                        's += " bp_ne_accepted="; s += String((int)g_bp_ne_accepted);\n'
                        '  s += " bp_ne_observed="; s += String((int)g_bp_ne_observed);\n'
                        '  s += " bp_ne_flags="; s += String((int)g_bp_ne_flags);\n'
                        '  s += " bp_transport_fault="; s += String((int)g_bp_transport_fault);\n'
                        '  s += " bp_good_cnt=";')
    if "nucleo_crc8" in text:
        raise RuntimeError("Obsolete Uno XOR API retained")
    return text


def prepare(root: Path, out: Path) -> dict:
    # Refuse existing destinations; never overwrite a known build or worktree.
    out.mkdir(parents=True, exist_ok=False)
    source_paths = [root / PROJECT / "Src/main.c", root / "UNOQ_MOTOR/UNOQ_MOTOR.ino"]
    source_paths += list((root / "research/uart_v3").glob("*"))
    before = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source_paths if p.is_file()}
    nuc = out / "nucleo"
    uno = out / "UNOQ_MOTOR"
    shutil.copytree(root / PROJECT, nuc, ignore=shutil.ignore_patterns("Debug", "Release", ".settings"))
    shutil.copytree(root / "UNOQ_MOTOR", uno)
    (nuc / "Src/main.c").write_text(nucleo_source(root), encoding="utf-8")
    (uno / "UNOQ_MOTOR.ino").write_text(uno_source(root), encoding="utf-8")
    for dest in (nuc / "Inc/uart_v3_transport.h", uno / "uart_v3_transport.h"):
        shutil.copyfile(root / "research/uart_v3/uart_v3_transport.h", dest)
    decoder = uno / "nucleo_fault_diagnostics.h"
    body = decoder.read_text(encoding="utf-8-sig")
    body = replace_once(body, "build == 2026100801U || build == 2026100899U;",
                        f"build == 2026100801U || build == 2026100899U || build == 2026101003U || build == {NUCLEO_BUILD}U;")
    body = replace_once(body, "complete 32-byte frame CRC", "complete versioned frame CRC")
    decoder.write_text(body, encoding="utf-8")
    timing = uno / "link_timing.h"
    body = timing.read_text(encoding="utf-8-sig")
    body = replace_once(body, "#pragma once", '#pragma once\n#include "uart_v3_transport.h"')
    body = replace_once(body, "written != 32U", "written != UV3_FRAME")
    timing.write_text(body, encoding="utf-8")
    if before != {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in source_paths if p.is_file()}:
        raise RuntimeError("Source changed during candidate preparation")
    report = {"schema": "mic.uart_v3_candidate.v1", "prepared": True,
              "protocol_version": 3, "frame_bytes": 43, "checksum": "CRC-32C little endian",
              "uno_fw_build": UNO_BUILD, "nucleo_fw_build": NUCLEO_BUILD,
              "source_sha256": before, "hardware_commands": 0,
              "flash_ready": False, "hv_release_approved": False,
              "warning": "ISOLATED CANDIDATE: HMI identity approval and physical link qualification pending"}
    (out / "candidate-manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(Path(__file__).resolve().parents[1], args.outdir.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

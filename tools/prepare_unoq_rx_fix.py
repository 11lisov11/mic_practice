"""Isolated RX repair from the exact installed passive snapshot sketch; no deployment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_mcsdk_logic_bench import replace_once
from prepare_ipm_break_wifi import patch_function, source_hashes, ROOT

BASE = ROOT / 'artifacts/live_bench_20261011/ipm_break_wifi/candidate_r6'
ASSETS = ROOT / 'research/uart_rx'
BUILD = 2026101104


def sketch(text):
    text = replace_once(text, 'FW_BUILD_ID = 2026101103U', f'FW_BUILD_ID = {BUILD}U')
    text = replace_once(text, '#define NUCLEO_SERIAL Serial1',
        '#include "nucleo_buffered_serial.h"\n'
        'static NucleoBufferedSerial g_nucleo_serial(DEVICE_DT_GET(DT_PHANDLE_BY_IDX(DT_PATH(zephyr_user), serials, 0)));\n'
        '#define NUCLEO_SERIAL g_nucleo_serial')
    text = replace_once(text, 'static bw_receiver g_break_wire;',
        'static bw_receiver g_break_wire;\n'
        'static uint8_t g_rx_rejected[UV3_FRAME];\n'
        'static uint32_t g_rx_rejected_ms, g_rx_poll_ms, g_rx_poll_gap_max_ms;')
    def rpc(code):
        code = replace_once(code, '  s.reserve(160);', '  s.reserve(4096);')
        code = replace_once(code, '  const unsigned int timing_done_key = irq_lock();',
            '  // ControlMutex already protects snapshot writers. Never format strings with IRQs off.')
        code = replace_once(code, '  g_link_timing.rpc(micros() - timing_started);',
            '  const auto rx_stats = g_nucleo_serial.stats();\n'
            '  s += " uno_rx_dropped="; s += String((unsigned long)rx_stats.dropped);\n'
            '  s += " uno_rx_hw_errors="; s += String((unsigned long)rx_stats.errors);\n'
            '  s += " uno_rx_hw_flags="; s += String((unsigned long)rx_stats.error_flags);\n'
            '  s += " uno_rx_high_water="; s += String((unsigned long)rx_stats.high_water);\n'
            '  s += " uno_rx_pending="; s += String((unsigned long)rx_stats.pending);\n'
            '  s += " uno_rx_poll_gap_max_ms="; s += String((unsigned long)g_rx_poll_gap_max_ms);\n'
            '  s += " uno_rx_rejected_ms="; s += String((unsigned long)g_rx_rejected_ms);\n'
            '  s += " uno_rx_rejected_hex=";\n'
            '  if (!g_rx_rejected_ms) s += "-";\n'
            '  else for (unsigned i=0;i<UV3_FRAME;++i) {\n'
            '    s += break_hex[g_rx_rejected[i]>>4]; s += break_hex[g_rx_rejected[i]&15];\n'
            '  }\n'
            '  const unsigned int timing_done_key = irq_lock();\n'
            '  g_link_timing.rpc(micros() - timing_started);')
        return code
    text = patch_function(text, 'rpc_get', rpc)
    def poll(code):
        code = replace_once(code, '  while (NUCLEO_SERIAL.available() > 0) {',
            '  const uint32_t poll_ms = millis();\n'
            '  if (g_rx_poll_ms) LinkTiming::maximum(g_rx_poll_gap_max_ms, poll_ms-g_rx_poll_ms);\n'
            '  g_rx_poll_ms = poll_ms;\n'
            '  while (NUCLEO_SERIAL.available() > 0) {')
        return replace_once(code, '      if (buf[2] == BW_VERSION) {',
            '      if (!uv3_crc_ok(buf)) {\n'
            '        memcpy(g_rx_rejected,buf,sizeof(buf)); g_rx_rejected_ms=millis();\n'
            '      }\n'
            '      if (buf[2] == BW_VERSION) {')
    return patch_function(text, 'nucleo_uart_poll', poll)


def hmi(text):
    return replace_once(text, '                "bp_bad_integrity":',
        '                **{k: int(kv[k]) for k in ("uno_rx_dropped", "uno_rx_hw_errors",\n'
        '                    "uno_rx_hw_flags", "uno_rx_high_water", "uno_rx_pending",\n'
        '                    "uno_rx_poll_gap_max_ms", "uno_rx_rejected_ms") if k in kv},\n'
        '                "uno_rx_rejected_hex": kv.get("uno_rx_rejected_hex", "-"),\n'
        '                "bp_bad_integrity":')


def prepare(out):
    before = source_hashes(BASE / 'UNOQ_MOTOR')
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(BASE / 'UNOQ_MOTOR', out / 'UNOQ_MOTOR')
    shutil.copytree(BASE / 'web_hmi', out / 'web_hmi', ignore=shutil.ignore_patterns('__pycache__', '.venv'))
    for rel, transform in (('UNOQ_MOTOR/UNOQ_MOTOR.ino', sketch), ('web_hmi/server.py', hmi)):
        path = out / rel
        path.write_text(transform(path.read_text(encoding='utf-8-sig')), encoding='utf-8')
    for path in ASSETS.glob('*.h'): shutil.copy2(path, out / 'UNOQ_MOTOR' / path.name)
    assert source_hashes(BASE / 'UNOQ_MOTOR') == before
    manifest = dict(uno_build=BUILD, nucleo_build=2026101102, base_uno=before,
        source_sha256=source_hashes(out / 'UNOQ_MOTOR'),
        hmi_sha256=hashlib.sha256((out/'web_hmi/server.py').read_bytes()).hexdigest(),
        installed=False, hv_release_approved=False, rx_capacity=1024,
        control_crc_unchanged=True, nucleo_image_unchanged=True)
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(prepare(args.outdir.resolve())))

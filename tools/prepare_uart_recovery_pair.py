"""Prepare one working bundle with bounded UART recovery; never touch hardware."""
import argparse
import json
import shutil
import re
from pathlib import Path
from prepare_ipm_break_wifi import source_hashes
from prepare_pwm_filter_pair import sha, write, change

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/live_bench_20261014/pwm_filter_pair_r7/production'
HMI = ROOT / 'artifacts/live_bench_20261014/normal_start_hmi_r1/web_hmi/server.py'
PAIR = (2026101413, 2026101412)

RECOVERY = r'''
/* Every recovered event shares one sliding budget. Noise never refreshes the
   watchdog or publishes a command. Persistent damage still latches OFF. */
static inline bool uv3_take_recovery_budget(uv3_rx *rx, uint32_t now_ms) {
  if (!rx->bounded_noise || rx->fault_latched) return false;
  uint8_t keep = 0;
  for (uint8_t i = 0; i < rx->noise_used; ++i)
    if ((uint32_t)(now_ms - rx->noise_times[i]) < UV3_NE_WINDOW_MS)
      rx->noise_times[keep++] = rx->noise_times[i];
  rx->noise_used = keep;
  if (rx->noise_used >= UV3_NE_BUDGET) return false;
  rx->noise_times[rx->noise_used++] = now_ms;
  return true;
}

static inline uv3_result uv3_drop(uv3_rx *rx, uv3_result reason, uint32_t now_ms) {
  rx->last_uart_flags |= rx->frame_uart_flags;
  if (!uv3_take_recovery_budget(rx, now_ms)) return uv3_trip(rx, reason);
  if (rx->dropped_frames != UINT32_MAX) ++rx->dropped_frames;
  if (rx->recoverable_losses < UV3_NE_BUDGET) ++rx->recoverable_losses;
  rx->last_drop_reason = reason;
  rx->index = 0;
  rx->seeking_sync = true;
  /* Keep the last SEMANTICALLY committed sequence and its original deadline. */
  return UV3_DROPPED;
}

static inline void uv3_resync(uv3_rx *rx, uint32_t now_ms) {
  unsigned start = UV3_FRAME;
  for (unsigned i = 1; i + 1 < UV3_FRAME; ++i)
    if (rx->frame[i] == 0xaa && rx->frame[i+1] == 0x55) { start = i; break; }
  if (start == UV3_FRAME && rx->frame[UV3_FRAME-1] == 0xaa) start = UV3_FRAME-1;
  rx->index = (uint8_t)(UV3_FRAME - start);
  rx->seeking_sync = rx->index == 0;
  if (rx->index) {
    memmove(rx->frame, rx->frame + start, rx->index);
    memmove(rx->marks, rx->marks + start, rx->index);
    rx->frame_started_ms = now_ms;
  }
  rx->ne_bytes = 0;
  rx->frame_uart_flags = 0;
  for (unsigned i = 0; i < rx->index; ++i) {
    rx->frame_uart_flags |= rx->marks[i];
    if (rx->marks[i] & UV3_NE) ++rx->ne_bytes;
  }
}
'''

TICK = r'''static inline uv3_result uv3_tick(uv3_rx *rx, uint32_t now_ms) {
  if (rx->link_seen && !rx->fault_latched &&
      (uint32_t)(now_ms - rx->last_valid_ms) > UV3_WATCHDOG_MS)
    return uv3_trip(rx, UV3_LINK_TIMEOUT);
  if (rx->index != 0 && (uint32_t)(now_ms - rx->frame_started_ms) > UV3_FRAME_DEADLINE_MS)
    return uv3_drop(rx, UV3_FRAME_TIMEOUT, now_ms);
  return UV3_WAIT;
}'''

NOISE = r'''static inline bool uv3_noise_allowed(uv3_rx *rx, uint32_t now_ms) {
  /* Qualification follows clean LINK frames, including STOP. A CRC-valid
     fresh START/frequency change gets exactly the same rule as a heartbeat.
     CLEAR is deliberately required to be completely clean. */
  if (rx->ne_bytes != 1 || rx->clean_run_frames < UV3_CLEAN_REQUIRED ||
      rx->frame[3] == 8 || !uv3_take_recovery_budget(rx, now_ms)) return false;
  if (rx->accepted_noise_frames != UINT32_MAX) ++rx->accepted_noise_frames;
  return true;
}'''

BYTE = r'''static inline uv3_result uv3_byte(uv3_rx *rx, uint8_t byte, uint8_t flags, uint32_t now_ms) {
  rx->last_uart_flags = flags;
  if ((flags & UV3_NE) && rx->observed_noise_bytes != UINT32_MAX) ++rx->observed_noise_bytes;
  if (flags & (uint8_t)~UV3_NE) return uv3_trip(rx, UV3_HARD_UART);
  uv3_result pending = uv3_tick(rx, now_ms);
  if (pending != UV3_WAIT && pending != UV3_DROPPED) return pending;
  if (rx->index == 0) {
    if (byte != 0xaa) {
      if (!rx->seeking_sync && (flags || rx->link_seen)) {
        rx->frame_uart_flags = flags;
        return uv3_drop(rx, flags ? UV3_NOISE_REJECTED : UV3_BAD_CRC, now_ms);
      }
      return pending;
    }
    rx->seeking_sync = false;
    rx->frame_started_ms = now_ms;
    rx->ne_bytes = 0;
    rx->frame_uart_flags = 0;
  } else if (rx->index == 1 && byte != 0x55) {
    rx->frame_uart_flags |= flags;
    rx->index = 0;
    pending = uv3_drop(rx, flags || rx->ne_bytes ? UV3_NOISE_REJECTED : UV3_BAD_CRC, now_ms);
    if (pending != UV3_DROPPED) return pending;
    if (byte == 0xaa) {
      rx->frame[0] = byte; rx->marks[0] = flags;
      rx->ne_bytes = (flags & UV3_NE) ? 1 : 0;
      rx->frame_uart_flags = flags;
      rx->frame_started_ms = now_ms; rx->index = 1;
      rx->seeking_sync = false;
    }
    return pending;
  }
  rx->frame[rx->index] = byte;
  rx->marks[rx->index++] = flags;
  rx->frame_uart_flags |= flags;
  if (flags & UV3_NE) ++rx->ne_bytes;
  if (rx->index != UV3_FRAME) return pending;
  rx->index = 0;
  rx->last_uart_flags = rx->frame_uart_flags;
  if (!uv3_crc_ok(rx->frame)) {
    uv3_result result = uv3_drop(rx, UV3_BAD_CRC, now_ms);
    if (result == UV3_DROPPED) uv3_resync(rx, now_ms);
    return result;
  }
  if (rx->frame[2] != UV3_VERSION) return uv3_trip(rx, UV3_BAD_VERSION);
  if (rx->link_seen && !rx->fault_latched && rx->frame[3] == 1) {
    const uint8_t advance = (uint8_t)(rx->frame[5] - rx->previous[5]);
    /* A gap is legal only after a specific observed discarded packet and
       within the unextended 300 ms deadline. Replays/backward jumps fail. */
    if (advance == 0 || advance > (uint8_t)(rx->recoverable_losses + 1U))
      return uv3_trip(rx, UV3_BAD_SEQUENCE);
  }
  if (rx->ne_bytes && !uv3_noise_allowed(rx, now_ms))
    return uv3_drop(rx, UV3_NOISE_REJECTED, now_ms);
  return UV3_READY;
}'''

COMMIT = r'''static inline void uv3_commit(uv3_rx *rx, uint32_t now_ms, bool actually_running,
                              bool controller_fault, bool explicit_clean_clear) {
  if (explicit_clean_clear && rx->ne_bytes == 0 && !actually_running && !controller_fault) {
    rx->fault_latched = false; rx->fault = UV3_WAIT;
  }
  if (controller_fault || rx->fault_latched) {
    rx->link_seen = false; rx->run_anchor = false; rx->clean_run_frames = 0;
    rx->recoverable_losses = 0;
    return;
  }
  rx->link_seen = true; rx->last_valid_ms = now_ms;
  rx->run_anchor = actually_running && rx->frame[3] == 1 && rx->frame[4] == 3;
  if (rx->ne_bytes) rx->clean_run_frames = 0;
  else if (rx->clean_run_frames < UV3_CLEAN_REQUIRED) ++rx->clean_run_frames;
  rx->recoverable_losses = 0;
  memcpy(rx->previous, rx->frame, UV3_PAYLOAD);
}'''

def replace_function(text, name, code):
    match = re.search(r'(?m)^static inline [^\n]+?\b' + re.escape(name) + r'\(', text)
    assert match, name
    a = match.start()
    opening = text.index('{', match.end())
    depth = 1
    b = opening + 1
    while depth:
        depth += (text[b] == '{') - (text[b] == '}')
        b += 1
    return text[:a] + code + text[b:]

def transport(text):
    text = text.replace('/* Offline candidate. Not included by the installed firmware. */',
                        '/* Working UART v3: bounded recovery, CRC32C and fail-stop watchdog. */')
    text = text.replace('  UV3_BAD_SEQUENCE\n', '  UV3_BAD_SEQUENCE,\n  UV3_DROPPED\n')
    text = text.replace('  uint32_t accepted_noise_frames;',
                        '  uint32_t dropped_frames;\n  bool seeking_sync;\n  uint8_t recoverable_losses;\n  uv3_result last_drop_reason;\n  uint32_t accepted_noise_frames;')
    text = text.replace('  reply[35] = rx->clean_run_frames;\n  reply[36] = rx->noise_used;',
                        '  uint16_t dropped = uv3_sat16(rx->dropped_frames);\n  reply[35] = (uint8_t)dropped;\n  reply[36] = (uint8_t)(dropped >> 8);')
    text = text.replace('  rx->clean_run_frames = 0;\n  rx->index = 0;',
                        '  rx->clean_run_frames = 0;\n  rx->recoverable_losses = 0;\n  rx->index = 0;')
    text = replace_function(text, 'uv3_tick', RECOVERY + '\n' + TICK)
    text = replace_function(text, 'uv3_noise_allowed', NOISE)
    text = replace_function(text, 'uv3_byte', BYTE)
    text = replace_function(text, 'uv3_commit', COMMIT)
    return text

def prepare(out):
    original = json.loads((BASE / 'manifest.json').read_text())
    for tree, key in (('nucleo', 'nucleo_source_sha256'), ('UNOQ_MOTOR', 'uno_source_sha256')):
        assert source_hashes(BASE / tree) == original[key]
    assert sha(HMI) == '8de308a5a818f6c490e7ccf34cfecdeeac4a04175e1413ca39e8a5a842a253f6'
    out.mkdir(parents=True, exist_ok=False)
    for tree in ('nucleo', 'UNOQ_MOTOR'):
        shutil.copytree(BASE / tree, out / tree,
            ignore=shutil.ignore_patterns('Debug', 'Release', '.metadata', '__pycache__'))
    (out / 'web_hmi').mkdir()
    shutil.copy2(HMI, out / 'web_hmi/server.py')
    for tree in ('nucleo/Inc', 'UNOQ_MOTOR'):
        p = out / tree / 'uart_v3_transport.h'
        write(p, transport(p.read_text()))
        change(out / tree / 'break_wire.h', 'BW_NUCLEO_BUILD 2026101410UL', 'BW_NUCLEO_BUILD 2026101412UL')
    main = out / 'nucleo/Src/main.c'
    change(main, 'MIC_NUCLEO_FW_BUILD_ID 2026101410UL', 'MIC_NUCLEO_FW_BUILD_ID 2026101412UL')
    change(main, '  if (result == UV3_WAIT) return;',
                 '  if (result == UV3_WAIT || result == UV3_DROPPED) return;')
    uno = out / 'UNOQ_MOTOR/UNOQ_MOTOR.ino'
    change(uno, 'FW_BUILD_ID = 2026101411U', 'FW_BUILD_ID = 2026101413U')
    change(uno, 'static uint16_t g_bp_ne_observed = 0;',
                'static uint16_t g_bp_ne_observed = 0;\nstatic uint16_t g_bp_recovered_drops = 0;')
    change(uno, '  g_bp_ne_flags = rx[37];',
                '  g_bp_recovered_drops = (uint16_t)rx[35] | ((uint16_t)rx[36] << 8);\n  g_bp_ne_flags = rx[37];')
    change(uno, '  s += " bp_ne_flags=";',
                '  s += " bp_recovered_drops="; s += String((int)g_bp_recovered_drops);\n  s += " bp_ne_flags=";')
    change(out / 'UNOQ_MOTOR/nucleo_fault_diagnostics.h', 'build == 2026101410U;',
                'build == 2026101410U || build == 2026101412U;')
    web = out / 'web_hmi/server.py'
    change(web, '(2026101411, 2026101410),', '(2026101411, 2026101410),\n        (2026101413, 2026101412),')
    change(web, '    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101410',
               '    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101412 and _as_int(data or {}, "fw_build", -1) != 2026101413:\n        return False, "working motor-controller image requires its matching supervisory firmware"\n    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101410')
    change(web, 'peer not in (2026101102, 2026101204, 2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495, 2026101410, 2026101493)',
               'peer not in (2026101102, 2026101204, 2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495, 2026101410, 2026101493, 2026101412)')
    change(web, '"bp_ne_accepted", "bp_ne_observed", "bp_ne_flags", "bp_transport_fault")},',
               '"bp_ne_accepted", "bp_ne_observed", "bp_ne_flags", "bp_transport_fault", "bp_recovered_drops")},')
    compile(web.read_text(), str(web), 'exec')
    assert (out / 'nucleo/Inc/uart_v3_transport.h').read_bytes() == (out / 'UNOQ_MOTOR/uart_v3_transport.h').read_bytes()
    hashes = source_hashes(out / 'nucleo')
    changes = [p for p, h in hashes.items() if h != original['nucleo_source_sha256'].get(p)]
    assert sorted(changes) == ['Inc/break_wire.h', 'Inc/uart_v3_transport.h', 'Src/main.c']
    # ADC, PWM, MCSDK protection, motor model and measurement scale are exact copies.
    manifest = dict(schema='mic_ai.uart_recovery_working_pair.v1', pair=list(PAIR),
        predecessor_pair=[2026101411, 2026101410], nucleo_source_sha256=hashes,
        uno_source_sha256=source_hashes(out / 'UNOQ_MOTOR'), hmi_sha256=sha(web),
        nucleo_changed_files=changes, source_only=True, installed=False, hardware_commands=0,
        watchdog_ms=300, recovered_event_budget=2, recovered_event_window_ms=1000,
        calibration_points_preserved=True, measurement_and_pwm_sources_unchanged=True,
        no_fixture_firmware=True, qualification_pending=True)
    write(out / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ('pair', 'installed', 'hardware_commands', 'nucleo_changed_files')}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    prepare(parser.parse_args().outdir.resolve())

"""Prepare a matched passive snapshot pair and HMI; no live deployment or actuation."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil

from prepare_ipm_break_snapshot import ROOT, HEADER, REFERENCE, patched_main, patched_irq, source_hashes
from prepare_mcsdk_logic_bench import replace_once

ASSETS = ROOT / "research/ipm_break"
UNO = ROOT / "artifacts/live_bench_20261010/uart_v3_candidate/sender_invariant_fix_r1/UNOQ_MOTOR"
NUCLEO_ID = 2026101102
UNO_ID = 2026101103


def patch_function(text, name, transform):
    match = re.search(r"static (?:void|bool|String) " + re.escape(name) + r"\([^;]*?\)\s*\{", text)
    if not match:
        raise RuntimeError("Missing function " + name)
    a, b, depth = match.start(), match.end(), 1
    while depth:
        depth += (text[b] == "{") - (text[b] == "}")
        b += 1
    return text[:a] + transform(text[a:b]) + text[b:]


def nucleo_main(text):
    text = patched_main(text)
    text = replace_once(text, "2026101101UL", f"{NUCLEO_ID}UL")
    text = replace_once(text, '#include "first_break_snapshot.h"',
        '#include "first_break_snapshot.h"\n#include "break_wire.h"\nstatic uint32_t mic_break_diag_tx_errors;')
    text = replace_once(text, "static void uno_send_reply(void) {",
        (ASSETS / "nucleo_emitter.inc").read_text() + "\nstatic void uno_send_reply(void) {")
    return replace_once(text,
        '  const int tx_status = HAL_UART_Transmit(&huart1, reply, UNO_FRAME_LEN, UNO_REPLY_TIMEOUT_MS);',
        '  const int tx_status = HAL_UART_Transmit(&huart1, reply, UNO_FRAME_LEN, UNO_REPLY_TIMEOUT_MS);\n'
        '  if (tx_status == HAL_OK) mic_send_break_page(now_ms);')


def uno_sketch(text):
    text = replace_once(text, "FW_BUILD_ID = 2026101008U", f"FW_BUILD_ID = {UNO_ID}U")
    text = replace_once(text, '#include "uart_v3_transport.h"',
        '#include "uart_v3_transport.h"\n#include "break_wire.h"\nstatic bw_receiver g_break_wire;')
    def reply(code):
        code = replace_once(code, '  uint32_t now_ms = millis();',
            '  uint32_t now_ms = millis();\n'
            '  const uint32_t previous_build = g_bp_fw_build;\n'
            '  const uint16_t previous_good = g_bp_good_cnt;\n'
            '  const uint32_t previous_age = now_ms - g_bp_last_rsp_ms;')
        return replace_once(code, '  g_mc_diagnostics = decode_nucleo_fault_diagnostics',
            '  if (bw_peer_reset_required(previous_build,g_bp_fw_build,previous_good,g_bp_good_cnt,previous_age))\n'
            '    bw_reset(&g_break_wire);\n'
            '  g_mc_diagnostics = decode_nucleo_fault_diagnostics')
    text = patch_function(text, "nucleo_check_reply", reply)
    def poll(code):
        return replace_once(code, '      const bool integrity_ok = buf[0] == 0x55 && buf[1] == 0xAA &&',
            '      if (buf[2] == BW_VERSION) {\n'
            '        if (!uv3_crc_ok(buf)) {\n'
            '          bw_increment(&g_break_wire.bad_pages);\n'
            '          if (g_nucleo_rx_bad < 0xFFFFU) ++g_nucleo_rx_bad;\n'
            '          if (g_nucleo_rx_bad_integrity < 0xFFFFU) ++g_nucleo_rx_bad_integrity;\n'
            '        } else {\n'
            '          const bool fresh_off = g_bp_mcsdk_telemetry && !g_pwm_enabled &&\n'
            '              (g_bp_status & 0x22U) == 0U && (uint32_t)(millis()-g_bp_last_rsp_ms) < 300U;\n'
            '          (void)bw_receive(&g_break_wire,buf,g_bp_fw_build,fresh_off,millis());\n'
            '        }\n'
            '        continue;\n'
            '      }\n'
            '      const bool integrity_ok = buf[0] == 0x55 && buf[1] == 0xAA &&')
    text = patch_function(text, "nucleo_uart_poll", poll)
    return replace_once(text, '  g_link_timing.rpc(micros() - timing_started);',
        (ASSETS / "uno_rpc_append.inc").read_text() + '\n  g_link_timing.rpc(micros() - timing_started);')


def hmi_server(text):
    text = replace_once(text, "STATE_NAMES = {", (ASSETS / "hmi_snapshot.py").read_text() + "\n\nSTATE_NAMES = {")
    text = replace_once(text, '    def _require_control_access(self) -> bool:',
                        '    def _require_control_access(self, mark_heartbeat: bool = True) -> bool:')
    text = replace_once(text, '            self.server.app.mark_operator_heartbeat()  # type: ignore[attr-defined]',
        '            if mark_heartbeat:\n'
        '                self.server.app.mark_operator_heartbeat()  # type: ignore[attr-defined]')
    text = replace_once(text, '                "mc_diag_valid": int(float(kv.get("mc_diag_valid", "0"))),',
        '                **break_wire_status(kv),\n'
        '                "mc_break_rx_good": int(kv.get("mc_break_rx_good", "0")),\n'
        '                "mc_break_rx_bad": int(kv.get("mc_break_rx_bad", "0")),\n'
        '                "mc_diag_valid": int(float(kv.get("mc_diag_valid", "0"))),')
    text = replace_once(text, '        if parsed.path == "/api/status":',
        '        if parsed.path == "/api/break-snapshot":\n'
        '            if not self._require_control_access(mark_heartbeat=False):\n'
        '                return\n'
        '            ok, data, err = self.server.app.rpc.get()\n'
        '            if not ok or data is None:\n'
        '                self._send_json({"ok": False, "error": err or "no response"}, 503)\n'
        '                return\n'
        '            self.server.app.maybe_log_status(data)\n'
        '            fields = {k: v for k, v in data.items() if k.startswith("mc_break_")}\n'
        '            self._send_json({"ok": True, "data": fields})\n'
        '            return\n'
        '        if parsed.path == "/api/status":')
    text = replace_once(text, '        self.maybe_log_fault_diagnostics(data)\n        now = _now_ts()',
        '        self.maybe_log_fault_diagnostics(data)\n'
        '        for index, record in enumerate(data.get("mc_break_snapshots", [])):\n'
        '            if not record.get("available") or not record.get("captured"):\n'
        '                continue\n'
        '            key = json.dumps(record["raw"], sort_keys=True)\n'
        '            with self._lock:\n'
        '                if not hasattr(self, "_last_break_snapshot_keys"):\n'
        '                    self._last_break_snapshot_keys = {}\n'
        '                changed = self._last_break_snapshot_keys.get(index) != key\n'
        '                self._last_break_snapshot_keys[index] = key\n'
        '            if changed:\n'
        '                self.logs.add("IPM_BREAK_SNAPSHOT " + json.dumps(record, sort_keys=True))\n'
        '        now = _now_ts()')
    return text


def prepare(out):
    before_nucleo, before_uno = source_hashes(REFERENCE), source_hashes(UNO)
    hmi_hash = hashlib.sha256((ROOT / "web_hmi/server.py").read_bytes()).hexdigest()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(REFERENCE, out / "nucleo", ignore=shutil.ignore_patterns("Debug", "Release"))
    shutil.copytree(UNO, out / "UNOQ_MOTOR")
    shutil.copytree(ROOT / "web_hmi", out / "web_hmi", ignore=shutil.ignore_patterns("__pycache__", ".venv"))
    for relative, transform in (("nucleo/Src/main.c", nucleo_main),
        ("nucleo/Src/stm32g4xx_mc_it.c", patched_irq), ("UNOQ_MOTOR/UNOQ_MOTOR.ino", uno_sketch),
        ("web_hmi/server.py", hmi_server)):
        path = out / relative
        path.write_text(transform(path.read_text(encoding="utf-8-sig")), encoding="utf-8")
    shutil.copy2(HEADER, out / "nucleo/Inc/first_break_snapshot.h")
    for destination in (out / "nucleo/Inc", out / "UNOQ_MOTOR"):
        shutil.copy2(ASSETS / "break_wire.h", destination / "break_wire.h")
    decoder = out / "UNOQ_MOTOR/nucleo_fault_diagnostics.h"
    decoder.write_text(replace_once(decoder.read_text(encoding="utf-8-sig"),
        "build == 2026101006U;", f"build == 2026101006U || build == {NUCLEO_ID}U;"), encoding="utf-8")
    if before_nucleo != source_hashes(REFERENCE) or before_uno != source_hashes(UNO) or hmi_hash != hashlib.sha256((ROOT / "web_hmi/server.py").read_bytes()).hexdigest():
        raise RuntimeError("Baseline changed")
    result = dict(schema="mic_ai.ipm_break_wifi_pair.v1", uno_build=UNO_ID, nucleo_build=NUCLEO_ID,
        installed=False, hv_release_approved=False, hardware_commands=0,
        control_frame_abi_changed=False, diagnostic_packet_tag=0xD1,
        diagnostic_period_ms=200, records=2, pages_per_record=4,
        note="Passive output-off snapshots; the existing powered gate still rejects the new pair",
        baseline_nucleo=before_nucleo, baseline_uno=before_uno, baseline_hmi_sha256=hmi_hash,
        candidate_nucleo=source_hashes(out / "nucleo"), candidate_uno=source_hashes(out / "UNOQ_MOTOR"),
        candidate_hmi_sha256=hashlib.sha256((out / "web_hmi/server.py").read_bytes()).hexdigest())
    (out / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir", required=True, type=Path)
    args = p.parse_args()
    manifest = prepare(args.outdir.resolve())
    print(json.dumps({k: manifest[k] for k in ("uno_build", "nucleo_build", "installed")}))


if __name__ == "__main__":
    main()

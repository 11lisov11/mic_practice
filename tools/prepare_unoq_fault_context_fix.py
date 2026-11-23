"""Extend Linux fault history with existing UART evidence; no control changes."""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_unoq_rx_fix import ROOT
from prepare_mcsdk_logic_bench import replace_once

BASE = ROOT / 'artifacts/live_bench_20261012/llext_fix/candidate_r1/web_hmi/server.py'
FIELDS = (
    'uno_tx_all_max_gap_us', 'uno_tx_last_gap_us', 'uno_tx_gaps_over_watchdog',
    'uno_rx_poll_gap_max_ms', 'uno_tx_call_max_us', 'uno_rpc_max_us',
    'uno_rx_dropped', 'uno_rx_hw_errors', 'uno_rx_hw_flags', 'uno_rx_high_water',
    'uno_rx_pending', 'uno_rx_rejected_ms', 'uno_rx_rejected_hex',
    'uno_tx_short_writes', 'uno_tx_count', 'uno_rx_count',
    'mc_transport_fault', 'mc_break_rx_good', 'mc_break_rx_bad',
)


def patched(text):
    anchor = '        "enc_status", "hmi_hv_armed", "hmi_operator_heartbeat_age_s",\n'
    lines = ''.join(f'        "{field}",\n' for field in FIELDS)
    text = replace_once(text, anchor, anchor + lines)
    return replace_once(text,
        'for field in ("state", "pwm", "mc_fault", "enc_bus_ok", "enc_errors")',
        'for field in ("state", "pwm", "mc_fault", "enc_bus_ok", "enc_errors",\n'
        '                              "uno_rx_dropped", "uno_rx_hw_errors", "uno_rx_hw_flags",\n'
        '                              "uno_tx_gaps_over_watchdog", "mc_transport_fault")')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    target = out / 'web_hmi/server.py'
    target.parent.mkdir()
    target.write_text(patched(BASE.read_text()), encoding='utf-8')
    result = dict(schema='mic_ai.linux_fault_history.v1', pair=[2026101108, 2026101102],
                  source=str(BASE), previous_hmi_sha256=sha(BASE), hmi_sha256=sha(target),
                  added_fields=list(FIELDS), mcu_firmware_changed=False,
                  control_guards_changed=False, calibration_file_modified=False,
                  hardware_commands=0, installed=False)
    (out / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(prepare(a.outdir.resolve())))

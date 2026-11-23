"""Prepare Uno2603, leaving installed Uno2601/Nucleo2602 immutable."""
import ast
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/live_bench_20261026/nucleo_as5600_r1'
OUT = ROOT / 'artifacts/live_bench_20261026/uart_rx_handoff_r1'
OLD, NEW = (2026102601, 2026102602), (2026102603, 2026102602)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (OUT / 'manifest.json').exists(), 'Preserve existing candidate'
    m = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    assert m['installed'] and m['installation_readback_verified']
    for rel, digest in m['source_sha256'].items():
        assert sha(BASE / rel) == digest, rel
    race = json.loads((BASE / 'rx_handoff_audit_r1/report.json').read_text(encoding='utf-8'))
    assert race['passed'] and race['results']['candidate']['exact_crc_valid'] == 43
    for name in ('UNOQ_MOTOR', 'web_hmi'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
    sk = OUT / 'UNOQ_MOTOR'
    header = (BASE / 'rx_handoff_audit_r1/nucleo_buffered_serial_candidate.h').read_text(encoding='utf-8')
    header = header.replace('high_water, pending;','high_water, pending, rescued;')
    header = header.replace('queue.high_water, queue.count};','queue.high_water, queue.count, rescued};')
    header = header.replace('uint32_t errors = 0, error_flags = 0;','uint32_t errors = 0, error_flags = 0, rescued = 0;')
    header = header.replace('if (value >= 0) queue.put(static_cast<uint8_t>(value));',
        'if (value >= 0) {\n        if (rescued != UINT32_MAX) ++rescued;\n        queue.put(static_cast<uint8_t>(value));\n      }')
    (sk / 'nucleo_buffered_serial.h').write_text(header, encoding='utf-8')
    ino = sk / 'UNOQ_MOTOR.ino'
    old = ino.read_text(encoding='utf-8')
    new = old.replace('FW_BUILD_ID = 2026102601U;', 'FW_BUILD_ID = 2026102603U;')
    anchor = '  s += " uno_rx_dropped="; s += String((unsigned long)rx_stats.dropped);'
    assert new.count(anchor) == 1
    new = new.replace(anchor, anchor + '\n  s += " uno_rx_rescued="; s += String((unsigned long)rx_stats.rescued);')
    assert old != new
    ino.write_text(new, encoding='utf-8')
    f = OUT / 'web_hmi/server.py'
    text = f.read_text(encoding='utf-8')
    for old_pair, new_pair in [('(2026102601, 2026102602)', '(2026102603, 2026102602)'),
                               ('(2026102601,2026102602)', '(2026102603,2026102602)')]:
        text = text.replace(old_pair, old_pair + ',' + new_pair)
    anchor = '                **{k: int(kv[k]) for k in ("uno_rx_dropped", "uno_rx_hw_errors",'
    assert text.count(anchor) == 1
    text = text.replace(anchor, '                "uno_rx_rescued": int(kv.get("uno_rx_rescued", "0")),\n' + anchor)
    ast.parse(text)
    f.write_text(text, encoding='utf-8')
    (OUT / 'build/uno').mkdir(parents=True, exist_ok=True)
    (OUT / 'verification').mkdir(exist_ok=True)
    metadata = dict(schema='mic_ai.uart_rx_handoff.v1', pair_compatibility_ids=list(NEW),
        predecessor=str(BASE), built=False, selftest_pass=False, installed=False,
        uno_only=True, nucleo_firmware_unchanged=True, sensor_feedback_control=False,
        motor_control_changed=False, calibration_changed=False, thresholds_changed=False,
        sd_capture_changed=False, uart_protocol_changed=False, watchdogs_changed=False,
        changes='Preserve late vendor RX bytes in bounded primary RX queue; expose rescued count',
        source_sha256={str(f.relative_to(OUT)).replace('\\','/'):sha(f)
                       for name in ('UNOQ_MOTOR','web_hmi') for f in (OUT/name).rglob('*') if f.is_file()})
    (OUT / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(dict(prepared=True, pair=NEW, nucleo_changed=False)))


if __name__ == '__main__':
    main()

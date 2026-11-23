"""Read and export a frozen ADC trace over Wi-Fi. GET only; no motor commands."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys
import time
from urllib.request import build_opener, ProxyHandler

from collect_wifi_telemetry import get_status, validate_url
import prepare_current_peak_capture as package


def decoder(candidate=None):
    path = (candidate or package.OUT)/'web_hmi/server.py'
    spec = importlib.util.spec_from_file_location('peak_capture_hmi', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fresh_off(s, pair=None):
    return ((s.get('fw_build'), s.get('mc_fw_build')) == (pair or package.NEW)
            and s.get('state') == 'SAFE' and s.get('pwm') == 0
            and type(s.get('bp_status')) is int and not (s['bp_status'] & 0x22)
            and type(s.get('mc_age_ms')) in (int, float)
            and 0 <= s['mc_age_ms'] < 300)


def export(raw, out, module):
    trace = module.decode_adc_peak_hex(raw.hex())
    (out/'trace.bin').write_bytes(raw)
    (out/'decoded.json').write_text(json.dumps(trace, indent=2)+'\n', encoding='utf-8')
    with (out/'samples.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(trace['samples'][0]))
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, list) else v for k,v in row.items()}
                         for row in trace['samples'])
    return trace


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hmi', default='http://192.168.1.138:8080')
    p.add_argument('--outdir', type=Path, required=True)
    p.add_argument('--wait-seconds', type=float, default=30)
    p.add_argument('--offline-trace', type=Path)
    p.add_argument('--candidate', type=Path, default=package.OUT)
    a = p.parse_args()
    if not 0 < a.wait_seconds <= 60:
        p.error('--wait-seconds must be in (0,60]')
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, motor_commands=0, clear_commands=0, flash_commands=0,
                  offline=a.offline_trace is not None, physical_current_qualified=False)
    try:
        pair=tuple(json.loads((a.candidate/'manifest.json').read_text(encoding='utf-8'))['pair_compatibility_ids'])
        module = decoder(a.candidate)
        if a.offline_trace:
            raw = a.offline_trace.read_bytes()
        else:
            base = validate_url(a.hmi)
            opener = build_opener(ProxyHandler({}))
            deadline = time.monotonic()+a.wait_seconds
            with (out/'status.jsonl').open('w', encoding='utf-8') as stream:
                while True:
                    status = get_status(opener, base)
                    stream.write(json.dumps(dict(at=time.time(), status=status), ensure_ascii=False)+'\n')
                    stream.flush()
                    if not fresh_off(status,pair):
                        raise RuntimeError('Expected fresh OFF telemetry from the capture firmware pair')
                    value = status.get('mc_adc_peak_hex', '-')
                    if value != '-':
                        raw = bytes.fromhex(value)
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('No completed trace received; no RESET or retry was sent')
                    time.sleep(.25)
        trace = export(raw, out, module)
        report.update(passed=True, peak_seen=trace['peak_seen'], sample_count=trace['sample_count'],
                      post_short=trace['post_short'], trigger_reference_hz=trace['trigger_reference_hz'])
    except Exception as exc:
        report['error'] = str(exc)
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

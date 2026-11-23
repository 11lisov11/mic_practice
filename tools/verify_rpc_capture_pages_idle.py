"""Verify release 2013 and read-only page handling over the existing USB tunnel."""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from prepare_rpc_capture_pages import OUT, ROOT

BASE_URL = 'http://127.0.0.1:18080'
COUNTERS = ('rpc_response_timeouts', 'rpc_send_timeouts', 'rpc_route_failures',
            'uno_rx_hw_errors', 'uno_rx_dropped', 'mc_uart_error_flags', 'mc_bad_sequence')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=45)
    args = parser.parse_args()
    if not 1 <= args.samples <= 120:
        parser.error('Samples must be between 1 and 120')
    output = OUT / 'idle_qualification_r1'
    output.mkdir()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = (ROOT / '.unoq_ssh/control_token').read_text(encoding='utf-8').strip()
    assert token

    def get(path, authorized=False):
        headers = {'X-UNOQ-Control-Token': token} if authorized else {}
        request = urllib.request.Request(BASE_URL + path, headers=headers)
        try:
            with opener.open(request, timeout=8) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    started = time.monotonic()
    rows = []
    report = {'passed': False, 'START': 0, 'CLEAR': 0, 'ARM': 0}
    try:
        with (output / 'status.jsonl').open('w', encoding='utf-8') as stream:
            for _ in range(args.samples):
                before = time.monotonic()
                code, payload = get('/api/status')
                assert code == 200 and payload['ok']
                data = payload['data']
                row = {'latency_ms': round((time.monotonic() - before) * 1000), 'data': data}
                rows.append(row)
                stream.write(json.dumps(row) + '\n')
                stream.flush()
                assert (data['fw_build'], data['mc_fw_build']) == (2026112013, 2026111810)
                assert data['state'] == 'SAFE' and data['pwm'] == 0 and data['hmi_hv_armed'] == 0
                assert data['bp_vbus_valid'] == 1 and 0 <= data['bp_vdc'] < 20 and data['mc_age_ms'] < 300
                assert all(data[key] == rows[0]['data'][key] for key in COUNTERS)
                assert data['mc_adc_peak_hex'] == data['mc_observer_trace_hex'] == '-'
                time.sleep(0.6)
        page = '/api/capture-page?kind=adc&page=0'
        anonymous, _ = get(page)
        invalid, _ = get('/api/capture-page?kind=adc&page=6', authorized=True)
        accepted = {}
        for kind, flag in [('adc', 'mc_adc_peak_complete'), ('observer', 'mc_observer_trace_complete')]:
            code, payload = get(f'/api/capture-page?kind={kind}&page=0', authorized=True)
            accepted[kind] = {'code': code, 'payload': payload}
            if rows[-1]['data'][flag] == 0:
                assert (code, payload) == (409, {'ok': False, 'error': 'ERR NOT_COMPLETE'})
            else:
                assert code == 200 and payload['ok'] and payload['data']['page'] == 0
        report.update(page_without_auth=anonymous, invalid_page=invalid, page_from_Uno=accepted)
        assert anonymous == 401 and invalid == 400
        report['passed'] = True
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report.update(samples=len(rows), elapsed_s=round(time.monotonic()-started, 2),
                      max_latency_ms=max((r['latency_ms'] for r in rows), default=0),
                      rpc_uart_counters={key: rows[-1]['data'].get(key) for key in COUNTERS} if rows else {})
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""One expressly authorized CLEAR with J1 off; never ARM or START."""
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIR = (2026103009, 2026103010)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--confirm-one-clear-no-start', action='store_true')
    ap.add_argument('--outdir', required=True, type=Path)
    args = ap.parse_args()
    if not args.confirm_one_clear_no_start:
        ap.error('Explicit authorization for one CLEAR without a start is required')
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    token = (ROOT / '.unoq_ssh/control_token').read_text().strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    report = dict(passed=False, clear_requests_attempted=0, START=0, ARM=0,
                  RESET=0, flash=0, pair=list(PAIR), thresholds_changed=False)

    def write(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def request(path, body=None):
        req = urllib.request.Request('http://192.168.1.138:8080' + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'X-UNOQ-Control-Token': token},
            method='GET' if body is None else 'POST')
        with opener.open(req, timeout=8) as response:
            result = json.load(response)
        if result.get('ok') is not True:
            raise RuntimeError(str(result.get('error', 'request rejected')))
        return result['data'] if 'data' in result else result

    def off(s):
        assert (s['fw_build'], s['mc_fw_build']) == PAIR
        assert s['state'] == 'SAFE' and s['pwm'] == 0
        assert not (s['bp_status'] & 0x22) and s['hmi_hv_armed'] == 0
        assert s['run_id'] == s['run_start_ms'] == 0
        assert 0 <= s['mc_age_ms'] < 300 and 0 <= s['vdc'] <= 20

    rows = []
    wave = None
    try:
        before = request('/api/status')
        write('before.json', before)
        off(before)
        sd = before['mc_sd_live']
        assert sd['level'] == 'HIGH' and sd['config_ok']
        assert before['mc_fault_current_mask'] in (0, 4)
        assert before['mc_fault_occurred_mask'] in (0, 4, 1024, 1028)
        for k in ('mc_uart_error_flags', 'mc_transport_fault', 'mc_bad_integrity',
                  'mc_bad_sequence', 'rpc_response_timeouts', 'rpc_send_timeouts', 'algorithm_fault'):
            assert before[k] == 0, (k, before[k])
        wave = bytes.fromhex(before['mc_break_wave_hex'])
        assert len(wave) == 320 and sd['first_record_ready']
        (out / 'SD_before.bin').write_bytes(wave)
        write('SD_before_decoded.json', request('/api/bkin-trace'))
        write('SD_before_snapshots.json', request('/api/break-snapshot'))
        report['SD_before_sha256'] = hashlib.sha256(wave).hexdigest()
        report['clear_requests_attempted'] = 1
        write('report.json', report)  # Durable intent; a failed POST is never retried.
        write('CLEAR_response.json', request('/api/cmd', {'cmd': 'CLEAR'}))
        report['CLEAR_HTTP_acknowledged'] = True
        for i in range(12):
            s = request('/api/status')
            rows.append(dict(monotonic=time.monotonic(), status=s))
            write('after_samples.json', rows)
            off(s)
            assert bytes.fromhex(s['mc_break_wave_hex']) == wave, 'Frozen SD record changed'
            for k in ('mc_uart_error_flags', 'mc_transport_fault', 'mc_bad_integrity',
                      'mc_bad_sequence', 'rpc_response_timeouts', 'rpc_send_timeouts', 'algorithm_fault'):
                assert s[k] == 0, (k, s[k])
            assert s['mc_sd_live']['level'] == 'HIGH' and s['mc_sd_live']['config_ok']
            assert s['mc_fault_current_mask'] in (0, 4)
            assert s['mc_fault_occurred_mask'] in (0, 4)
            time.sleep(1)
        assert all(x['status']['mc_sd_live']['break_irq_enabled'] for x in rows[-5:]), 'BIE did not remain enabled'
        report.update(passed=True, Break_IRQ_rearmed=True, UART_RPC_errors_zero=True,
            SD_record_unchanged=True, SD_HIGH_all_samples=True,
            observation_seconds=rows[-1]['monotonic'] - rows[0]['monotonic'],
            after=rows[-1]['status'],
            UNDER_VOLT_expected_with_J1_off=True, motor_start_clearance=False,
            limitation='Frozen first-event capture cannot record a second pulse; live status is sampled, not continuous.')
    except Exception as e:
        report['error'] = repr(e)
    finally:
        for name, path in (('final_status.json', '/api/status'), ('SD_after_decoded.json', '/api/bkin-trace')):
            try:
                obj = request(path)
                write(name, obj)
                if name == 'final_status.json':
                    off(obj)
                    if wave is not None:
                        report['SD_record_unchanged_at_final'] = bytes.fromhex(obj['mc_break_wave_hex']) == wave
                        assert report['SD_record_unchanged_at_final']
                    report['final_SD'] = obj['mc_sd_live']
                    report['final_masks'] = [obj['mc_fault_current_mask'], obj['mc_fault_occurred_mask']]
            except Exception as e:
                report['passed'] = False
                report[name + '_error'] = repr(e)
        write('report.json', report)
        write('saved_files_sha256.json', {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in out.iterdir() if f.is_file() and f.name != 'saved_files_sha256.json'})
    print(json.dumps({k: report.get(k) for k in ('passed', 'clear_requests_attempted',
        'Break_IRQ_rearmed', 'SD_record_unchanged_at_final', 'final_SD', 'final_masks', 'error')}, ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

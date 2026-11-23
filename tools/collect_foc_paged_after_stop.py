"""Collect 2013/1810 ADC and NIS pages after an already confirmed five-second run."""
import argparse
import hashlib
import json
import runpy
import time
import urllib.parse
import urllib.request
from pathlib import Path

from prepare_rpc_capture_pages import OUT, ROOT
from rpc_counter_guard import RpcCounterGuard
from run_foc_boot_capture_trial import decode_boot

PAIR = (2026112013, 2026111810)


def require_stopped(status, stop_status, *, pair=PAIR, allow_short_stop=False):
    if (status.get('fw_build'), status.get('mc_fw_build')) != pair:
        raise RuntimeError('Unexpected firmware pair')
    if (status.get('state') != 'SAFE' or status.get('pwm') != 0
            or status.get('hmi_hv_armed') != 0 or status.get('bp_status', 0x22) & 0x22):
        raise RuntimeError('Outputs OFF not confirmed')
    reason, elapsed = status.get('run_reason'), status.get('run_elapsed_ms', 0)
    timed_stop = reason == 1 and 5000 <= elapsed <= 5100
    short_stop = (allow_short_stop and reason == 2 and 0 < elapsed < 5000
                  and status.get('run_limit_ms') == 5000 and status.get('run_stop_ms', 0) > 0
                  and all(status.get(k) == stop_status.get(k) for k in
                          ('run_reason', 'run_elapsed_ms', 'run_start_ms', 'run_stop_ms', 'run_limit_ms')))
    if (not 0 <= status.get('mc_age_ms', 9999) < 300
            or status.get('run_id') != stop_status['run_id']
            or not (timed_stop or short_stop)
            or status.get('linux_boot_id') != stop_status['linux_boot_id']):
        raise RuntimeError('Stopped run identity changed or status stale')
    if type(status.get('run_id')) is not int or status['run_id'] < 1:
        raise RuntimeError('A completed run is required')


def collect(get, read_record, stop_status, output, *, monitor_samples=30,
            clock=time.monotonic, sleep=time.sleep, pair=PAIR, allow_short_stop=False):
    require_stopped(stop_status, stop_status, pair=pair, allow_short_stop=allow_short_stop)
    output.mkdir()
    report = {'passed': False, 'run_id': stop_status['run_id'],
              'run_reason': stop_status['run_reason'], 'run_elapsed_ms': stop_status['run_elapsed_ms'],
              'records': {}, 'RPC_samples_after_download': 0, 'GET_only': True}
    guard = RpcCounterGuard(lambda status, **kw: decode_boot(status, pair, **kw), clock=clock)
    reference = {
        name: stop_status[name] for name in (*guard.KEYS, 'rpc_route_failures')
    }
    last_status = {}
    started = clock()

    def sample():
        payload = get('/api/status')
        status = payload['data']
        require_stopped(status, stop_status, pair=pair, allow_short_stop=allow_short_stop)
        if any(status[key] != value for key, value in reference.items()):
            raise RuntimeError('RPC counter changed after auto-stop')
        if not guard.observe(status):
            raise RuntimeError(guard.failure)
        last_status.clear()
        last_status.update(status)
        with (output / 'status.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(status) + '\n')

    def page(kind, number):
        sample()
        query = urllib.parse.urlencode({'kind': kind, 'page': number})
        return get('/api/capture-page?' + query)['data']

    try:
        deadline = started + 20
        pending = {'adc': ('mc_adc_peak_complete', 'ADC_peak.bin'),
                   'observer': ('mc_observer_trace_complete', 'observer_trace.bin')}
        while pending:
            sample()
            for kind, (flag, filename) in list(pending.items()):
                if last_status.get(flag) != 1:
                    continue
                raw = read_record(page, kind)
                if raw[:4] != {'adc': b'APC1', 'observer': b'OSD1'}[kind]:
                    raise RuntimeError('Unexpected capture header')
                (output / filename).write_bytes(raw)
                report['records'][filename] = hashlib.sha256(raw).hexdigest()
                del pending[kind]
            if pending:
                if clock() >= deadline:
                    raise TimeoutError('Capture not received: ' + ', '.join(pending))
                sleep(.25)
        for _ in range(monitor_samples):
            sample()
            report['RPC_samples_after_download'] += 1
            sleep(.6)
        report['passed'] = guard.ready
    except Exception as error:
        report['error'] = str(error)
    finally:
        report['rpc_guard'] = guard.snapshot()
        report['elapsed_s'] = round(clock() - started, 3)
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trial', type=Path, help='New run directory containing autostop.json')
    args = parser.parse_args()
    trial = args.trial.resolve()
    stop_status = json.loads((trial / 'autostop.json').read_text(encoding='utf-8'))
    before = json.loads((trial / 'before_START.json').read_text(encoding='utf-8'))
    if (before.get('run_id') != stop_status.get('run_id', 0) - 1
            or any(before.get(key) != 0 for key in ('mc_adc_peak_complete', 'mc_observer_trace_complete'))):
        parser.error('Previous capture or unproven run identity')
    token = (ROOT / '.unoq_ssh/control_token').read_text(encoding='utf-8').strip()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(path):
        request = urllib.request.Request('http://192.168.1.138:8080' + path,
                                         headers={'X-UNOQ-Control-Token': token})
        with client.open(request, timeout=4) as response:
            payload = json.load(response)
        if payload.get('ok') is not True:
            raise RuntimeError(str(payload.get('error', 'GET rejected')))
        return payload

    read_record = runpy.run_path(str(OUT / 'web_hmi/server.py'))['receive_capture_pages']
    result = collect(get, read_record, stop_status, trial / 'paged_capture')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

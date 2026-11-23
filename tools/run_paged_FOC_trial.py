"""One explicitly authorized 2013/1810 FOC 5 Hz trial with paged capture."""
import argparse
import hashlib
import json
import runpy
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import run_telemetry_deadline_trial as supervised
from collect_foc_paged_after_stop import PAIR, collect
from prepare_rpc_capture_pages import OUT, ROOT
from run_foc_boot_capture_trial import decode_boot


def read(path):
    return path.read_text(encoding='utf-8')


def write(path, content):
    path.write_text(content, encoding='utf-8')


def verify_release():
    manifest = json.loads(read(OUT / 'release_manifest.json'))
    installation = json.loads(read(OUT / 'installation_r1/report.json'))
    page_test = json.loads(read(OUT / 'verification/post_STOP_replay_r1/report.json'))
    old = ROOT / 'artifacts/live_bench_20261118/boot_stack_integrity_r1'
    native = json.loads(read(old / 'release_manifest.json'))
    assert tuple(manifest['pair']) == PAIR and manifest['installed'] and manifest['readback_verified']
    assert installation['passed'] and installation['native_image_unchanged_verified']
    assert installation['calibration_unchanged'] and page_test['passed']
    assert (native['OFF_fast_limit_cycles'], native['estimate_age_ms'],
            native['raw_current_trip_A'], native['ADC_UPDATE_ticks']) == (4000, 2, 1.35, 2048)
    candidate = OUT / 'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == manifest['image_sha256']
    assert hashlib.sha256((OUT / 'web_hmi/server.py').read_bytes()).hexdigest() == manifest['server_sha256']
    previous = old / 'FOC_5Hz_20261120_r1'
    inventory = json.loads(read(previous / 'saved_files_sha256.json'))
    for name, expected in inventory.items():
        assert hashlib.sha256((previous / name).read_bytes()).hexdigest() == expected, name
    return previous, inventory


def startup_undervoltage_only(s):
    return (s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==4
            and s.get('mc_fault')==s.get('bp_fault')==5 and s.get('mc_fault_reason')==8
            and s.get('clear_recovery',{}).get('available') is False)


def main(*, permit_clear_option=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--confirm-autonomous-powered', action='store_true')
    parser.add_argument('--outdir', type=Path)
    if permit_clear_option:
        parser.add_argument('--clear-once', action='store_true',
                            help='Only when one CLEAR for the observed startup undervoltage was explicitly authorized')
    args = parser.parse_args()
    clear_once = getattr(args, 'clear_once', False)
    previous, inventory = verify_release()
    if args.verify_only:
        print(json.dumps({'verified': True, 'earlier_files_verified': len(inventory), 'stand_commands': 0}))
        return 0
    if not args.confirm_autonomous_powered or args.outdir is None:
        parser.error('Current powered-bench confirmation and a new output directory are required')
    out = args.outdir.resolve()
    if out.exists() or OUT not in out.parents:
        parser.error('Choose a new directory inside the installed release')
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = read(ROOT / '.unoq_ssh/control_token').strip()
    assert token

    def request(path, body=None):
        assert body is None or (path == '/api/algorithm' and body == {'algorithm': 2})
        req = urllib.request.Request('http://192.168.1.138:8080' + path,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={'X-UNOQ-Control-Token': token,
                                              'Content-Type': 'application/json'})
        with client.open(req, timeout=6) as response:
            payload = json.load(response)
        if payload.get('ok') is not True:
            raise RuntimeError(str(payload.get('error', 'Request rejected')))
        return payload

    runtime = supervised.driver.trial
    runtime.PAIR = PAIR
    supervised.p = SimpleNamespace(NEW=PAIR, write=write)
    preflight = out.with_name(out.name + '_RPC_preflight')
    guard = supervised.prepare_rpc_guard(lambda: request('/api/status'), preflight)
    runtime.RPC_GUARD = guard
    read_record = runpy.run_path(str(OUT / 'web_hmi/server.py'))['receive_capture_pages']
    runtime.POST_STOP_PAGE_COLLECTOR = (
        lambda directory, state, get: collect(get, read_record, state, directory / 'paged_capture')
    )

    def check(s):
        decode_boot(s, PAIR)
        assert runtime.off(s) and runtime.link_power(s) and runtime.off_timing_ready(s)
        assert s['run_id'] == s['run_start_ms'] == s['hmi_hv_armed'] == 0
        assert s['mc_adc_peak_complete'] == s['mc_observer_trace_complete'] == 0
        assert s['mc_current_zero_ready'] == 1 and s['estop'] == s['algorithm_fault'] == 0
        assert s.get('rpc_route_failures')==0
        if clear_once:
            assert startup_undervoltage_only(s), 'Startup undervoltage latch has changed'
        else:
            assert all(s.get(k) == 0 for k in ('mc_fault_current_mask','mc_fault_occurred_mask',
                                              'mc_fault','bp_fault'))
        sd = s['mc_sd_live']
        assert sd['level'] == 'HIGH' and sd['config_ok'] and sd['break_irq_enabled']
        assert s['repeat_break']['fresh'] and s['repeat_break']['epoch_matches']

    try:
        before = request('/api/status')['data']
        write(preflight / 'before_selection.json', json.dumps(before))
        check(before)
        selected = request('/api/algorithm', {'algorithm': 2})
        write(preflight / 'selection_ack.json', json.dumps(selected))
        for _ in range(10):
            s = request('/api/status')['data']
            if runtime.profile(s):
                break
            time.sleep(.2)
        check(s)
        assert (clear_once or runtime.healthy(s)) and s['algorithm_selected'] == 2
        result = runtime.main()
    finally:
        write(preflight / 'final_guard.json', json.dumps(guard.snapshot(), indent=2))
        runtime.RPC_GUARD = None
        runtime.POST_STOP_PAGE_COLLECTOR = None
        for name, expected in inventory.items():
            assert hashlib.sha256((previous / name).read_bytes()).hexdigest() == expected
    if out.exists():
        sealed = {file.relative_to(out).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
                  for file in out.rglob('*') if file.is_file()}
        write(out / 'saved_files_sha256.json', json.dumps(sealed, indent=2))
    return result


if __name__ == '__main__':
    raise SystemExit(main())

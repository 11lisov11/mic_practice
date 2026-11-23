"""GET-only autonomous qualification; never sends motor or reset commands."""
import argparse
import json
import time
import urllib.error
import urllib.request
import prepare_current_polarity_budget as p


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--outdir', type=__import__('pathlib').Path, required=True)
    out = ap.parse_args().outdir.resolve()
    assert p.OUT in out.parents
    out.mkdir(exist_ok=False)
    report = dict(passed=False, START=0, CLEAR=0, ARM=0, RESET=0, flash=0,
                  SWD=0, HTTP_methods=['GET'], operator_state='Powerbanks; PC/Saleae detached; J4 ON; J1 OFF')
    def save(name, obj):
        p.write(out/name, json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    def get(path, binary=False):
        req = urllib.request.Request('http://192.168.1.138:8080'+path,
            headers={'X-UNOQ-Control-Token': token}, method='GET')
        try:
            with op.open(req, timeout=8) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raw = error.read()
            raise RuntimeError(f'GET {path}: HTTP {error.code}: {raw.decode(errors="replace")}')
        return raw if binary else json.loads(raw)
    try:
        rows = []
        for i in range(20):
            response = get('/api/status')
            assert response.get('ok') is True
            s = response['data']
            rows.append(s)
            with (out/'status_samples.jsonl').open('a', encoding='utf-8') as f:
                f.write(json.dumps(dict(monotonic=time.monotonic(), response=response), ensure_ascii=False)+'\n')
            time.sleep(.4)
        save('final_status.json', response)
        for name, path in [('SD_snapshots.json', '/api/break-snapshot'),
                           ('SD_trace.json', '/api/bkin-trace'),
                           ('repeat_break.json', '/api/repeat-break')]:
            save(name, get(path))
        (out/'HMI_logs.txt').write_bytes(get('/api/logs', binary=True))
        old = json.loads(p.read(p.OUT/'post_install_idle_r1/final_status.json'))['data']
        checks = {}
        def check(name, value):
            checks[name] = bool(value)
        check('installed_pair', all((s.get('fw_build'), s.get('mc_fw_build')) == p.NEW for s in rows))
        check('disarmed_no_runs', all(s.get('state') == 'SAFE' and all(s.get(k) == 0 for k in ('pwm', 'run_id', 'hmi_hv_armed')) for s in rows))
        check('bus_below20', all(0 <= s.get('vdc', -1) < 20 for s in rows))
        check('fresh_native_replies', all(0 <= s.get('mc_age_ms', 99999) < 300 for s in rows)
              and rows[-1]['mc_good_cnt'] > rows[0]['mc_good_cnt'])
        check('no_new_bad_frames', len({s['mc_bad_cnt'] for s in rows}) == 1)
        check('UART_RPC_clean', all(s.get(k) == 0 for s in rows for k in (
            'mc_bad_integrity', 'mc_bad_sequence', 'mc_uart_error_flags', 'mc_last_uart_error_flags',
            'rpc_response_timeouts', 'rpc_send_timeouts', 'mc_transport_fault')))
        check('autonull_ready', all(s.get('mc_current_zero_ready') == 1 and s.get('mc_current_zero_stable') == 3 for s in rows))
        check('calculated_profile', all(s.get('algorithm_qualification') == 128 and s.get('algorithm_profile_crc') == 1354279011 for s in rows))
        check('CPU64_cases', all(s.get('foc_experiment_flags') == 1 and s.get('foc_timing_cases') == 64 and s.get('foc_timing_fault') == 0 for s in rows))
        check('fast_budget4000', all(0 < s.get('algorithm_fast_cycles', 0) <= 4000 for s in rows))
        check('CPU_meter', all(s['foc_runtime'].get('source') == 'OFF_synthetic_CPU_probe'
            and s['foc_runtime'].get('observer_steps') == 64 and s['foc_runtime'].get('meter_errors') == 0
            and s['foc_runtime'].get('first_fault') is None for s in rows))
        check('observer_record_unoccupied', all(s.get('mc_observer_trace_complete') == 0
            and s.get('mc_observer_trace_hex') == '-' and s.get('mc_observer_trace_good') == 0
            and s.get('mc_observer_trace_bad') == 0 for s in rows))
        check('boot_records_fresh', all(s['native_boot'].get('fresh') and s['repeat_break'].get('fresh') for s in rows))
        check('no_reboot_during_observation', len({s['linux_boot_id'] for s in rows}) == 1
            and len({s['native_boot']['early_record_crc'] for s in rows}) == 1
            and rows[-1]['native_boot']['native_tick_ms'] > rows[0]['native_boot']['native_tick_ms'])
        check('SD_currently_HIGH_configured', all(s['mc_sd_live'].get('config_ok')
            and s['mc_sd_live'].get('level') == 'HIGH' for s in rows))
        preserved = json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
        for rel, expected in preserved.items():
            assert p.sha(p.ROOT/rel) == expected, rel
        report.update(checks=checks, passed=all(checks.values()), pair=list(p.NEW), samples=len(rows),
            boot_changed_since_PC=s['linux_boot_id'] != old['linux_boot_id'],
            good_frame_increase=rows[-1]['mc_good_cnt']-rows[0]['mc_good_cnt'],
            rejected_frames=s['mc_bad_cnt'], zero_ready=s['mc_current_zero_ready'],
            zero_offsets=s['mc_current_offsets_adc'], zero_spans=s['mc_current_zero_spans'],
            zero_attempts=s['mc_current_zero_attempts'], SD=s['mc_sd_live'], repeat_break=s['repeat_break'],
            active_fault_mask=s['mc_fault_current_mask'], saved_fault_mask=s['mc_fault_occurred_mask'],
            native_boot=s['native_boot'], CPU=s['foc_runtime'], preserved_files_verified=len(preserved),
            fast_kernel_cycles=s['algorithm_fast_cycles'], fast_kernel_budget_cycles=4000,
            motor_start_ready=False, PWM_test=False,
            limitation='GET telemetry only; no SWD access on powerbanks. Empty recorder inferred from fresh boot/run_id0 and receiver state, not a direct RAM read.')
    except Exception as error:
        report['error'] = repr(error)
    save('report.json', report)
    save('saved_files_sha256.json', {f.name:p.sha(f) for f in out.iterdir() if f.is_file()})
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

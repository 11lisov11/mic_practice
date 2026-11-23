"""One explicitly authorized CLEAR, GET-only diagnostics, no motor start."""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
import prepare_current_polarity_budget as p


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--confirmed-one-clear-no-start', action='store_true', required=True)
    ap.add_argument('--outdir', type=__import__('pathlib').Path, required=True)
    a = ap.parse_args()
    out = a.outdir.resolve()
    assert p.OUT in out.parents
    out.mkdir(exist_ok=False)
    report = dict(passed=False, CLEAR=0, START=0, ARM=0, RESET=0, flash=0, SWD=0,
                  operator_state='Powerbanks; J1 and J4 ON; PC/Saleae detached; unchanged',
                  authorization='Exactly one native CLEAR without START', commands=[])
    def save(name, obj):
        p.write(out/name, json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
    def checkpoint():
        save('report.json', report)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    def request(path, body=None, binary=False):
        req = urllib.request.Request('http://192.168.1.138:8080'+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json', 'X-UNOQ-Control-Token':token},
            method='GET' if body is None else 'POST')
        try:
            with op.open(req, timeout=8) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raw = error.read()
            save('HTTP_error.json', dict(path=path, code=error.code, body=raw.decode(errors='replace')))
            raise RuntimeError(f'{path}: HTTP {error.code}')
        if binary:
            return raw
        data = json.loads(raw)
        if data.get('ok') is not True:
            raise RuntimeError(f'{path}: {data.get("error", "not acknowledged")}')
        return data
    def status(label):
        d = request('/api/status')
        with (out/'status_samples.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(dict(label=label, monotonic=time.monotonic(), response=d), ensure_ascii=False)+'\n')
        return d['data']
    def disarmed(s):
        return s.get('state') == 'SAFE' and all(s.get(k) == 0 for k in ('pwm','run_id','hmi_hv_armed')) and not s.get('bp_status',0x22)&0x22
    def clean_link(s):
        return 0 <= s.get('mc_age_ms',99999) < 300 and all(s.get(k) == 0 for k in (
            'mc_transport_fault','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags',
            'mc_last_uart_error_flags','rpc_response_timeouts','rpc_send_timeouts'))
    def restored(s):
        sd = s.get('mc_sd_live') or {}
        return disarmed(s) and clean_link(s) and all(s.get(k) == 0 for k in (
            'mc_fault_current_mask','mc_fault_occurred_mask','mc_fault','bp_fault','estop','algorithm_fault')) and (
            sd.get('level') == 'HIGH' and sd.get('config_ok') is True and sd.get('break_irq_enabled') is True)
    checkpoint()
    before = None
    try:
        before = status('before_CLEAR')
        save('before_CLEAR.json', before)
        assert (before['fw_build'], before['mc_fw_build']) == p.NEW
        assert disarmed(before) and clean_link(before) and 250 <= before['vdc'] <= 350
        assert before['mc_sd_live']['level'] == 'HIGH' and before['mc_sd_live']['config_ok']
        assert before['mc_fault_current_mask'] in (0,4) and before['mc_fault_occurred_mask'] in (0,4,1024,1028)
        assert before['mc_current_zero_ready'] == 1 and before['algorithm_fault'] == 0
        assert before['native_boot']['fresh'] and before['repeat_break']['fresh']
        wave = before.get('mc_break_wave_hex','-')
        assert wave not in ('','-') and before['mc_sd_live']['first_record_ready']
        (out/'SD_first_before.bin').write_bytes(bytes.fromhex(wave))
        for name, path in [('SD_snapshots_before.json','/api/break-snapshot'), ('SD_trace_before.json','/api/bkin-trace')]:
            save(name, request(path))
        # Count before transmission. A timeout or negative reply must never retry.
        report['CLEAR'] = 1
        report['commands'].append('CLEAR')
        checkpoint()
        response = request('/api/cmd', {'cmd':'CLEAR'})
        save('CLEAR_response.json', response)
        report['CLEAR_HTTP_acknowledged'] = True
        rows = []
        for i in range(12):
            s = status('after_one_CLEAR')
            rows.append(s)
            assert disarmed(s), 'Unexpected outputs or run identifier change; no further commands'
            assert (s['fw_build'],s['mc_fw_build']) == p.NEW
            assert s['native_boot']['early_record_crc'] == before['native_boot']['early_record_crc']
            assert s['linux_boot_id'] == before['linux_boot_id']
            assert s.get('mc_break_wave_hex') == wave, 'First Break changed'
            time.sleep(.35)
        save('after_CLEAR.json', s)
        report.update(passed=all(restored(x) for x in rows[-4:]),
            protections_restored=all(restored(x) for x in rows[-4:]),
            samples=len(rows), first_SD_record_unchanged=True,
            good_frame_increase=s['mc_good_cnt']-rows[0]['mc_good_cnt'],
            no_new_bad_frames=len({x['mc_bad_cnt'] for x in rows}) == 1,
            SD=s['mc_sd_live'], repeat_break=s['repeat_break'],
            active_fault_mask=s['mc_fault_current_mask'], saved_fault_mask=s['mc_fault_occurred_mask'],
            local_Uno_fault=s.get('uno_local_fault'), estop=s['estop'],
            transport_fault=s['mc_transport_fault'], zero_ready=s['mc_current_zero_ready'],
            algorithm_selected=s['algorithm_selected'], algorithm_fault=s['algorithm_fault'],
            fast_kernel_cycles=s['algorithm_fast_cycles'],
            observer_record_unoccupied=s['mc_observer_trace_complete']==0 and s['mc_observer_trace_hex']=='-',
            repeat_capture_armed=s['repeat_break']['state']=='ARMED')
        if not report['passed']:
            report['error'] = 'One CLEAR did not restore all protections; no retry and no START'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        try:
            last = status('final_observation')
            save('final_status.json', dict(ok=True,data=last))
            report['final_outputs_off'] = disarmed(last)
            for name, path in [('SD_snapshots_after.json','/api/break-snapshot'),
                               ('SD_trace_after.json','/api/bkin-trace'),
                               ('repeat_break_after.json','/api/repeat-break')]:
                save(name, request(path))
            (out/'HMI_logs_after.txt').write_bytes(request('/api/logs',binary=True))
        except Exception as error:
            report['collection_error'] = repr(error)
        checkpoint()
        save('saved_files_sha256.json', {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file()})
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

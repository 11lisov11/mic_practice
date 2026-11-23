"""One authorized 1407/1408 FOC5Hz/5s trial, no CLEAR, schema2 collection."""
import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import time
import urllib.request
from pathlib import Path
import prepare_current_polarity_budget as p
import run_observer_input_epoch_runtime as trial
from run_foc_boot_capture_trial import decode_boot
from test_foc_update_latency_fix import function

trial.PAIR = p.NEW


def load_server():
    spec = importlib.util.spec_from_file_location('current_trial_HMI', p.OUT/'web_hmi/server.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def offline_check(out):
    """Saved status and production functions only; no network or MCU commands."""
    out.mkdir(exist_ok=False)
    source = p.read(p.OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    native_start = function(source, 'start_precheck')
    native_guard = function(source, 'bp_fault_or_timeout')
    assert 'g_fault' not in native_start and 'g_fault' not in native_guard
    assert 'g_estop_latched' in native_start and 'g_bp_fault_code != 0' in native_start
    assert 'BP_STATUS_TIMEOUT' in native_start and 'g_nucleo_rx_bad != 0U' in native_start
    hmi = load_server()
    saved = p.OUT/'CLEAR_only_20261115_r1/final_status.json'
    s = json.loads(p.read(saved))['data']
    assert s['uno_local_fault'] == 5 and s['mc_fault'] == s['bp_fault'] == 0
    config = hmi.HvArmConfig(enabled=True)
    command = hmi.CommandGuardConfig(max_vdc=400, allow_hv=True, local_bench_gate=True)
    def gates(value):
        return [hmi.hv_arm_precheck(value, config, vbus_calibrated=True),
                hmi.command_guard_check('START', value, command)]
    zero = dict(s, uno_local_fault=0)
    assert gates(s) == gates(zero)
    assert all(ok for ok, reason in gates(s)), gates(s)
    cases = []
    for change in ({'estop':1}, {'bp_fault':5,'mc_fault':5}, {'link':False},
                   {'mc_bad_cnt':1,'bp_bad_cnt':1}):
        changed = dict(s, **change)
        result = gates(changed)
        assert not all(ok for ok, reason in result), (change,result)
        cases.append(dict(change=change, results=result))
    foc = dict(s, algorithm_selected=2, algorithm_requested=2)
    assert trial.healthy(foc) and trial.off_timing_ready(foc)
    for key, value in [('mc_fault_current_mask',4), ('mc_fault_occurred_mask',1024),
                       ('mc_transport_fault',7), ('mc_current_zero_ready',0), ('algorithm_fault',1)]:
        assert not trial.healthy(dict(foc, **{key:value})), key
    for cycles in (4001,5313):
        assert not trial.off_timing_ready(dict(foc,algorithm_fast_cycles=cycles))
    blocked = copy.deepcopy(foc)
    blocked['mc_sd_live']['break_irq_enabled'] = False
    assert not trial.healthy(blocked)
    assert trial.PAIR == p.NEW
    result = dict(passed=True, network_requests=0, motor_commands=0,
        local_code5_blocks_normal_START=False,
        HMI_local0_and5_results=gates(s), active_fault_negative_cases=cases,
        native_start_source=native_start, native_peer_guard_source=native_guard,
        production_runtime_SHA256=p.sha(p.ROOT/'tools/run_observer_input_epoch_runtime.py'),
        schema2_decoder_source_SHA256=p.sha(p.OUT/'web_hmi/server.py'),
        source_note='Native functions inspected without editing; HMI gates executed against saved status. Live server and MCU repeat all real guards.')
    p.write(out/'report.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--offline-check-only', action='store_true')
    ap.add_argument('--confirm-autonomous-powered', action='store_true')
    ap.add_argument('--outdir', type=Path, required=True)
    a = ap.parse_args()
    out = a.outdir.resolve()
    assert p.OUT in out.parents and not out.exists()
    if a.offline_check_only:
        result = offline_check(out)
        print(json.dumps({k:result[k] for k in ('passed','network_requests','motor_commands','local_code5_blocks_normal_START')}))
        return 0
    assert a.confirm_autonomous_powered
    verified = json.loads(p.read(p.OUT/'trial_preparation_20261115_r4/report.json'))
    assert verified['passed'] and verified['production_runtime_SHA256'] == p.sha(p.ROOT/'tools/run_observer_input_epoch_runtime.py')
    assert verified['schema2_decoder_source_SHA256'] == p.sha(p.OUT/'web_hmi/server.py')
    assert 'CLEAR' not in sys.argv
    hmi = load_server()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    prep = out.with_name(out.name+'_preflight')
    prep.mkdir(exist_ok=False)
    def save(target,name,value):
        p.write(target/name,json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    def request(path,body=None,binary=False):
        req = urllib.request.Request('http://192.168.1.138:8080'+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},
            method='GET' if body is None else 'POST')
        with opener.open(req,timeout=8) as response:
            raw = response.read()
        if binary:return raw
        d = json.loads(raw)
        assert d.get('ok') is True,d.get('error')
        return d
    initial = request('/api/status')['data']
    save(prep,'initial_status.json',initial)
    assert (initial['fw_build'],initial['mc_fw_build']) == p.NEW
    assert trial.off(initial) and trial.link_power(initial) and trial.off_timing_ready(initial)
    assert initial['mc_current_zero_ready'] == 1 and initial['run_id'] == initial['run_start_ms'] == 0
    assert all(initial[k] == 0 for k in ('mc_fault_current_mask','mc_fault_occurred_mask','mc_fault','bp_fault','estop','algorithm_fault'))
    assert initial['mc_sd_live']['level']=='HIGH' and initial['mc_sd_live']['config_ok'] and initial['mc_sd_live']['break_irq_enabled']
    assert initial['repeat_break']['state']=='ARMED' and initial['repeat_break']['fresh']
    assert initial['mc_adc_peak_complete']==initial['mc_observer_trace_complete']==initial['mc_observer_trace_bad']==0
    assert initial['mc_observer_trace_hex']=='-'
    initial_boot = decode_boot(initial,p.NEW)
    old = json.loads(p.read(p.OUT/'CLEAR_only_20261115_r1/final_status.json'))['data']
    assert initial_boot['identity'] == decode_boot(old,p.NEW)['identity']
    assert initial['mc_break_wave_hex'] == old['mc_break_wave_hex']
    save(prep,'SD_first_before.json',request('/api/bkin-trace'))
    # Stopped-only selection; this endpoint cannot START or CLEAR.
    selected = request('/api/algorithm',{'algorithm':2})
    save(prep,'algorithm_selection_response.json',selected)
    for _ in range(10):
        before = request('/api/status')['data']
        if trial.off(before) and trial.healthy(before):break
        time.sleep(.2)
    save(prep,'FOC_selected_before_START.json',before)
    assert trial.off(before) and trial.healthy(before) and trial.off_timing_ready(before)
    assert before['run_id']==0 and before['mc_break_wave_hex']==initial['mc_break_wave_hex']
    # Reuse the reviewed bounded runner byte-for-byte. Only its pair identity
    # is configured above; all runtime guards, 5s MCU deadline, heartbeats,
    # host backup STOP, and its strict raw-ADC availability audit remain intact.
    sys.argv = [sys.argv[0],'--confirm-autonomous-powered','--outdir',str(out)]
    runtime_rc = trial.main()
    report = json.loads(p.read(out/'report.json'))
    result = dict(passed=False, collection_GET_only=True, additional_motor_commands=0)
    try:
        deadline = time.monotonic()+25
        while True:
            d = request('/api/status');s = d['data']
            with (out/'observer_collection_status.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(d,ensure_ascii=False)+'\n')
            assert trial.off(s)
            now = decode_boot(s,p.NEW)
            assert now['identity']==initial_boot['identity'] and now['Linux_boot_id']==initial_boot['Linux_boot_id']
            assert s['mc_break_wave_hex']==initial['mc_break_wave_hex']
            if s.get('mc_observer_trace_complete')==1:
                assert s['mc_observer_trace_bad']==0
                raw = bytes.fromhex(s['mc_observer_trace_hex'])
                decoded = hmi.decode_observer_trace_hex(raw.hex(),p.NEW[1])
                assert decoded['available'] and decoded['schema']==2 and decoded['count']>0
                (out/'observer_trace.bin').write_bytes(raw)
                save(out,'observer_trace_decoded.json',decoded)
                result.update(passed=True,bytes=len(raw),SHA256=hashlib.sha256(raw).hexdigest(),
                    total_samples=decoded['total_observer_samples'],valid_samples=decoded['valid_samples'],
                    invalid_samples=decoded['invalid_samples'],first_loss=decoded['first_loss'],control_fault=decoded['control_fault'])
                break
            if time.monotonic()>=deadline:raise RuntimeError('Observer record incomplete; no automatic repeat')
            time.sleep(.25)
        save(out,'observer_final_status.json',d)
        save(out,'boot_continuity.json',dict(passed=True,before=initial_boot,after=now,raw_ADC_availability_not_used_to_infer_reboot=True))
    except Exception as error:
        result['error']=str(error)
    save(out,'observer_record_audit.json',result)
    for name,path in [('SD_snapshots_after.json','/api/break-snapshot'),('SD_trace_after.json','/api/bkin-trace'),('repeat_break_after.json','/api/repeat-break')]:
        try:save(out,name,request(path))
        except Exception as error:save(out,name,dict(error=str(error)))
    try:(out/'HMI_logs_after.txt').write_bytes(request('/api/logs',binary=True))
    except Exception as error:save(out,'HMI_logs_error.json',dict(error=str(error)))
    report.update(observer_record_audit=result,local_code5_blocks_normal_START=False,
        no_additional_CLEAR=True,runtime_exit_code=runtime_rc,
        CPU_AND_observer_trial_complete=bool(report.get('completed_5s') and report.get('runtime_record_received') and result['passed']),
        physical_rotation_verified=False)
    # Retain the runner's strict overall result if raw ADC capture is missing.
    # A five-second completion is reported separately, never fabricated.
    report['passed']=bool(report.get('passed') and result['passed'])
    save(out,'report.json',report)
    save(out,'saved_files_sha256.json',{f.name:p.sha(f) for f in out.iterdir() if f.is_file() and f.name!='saved_files_sha256.json'})
    print(json.dumps({k:report.get(k) for k in ('passed','completed_5s','CPU_AND_observer_trial_complete','clear_commands','start_commands','runtime_record_received','ADC_record_received','error')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

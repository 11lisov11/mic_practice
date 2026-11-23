"""One explicitly authorized FOC5Hz/5s RUN with immutable observer/SD/ADC evidence."""
import argparse
import json
import sys
import time
import urllib.request
import prepare_observer_input_epoch as package
import run_observer_input_epoch_runtime as trial
import run_foc_boot_capture_trial as boot
import run_foc_observer_trace_trial as capture

boot.package=package
boot.trial=trial
capture.package=package
capture.base=boot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-autonomous-powered',action='store_true',required=True)
    parser.add_argument('--clear-once',action='store_true',help='Only with explicit human authorization for one CLEAR')
    parser.add_argument('--outdir',type=__import__('pathlib').Path,required=True)
    a=parser.parse_args();out=a.outdir.resolve();assert not out.exists()
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=package.read(package.ROOT/'.unoq_ssh/control_token').strip()
    def request(path,body=None):
        q=urllib.request.Request('http://192.168.1.138:8080'+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},
            method='GET' if body is None else 'POST')
        with op.open(q,timeout=8) as f:r=json.load(f)
        assert r['ok'],r.get('error');return r
    initial=request('/api/status');s=initial['data']
    assert trial.off(s) and trial.link_power(s) and trial.off_timing_ready(s)
    boot.decode_boot(s,package.NEW)
    assert s['run_id']==s['run_start_ms']==0 and s['mc_current_zero_ready']==1
    assert s['mc_adc_peak_complete']==s['mc_observer_trace_complete']==s['mc_observer_trace_bad']==0
    assert s['mc_observer_trace_hex']=='-'
    assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['config_ok']
    if not a.clear_once:
        assert all(s.get(k)==0 for k in ('mc_fault_current_mask','mc_fault_occurred_mask','mc_fault','bp_fault'))
        assert s['mc_sd_live']['break_irq_enabled'],'No CLEAR authorized; no configuration or START'
    # Algorithm configuration while SAFE is stopped-only and cannot start/clear.
    selected=request('/api/algorithm',{'algorithm':2})
    for _ in range(10):
        r=request('/api/status');s=r['data']
        if trial.off(s) and trial.profile(s):break
        time.sleep(.2)
    assert trial.off(s) and trial.profile(s) and trial.link_power(s)
    before=s
    rc=boot.main()  # Uses the same argv; performs at most the authorized one CLEAR/START.
    package.write(out/'selection_before.json',json.dumps(initial,ensure_ascii=False,indent=2)+'\n')
    package.write(out/'algorithm_response.json',json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
    done=capture.collect_observer(out,lambda:request('/api/status'),before,limit_s=20)
    print(json.dumps(dict(passed=rc==0 and done,additional_motor_commands=0)))
    return 0 if rc==0 and done else 1


if __name__=='__main__':raise SystemExit(main())

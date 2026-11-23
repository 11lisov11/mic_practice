"""Read-only preparation of installed1607/1606 for a future isolated FOC trial."""
import json,socket,urllib.request
from unittest.mock import patch
import prepare_rpc_route_recovery as p

def main():
    out=p.OUT/'FOC_preparation_r1';out.mkdir(exist_ok=False)
    report=dict(passed=False,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,pair=list(p.NEW))
    try:
        manifest=json.loads(p.read(p.OUT/'manifest.json'))
        assert manifest['installed'] and manifest['OFF_route_reconnect_verified']
        for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
        history=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
        for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
        with patch.object(socket.socket,'connect',side_effect=AssertionError('Import must not access devices')):
            import run_rpc_route_recovery_trial as trial
            assert trial.runner.p is p and trial.runner.driver.package is p
            assert trial.runner.driver.trial.PAIR==p.NEW
            assert trial.runner.driver.boot.package is p and trial.runner.driver.capture.package is p
        token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req=urllib.request.Request('http://127.0.0.1:18080/api/status',headers={'X-UNOQ-Control-Token':token})
        with op.open(req,timeout=8) as f:raw=f.read()
        (out/'status.json').write_bytes(raw);reply=json.loads(raw);assert reply['ok']
        s=reply['data'];assert (s['fw_build'],s['mc_fw_build'])==p.NEW
        assert s['pwm']==0 and s['state']=='SAFE' and s['hmi_hv_armed']==0
        assert 0<=s['vdc']<20 and s['mc_current_zero_ready']==1
        assert 0<=s['mc_age_ms']<300 and 0<s['algorithm_fast_cycles']<=4000
        assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled']
        trial.runner.driver.boot.decode_boot(s,p.NEW)
        report.update(passed=True,USB_idle_state_verified=True,vdc=s['vdc'],zero_ready=s['mc_current_zero_ready'],
            CPU_fast_cycles=s['algorithm_fast_cycles'],CPU_budget=4000,estimate_limit_ms=2,
            SD=s['mc_sd_live'],preserved_files=len(history),trial_wrapper_bound=True,
            FOC_RUN_ready=False,operator_next='Transfer both boards to powerbanks; detach PC and Saleae; J4 ON, J1 OFF; no START/RESET')
    except Exception as error:report['error']=str(error)
    p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=True));return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

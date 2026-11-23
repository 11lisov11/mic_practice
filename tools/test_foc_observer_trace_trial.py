"""Replay saved immutable trace and failure cases; no network/board access."""
import copy,json,tempfile,hashlib
from pathlib import Path
import run_foc_observer_trace_trial as run


def main():
    p=run.package;out=p.OUT/'verification/trial_preparation_r1';out.mkdir(exist_ok=False)
    before=json.loads(p.read(p.OUT/'post_install_readback_r1/final_status.json'))['data']
    raw=(p.OUT/'verification/candidate_ADC_plusminus16counts_trace.bin').read_bytes()
    s=dict(before,mc_observer_trace_complete=1,mc_observer_trace_hex=raw.hex())
    blob,d,b=run.observer_record(s,before);assert blob==raw and d['first_loss']['reason_mask']==32
    tests=1
    def rejected(v):
        try:run.observer_record(v,before)
        except (AssertionError,ValueError):return
        raise AssertionError('Invalid observer trace accepted')
    for fields in (dict(pwm=1),dict(mc_fw_build=0),dict(mc_observer_trace_complete=0),
                   dict(mc_observer_trace_bad=1),dict(linux_boot_id='00000000-0000-0000-0000-000000000000')):
        rejected(dict(s,**fields));tests+=1
    for byte in (0,8,12,60,100,1695):
        damaged=bytearray(raw);damaged[byte]^=1;rejected(dict(s,mc_observer_trace_hex=damaged.hex()));tests+=1
    with tempfile.TemporaryDirectory(prefix='observer_trial_') as temporary:
        path=Path(temporary);package=run.package
        package.write(path/'report.json',json.dumps(dict(passed=True,start_commands=1)))
        calls=[]
        def fetch():calls.append('GET /api/status');return dict(ok=True,data=s)
        assert run.collect_observer(path,fetch,before)
        assert calls==['GET /api/status'] and (path/'observer_trace.bin').read_bytes()==raw;tests+=1
        package.write(path/'report.json',json.dumps(dict(passed=True,start_commands=1)))
        failed=copy.deepcopy(s);failed['pwm']=1
        assert not run.collect_observer(path,lambda:dict(ok=True,data=failed),before)
        assert not json.loads(package.read(path/'report.json'))['passed'];tests+=1
    for rel,digest in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert hashlib.sha256((p.OUT/rel).read_bytes()).hexdigest()==digest,rel
    report=dict(passed=True,checks=tests,GET_only_post_collection=True,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,
        source_FW_unchanged=True,generic_trial_runner_unchanged=True)
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()

"""Check new recording against saved packets; no hardware access."""
import copy
import hashlib
import json
import tempfile
from pathlib import Path
import run_foc_boot_capture_trial as run
from configure_multi_algorithm import crc32c


def main():
    p=run.package;out=p.OUT/'verification/trial_preparation_r1';out.mkdir(exist_ok=False)
    saved=json.loads(p.read(p.OUT/'post_install_readback_r1/final_status.json'))['data']
    evidence=run.decode_boot(saved,p.NEW);checked=1
    def reject(s):
        try:run.decode_boot(s,p.NEW)
        except (AssertionError,ValueError):return
        raise AssertionError('Corrupted/stale boot accepted')
    for update in (dict(mc_fw_build=0),dict(linux_boot_id=None),dict(mc_boot_packet_hex='-')):
        reject(dict(saved,**update));checked+=1
    bad=copy.deepcopy(saved);bad['native_boot']['fresh']=False;reject(bad);checked+=1
    frame=bytes.fromhex(saved['mc_boot_packet_hex'])
    for bit in range(len(frame)*8):
        b=bytearray(frame);b[bit//8]^=1<<(bit%8)
        reject(dict(saved,mc_boot_packet_hex=b.hex()));checked+=1
    # Replay first-trial profile guards with the new build identity.
    good=dict(saved,algorithm_selected=2,algorithm_requested=2)
    assert run.trial.profile(good)
    for update in (dict(mc_current_zero_ready=0),dict(algorithm_fault=2),
                   dict(algorithm_profile_crc=0),dict(mc_age_ms=300)):
        assert not run.trial.profile(dict(good,**update));checked+=1
    # Audit writes evidence but must not synthesize a successful motor run.
    with tempfile.TemporaryDirectory(prefix='boot_trial_evidence_') as temporary:
        d=Path(temporary)
        def seed(before,after,passed):
            for name,data in [('report.json',dict(passed=passed,start_commands=0)),
                              ('before_CLEAR.json',before),('final_status.json',after)]:
                (d/name).write_text(json.dumps(data),encoding='utf-8')
        seed(saved,saved,False);assert not run.audit_saved_trial(d)
        assert json.loads((d/'boot_evidence_audit.json').read_text())['passed'];checked+=1
        seed(saved,dict(saved,linux_boot_id='00000000-0000-0000-0000-000000000000'),True)
        assert not run.audit_saved_trial(d);checked+=1
    # Critical runner and all installed firmware sources remain unchanged.
    sources=json.loads(p.read(p.OUT/'source_hashes.json'))
    for rel,digest in sources.items():assert hashlib.sha256((p.OUT/rel).read_bytes()).hexdigest()==digest,rel
    result=dict(passed=True,checks=checked,pair=list(p.NEW),sources_verified=len(sources),
        boot=evidence,hardware_commands=0,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,
        generic_trial_runner_unchanged=True,firmware_unchanged=True)
    p.write(out/'report.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,checks=checked,hardware_commands=0,sources_verified=len(sources))))


if __name__=='__main__':main()

"""Future explicitly authorized1713/1714 FOC5Hz/5s with immutable NIS replay.

No device access on import or --verify-package-only. Normal execution retains
the existing bounded-run/heartbeat/SD/current/age/RPC gates and at most the
separately authorized one CLEAR. Post-run ARM replay is offline, never a retry.
"""
import json
import sys
from pathlib import Path

import prepare_observer_nis_replay as p
import run_telemetry_deadline_trial as runner
from release_observer_decoder import load_decoder
from replay_observer_nis import record_payload,replay

runner.p=p
runner.driver.package=p
runner.driver.trial.PAIR=p.NEW
runner.driver.boot.package=p
runner.driver.boot.trial=runner.driver.trial
runner.driver.capture.package=p
runner.driver.capture.base=runner.driver.boot
runner.driver.capture.decode_observer_trace_hex=load_decoder(p.OUT)


def package_check():
    prepared=json.loads(p.read(p.OUT/'manifest.json'))
    installed=json.loads(p.read(p.OUT/'installation_acceptance.json'))
    assert prepared['pair']==installed['pair']==list(p.NEW)
    assert prepared['built'] and prepared['observer_math_unchanged'] and prepared['protections_and_limits_unchanged']
    assert installed['installed'] and installed['native_readback_verified'] and installed['uno_readback_verified']
    for file,base in ((p.OUT/'source_hashes.json',p.OUT),
                      (p.OUT/'release/sha256.json',p.OUT/'release'),
                      (p.BASE/'preserved_all_hashes.json',p.ROOT)):
        for rel,h in json.loads(p.read(file)).items():assert p.sha(base/rel)==h,rel
    for name in ('capture_report.json','ARM_math_identity.json','adapter_report.json','release_CLI_replay.json'):
        assert json.loads(p.read(p.OUT/'verification'/name))['passed'],name
    for rel in prepared['unchanged_modules']:assert p.sha(p.OUT/rel)==p.sha(p.BASE/rel),rel
    return prepared


def offline_post_replay(out):
    result=dict(attempted=False,hardware_commands=0)
    try:
        record=out/'observer_trace.bin'
        if not record.exists():
            result['reason']='No complete observer record; do not repeat a motor run automatically'
        else:
            raw=record.read_bytes();decoded=load_decoder(p.OUT)(raw.hex(),p.NEW[1])
            if decoded.get('first_nis_replay') is None:
                result['reason']='No eligible NIS refusal recorded; raw observer record still archived'
            else:
                payload=record_payload(raw,p.NEW[1])
                m=json.loads(p.read(p.OUT/'release/replay_manifest.json'))
                elf=p.OUT/'release'/m['elf'];assert p.sha(elf)==m['elf_sha256']
                result.update(attempted=True,**replay(payload,elf),record_sha256=p.sha(record),elf_sha256=m['elf_sha256'])
    except Exception as error:result.update(passed=False,error=str(error))
    target=out/'NIS_step_replay.json';assert not target.exists()
    p.write(target,json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    p.write(out/'NIS_replay_files_sha256.json',json.dumps({target.name:p.sha(target)},indent=2)+'\n')
    return result


def main():
    package_check()
    if sys.argv[1:]==['--verify-package-only']:
        print(json.dumps(dict(passed=True,pair=p.NEW,hardware_commands=0,START=0,CLEAR=0,ARM=0)))
        return 0
    rc=runner.main()
    out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
    if out.exists():
        audit=offline_post_replay(out)
        print(json.dumps(dict(offline_replay_attempted=audit['attempted'],offline_replay_passed=audit.get('passed'),additional_motor_commands=0)))
        if audit.get('attempted') and not audit.get('passed'):return 1
    return rc


if __name__=='__main__':raise SystemExit(main())

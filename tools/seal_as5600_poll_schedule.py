"""Seal scheduling candidate; no hardware action."""
import json
import prepare_as5600_poll_schedule as p
import prepare_current_shunt_monitor as u
def main():
    out=p.OUT;m=json.loads(u.read(out/'manifest.json'));assert not m['installed']
    for rel,digest in m['source_sha256'].items():assert u.sha(out/rel)==digest,rel
    assert json.loads(u.read(out/'offline-checks.json'))['passed']
    b=json.loads(u.read(out/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    assert b['firmware_build_id']==2026102517
    for item in b['artifacts']:assert u.sha(out/'build/uno'/item['file'])==item['sha256'].lower()
    assert json.loads(u.read(out/'build/uno/llext-check.json'))['pass']
    m.update(built=True,selftest_pass=True,
        build_sha256={str(x.relative_to(out)).replace('\\','/'):u.sha(x) for x in (out/'build/uno').iterdir() if x.is_file()},
        verification_sha256={name:u.sha(out/name) for name in ('offline-checks.json','recorded-scheduling-replay.json')},
        flash_artifact_sha256=u.sha(out/'build/uno'/b['flash_artifact']),
        source_reference='https://docs.zephyrproject.org/4.2.0/kernel/services/scheduling/index.html#scheduler-locking')
    u.write(out/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(passed=True,installed=False,sha256=m['flash_artifact_sha256'])))
if __name__=='__main__':main()

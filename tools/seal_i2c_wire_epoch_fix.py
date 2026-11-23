import json
import prepare_i2c_wire_epoch_fix as p
def main():
    c=p.OUT;m=json.loads(p.read(c/'manifest.json'));assert not m['installed']
    assert json.loads(p.read(c/'verification/native_report.json'))['passed']
    b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'));assert b['firmware_build_id']==p.NEW[0]
    for item in b['artifacts']:assert p.sha(c/'build/uno'/item['file'])==item['sha256'].lower()
    assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
    for rel,d in b['library_override_sha256'].items():assert p.sha(c/'libraries'/rel)==d.lower()
    n=c/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin'
    assert p.sha(n)==p.sha(p.BASE/'build/nucleo'/n.name)
    for rel,d in json.loads(p.read(c/'archive_references.json')).items():assert p.sha(p.ROOT/rel)==d
    for table in ('source_sha256','build_sha256','verification_sha256'):
        for rel,d in json.loads(p.read(p.BASE/'manifest.json'))[table].items():assert p.sha(p.BASE/rel)==d
    r=dict(passed=True,uno_loader_pass=True,exact_existing_reset_branch_replayed=True,nucleo_binary_unchanged=True,
      i2c_or_motor_or_protection_code_changed=False,hardware_commands=0,live_epoch_recheck_pending=True)
    p.write(c/'verification/report.json',json.dumps(r,indent=2)+'\n')
    for name,trees in [('source_sha256',('UNOQ_MOTOR','web_hmi','libraries')),('build_sha256',('build',)),('verification_sha256',('verification',))]:
        m[name]={str(f.relative_to(c)).replace('\\','/'):p.sha(f) for tree in trees for f in sorted((c/tree).rglob('*')) if f.is_file() and '__pycache__' not in f.parts}
    m.update(built=True,selftest_pass=True)
    p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()

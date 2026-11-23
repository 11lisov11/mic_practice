"""Seal tested Uno-only RPC candidate without hardware access."""
import json
import prepare_rpc_coldboot_fix as p
import sys
if '--boot-retry' in sys.argv:import prepare_rpc_boot_retry as p
def main():
    c=p.OUT;m=json.loads(p.util.read(c/'manifest.json'));assert not m['installed']
    assert json.loads(p.util.read(c/'verification/report.json'))['passed']
    m.update(built=True,selftest_pass=True,autonomous_coldboot_rpc_verified=False)
    for name,trees in [('source_sha256',('UNOQ_MOTOR','web_hmi','libraries')),('build_sha256',('build',)),('verification_sha256',('verification',))]:
        m[name]={str(f.relative_to(c)).replace('\\','/'):p.util.sha(f) for tree in trees for f in sorted((c/tree).rglob('*')) if f.is_file() and '__pycache__' not in f.parts}
    p.util.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(sealed=True,pair=p.NEW)))
if __name__=='__main__':main()

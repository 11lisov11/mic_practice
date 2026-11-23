"""Seal1609 without touching native1606 or recorded captures."""
import json,shutil
import prepare_rpc_short_lock as p
def main():
    assert not (p.OUT/'source_hashes.json').exists()
    assert json.loads(p.read(p.OUT/'verification/report.json'))['passed']
    assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
    history=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
    for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
    sources={f.relative_to(p.OUT).as_posix():p.sha(f) for name in ('UNOQ_MOTOR','web_hmi','libraries') for f in (p.OUT/name).rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    changed=[rel for rel in sources if (p.BASE/rel).exists() and p.sha(p.BASE/rel)!=sources[rel]]
    assert set(changed)=={'libraries/Arduino_RouterBridge/src/bridge.h','UNOQ_MOTOR/UNOQ_MOTOR.ino','web_hmi/server.py'}
    (p.OUT/'release').mkdir()
    image=p.OUT/'release/uno_2026111609_rpc_route_recovery.elf-zsk.bin'
    shutil.copy2(p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',image)
    p.write(p.OUT/'source_hashes.json',json.dumps(sources,indent=2)+'\n')
    m=json.loads(p.read(p.OUT/'manifest.json'));m.update(built=True,host_tests_passed=True,
        artifacts={image.relative_to(p.OUT).as_posix():p.sha(image)},preserved_files_verified=len(history),
        qualification='PC-tested updater starvation fix; firmware not installed yet. Serial failure trigger unresolved.')
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(built=True,pair=p.NEW,preserved=len(history))))
if __name__=='__main__':main()

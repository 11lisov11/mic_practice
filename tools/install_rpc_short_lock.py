"""Uno1609 only, same stopped PC bench; checked installer performs no Nucleo reset/flash."""
import json
from types import SimpleNamespace
import prepare_rpc_short_lock as p
import install_rpc_route_recovery as previous

def package_check():
    m=json.loads(p.read(p.OUT/'manifest.json'))
    assert m['built'] and m['host_tests_passed'] and not m['installed']
    assert m['pair']==list(p.NEW) and m['uno_only'] and not m['thresholds_changed']
    assert json.loads(p.read(p.OUT/'verification/report.json'))['passed']
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
    for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
    for rel,h in json.loads(p.read(p.OUT/'preserved_all_hashes.json')).items():assert p.sha(p.ROOT/rel)==h,rel
    return m

install=previous.install
install.p=SimpleNamespace(ROOT=p.ROOT,OUT=p.OUT,BASE=p.ROOT/'artifacts/live_bench_20261116/clear_recovery_r1',
    NEW=p.NEW,read=p.read,write=p.write,sha=p.sha)
install.OLD=(2026111607,2026111606);install.NEW=p.NEW;install.package_check=package_check
if __name__=='__main__':raise SystemExit(install.main())

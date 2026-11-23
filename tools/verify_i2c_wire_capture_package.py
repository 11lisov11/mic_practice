"""Read-only pre-install verification for2811/2812. No device/network access."""
import json
import prepare_i2c_wire_capture as p

def main():
    m=json.loads(p.read(p.OUT/'manifest.json'))
    assert m['built'] and m['selftest_pass'] and m['pair_compatibility_ids']==list(p.NEW)
    counts={}
    for table in ('source_sha256','build_sha256','verification_sha256'):
        for rel,digest in m[table].items():assert p.sha(p.OUT/rel)==digest,rel
        counts[table]=len(m[table])
    for path,digest in json.loads(p.read(p.OUT/'verification/tool_sources.json')).items():
        from pathlib import Path
        assert p.sha(Path(path))==digest,path
    for rel,digest in json.loads(p.read(p.OUT/'preserved_records/reference_sha256.json')).items():
        assert p.sha(p.ROOT/rel)==digest,rel
    assert json.loads(p.read(p.OUT/'verification/report.json'))['passed']
    old=json.loads(p.read(p.BASE/'manifest.json'))
    for table in ('source_sha256','build_sha256','verification_sha256'):
        for rel,digest in old[table].items():assert p.sha(p.BASE/rel)==digest,rel
    print(json.dumps(dict(passed=True,pair=p.NEW,counts=counts,hardware_commands=0,installed=m['installed'])))
if __name__=='__main__':main()

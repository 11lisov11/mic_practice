"""Seal the tested Uno-only route repair; preserve native image and historical records."""
import ast,json,shutil
import prepare_rpc_route_recovery as p

def main():
    out=p.OUT;manifest=json.loads(p.read(out/'manifest.json'))
    assert not (out/'source_hashes.json').exists()
    tests=json.loads(p.read(out/'verification_router053/report.json'));assert tests['passed']
    assert json.loads(p.read(out/'build/uno_router053/llext-check.json'))['pass']
    build=json.loads(p.read(out/'build/uno_router053/unoq_mcsdk_scalar.build-manifest.json'))
    assert build['firmware_build_id']==p.NEW[0]
    sources={f.relative_to(out).as_posix():p.sha(f) for name in ('UNOQ_MOTOR','libraries','web_hmi')
        for f in (out/name).rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    changed=[]
    for rel in sources:
        if (p.BASE/rel).exists() and p.sha(out/rel)!=p.sha(p.BASE/rel):changed.append(rel)
    assert set(changed)=={'UNOQ_MOTOR/UNOQ_MOTOR.ino','libraries/Arduino_RouterBridge/src/bridge.h',
        'libraries/Arduino_RPClite/src/server.h','web_hmi/server.py'},changed
    history=json.loads(p.read(out/'preserved_hashes.json'))
    history.update(json.loads(p.read(p.BASE/'preserved_capture_hashes.json')))
    for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
    p.write(out/'preserved_all_hashes.json',json.dumps(history,indent=2)+'\n')
    # No FOC/NIS/ADC/current/CPU protection source is touched by this candidate.
    native=p.BASE/'release/nucleo_2026111606_clear_recovery.hex'
    expected=p.BASE/'release/nucleo_2026111606_expected_readback.bin'
    release=out/'release';release.mkdir(exist_ok=False)
    image=release/'uno_2026111607_rpc_route_recovery.elf-zsk.bin'
    shutil.copy2(out/'build/uno_router053/UNOQ_MOTOR.ino.elf-zsk.bin',image)
    p.write(out/'source_hashes.json',json.dumps(sources,indent=2)+'\n')
    manifest.update(built=True,host_tests_passed=True,installed=False,tests='verification_router053/report.json',
        superseded_tests='verification/report.json uses newer router duplicate semantics; not sufficient for installed0.5.3',
        native_hex_sha256=p.sha(native),native_expected_sha256=p.sha(expected),
        artifacts={image.relative_to(out).as_posix():p.sha(image)},preserved_files_verified=len(history),
        rpc_actual_router_version='0.5.3',route_exists_is_not_registration_proof=True,
        offline_limits_unchanged=dict(OFF_fast_cycles=4000,estimate_ms=2,trip_A=1.35,ADC_ticks=2048),
        qualification='Host library/decoder tests and Uno build only. Initial RPC outage and FOC RUN remain unresolved.')
    p.write(out/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(built=True,pair=p.NEW,preserved=len(history),START=0,CLEAR=0,flash=0)))

if __name__=='__main__':main()

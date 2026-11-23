"""Install tested Uno route fix on the already confirmed PC/J1-OFF bench; no motor commands."""
import ast,inspect,json
import prepare_rpc_route_recovery as p
import install_clear_recovery as install

OLD=(2026111605,2026111606)

def package_check():
    m=json.loads(p.read(p.OUT/'manifest.json'))
    assert m['built'] and m['host_tests_passed'] and not m['installed']
    assert m['pair']==list(p.NEW) and m['uno_only'] and m['nucleo_image_unchanged']
    for key in ('thresholds_changed','controller_equations_changed'):assert m[key] is False
    assert json.loads(p.read(p.OUT/'verification_router053/report.json'))['passed']
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
    for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
    for rel,h in json.loads(p.read(p.OUT/'preserved_all_hashes.json')).items():assert p.sha(p.ROOT/rel)==h,rel
    assert p.sha(p.BASE/'release/nucleo_2026111606_expected_readback.bin')==m['native_expected_sha256']
    return m

# Reuse exact checked RAM backup, safe-state/calibration/HMI atomic installer,
# Arduino upload+OpenOCD readback recipes and passive native register checks.
# Remove the ONLY native flash block; Nucleo reset/flash remain forbidden.
source=inspect.getsource(install.main)
a=source.index("  r['nucleo_flash_commands']=1;save()")
b=source.index('  def route(action):',a)
source=source[:a]+"  r['nucleo_flash_commands']=0;save()\n"+source[b:]
source=source.replace("p.OUT/f'release/uno_{NEW[0]}_clear_recovery.elf-zsk.bin'", "p.OUT/f'release/uno_{NEW[0]}_rpc_route_recovery.elf-zsk.bin'")
source=source.replace("expected=p.OUT/f'release/nucleo_{NEW[1]}_expected_readback.bin'", "expected=p.BASE/f'release/nucleo_{NEW[1]}_expected_readback.bin'")
# Past immutable records may be present: the installer must not demand erasure.
source=source.replace("    assert after.get('observer_trace')==dict(available=False,reason='not_received'),'observer recorder not empty'\n",'')
assert "mode=UR" not in source and "flash_verify_nucleo" not in source
assert "r['nucleo_flash_commands']=1" not in source
install.p=p;install.OLD=OLD;install.NEW=p.NEW;install.package_check=package_check
exec(compile(source,__file__,'exec'),install.__dict__)

if __name__=='__main__':raise SystemExit(install.main())

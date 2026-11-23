import importlib.util,json,subprocess,sys
from pathlib import Path
import install_unoq_bus_display as install
import prepare_i2c_wire_epoch_fix as p
install.ROOT,install.C,install.OLD,install.NEW=p.ROOT,p.OUT,p.OLD,p.NEW
install.GUARD=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
 '((2026101805,2026101804),(2026101807,2026101806))','((2026102811,2026102812),(2026102813,2026102812))')
exec(install.GUARD,install.__dict__)
def verify_package():
    m=json.loads(p.read(p.OUT/'manifest.json'));assert m['schema']=='mic_ai.i2c_wire_epoch_fix.v1' and m['pair_compatibility_ids']==list(p.NEW)
    assert m['built'] and m['selftest_pass'] and not m['installed'] and m['nucleo_firmware_unchanged']
    for key in ('calibration_changed','uart_changed','motor_control_changed','thresholds_changed','rpc_libraries_changed'):assert m[key] is False
    for table in ('source_sha256','build_sha256','verification_sha256'):
        for rel,d in m[table].items():assert p.sha(p.OUT/rel)==d,rel
    for rel,d in json.loads(p.read(p.OUT/'archive_references.json')).items():assert p.sha(p.ROOT/rel)==d
    assert json.loads(p.read(p.OUT/'verification/report.json'))['passed']
    b=json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'));assert b['firmware_build_id']==p.NEW[0]
    for item in b['artifacts']:assert p.sha(p.OUT/'build/uno'/item['file'])==item['sha256'].lower()
    return p.OUT/'build/uno'/b['flash_artifact']
install.verify_package=verify_package
def main():
    if '--verify-package-only' in sys.argv:return install.main()
    if '--confirm-j1-off-meter-below-20v-uno-usb' in sys.argv and '--outdir' in sys.argv:
        verify_package();adb=['adb','-s',install.io.UNO_SERIAL]
        assert subprocess.check_output(adb+['get-state'],text=True).strip()=='device'
        subprocess.run(adb+['forward','tcp:18080','tcp:8080'],check=True,capture_output=True)
        install.io.URL='http://127.0.0.1:18080'
        spec=importlib.util.spec_from_file_location('preserve_live',p.ROOT/'tools/pe_release_capture/preserve_live.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        original=mod.complete
        mod.complete=lambda s:original(s) and s.get('enc_release_decode_valid')==1 and s.get('enc_bus_clear_decode_valid')==1
        out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
        def guard(s):
            if (s.get('fw_build'),s.get('mc_fw_build'))!=p.OLD:return False,'Wrong installed pair'
            return install.precheck(s)
        mod.preserve(install.io.live_status,guard,out.with_name(out.name+'_preserved_live'))
    return install.main()
if __name__=='__main__':raise SystemExit(main())

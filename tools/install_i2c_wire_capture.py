"""Install sealed2811/2812 on the confirmed discharged USB bench. No START/CLEAR."""
import importlib.util,json,subprocess,sys
from pathlib import Path
import install_current_shunt_monitor as install
import prepare_i2c_wire_capture as p

install.ROOT,install.C,install.OLD,install.NEW=p.ROOT,p.OUT,p.OLD,p.NEW
install.GUARD=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026102709,2026102710),(2026102811,2026102812))')
exec(install.GUARD,install.__dict__)

def verify_package():
    import verify_i2c_wire_capture_package as verify
    # Read-only verifier checks every sealed source, test, build and archive.
    verify.main()
    m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
    for key in ('motor_control_changed','i2c_recovery_changed','i2c_timing_filters_changed','thresholds_changed','calibration_changed','rpc_libraries_changed'):
        assert m[key] is False,key
    images=[]
    for folder,name,fw in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
        b=json.loads(p.read(p.OUT/'build'/folder/(name+'.build-manifest.json')))
        assert b['firmware_build_id']==fw
        for item in b['artifacts']:assert p.sha(p.OUT/'build'/folder/item['file'])==item['sha256'].lower()
        images.append(p.OUT/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
    return tuple(images)
install.verify_package=verify_package

def main():
    if '--verify-package-only' in sys.argv:return install.main()
    if '--confirm-j1-off-meter-below-20v-both-usb' in sys.argv and '--outdir' in sys.argv:
        verify_package();adb=['adb','-s',install.io.UNO_SERIAL]
        assert subprocess.check_output(adb+['get-state'],text=True).strip()=='device'
        subprocess.run(adb+['forward','tcp:18080','tcp:8080'],check=True,capture_output=True)
        install.io.URL='http://127.0.0.1:18080'
        spec=importlib.util.spec_from_file_location('preserve_live',p.ROOT/'tools/pe_release_capture/preserve_live.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        complete=module.complete
        def full(s):
            if not complete(s) or s.get('enc_release_decode_valid')!=1 or s.get('enc_bus_clear_decode_valid')!=1:return False
            if s.get('enc_fault_first_hex','-')!='-' and s.get('enc_release_first_hex','-')=='-':return False
            if s.get('enc_bus_clear_hex','-')!='-' and not s.get('enc_bus_clear_record'):return False
            return True
        module.complete=full
        out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
        def guard(s):
            if (s.get('fw_build'),s.get('mc_fw_build'))!=p.OLD:return False,'Unexpected installed pair'
            return install.precheck(s)
        archive=out.with_name(out.name+'_preserved_live')
        module.preserve(install.io.live_status,guard,archive)
        samples=[json.loads(line) for line in p.read(archive/'samples.jsonl').splitlines()]
        for key in ('mc_bad_cnt','bp_bad_cnt','mc_uart_error_flags','mc_last_uart_error_flags','uno_rx_hw_errors',
                    'enc_fault_first_hex','enc_fault_pwm_hex','enc_release_first_hex','enc_release_pwm_hex','enc_bus_clear_hex'):
            assert len({s.get(key) for s in samples[-3:]})==1,'Changing diagnostic evidence: '+key
    # No automatic router-port close/open or controller CLEAR fallback.
    return install.main()
if __name__=='__main__':raise SystemExit(main())

"""Seal the UNO-only matrix correction, checking unchanged control/capture code."""
import ast
import importlib.util
import json
import subprocess
import sys
import prepare_unoq_display_order_r2 as p
import prepare_current_shunt_monitor as util
from current_peak_capture.display_orientation import NEW as PREVIOUS_MAPPING


def main():
    c=p.OUT
    m=json.loads(util.read(c/'manifest.json'))
    assert not m['built'] and not m['installed']
    out=c/'verification';out.mkdir(exist_ok=False)
    display=json.loads(util.read(c/'display_selftest_r1/report.json'))
    assert display['passed'] and display['mutations_detected']['reported_bad_y_only_mapping']
    old=util.read(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    new=util.read(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    assert new.replace('FW_BUILD_ID = 2026102503U;','FW_BUILD_ID = 2026102501U;').replace(p.MAPPING,PREVIOUS_MAPPING)==old
    for f in (p.BASE/'UNOQ_MOTOR').rglob('*'):
        if f.is_file() and f.name!='UNOQ_MOTOR.ino':
            assert f.read_bytes()==(c/f.relative_to(p.BASE)).read_bytes(),str(f)
    previous=json.loads(util.read(p.BASE/'manifest.json'))
    for rel,digest in previous['source_sha256'].items():
        assert util.sha(p.BASE/rel)==digest, 'Installed source altered: '+rel
    assert (c/'web_hmi/static/app.js').read_bytes()==(p.BASE/'web_hmi/static/app.js').read_bytes()
    ast.parse(util.read(c/'web_hmi/server.py'))
    spec=importlib.util.spec_from_file_location('matrix_order_hmi',c/'web_hmi/server.py')
    h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
    live=json.loads(util.read(p.BASE/'wifi_after_b2_reset_r1/status.jsonl').splitlines()[-1])['status']
    # Existing zero-failure diagnostics must remain visible for both identities.
    for uno in (p.OLD[0],p.NEW[0]):
        decoded=h.with_shunt_currents(dict(live,fw_build=uno))
        assert decoded['mc_current_zero_attempts']==8 and decoded['mc_current_zero_stable']==1
        assert decoded['mc_current_zero_ready']==0
        assert h.manual_scalar_supported(dict(live,fw_build=uno,manual_scalar_capable=1))
        blob=(p.BASE/'peak_selftest_r4/trace.bin').read_bytes().hex()
        peak=h.with_adc_peak(dict(live,fw_build=uno,mc_adc_peak_hex=blob))
        assert peak['mc_adc_peak_valid']==1 and peak['mc_adc_peak']['peak_seen']
    assert h.with_shunt_currents(dict(live,fw_build=0))['mc_current_zero_attempts'] is None
    assert not h.manual_scalar_supported(dict(live,fw_build=0,manual_scalar_capable=1))
    stored=dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(stored,dict(stored,fw_build=p.NEW[0]))
    assert not h._vbus_calibration_identity_matches(stored,dict(stored,fw_build=0))
    ui=subprocess.run(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],
                      capture_output=True,text=True,check=True,timeout=20)
    ui_report=json.loads(ui.stdout);assert ui_report['passed']
    util.write(out/'frontend.json',json.dumps(ui_report,indent=2)+'\n')
    build=json.loads(util.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    assert build['firmware_build_id']==p.NEW[0]
    for item in build['artifacts']:
        assert util.sha(c/'build/uno'/item['file'])==item['sha256'].lower()
    assert json.loads(util.read(c/'build/uno/llext-check.json'))['pass']
    report=dict(passed=True,hardware_commands=0,uno_only=True,nucleo_flash_required=False,
        display_checks=display['checks'],old_mapping_negative_control=True,
        motor_control_and_uart_and_peak_acquisition_unchanged=True,
        old_and_new_identity_telemetry_decoders_verified=True,unknown_identity_rejected=True,
        zero_failure_still_reported=True,existing_calibration_accepted=True,
        frontend_checks=ui_report['checks'],physical_display_verified=False,
        limitation='Display model inferred from user feedback; actual10V digit order requires visual confirmation after flashing.')
    util.write(out/'report.json',json.dumps(report,indent=2)+'\n')
    def hashes(paths):
        return {str(f.relative_to(c)).replace('\\','/'):util.sha(f) for f in sorted(paths) if f.is_file()}
    m.update(built=True,selftest_pass=True,verification_summary=report)
    m['source_sha256']=hashes(f for name in ('UNOQ_MOTOR','web_hmi') for f in (c/name).rglob('*')
        if '__pycache__' not in f.parts)
    m['build_sha256']=hashes((c/'build').rglob('*'))
    m['verification_sha256']=hashes(f for name in ('display_selftest_r1','verification') for f in (c/name).rglob('*'))
    util.write(c/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':
    main()

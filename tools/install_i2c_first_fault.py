"""Install diagnostic pair only after discharged USB programming-state confirmation."""
import json
import install_current_shunt_monitor as install
import prepare_i2c_first_fault as package

install.ROOT,install.C,install.OLD,install.NEW=package.ROOT,package.OUT,package.OLD,package.NEW
install.GUARD=(package.ROOT/'tools/uart_resync_fix/update_guard.py').read_text().replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026102603,2026102602),(2026102605,2026102604))')
assert '2026102605' in install.GUARD
exec(install.GUARD,install.__dict__)

def verify_package():
    c=package.OUT;m=json.loads(package.read(c/'manifest.json'))
    assert m['schema']=='mic_ai.i2c_first_fault.v1' and m['pair_compatibility_ids']==list(package.NEW)
    assert m['built'] and m['selftest_pass'] and m['capture_before_reset']
    assert m['capture_delivery_outputs_off_only'] and m['capture_slots']==2
    for key in ('sensor_feedback_control','motor_control_changed','calibration_changed','thresholds_changed',
                'uart_command_protocol_changed','bkin_changed','adc_trigger_changed','pwm_ccr123_changed',
                'deadtime_changed','watchdogs_changed','i2c_recovery_policy_changed'):
        assert m[key] is False,key
    for table in ('source_sha256','build_sha256','verification_sha256'):
        assert m[table]
        for rel,digest in m[table].items():assert install.io.sha(c/rel)==digest,rel
    images=[]
    for folder,name,build in [('uno','unoq_mcsdk_scalar',package.NEW[0]),
                              ('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',package.NEW[1])]:
        b=json.loads(package.read(c/'build'/folder/(name+'.build-manifest.json')))
        assert b['firmware_build_id']==build
        for item in b['artifacts']:assert install.io.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
        images.append(c/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
    assert json.loads(package.read(c/'verification/report.json'))['passed']
    assert json.loads(package.read(c/'build/uno/llext-check.json'))['pass']
    return tuple(images)

install.verify_package=verify_package
if __name__=='__main__':raise SystemExit(install.main())

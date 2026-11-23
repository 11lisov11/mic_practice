"""Install checked Nucleo sensor pair after the confirmed discharged USB state."""
import json
import install_current_shunt_monitor as install
import prepare_nucleo_as5600 as package

install.ROOT=package.ROOT;install.C=package.OUT;install.OLD=package.OLD;install.NEW=package.NEW
install.GUARD=(package.ROOT/'tools/uart_resync_fix/update_guard.py').read_text().replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026102518,2026102510),(2026102601,2026102602))')
exec(install.GUARD,install.__dict__)

def verify_package():
    c=package.OUT;m=json.loads((c/'manifest.json').read_text())
    assert m['schema']=='mic_ai.nucleo_as5600.v1' and m['pair_compatibility_ids']==list(package.NEW)
    assert m['built'] and m['selftest_pass'] and m['sensor_source']=='nucleo_g431_i2c1'
    for key in ('sensor_feedback_control','calibration_changed','thresholds_changed','watchdogs_changed',
                'bkin_changed','pwm_ccr123_changed','deadtime_changed','adc_trigger_changed','uart_command_protocol_changed'):
        assert m[key] is False,key
    for table in ('source_sha256','build_sha256','verification_sha256'):
        assert m[table]
        for rel,digest in m[table].items():assert install.io.sha(c/rel)==digest,rel
    images=[]
    for folder,name,build in [('uno','unoq_mcsdk_scalar',package.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',package.NEW[1])]:
        b=json.loads((c/'build'/folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        assert b['firmware_build_id']==build
        for item in b['artifacts']:assert install.io.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
        images.append(c/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
    return tuple(images)

install.verify_package=verify_package
if __name__=='__main__':raise SystemExit(install.main())

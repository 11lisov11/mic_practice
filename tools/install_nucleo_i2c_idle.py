"""Both-image update, only after confirmed J1OFF/DMM<20V/bothUSB; no motor commands."""
import json
from pathlib import Path
import subprocess
import sys
import time
import install_current_shunt_monitor as install
import prepare_nucleo_i2c_idle as p

install.ROOT,install.C,install.OLD,install.NEW=p.ROOT,p.OUT,p.OLD,p.NEW
install.GUARD=(p.ROOT/'tools/uart_resync_fix/update_guard.py').read_text().replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026102609,2026102604),(2026102701,2026102702))')
exec(install.GUARD,install.__dict__)

def verify_package():
    c=p.OUT;m=json.loads(p.read(c/'manifest.json'))
    assert m['schema']=='mic_ai.nucleo_i2c_idle.v1' and m['pair_compatibility_ids']==list(p.NEW)
    assert m['built'] and m['selftest_pass'] and m['capture_before_reset'] and m['capture_delivery_outputs_off_only']
    assert m['i2c_recovery_policy_changed'] and m['encoder_wire_format']==2
    for k in ('sensor_feedback_control','motor_control_changed','thresholds_changed','calibration_changed',
              'uart_command_protocol_changed','bkin_changed','adc_trigger_changed','pwm_ccr123_changed','deadtime_changed','watchdogs_changed'):
        assert m[k] is False,k
    for table in ('source_sha256','build_sha256','verification_sha256'):
        assert m[table]
        for rel,digest in m[table].items():assert install.io.sha(c/rel)==digest,rel
    images=[]
    for folder,name,build in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
        b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==build
        if folder=='nucleo':assert b['build_errors']==b['build_warnings']==0
        for item in b['artifacts']:assert install.io.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
        images.append(c/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
    b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    for rel,digest in b['library_override_sha256'].items():assert p.sha(c/'libraries'/rel)==digest.lower()
    assert json.loads(p.read(c/'verification/report.json'))['passed']
    assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
    return tuple(images)
install.verify_package=verify_package

def main():
    result=install.main()
    if '--verify-package-only' in sys.argv or result==0:return result
    # One scoped post-flash transport recovery only after both readbacks and
    # calibration verification, in the already confirmed deenergized state.
    if '--confirm-j1-off-meter-below-20v-both-usb' not in sys.argv:return result
    if '--outdir' not in sys.argv:return result
    out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
    r=json.loads(p.read(out/'report.json'))
    if not (r.get('uno_readback_verified') and r.get('nucleo_readback_verified') and r.get('calibration_unchanged')
            and r.get('error','').startswith('Runtime verification pending:')):return result
    cmd=[sys.executable,str(p.ROOT/'tools/reopen_unoq_router_serial.py'),
        '--confirm-j1-off-meter-below-20v-uno-usb','--log',str(out/'serial_reopen.log')]
    recovered=dict(passed=False,initial_report_retained=True,serial_reopen_attempts=1,motor_commands=0,
        clear_commands=0,additional_flash_commands=0,mcu_reset_commands=0)
    try:
        subprocess.run(cmd,check=True,timeout=25,capture_output=True,text=True)
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            try:
                s=install.io.live_status();okay,reason=install.precheck(s)
                assert okay,reason
                assert (s['fw_build'],s['mc_fw_build'])==p.NEW
                recovered.update(passed=True,status=s);break
            except Exception as exc:recovered['last_error']=str(exc);time.sleep(1)
    except Exception as exc:recovered['error']=str(exc)
    p.write(out/'post_flash_recovery.json',json.dumps(recovered,indent=2)+'\n')
    print(json.dumps({k:recovered.get(k) for k in ('passed','serial_reopen_attempts','additional_flash_commands','mcu_reset_commands','error','last_error')}))
    return 0 if recovered['passed'] else result
if __name__=='__main__':raise SystemExit(main())

"""Install sealed shunt monitoring on both USB controllers, J1 off, meter <=20V."""
import argparse
import json
import math
from pathlib import Path
import shlex
import subprocess
import time
import uuid

import prepare_current_shunt_monitor as package
import install_bkin_boot_armed_pair as io
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base, scp_base

ROOT, C, OLD, NEW = package.ROOT, package.OUT, package.OLD, package.NEW
GUARD=(ROOT/'tools/uart_resync_fix/update_guard.py').read_text(encoding='utf-8').replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026102403,2026102402),(2026102405,2026102406))')
exec(GUARD)


def remote_installer():
    s=(ROOT/'tools/install_vbus_hmi_fix_remote.py').read_text(encoding='utf-8-sig')
    a=s.index('def precheck(');b=s.index('\n\ndef status():',a)
    s=s[:a]+GUARD+s[b:]
    return s.replace('choices=(2, 10), default=2','choices=(20,), default=20').replace('args.max_vdc == 10','args.max_vdc == 20')


def verify_package():
    m=json.loads((C/'manifest.json').read_text(encoding='utf-8'))
    assert m['schema']=='mic_ai.current_shunt_monitor.v1' and m['pair_compatibility_ids']==list(NEW)
    assert m['built'] and m['selftest_pass'] and m['control_mode']=='MAIN_VF_OL'
    assert all(m[k] is False for k in ('calibration_changed','watchdogs_changed','bkin_changed',
               'uart_command_protocol_changed','pwm_ccr123_changed','deadtime_changed','foc_enabled'))
    assert m['current_scale_qualified'] is False
    for table in ('source_sha256','build_sha256','verification_sha256'):
        assert m[table]
        for rel,digest in m[table].items():assert io.sha(C/rel)==digest,rel
    images=[]
    for folder,name,build in [('uno','unoq_mcsdk_scalar',NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',NEW[1])]:
        b=json.loads((C/'build'/folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        assert b['firmware_build_id']==build
        if folder=='nucleo':assert b['build_errors']==0 and b['build_warnings']==0
        for item in b['artifacts']:assert io.sha(C/'build'/folder/item['file'])==item['sha256'].lower()
        images.append(C/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
    return tuple(images)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify-package-only',action='store_true')
    p.add_argument('--confirm-j1-off-meter-below-20v-both-usb',action='store_true')
    p.add_argument('--outdir',type=Path)
    args=p.parse_args();image,nucleo=verify_package()
    if args.verify_package_only:
        print(json.dumps(dict(passed=True,hardware_commands=0,uno_sha256=io.sha(image),nucleo_sha256=io.sha(nucleo))));return 0
    if not args.confirm_j1_off_meter_below_20v_both_usb:
        p.error('J1 off, independent meter <=20V and both USB controllers required; 15V may remain on')
    if args.outdir is None:p.error('--outdir required for installation')
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(passed=False,uno_flash_commands=0,nucleo_flash_commands=0,motor_commands=0,clear_commands=0,
           physical_programming_state_operator_confirmed=True)
    def run(cmd,label,timeout=240):return io.run(cmd,label,out,r,timeout)
    def safe(pair):
        s=io.live_status();okay,reason=precheck(s)
        assert okay,reason
        assert (s['fw_build'],s['mc_fw_build'])==pair,'Unexpected live pair'
        return s
    try:
        adb=['adb','-s',io.UNO_SERIAL]
        assert subprocess.check_output(adb+['get-state'],text=True).strip()=='device'
        for local,remote in ((18080,8080),(12222,2222)):
            subprocess.run(adb+['forward',f'tcp:{local}',f'tcp:{remote}'],capture_output=True,check=True)
        io.URL='http://127.0.0.1:18080';io.ssh_base=tunneled(ssh_base)
        r['before']=safe(OLD);r['calibration_before']=io.calibration_hash(out,r)
        uno_port,nucleo_port=io.board_ports()
        ssh=io.ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        scp=tunneled(scp_base)('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        installer=out/'remote_hmi_installer.py';installer.write_text(remote_installer(),encoding='utf-8')
        prefix='/tmp/mic_current_'+uuid.uuid4().hex
        files=[(C/'web_hmi/server.py',prefix+'_server.py'),(C/'web_hmi/static/app.js',prefix+'_app.js'),(installer,prefix+'_installer.py')]
        for local,remote in files:run(scp+[str(local),'arduino@192.168.1.138:'+remote],'stage_'+local.name,40)
        command=['python3',files[2][1],'--candidate',files[0][1],'--sha256',io.sha(files[0][0]),
                 '--app-js',files[1][1],'--app-js-sha256',io.sha(files[1][0]),'--max-vdc','20','--confirm-mains-off']
        run(ssh+[shlex.join(command+['--check-only'])],'hmi_precheck',45)
        safe(OLD);run(ssh+[shlex.join(command)],'install_hmi',60);r['hmi_installed']=True
        r['before_flash']=safe(OLD)
        r['nucleo_flash_commands']=1
        run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','sn='+io.STLINK_SERIAL,'-w',str(nucleo),'-v','-rst'],'flash_verify_nucleo')
        r['nucleo_readback_verified']=True
        upload=['arduino-cli','upload','-p',uno_port,'-b','arduino:zephyr:unoq','-i',str(image),
                '--upload-property','upload.artifacts.sketch='+str(image),
                '--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL]
        r['uno_flash_commands']=1;run(upload,'flash_uno')
        run(upload+['--upload-property','build.variant.path='+str(ROOT/'tools'),
                    '--upload-property','openocd_cfg=verify_restart_unoq_sketch.cfg'],'verify_uno')
        assert 'UNO Q verification PASSED; restarting unchanged images' in (out/'verify_uno.log').read_text()
        r['uno_readback_verified']=True
        # Preserve the vendor loader's boot-release sequence in the verifier.
        # An additional bare reset here is unnecessary and can prevent startup.
        r['calibration_after']=io.calibration_hash(out,r)
        assert r['calibration_before']==r['calibration_after'],'Calibration changed'
        r['calibration_unchanged']=True
        deadline=time.monotonic()+60;last=''
        while time.monotonic()<deadline:
            try:r['after']=safe(NEW);r['passed']=True;break
            except Exception as exc:last=str(exc);time.sleep(1)
        if not r['passed']:raise RuntimeError('Runtime verification pending: '+last)
    except Exception as exc:r['error']=str(exc)
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('passed','uno_flash_commands','nucleo_flash_commands','uno_readback_verified','calibration_unchanged','error')}))
    return 0 if r['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

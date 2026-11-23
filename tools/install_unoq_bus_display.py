"""Uno-only display update; MCU programming requires J1 off and meter <=20V."""
import argparse
import json
import math
from pathlib import Path
import shlex
import subprocess
import time
import uuid

import prepare_unoq_bus_display as package
import install_bkin_boot_armed_pair as io
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base, scp_base

ROOT, C, OLD, NEW = package.ROOT, package.OUT, package.OLD, package.NEW
GUARD=(ROOT/'tools/uart_resync_fix/update_guard.py').read_text(encoding='utf-8').replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026102401,2026102402),(2026102403,2026102402))')
exec(GUARD)


def remote_installer():
    s=(ROOT/'tools/install_vbus_hmi_fix_remote.py').read_text(encoding='utf-8-sig')
    a=s.index('def precheck(');b=s.index('\n\ndef status():',a)
    s=s[:a]+GUARD+s[b:]
    return s.replace('choices=(2, 10), default=2','choices=(20,), default=20').replace('args.max_vdc == 10','args.max_vdc == 20')


def verify_package():
    m=json.loads((C/'manifest.json').read_text(encoding='utf-8'))
    assert m['schema']=='mic_ai.uno_bus_display.v1' and m['pair_compatibility_ids']==list(NEW)
    assert m['built'] and m['selftest_pass'] and m['uno_only'] and m['nucleo_firmware_unchanged']
    assert all(m[k] is False for k in ('calibration_changed','uart_changed','motor_control_changed'))
    for table in ('source_sha256','build_sha256','verification_sha256'):
        assert m[table]
        for rel,digest in m[table].items():assert io.sha(C/rel)==digest,rel
    b=json.loads((C/'build/uno/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    assert b['firmware_build_id']==NEW[0]
    image=C/'build/uno'/b['flash_artifact']
    for item in b['artifacts']:assert io.sha(C/'build/uno'/item['file'])==item['sha256'].lower()
    return image


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify-package-only',action='store_true')
    p.add_argument('--confirm-j1-off-meter-below-20v-uno-usb',action='store_true')
    p.add_argument('--outdir',type=Path)
    args=p.parse_args();image=verify_package()
    if args.verify_package_only:
        print(json.dumps(dict(passed=True,hardware_commands=0,uno_sha256=io.sha(image),nucleo_flash_commands=0)));return 0
    if not args.confirm_j1_off_meter_below_20v_uno_usb:
        p.error('J1 off, independent meter <=20V and Uno USB onPC required; no Nucleo USB needed')
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
        boards=json.loads(subprocess.check_output(['arduino-cli','board','list','--format','json'],text=True))
        ports=[e['port']['address'] for e in boards['detected_ports'] if e['port'].get('properties',{}).get('serialNumber')==io.UNO_SERIAL]
        assert len(ports)==1,'Expected unique Uno serial'
        ssh=io.ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        scp=tunneled(scp_base)('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        installer=out/'remote_hmi_installer.py';installer.write_text(remote_installer(),encoding='utf-8')
        prefix='/tmp/mic_display_'+uuid.uuid4().hex
        files=[(C/'web_hmi/server.py',prefix+'_server.py'),(installer,prefix+'_installer.py')]
        for local,remote in files:run(scp+[str(local),'arduino@192.168.1.138:'+remote],'stage_'+local.name,40)
        command=['python3',files[1][1],'--candidate',files[0][1],'--sha256',io.sha(files[0][0]),'--max-vdc','20','--confirm-mains-off']
        run(ssh+[shlex.join(command+['--check-only'])],'hmi_precheck',45)
        safe(OLD);run(ssh+[shlex.join(command)],'install_hmi',60);r['hmi_installed']=True
        r['before_flash']=safe(OLD)
        upload=['arduino-cli','upload','-p',ports[0],'-b','arduino:zephyr:unoq','-i',str(image),
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
        deadline=time.monotonic()+40;last=''
        while time.monotonic()<deadline:
            try:r['after']=safe(NEW);r['passed']=True;break
            except Exception as exc:last=str(exc);time.sleep(1)
        if not r['passed']:raise RuntimeError('Runtime verification pending: '+last)
    except Exception as exc:r['error']=str(exc)
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('passed','uno_flash_commands','nucleo_flash_commands','uno_readback_verified','calibration_unchanged','error')}))
    return 0 if r['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

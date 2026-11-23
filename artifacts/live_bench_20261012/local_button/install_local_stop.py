"""Install the pinned local-stop image/HMI on the operator-confirmed offline stand."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_ipm_break_wifi import source_hashes
from prepare_nucleo_local_stop import BASE, patched_main, guarded_pwm, PWM, R3
from prepare_unoq_local_stop_peer import BASE as UNO_BASE, sketch, diagnostics, wire
from prepare_trial_wait_fix import BASE as HMI_BASE, server
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL

HERE=Path(__file__).resolve().parent
PROJECT=HERE/'candidate_r5/nucleo'
HMI=HERE/'wait_candidate_r6/web_hmi/server.py'
UNO_SERIAL='3880458060'
OLD_IMAGE_SHA='27d7b1151ad69a0958043552ef53c840867edb1e0fd3ad145c2645f3922aa033'
NEW_IMAGE_SHA='f35dfb3c583b1e6f4822d62f3e7971f3a7cac0e3beed76565f273dbfa203e949'
HMI_SHA='5b9a25097b8d590db98ddcd37b121f30f573f4465fea67c512231a2f0dc40d15'
OLD_HMI_SHA='27bb632e1c8b6636f9d5531e7c1b541565751757f13631c4c5b080912e0e3875'
CAL_SHA='a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def package():
    m=json.loads((HERE/'candidate_r5/manifest.json').read_text())
    if source_hashes(BASE)!=m['baseline_sha256'] or source_hashes(PROJECT)!=m['candidate_sha256']:
        raise RuntimeError('Nucleo sources changed')
    for name, transform in (('Src/main.c',patched_main),(PWM,guarded_pwm),(R3,guarded_pwm)):
        if (PROJECT/name).read_text()!=transform((BASE/name).read_text()):
            raise RuntimeError('Candidate does not match recipe: '+name)
    if HMI.read_text()!=server(HMI_BASE.read_text()) or sha(HMI)!=HMI_SHA:
        raise RuntimeError('HMI changed after tests')
    for name in ('selftest_r5/report.json','hmi_guards_r5/report.json','peer_selftest_r2/report.json'):
        if json.loads((HERE/name).read_text()).get('pass') is not True:
            raise RuntimeError('Offline tests failed')
    folder=PROJECT/'STM32CubeIDE/Debug'
    build=json.loads(next(folder.glob('*.build-manifest.json')).read_text(encoding='utf-8-sig'))
    if build['firmware_build_id']!=2026101204 or build['build_errors']!=0 or build['build_exit_code']!=0:
        raise RuntimeError('Target build failed')
    for item in build['artifacts']:
        p=folder/item['file']
        if sha(p)!=item['sha256'].lower() or p.stat().st_size!=item['bytes']:
            raise RuntimeError('Built image changed')
    image=next(folder.glob('*.bin'))
    if sha(image)!=NEW_IMAGE_SHA:raise RuntimeError('Unexpected target image')
    uno=HERE/'uno_peer_r2/UNOQ_MOTOR'
    for name,transform in (('UNOQ_MOTOR.ino',sketch),('nucleo_fault_diagnostics.h',diagnostics),('break_wire.h',wire)):
        if (uno/name).read_text()!=transform((UNO_BASE/name).read_text()):raise RuntimeError('Uno source changed: '+name)
    um=json.loads((HERE/'uno_peer_r2/manifest.json').read_text())
    if source_hashes(uno)!=um['source_sha256']:raise RuntimeError('Uno peer source changed')
    if (uno/'break_wire.h').read_bytes()!=(PROJECT/'Inc/break_wire.h').read_bytes():raise RuntimeError('Snapshot peer header mismatch')
    uf=HERE/'uno_peer_r2/uno_build'
    ub=json.loads((uf/'unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    if ub['firmware_build_id']!=2026101205:raise RuntimeError('Unexpected Uno build')
    if json.loads((uf/'llext-check.json').read_text())['pass'] is not True:raise RuntimeError('Uno loader check failed')
    for item in ub['artifacts']:
        if sha(uf/item['file'])!=item['sha256'].lower():raise RuntimeError('Uno image changed')
    return image,uf/ub['flash_artifact']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-physical-offline',action='store_true')
    p.add_argument('--check-only',action='store_true')
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();image,uno_image=package()
    if a.check_only:
        print(json.dumps(dict(package_verified=True,hardware_commands=0)));return 0
    if not a.confirm_physical_offline:p.error('Require mains physically disconnected, J4 off and operator-measured bus <=2V')
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(pass_=False,operator_confirmed_physical_offline=True,start_commands=0,
                arm_commands=0,clear_commands=0,uno_firmware_changed=False,hv_release_approved=False,
                commands=[],image_sha256=NEW_IMAGE_SHA,hmi_sha256=HMI_SHA)
    def run(cmd,label,timeout=90):
        result=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        (out/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        report['commands'].append(dict(label=label,exit_code=result.returncode))
        if result.returncode:raise RuntimeError(label+' failed')
        return result.stdout
    adb=['adb','-s',UNO_SERIAL]
    try:
        boards=json.loads(run(['arduino-cli','board','list','--format','json'],'usb_inventory'))
        serials={x['port'].get('properties',{}).get('serialNumber') for x in boards['detected_ports']}
        if SERIAL not in serials or UNO_SERIAL not in serials:raise RuntimeError('Expected USB boards unavailable')
        before=run(adb+['shell','sha256sum /home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py /home/arduino/.config/mic-ai/vbus_calibration.json'],'remote_before').splitlines()
        if before[0].split()[0]!=OLD_HMI_SHA or before[1].split()[0]!=CAL_SHA:
            raise RuntimeError('Unexpected installed HMI/calibration')
        # Validate the currently installed firmware before modifying either MCU.
        old=out/'nucleo_before.bin'
        run([PROGRAMMER,'-c','port=SWD','mode=UR','sn='+SERIAL,'-u','0x08000000','44676',old,'-rst'],'nucleo_backup')
        report['old_image_sha256']=sha(old)
        if report['old_image_sha256']!=OLD_IMAGE_SHA:raise RuntimeError('Unexpected installed Nucleo image')
        run(adb+['shell','mkdir -p /home/arduino/.cache/mic-local-stop'],'remote_staging')
        remote='/home/arduino/.cache/mic-local-stop'
        run(adb+['push',HMI,remote+'/server.py'],'stage_hmi')
        run(adb+['push',ROOT/'tools/recover_unoq_hmi_router_remote.py',remote+'/recover.py'],'stage_recovery')
        remote_cmd='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python '+remote+'/recover.py --candidate '+remote+'/server.py --sha256 '+HMI_SHA+' --expected-live-sha256 '+OLD_HMI_SHA+' --confirm-mains-j4-off'
        recovery=json.loads(run(adb+['shell',remote_cmd],'install_hmi').strip().splitlines()[-1])
        report['hmi_install']=recovery
        if not recovery.get('installed') or not recovery.get('calibration_unchanged'):
            raise RuntimeError('HMI install verification failed')
        run([PROGRAMMER,'-c','port=SWD','mode=UR','sn='+SERIAL,'-w',image,'0x08000000','-v','-rst'],'flash_verify_nucleo')
        report['nucleo_programmer_verify_pass']=True
        after=out/'nucleo_after.bin'
        run([PROGRAMMER,'-c','port=SWD','mode=UR','sn='+SERIAL,'-u','0x08000000',str(image.stat().st_size),after,'-rst'],'nucleo_readback')
        report['nucleo_readback_sha256']=sha(after)
        report['nucleo_readback_matches']=sha(after)==NEW_IMAGE_SHA
        if not report['nucleo_readback_matches']:raise RuntimeError('Nucleo readback mismatch')
        report['uno_flash_attempted']=True
        report['uno_firmware_changed']=None
        run(['arduino-cli','upload','-p','COM10','-b','arduino:zephyr:unoq','-i',uno_image,
             '--upload-property','upload.artifacts.sketch='+str(uno_image),
             '--upload-property','upload.port.properties.serialNumber='+UNO_SERIAL,
             '--upload-property','build.variant.path='+str(ROOT/'tools'),
             '--upload-property','openocd_cfg=flash_verify_unoq_sketch.cfg'],'flash_verify_uno',180)
        report['uno_firmware_changed']=True
        report['uno_flash_verify_pass']=True
        report['uno_image_sha256']=sha(uno_image)
        after_remote=run(adb+['shell','sha256sum /home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py /home/arduino/.config/mic-ai/vbus_calibration.json'],'remote_after').splitlines()
        report['hmi_verified']=after_remote[0].split()[0]==HMI_SHA
        report['calibration_unchanged']=after_remote[1].split()[0]==CAL_SHA
        report['pass_']=report['hmi_verified'] and report['calibration_unchanged']
    except Exception as exc:
        report['error']=f'{type(exc).__name__}: {exc}'
    finally:
        report['pass']=report.pop('pass_')
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('pass','nucleo_programmer_verify_pass','nucleo_readback_matches','uno_flash_verify_pass','hmi_verified','calibration_unchanged','error')},indent=2))
    return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())

"""Install the reviewed 5-MHz diagnostic recorder; never issues START/CLEAR/ARM.

Requires physical J1/J4 off and DMM <=20 V before connecting either board to PC.
--verify-package-only is entirely offline and does not contact any device.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import math
import shlex
import subprocess
import time
import uuid

import install_bkin_boot_armed_pair as io
from unoq_wifi_hmi_deploy import ssh_base,scp_base

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'artifacts/live_bench_20261018/bkin_fast_capture_r1'
OLD=(2026101803,2026101802); NEW=(2026101805,2026101804)
exec((ROOT/'tools/bkin_fast_capture/update_guard.py').read_text(encoding='utf-8'))

def verify_package(candidate=C):
    m=json.loads((candidate/'manifest.json').read_text(encoding='utf-8'))
    if (m.get('schema')!='mic_ai.bkin_fast_capture_candidate.v1' or
        m.get('pair_compatibility_ids')!=list(NEW) or not m.get('built') or
        not m.get('selftest_pass') or m.get('host_cases',0)<450 or
        m.get('hv_release_approved') is not False): raise RuntimeError('unverified diagnostic package')
    for key in ('calibration_changed','control_protocol_changed','pwm_or_motor_control_changed'):
        if m.get(key) is not False: raise RuntimeError('unexpected change: '+key)
    for table in ('source_sha256','build_sha256'):
        if not m.get(table):raise RuntimeError('missing package hashes')
        for relative,expected in m[table].items():
            p=candidate/relative
            if io.sha(p)!=expected:raise RuntimeError('package changed: '+relative)
    for folder,name,build in [('uno','unoq_mcsdk_scalar',NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',NEW[1])]:
        b=json.loads((candidate/'build'/folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        if b['firmware_build_id']!=build:raise RuntimeError('image build identity mismatch')
    return candidate/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',candidate/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'

def make_remote_installer():
    source=(ROOT/'tools/install_vbus_hmi_fix_remote.py').read_text(encoding='utf-8-sig')
    a=source.index('def precheck(');b=source.index('\n\ndef status():',a)
    source=source[:a]+(ROOT/'tools/bkin_fast_capture/update_guard.py').read_text(encoding='utf-8')+source[b:]
    source=source.replace('choices=(2, 10), default=2','choices=(20,), default=20').replace('args.max_vdc == 10','args.max_vdc == 20')
    return source

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify-package-only',action='store_true')
    p.add_argument('--confirm-j1-j4-off-meter-below-20v',action='store_true')
    p.add_argument('--outdir',type=Path)
    a=p.parse_args();uno,nuc=verify_package()
    if a.verify_package_only:
        print(json.dumps({'pass':True,'package':str(C),'hardware_commands':0,'uno_sha256':io.sha(uno),'nucleo_sha256':io.sha(nuc)}));return 0
    if not a.confirm_j1_j4_off_meter_below_20v:p.error('physical J1/J4 off and independent meter confirmation required')
    out=(a.outdir or C.parent/('bkin_fast_capture_install_'+uuid.uuid4().hex)).resolve();out.mkdir(parents=True,exist_ok=False)
    report={'pass':False,'motor_commands':0,'clear_commands':0,'mcu_flash_commands':0,'physical_off_confirmed':True}
    def run(cmd,label,timeout=240):return io.run(cmd,label,out,report,timeout)
    def safe(pair):
        s=io.live_status();ok,reason=precheck(s)
        if not ok or (s.get('fw_build'),s.get('mc_fw_build'))!=pair:raise RuntimeError(reason)
        return s
    try:
        report['before']=safe(OLD)
        uno_port,_=io.board_ports()
        if not io.PROGRAMMER.is_file():raise RuntimeError('STM32 programmer unavailable')
        report['calibration_before']=io.calibration_hash(out,report)
        ssh=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        scp=scp_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        # Reuse the reviewed atomic HMI installer, with this pair's programming
        # gate. Its backup and owned-service restart require no sudo password.
        installer=out/'remote_hmi_installer.py';installer.write_text(make_remote_installer(),encoding='utf-8')
        ident=uuid.uuid4().hex;prefix='/tmp/mic_bkin_'+ident
        files=[(C/'web_hmi/server.py',prefix+'_server.py'),(C/'web_hmi/static/app.js',prefix+'_app.js'),(installer,prefix+'_installer.py')]
        for local,remote in files:run(scp+[str(local),'arduino@192.168.1.138:'+remote],'stage_'+local.name,40)
        cmd=['python3',files[2][1],'--candidate',files[0][1],'--sha256',io.sha(files[0][0]),'--app-js',files[1][1],'--app-js-sha256',io.sha(files[1][0]),'--max-vdc','20','--confirm-mains-off']
        run(ssh+[shlex.join(cmd+['--check-only'])],'hmi_precheck',45)
        safe(OLD)
        run(ssh+[shlex.join(cmd)],'install_hmi',60)
        report['hmi_installed']=True
        report['before_flash']=safe(OLD)
        run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','sn='+io.STLINK_SERIAL,'-w',str(nuc),'-v','-rst'],'flash_verify_nucleo')
        report['mcu_flash_commands']+=1;report['nucleo_readback_verified']=True
        base=['arduino-cli','upload','-p',uno_port,'-b','arduino:zephyr:unoq','-i',str(uno),'--upload-property','upload.artifacts.sketch='+str(uno),'--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL]
        run(base,'flash_uno');report['mcu_flash_commands']+=1
        run(base+['--upload-property','build.variant.path='+str(ROOT/'tools'),'--upload-property','openocd_cfg=verify_unoq_sketch.cfg'],'verify_uno')
        report['uno_readback_verified']=True
        run(base+['--upload-property','build.variant.path='+str(ROOT/'tools'),'--upload-property','openocd_cfg=unoq_reset_run.cfg'],'resume_uno')
        report['calibration_after']=io.calibration_hash(out,report)
        if report['calibration_after']!=report['calibration_before']:raise RuntimeError('calibration changed')
        report['calibration_unchanged']=True
        end=time.monotonic()+60;last_error=''
        while time.monotonic()<end:
            try: report['after']=safe(NEW);report['pass']=True;break
            except Exception as exc:last_error=str(exc);time.sleep(1)
        if not report['pass']:raise RuntimeError('post-flash connection not verified: '+last_error)
    except Exception as exc:report['error']=str(exc)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('pass','mcu_flash_commands','motor_commands','calibration_unchanged','error')}))
    return 0 if report['pass'] else 1
if __name__=='__main__':raise SystemExit(main())

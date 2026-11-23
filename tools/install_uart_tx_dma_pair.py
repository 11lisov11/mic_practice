"""Verified whole-frame UART TX update on J1-off USB bench, measured bus <=20 V.

J4 auxiliary 15 V may remain on under the user's existing low-voltage programming
authorization. This never authorizes mains, START, CLEAR or calibration writes.
"""
import argparse
import json
import math
from pathlib import Path
import shlex
import time
import uuid
import install_uart_resync_fix_pair as base
from unoq_wifi_hmi_deploy import ssh_base,scp_base

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'artifacts/live_bench_20261018/uart_tx_dma_fix_r1'
OLD=(2026101809,2026101808)
NEW=(2026101811,2026101810)
io=base.io
GUARD=(ROOT/'tools/uart_resync_fix/update_guard.py').read_text(encoding='utf-8').replace(
    '((2026101805,2026101804),(2026101807,2026101806))',
    '((2026101809,2026101808),(2026101811,2026101810))')
exec(GUARD)

def verify_package(candidate=C):
    m=json.loads((candidate/'manifest.json').read_text(encoding='utf-8'))
    if (m.get('schema')!='mic_ai.uart_tx_dma_fix.v1' or m.get('pair_compatibility_ids')!=list(NEW)
        or not m.get('built') or not m.get('selftest_pass') or m.get('tx_frame_deadline_ms')!=5
        or m.get('tx_timeout_aborts_frame') is not False or m.get('hv_release_approved') is not False):
        raise RuntimeError('unverified whole-frame TX package')
    for k in ('calibration_changed','control_protocol_changed','pwm_or_motor_control_changed','recovery_budget_changed','watchdog_changed'):
        if m.get(k) is not False:raise RuntimeError('unexpected change: '+k)
    t=json.loads((candidate/'selftest/report.json').read_text(encoding='utf-8'))
    if not t['pass'] or t['tx']['dma_stress_frames']!=2048 or t['bkin']['host_cases']!=450 or not t['uart']['pass'] or t['mutation_controls']<5:
        raise RuntimeError('missing actual driver/regression acceptance')
    for table in ('source_sha256','build_sha256'):
        if not m.get(table):raise RuntimeError('missing hashes')
        for rel,expected in m[table].items():
            if io.sha(candidate/rel)!=expected:raise RuntimeError('package changed: '+rel)
    for folder,name,build in [('uno','unoq_mcsdk_scalar',NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',NEW[1])]:
        b=json.loads((candidate/'build'/folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        if b['firmware_build_id']!=build:raise RuntimeError('image identity mismatch')
    return candidate/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',candidate/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'

def make_remote_installer():
    s=base.make_remote_installer()
    old=(ROOT/'tools/uart_resync_fix/update_guard.py').read_text(encoding='utf-8')
    if s.count(old)!=1:raise RuntimeError('remote guard layout changed')
    return s.replace(old,GUARD)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify-package-only',action='store_true')
    p.add_argument('--confirm-j1-off-usb-bus-below-20v',action='store_true')
    p.add_argument('--outdir',type=Path)
    a=p.parse_args();uno,nuc=verify_package()
    if a.verify_package_only:
        print(json.dumps(dict(pass_=True,hardware_commands=0,uno_sha256=io.sha(uno),nucleo_sha256=io.sha(nuc))));return 0
    if not a.confirm_j1_off_usb_bus_below_20v:p.error('J1 off, both USB, and <=20 V physical state required; J4 auxiliary may remain on')
    out=(a.outdir or C.parent/('uart_tx_dma_install_'+uuid.uuid4().hex)).resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(pass_=False,motor_commands=0,clear_commands=0,mcu_flash_commands=0,
           j1_off_user_confirmed=True,physical_bus_below_20v_user_confirmed=True,j4_auxiliary_may_remain_on=True)
    def run(cmd,label,timeout=240):return io.run(cmd,label,out,r,timeout)
    def safe(pair):
        s=io.live_status();okay,reason=precheck(s)
        if not okay or (s.get('fw_build'),s.get('mc_fw_build'))!=pair:raise RuntimeError(reason)
        return s
    try:
        r['before']=safe(OLD);uno_port,_=io.board_ports()
        r['calibration_before']=io.calibration_hash(out,r)
        ssh=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        scp=scp_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        installer=out/'remote_hmi_installer.py';installer.write_text(make_remote_installer(),encoding='utf-8')
        prefix='/tmp/mic_uart_tx_'+uuid.uuid4().hex
        files=[(C/'web_hmi/server.py',prefix+'_server.py'),(C/'web_hmi/static/app.js',prefix+'_app.js'),(installer,prefix+'_installer.py')]
        for local,remote in files:run(scp+[str(local),'arduino@192.168.1.138:'+remote],'stage_'+local.name,40)
        cmd=['python3',files[2][1],'--candidate',files[0][1],'--sha256',io.sha(files[0][0]),'--app-js',files[1][1],
             '--app-js-sha256',io.sha(files[1][0]),'--max-vdc','20','--confirm-mains-off']
        run(ssh+[shlex.join(cmd+['--check-only'])],'hmi_precheck',45)
        safe(OLD);run(ssh+[shlex.join(cmd)],'install_hmi',60);r['hmi_installed']=True
        r['before_flash']=safe(OLD)
        run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','sn='+io.STLINK_SERIAL,'-w',str(nuc),'-v','-rst'],'flash_verify_nucleo')
        r['mcu_flash_commands']+=1;r['nucleo_readback_verified']=True
        upload=['arduino-cli','upload','-p',uno_port,'-b','arduino:zephyr:unoq','-i',str(uno),
                '--upload-property','upload.artifacts.sketch='+str(uno),'--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL]
        run(upload,'flash_uno');r['mcu_flash_commands']+=1
        run(upload+['--upload-property','build.variant.path='+str(ROOT/'tools'),'--upload-property','openocd_cfg=verify_unoq_sketch.cfg'],'verify_uno')
        r['uno_readback_verified']=True
        run(upload+['--upload-property','build.variant.path='+str(ROOT/'tools'),'--upload-property','openocd_cfg=unoq_reset_run.cfg'],'resume_uno')
        r['calibration_after']=io.calibration_hash(out,r)
        if r['calibration_after']!=r['calibration_before']:raise RuntimeError('calibration changed')
        r['calibration_unchanged']=True
        deadline=time.monotonic()+60;error=''
        while time.monotonic()<deadline:
            try:r['after']=safe(NEW);r['pass_']=True;break
            except Exception as exc:error=str(exc);time.sleep(1)
        if not r['pass_']:raise RuntimeError('installed connection not verified: '+error)
    except Exception as exc:r['error']=str(exc)
    r['pass']=r.pop('pass_')
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('pass','mcu_flash_commands','motor_commands','calibration_unchanged','error')}))
    return 0 if r['pass'] else 1

if __name__=='__main__':raise SystemExit(main())

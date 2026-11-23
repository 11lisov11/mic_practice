"""Recover verified 1106 boot failure on an operator-confirmed discharged stand; no actuation."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from prepare_unoq_bridge_boot_fix import ROOT, BASE, BUILD, sketch, hmi, source_hashes
from install_unoq_rx_fix import sha
from unoq_wifi_hmi_deploy import ssh_base, scp_base
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','regression','outdir'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--confirm-mains-j4-off',action='store_true')
    p.add_argument('--confirm-meter-le-2',action='store_true')
    p.add_argument('--tls-fix',action='store_true')
    a=p.parse_args()
    base, build_id, patch_sketch, patch_hmi = BASE, BUILD, sketch, hmi
    if a.tls_fix:
        from prepare_unoq_llext_fix import BASE as base, BUILD as build_id, sketch as patch_sketch, hmi as patch_hmi
        from unoq_llext_check import inspect
        if not inspect(a.candidate/'uno_build/UNOQ_MOTOR.ino.elf')['pass_']:
            raise RuntimeError('Dynamic loader compatibility check failed')
    if not(a.confirm_mains_j4_off and a.confirm_meter_le_2): p.error('Both physical discharged-stand confirmations required')
    candidate=a.candidate.resolve(); report=json.loads(a.regression.read_text())
    if not report['pass'] or not report['sources_unchanged_during_tests']: raise RuntimeError('Boot-aware regression required')
    for name,value in report['source_sha256'].items():
        if sha(ROOT/name)!=value: raise RuntimeError('Regression source changed: '+name)
    if not any(x['test']=='unoq_bridge_boot_selftest' and x['pass'] for x in report['tests']):
        raise RuntimeError('Boot checks missing')
    if a.tls_fix and not any(x['test']=='unoq_llext_selftest' and x['pass'] for x in report['tests']):
        raise RuntimeError('ELF compatibility regression missing')
    manifest=json.loads((candidate/'manifest.json').read_text())
    if (manifest['uno_build']!=build_id or manifest['nucleo_build']!=2026101102
            or source_hashes(base/'UNOQ_MOTOR')!=manifest['baseline_source_sha256']
            or source_hashes(candidate/'UNOQ_MOTOR')!=manifest['source_sha256']
            or (candidate/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()!=patch_sketch((base/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text())
            or (candidate/'web_hmi/server.py').read_text()!=patch_hmi((base/'web_hmi/server.py').read_text())):
        raise RuntimeError('Boot-recovery package mismatch')
    for build_dir in (base/'uno_build',candidate/'uno_build'):
        build=json.loads((build_dir/'unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
        expected_id = build_id - 1 if build_dir == base/'uno_build' else build_id
        if build['firmware_build_id'] != expected_id:
            raise RuntimeError('Unexpected image identity')
        for item in build['artifacts']:
            path=build_dir/item['file']
            if sha(path)!=item['sha256'].lower() or path.stat().st_size!=item['bytes']: raise RuntimeError('Image mismatch')
    out=a.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    rep=dict(pass_=False,start_commands=0,arm_commands=0,clear_commands=0,nucleo_flash_commands=0,
        live_rpc_prewrite_available=False,physical_confirmation='mains/J4 off, meter <=2 V',
        safety_basis='No live status inferred; exact predecessor/loader readback plus physical deenergization',hv_release_approved=False)
    ssh=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
    scp=scp_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
    wifi=WifiHmi('http://192.168.1.138:8080',read_token('.unoq_ssh/control_token'),[],False)
    def run(cmd,name,timeout=120):
        r=subprocess.run([str(x) for x in cmd],capture_output=True,timeout=timeout)
        (out/(name+'.log')).write_bytes(r.stdout+r.stderr)
        if r.returncode: raise RuntimeError(name+' failed; retained log')
        return r.stdout.decode('utf-8',errors='replace')
    try:
        inv=json.loads(run(['arduino-cli','board','list','--format','json'],'inventory'))
        ports={x['port'].get('properties',{}).get('serialNumber'):x['port']['address'] for x in inv['detected_ports']}
        if '3880458060' not in ports: raise RuntimeError('Exact Uno USB not found')
        cal='/home/arduino/.config/mic-ai/vbus_calibration.json'
        before_cal=run(ssh+['sha256sum '+cal],'cal_before').split()[0]
        old=base/'uno_build/UNOQ_MOTOR.ino.elf-zsk.bin'
        run(['adb','-s','3880458060','push',old,'/home/arduino/mic_expected_boot_1106.bin'],'stage_expected')
        if run(ssh+['sha256sum /home/arduino/mic_expected_boot_1106.bin'],'expected_remote').split()[0]!=sha(old):
            raise RuntimeError('Predecessor staging mismatch')
        target='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py'; goal=sha(candidate/'web_hmi/server.py')
        actual=run(ssh+['sha256sum '+target],'hmi_before').split()[0]
        if actual!=sha(base/'web_hmi/server.py'): raise RuntimeError('Unexpected HMI')
        remote='/home/arduino/boot_1107_server.py'; helper='/home/arduino/boot_1107_recovery.py'
        run(scp+[candidate/'web_hmi/server.py','arduino@192.168.1.138:'+remote],'copy_hmi')
        run(scp+[ROOT/'tools/recover_unoq_hmi_router_remote.py','arduino@192.168.1.138:'+helper],'copy_helper')
        rep['hmi_install']=json.loads(run(ssh+[f'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python {helper} --candidate {remote} --sha256 {goal} --expected-live-sha256 {actual} --confirm-mains-j4-off'],'install_hmi'))
        image=candidate/'uno_build/UNOQ_MOTOR.ino.elf-zsk.bin'
        run(['arduino-cli','upload','-p',ports['3880458060'],'-b','arduino:zephyr:unoq','-i',image,
            '--upload-property','upload.artifacts.sketch='+str(image),
            '--upload-property','upload.port.properties.serialNumber=3880458060',
            '--upload-property','build.variant.path='+str(ROOT/'tools'),
            '--upload-property','openocd_cfg=flash_unoq_boot_recovery.cfg'],'flash_verified')
        rep['predecessor_verified']=rep['uno_flash_verified']=True
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            try:
                s=wifi.status()
                if (s.get('fw_build'),s.get('mc_fw_build'))==(build_id,2026101102):
                    rep['after']=s; break
            except Exception as exc: rep['last_rpc_error']=str(exc)
            time.sleep(1)
        else: raise RuntimeError('Image verified; live RPC not confirmed')
        if s.get('pwm')!=0 or s.get('hmi_hv_armed')!=0: raise RuntimeError('Unexpected enabled state')
        rep['calibration_unchanged']=run(ssh+['sha256sum '+cal],'cal_after').split()[0]==before_cal
        if not rep['calibration_unchanged']: raise RuntimeError('Calibration changed')
        rep['pass_']=True
    except Exception as exc: rep['error']=str(exc)
    finally:
        wifi.close(); rep['pass']=rep.pop('pass_'); (out/'report.json').write_text(json.dumps(rep,indent=2)+'\n')
    print(json.dumps({k:rep.get(k) for k in ('pass','predecessor_verified','uno_flash_verified','calibration_unchanged','error')}))
    return 0 if rep['pass'] else 1


if __name__=='__main__': raise SystemExit(main())

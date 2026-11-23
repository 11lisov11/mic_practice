"""Install only the Uno RX fix on the already confirmed deenergized stand."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from prepare_unoq_rx_fix import ROOT, BASE, BUILD, ASSETS, sketch, hmi, source_hashes
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token
from verify_wifi_command_path import get_wifi_logs
from unoq_wifi_hmi_deploy import ssh_base, scp_base


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def maintenance_safe(s):
    """Not a RUN gate: historical CRC rejects are archived, not excused for operation."""
    try:
        return ((s['fw_build'], s['mc_fw_build']) == (2026101103, 2026101102)
            and s['state'] == 'SAFE' and s['pwm'] == s['hmi_hv_armed'] == s['estop'] == 0
            and not (s['bp_status'] & 0x22)
            and all(type(s[k]) in (int, float) and 0 <= s[k] <= 2 for k in ('vdc', 'bp_vdc'))
            and all(type(s[k]) in (int, float) and 0 <= s[k] < 300 for k in ('mc_age_ms', 'bp_vbus_age_ms'))
            and s['bp_vbus_valid'] == 1 and 0 <= s['bp_vbus_raw'] <= 20
            and s['bp_bad_cnt'] == s['bp_transport_fault'] == s['bp_bad_sequence'] == 0
            and s['bp_bad'] == s['bp_bad_integrity']
            and s['bp_fault'] == 5 and s['mc_diag_valid'] == 1
            and s['mc_fault_reason'] == 8 and s['mc_fault_current_mask'] == 4
            and s['mc_fault_occurred_mask'] in (4, 0x404)
            and all(s[k] == 0 for k in ('bp_clear_pending', 'precharge', 'pfc', 'brake', 'bp_ext')))
    except (KeyError, TypeError): return False


def verify(candidate, regression):
    report=json.loads(regression.read_text())
    assert report['pass'] and report['sources_unchanged_during_tests']
    assert any(t['test']=='unoq_rx_fix_selftest' and t['pass'] for t in report['tests'])
    for name, expected in report['source_sha256'].items():
        assert sha(ROOT/name)==expected, name
    manifest=json.loads((candidate/'manifest.json').read_text())
    assert manifest['uno_build']==BUILD and manifest['nucleo_build']==2026101102
    assert source_hashes(BASE/'UNOQ_MOTOR')==manifest['base_uno']
    assert source_hashes(candidate/'UNOQ_MOTOR')==manifest['source_sha256']
    assert (candidate/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()==sketch((BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text())
    assert (candidate/'web_hmi/server.py').read_text()==hmi((BASE/'web_hmi/server.py').read_text())
    for path in ASSETS.glob('*.h'): assert sha(path)==sha(candidate/'UNOQ_MOTOR'/path.name)
    build=json.loads((candidate/'uno_build/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    assert build['firmware_build_id']==BUILD
    for artifact in build['artifacts']:
        path=candidate/'uno_build'/artifact['file']
        assert sha(path)==artifact['sha256'].lower() and path.stat().st_size==artifact['bytes']
    return candidate/'uno_build/UNOQ_MOTOR.ino.elf-zsk.bin'


def deadline_maintenance_safe(s):
    try:
        timeout=(s['bp_fault']==2 and s['bp_bad_cnt']==1 and s['bp_transport_fault']==7
            and s['mc_diag_valid']==1 and s['mc_last_bad_reason']==13
            and (s['mc_fault_reason']==13 or (s['mc_fault_reason']==8
                and s['mc_fault_current_mask']==4 and s['mc_fault_occurred_mask'] in (4,0x404))))
        undervoltage=(s['bp_fault']==5 and s['bp_bad_cnt']==s['bp_transport_fault']==0
            and s['mc_diag_valid']==1 and s['mc_fault_reason']==8 and s['mc_last_bad_reason']==0
            and s['mc_fault_current_mask']==4 and s['mc_fault_occurred_mask'] in (4,0x404))
        return ((s['fw_build'],s['mc_fw_build']) in ((2026101104,2026101102),(2026101105,2026101102),(2026101106,2026101102))
            and s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==s['estop']==0
            and not s['bp_status']&0x22
            and all(type(s[k]) in (int,float) and 0<=s[k]<=2 for k in ('vdc','bp_vdc'))
            and 0<=s['bp_vbus_raw']<=20 and s['bp_vbus_valid']==1
            and all(0<=s[k]<300 for k in ('bp_age_ms','mc_age_ms','bp_vbus_age_ms'))
            and (timeout or undervoltage)
            and all(s[k]==0 for k in ('bp_bad','bp_bad_integrity','bp_bad_sequence',
                'mc_uart_error_flags','mc_last_uart_error_flags','uno_rx_dropped','uno_rx_hw_errors',
                'uno_rx_hw_flags','bp_temp_fault','bp_clear_pending','precharge','pfc','brake','bp_ext')))
    except (KeyError,TypeError): return False


def verify_deadline(candidate, regression):
    from prepare_unoq_deadline_fix import BASE as base, HMI_BASE, BUILD as target, sketch, timing, hmi
    report=json.loads(regression.read_text())
    if not report['pass'] or not report['sources_unchanged_during_tests']:
        raise RuntimeError('Current offline regression required')
    for name,value in report['source_sha256'].items():
        if sha(ROOT/name)!=value: raise RuntimeError('Regression source changed: '+name)
    if not any(x['test']=='unoq_idle_deadline_selftest' and x['pass'] for x in report['tests']):
        raise RuntimeError('Deadline regression missing')
    manifest=json.loads((candidate/'manifest.json').read_text())
    if (manifest['uno_build']!=target or manifest['nucleo_build']!=2026101102
            or source_hashes(base/'UNOQ_MOTOR')!=manifest['baseline_source_sha256']
            or source_hashes(candidate/'UNOQ_MOTOR')!=manifest['source_sha256']):
        raise RuntimeError('Deadline package source mismatch')
    for name,transform in (('UNOQ_MOTOR.ino',sketch),('link_timing.h',timing)):
        if (candidate/'UNOQ_MOTOR'/name).read_text()!=transform((base/'UNOQ_MOTOR'/name).read_text()):
            raise RuntimeError('Unexpected deadline patch: '+name)
    if (candidate/'web_hmi/server.py').read_text()!=hmi((HMI_BASE/'web_hmi/server.py').read_text()):
        raise RuntimeError('Unexpected deadline HMI')
    build=json.loads((candidate/'uno_build/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    if build['firmware_build_id']!=target: raise RuntimeError('Wrong deadline image identity')
    for item in build['artifacts']:
        path=candidate/'uno_build'/item['file']
        if sha(path)!=item['sha256'].lower() or path.stat().st_size!=item['bytes']:
            raise RuntimeError('Deadline image mismatch')
    return candidate/'uno_build/UNOQ_MOTOR.ino.elf-zsk.bin'


def verify_priority(candidate, regression):
    from prepare_unoq_rpc_priority_fix import BASE as base, BUILD as target, sketch, sensor, hmi
    report=json.loads(regression.read_text())
    if not report['pass'] or not report['sources_unchanged_during_tests']:
        raise RuntimeError('Current priority regression required')
    for name,value in report['source_sha256'].items():
        if sha(ROOT/name)!=value: raise RuntimeError('Regression source changed: '+name)
    if not any(x['test']=='unoq_rpc_priority_selftest' and x['pass'] for x in report['tests']):
        raise RuntimeError('Priority model/source checks missing')
    manifest=json.loads((candidate/'manifest.json').read_text())
    if (manifest['uno_build']!=target or manifest['nucleo_build']!=2026101102
            or source_hashes(base/'UNOQ_MOTOR')!=manifest['baseline_source_sha256']
            or source_hashes(candidate/'UNOQ_MOTOR')!=manifest['source_sha256']):
        raise RuntimeError('Priority source package mismatch')
    for name,transform in (('UNOQ_MOTOR.ino',sketch),('as5600_teacher.cpp',sensor)):
        if (candidate/'UNOQ_MOTOR'/name).read_text()!=transform((base/'UNOQ_MOTOR'/name).read_text()):
            raise RuntimeError('Unexpected priority patch: '+name)
    if (candidate/'web_hmi/server.py').read_text()!=hmi((base/'web_hmi/server.py').read_text()):
        raise RuntimeError('Unexpected priority HMI')
    build=json.loads((candidate/'uno_build/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    if build['firmware_build_id']!=target: raise RuntimeError('Wrong priority image ID')
    for item in build['artifacts']:
        path=candidate/'uno_build'/item['file']
        if sha(path)!=item['sha256'].lower() or path.stat().st_size!=item['bytes']:
            raise RuntimeError('Priority image hash/length mismatch')
    return candidate/'uno_build/UNOQ_MOTOR.ino.elf-zsk.bin'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--regression',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--confirm-mains-j4-off',action='store_true')
    p.add_argument('--deadline-fix',action='store_true')
    p.add_argument('--rpc-priority-fix',action='store_true')
    p.add_argument('--confirm-meter-le-2',action='store_true')
    args=p.parse_args()
    if args.rpc_priority_fix: args.deadline_fix=True
    if not args.confirm_mains_j4_off: p.error('Previously confirmed physical mains/J4-off state required')
    if args.deadline_fix and not args.confirm_meter_le_2: p.error('Separate meter <=2 V confirmation required')
    candidate=args.candidate.resolve()
    verifier=verify_priority if args.rpc_priority_fix else (verify_deadline if args.deadline_fix else verify)
    image=verifier(candidate,args.regression.resolve())
    gate=deadline_maintenance_safe if args.deadline_fix else maintenance_safe
    target_build=2026101106 if args.rpc_priority_fix else (2026101105 if args.deadline_fix else BUILD)
    out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    result=dict(pass_=False, start_commands=0, clear_commands=0, nucleo_flash_commands=0, hv_release_approved=False)
    wifi=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),[],False)
    ssh=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
    scp=scp_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
    def run(cmd,name,timeout=120):
        proc=subprocess.run([str(c) for c in cmd],capture_output=True,timeout=timeout)
        (out/(name+'.log')).write_bytes(proc.stdout+proc.stderr)
        if proc.returncode: raise RuntimeError(name+' failed; see retained log')
        return proc.stdout.decode('utf-8',errors='replace')
    def cal(name):
        return run(ssh+['sha256sum /home/arduino/.config/mic-ai/vbus_calibration.json'],name).split()[0]
    try:
        result['before']=before=wifi.status()
        if not gate(before): raise RuntimeError('Unexpected physical/telemetry maintenance state')
        if args.deadline_fix: result['meter_confirmation']='Operator confirmed <=2 V; reported telemetry retained in before/after'
        (out/'before_logs.txt').write_text(get_wifi_logs(wifi,wifi.token),encoding='utf-8')
        result['calibration_before']=cal('cal_before')
        inventory=json.loads(run(['arduino-cli','board','list','--format','json'],'inventory'))
        ports={d['port'].get('properties',{}).get('serialNumber'):d['port']['address'] for d in inventory['detected_ports']}
        if '3880458060' not in ports: raise RuntimeError('Exact Uno Q USB serial not found')
        target='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py'
        from prepare_unoq_deadline_fix import HMI_BASE
        if args.rpc_priority_fix:
            from prepare_unoq_rpc_priority_fix import BASE as HMI_BASE
        expected=sha((HMI_BASE if args.deadline_fix else BASE)/'web_hmi/server.py'); goal=sha(candidate/'web_hmi/server.py')
        if run(ssh+['sha256sum '+target],'hmi_before').split()[0]!=expected:
            raise RuntimeError('Unexpected installed HMI')
        remote_candidate=f'/home/arduino/rx_fix_server_{target_build}.py'
        remote_tool=f'/home/arduino/rx_fix_recovery_{target_build}.py'
        run(scp+[candidate/'web_hmi/server.py','arduino@192.168.1.138:'+remote_candidate],'copy_hmi')
        run(scp+[ROOT/'tools/recover_unoq_hmi_router_remote.py','arduino@192.168.1.138:'+remote_tool],'copy_recovery')
        command=f'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python {remote_tool} --candidate {remote_candidate} --sha256 {goal} --expected-live-sha256 {expected} --confirm-mains-j4-off'
        result['hmi']=json.loads(run(ssh+[command],'install_hmi'))
        time.sleep(3)
        if not gate(wifi.status()): raise RuntimeError('Pre-flash maintenance state changed')
        run(['arduino-cli','upload','-p',ports['3880458060'],'-b','arduino:zephyr:unoq','-i',image,
             '--upload-property','upload.artifacts.sketch='+str(image),
             '--upload-property','upload.port.properties.serialNumber=3880458060',
             '--upload-property','build.variant.path='+str(ROOT/'tools'),
             '--upload-property','openocd_cfg=flash_verify_unoq_sketch.cfg'],'flash_verify_uno')
        result['uno_flash_verified']=True
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            try:
                after=wifi.status()
                if (after.get('fw_build'),after.get('mc_fw_build'))==(target_build,2026101102):
                    result['after']=after; break
            except Exception as exc: result['last_rpc_error']=str(exc)
            time.sleep(1)
        else: raise RuntimeError('Flashed/verified, live RPC identity still unavailable')
        result['calibration_after']=cal('cal_after')
        if result['calibration_before']!=result['calibration_after']: raise RuntimeError('Calibration changed')
        result['calibration_unchanged']=True
        if after.get('pwm')!=0 or after.get('hmi_hv_armed')!=0: raise RuntimeError('Outputs not disabled')
        result['pass_']=True
    except Exception as exc: result['error']=f'{type(exc).__name__}: {exc}'
    finally:
        wifi.close(); result['pass']=result.pop('pass_')
        (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result.get(k) for k in ('pass','uno_flash_verified','calibration_unchanged','error')}))
    return 0 if result['pass'] else 1


if __name__=='__main__': raise SystemExit(main())

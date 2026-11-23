"""Install the single tested working UART repair, preserving calibration and motor wiring."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
from collect_wifi_telemetry import get_status, get_logs
from prepare_ipm_break_wifi import source_hashes
from prepare_pwm_filter_pair import sha, write
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL
import pwm_filter_hardware_session as bench

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'artifacts/live_bench_20261014/uart_recovery_working_pair_r1'
PAIR=(2026101413,2026101412)

def qualify(package):
    global PAIR
    mf=json.loads((package/'manifest.json').read_text())
    PAIR=tuple(mf['pair']);assert PAIR in ((2026101413,2026101412),(2026101415,2026101414),(2026101501,2026101502),(2026101503,2026101502),(2026101505,2026101504))
    for tree,key in [('nucleo','nucleo_source_sha256'),('UNOQ_MOTOR','uno_source_sha256')]:
        assert source_hashes(package/tree)==mf[key]
    assert sha(package/'web_hmi/server.py')==mf['hmi_sha256']
    proof=json.loads((package/mf.get('uart_selftest_report','tests_final/report.json')).read_text())
    assert proof['pass'] and proof['header_sha256']==sha(package/'nucleo/Inc/uart_v3_transport.h')
    assert proof['source_sha256']==sha(package/'nucleo/Src/main.c')
    assert proof['uno_source_sha256']==sha(package/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    assert len(proof['mutations'])==4 and all(x['detected'] for x in proof['mutations'])
    if mf.get('intact_ne_is_advisory'):
        assert proof['old_shared_NE_budget_regression_detected']
        assert proof['intact_ne_metadata_not_counted_as_damaged_packet']
    guards=json.loads((package/mf.get('hmi_guard_report','hmi_guards/report.json')).read_text())
    http=json.loads((package/'selftest.json').read_text())
    assert guards['pass'] and len(guards['suites'])==5
    assert http['pass'] and http['hmi_sha256']==mf['hmi_sha256']
    if mf.get('manual_scalar'):
        manual=json.loads((package/mf['manual_selftest_report']).read_text())
        assert manual['pass'] and manual['hardware_commands']==0
        assert manual['nucleo_sha256']==sha(package/'nucleo/Src/main.c')
        assert manual['uno_sha256']==sha(package/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
        assert manual['hmi_sha256']==guards['hmi_sha256']==mf['hmi_sha256']
        assert manual['header_sha256']==sha(package/'nucleo/Inc/manual_scalar_control.h')
        browser=json.loads((package/'browser_qualification.json').read_text())
        assert browser['pass'] and browser['hardware_commands']==0
        for name,digest in mf['hmi_static_sha256'].items():
            assert sha(package/'web_hmi/static'/name)==browser['static_sha256'][name]==digest
        if mf.get('routerbridge_manual_status_fixed'):
            bridge=json.loads((package/'routerbridge_selftest/report.json').read_text())
            assert bridge['pass'] and bridge['hardware_commands']==0
            assert bridge['uno_sha256']==sha(package/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
            assert bridge['hmi_sha256']==mf['hmi_sha256']
        if mf.get('vf_open_loop_reference_fixed'):
            vf=json.loads((package/'vf_reference_selftest/report.json').read_text())
            assert vf['pass'] and vf['negative_control_reproduced'] and vf['hardware_commands']==0
            assert vf['mc_interface_sha256']==sha(package/'nucleo/Src/mc_interface.c')
            assert vf['nucleo_main_sha256']==sha(package/'nucleo/Src/main.c')
            lib=package/'nucleo/MCSDK_v6.4.2-Full/MotorControl/MCSDK'
            assert vf['vf_controller_sha256']==sha(lib/'MCLibACIM/Any/Src/acim_vf_control.c')
            assert vf['ramp_manager_sha256']==sha(lib/'MCLib/Any/Src/ramp_ext_mngr.c')
            old=json.loads((Path(mf['predecessor_candidate'])/'manifest.json').read_text())
            changes=sorted(k for k,v in mf['nucleo_source_sha256'].items() if old['nucleo_source_sha256'].get(k)!=v)
            assert changes==['Inc/break_wire.h','Src/main.c','Src/mc_interface.c'],changes
    assert json.loads((package/'uno_build/llext-check.json').read_text())['pass']
    artifacts={}
    for folder,name,build in [(package/'uno_build','unoq_mcsdk_scalar.build-manifest.json',PAIR[0]),
        (package/'nucleo/STM32CubeIDE/Debug','ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json',PAIR[1])]:
        bm=json.loads((folder/name).read_text(encoding='utf-8-sig'))
        assert bm['firmware_build_id']==build
        if build==PAIR[1]:assert bm['build_errors']==bm['build_warnings']==0
        for item in bm['artifacts']:
            path=folder/item['file'];assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256'].lower()
            artifacts[str(path.relative_to(package))]=sha(path)
    elf=package/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    assert elf.stat().st_mtime>=(package/'nucleo/Inc/uart_v3_transport.h').stat().st_mtime
    report=dict(pass_=True,pair=list(PAIR),artifacts_sha256=artifacts,
      hmi_sha256=mf['hmi_sha256'],header_sha256=proof['header_sha256'],
      source_hashes_verified=True,measurement_pwm_and_protection_sources_unchanged=not bool(mf.get('vf_open_loop_reference_fixed')),
      core_adc_filter_pwm_protection_sources_unchanged=True,
      physical_powered_uart_recovery_verified=False,hardware_commands=0,no_fixture_firmware=True,
      target_builds_compiled=True,tests=proof['assertions'],normal_http_starts=2,
      intact_ne_is_advisory=bool(mf.get('intact_ne_is_advisory')))
    if mf.get('manual_scalar'):
        report.update(manual_scalar=True,manual_selftest_report=mf['manual_selftest_report'],
          hmi_static_sha256=mf['hmi_static_sha256'],manual_selftests=manual,
          installed=False,physical_manual_operation_verified=False)
    report['pass']=report.pop('pass_')
    write(package/'qualification.json',json.dumps(report,indent=2)+'\n')
    return mf,report

def safe_off(data,expected=None):
    assert data['state']=='SAFE' and data['pwm']==0 and data['hmi_hv_armed']==0
    assert not(data['bp_status']&0x22) and 0<=data['bp_age_ms']<300
    voltage=float(data['bp_vdc']);assert math.isfinite(voltage) and 0<=voltage<20
    if expected:assert (data['fw_build'],data['mc_fw_build'])==expected

def install(package):
    mf,proof=qualify(package)
    assert not mf['installed'],'Working repair already installed; do not reflash for a test'
    session=bench.Session(ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1')
    assert session.state.get('operator_all_power_off_confirmed')
    assert session.state.get('dc_bus_meter_independent_below_20v_confirmed')
    assert session.state.get('j4_15v_on') is False and session.state.get('mains_on') is False
    out=package/'installation';out.mkdir(exist_ok=True)
    op=build_opener(ProxyHandler({}));url='http://192.168.1.138:8080'
    previous=tuple(mf['predecessor_pair'])
    before=get_status(op,url);safe_off(before,previous)
    suffix='' if not (out/'before_status.json').exists() else '_recheck_'+str(time.time_ns())
    write(out/('before_status'+suffix+'.json'),json.dumps(before,indent=2)+'\n')
    (out/('before_logs'+suffix+'.txt')).write_text(get_logs(op,url,session.token,1))
    session.hashes('uart_recovery_install_original_hashes')
    hmi=session.hmi(False)
    response=hmi.post('/api/stop-sequence',{'emergency':False},'UART repair prewrite STOP')
    assert response.get('ok')
    safe_off(get_status(op,url),previous)
    remote=bench.HMI_ROOT
    stage=remote+'/server.py.'+package.name+'.staged'
    backup=remote+'/server.py.before_'+package.name
    session.run(session.scp+[package/'web_hmi/server.py','arduino@192.168.1.138:'+stage],
                'uart_recovery_stage_hmi',timeout=40)
    static_files=mf.get('hmi_static_sha256',{})
    for name,digest in static_files.items():
        assert name in ('index.html','app.js','style.css')
        session.run(session.scp+[package/'web_hmi/static'/name,
          'arduino@192.168.1.138:'+remote+'/static/'+name+'.staged_'+package.name],
          'manual_scalar_stage_'+name.replace('.','_'),timeout=40)
    paused=json.loads(session.remote(f'''import os,signal,subprocess,json,hashlib
from pathlib import Path
root=Path({remote!r});target=root/'server.py';stage=Path({stage!r});backup=Path({backup!r})
assert hashlib.sha256(target.read_bytes()).hexdigest()=={session.hmi_sha!r}
assert hashlib.sha256(stage.read_bytes()).hexdigest()=={mf['hmi_sha256']!r}
assert hashlib.sha256(Path('/home/arduino/.config/mic-ai/vbus_calibration.json').read_bytes()).hexdigest()=={bench.CAL_SHA!r}
assert not backup.exists()
pid=int(subprocess.check_output(['systemctl','show','unoq-hmi.service','-p','MainPID','--value'],text=True))
assert pid>1 and os.stat('/proc/'+str(pid)).st_uid==os.getuid()
argv=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(b'\\0')
assert any(value == b'server.py' or value == str(target).encode() for value in argv)
os.kill(pid,signal.SIGSTOP)
print(json.dumps({{'pid':pid,'paused':True}}))
''','uart_recovery_pause_hmi'))
    write(out/'paused_hmi.json',json.dumps(paused)+'\n')
    pid=paused['pid'];installed=False
    try:
        image=package/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin'
        reused=bool(mf.get('reuse_identical_nucleo_image'))
        if reused:
            predecessor=Path(mf['predecessor_candidate'])/'nucleo/STM32CubeIDE/Debug'/image.name
            assert previous[1]==PAIR[1] and sha(predecessor)==sha(image)
            print('Keeping Nucleo image; checking full readback',flush=True)
        else:
            print('Writing Nucleo working repair',flush=True)
            session.run([PROGRAMMER,'-c','port=SWD','mode=UR','sn='+SERIAL,'-w',image,'0x08000000','-v','-rst'],
                        'uart_recovery_nucleo_write',timeout=90)
        readback=out/'nucleo_readback.bin'
        session.run([PROGRAMMER,'-c','port=SWD','mode=HOTPLUG','sn='+SERIAL,'-u','0x08000000',image.stat().st_size,readback],
                    'uart_recovery_nucleo_readback',timeout=60)
        assert sha(readback)==sha(image)
        print('Nucleo verified against full readback; writing Uno',flush=True)
        uno=package/'uno_build/UNOQ_MOTOR.ino.elf-zsk.bin'
        assert session.run(['adb','-s','3880458060','get-state'],'uart_recovery_uno_adb',timeout=15).strip()=='device'
        session.run(['arduino-cli','upload','-p','COM10','-b','arduino:zephyr:unoq','-i',uno,
          '--upload-property','upload.artifacts.sketch='+str(uno),
          '--upload-property','upload.port.properties.serialNumber=3880458060',
          '--upload-property','build.variant.path='+str(ROOT/'tools'),
          '--upload-property','openocd_cfg=flash_verify_unoq_sketch.cfg'],
          'uart_recovery_uno_write_verified',timeout=180)
        print('Uno upload and verification complete; resuming HMI',flush=True)
        session.remote(f'''from pathlib import Path
import hashlib,os,signal
target=Path({remote+'/server.py'!r});stage=Path({stage!r});backup=Path({backup!r})
assert hashlib.sha256(target.read_bytes()).hexdigest()=={session.hmi_sha!r}
assert hashlib.sha256(stage.read_bytes()).hexdigest()=={mf['hmi_sha256']!r}
assert not backup.exists();backup.write_bytes(target.read_bytes());os.replace(stage,target)
for name,digest in {static_files!r}.items():
    target=Path({remote!r})/'static'/name
    stage=target.with_name(name+'.staged_'+{package.name!r})
    backup=target.with_name(name+'.before_'+{package.name!r})
    assert hashlib.sha256(stage.read_bytes()).hexdigest()==digest and not backup.exists()
    backup.write_bytes(target.read_bytes());os.replace(stage,target)
assert hashlib.sha256(Path('/home/arduino/.config/mic-ai/vbus_calibration.json').read_bytes()).hexdigest()=={bench.CAL_SHA!r}
os.kill({pid},signal.SIGCONT);os.kill({pid},signal.SIGTERM)
print('working repair HMI installed')
''','uart_recovery_replace_hmi')
        installed=True
    finally:
        if not installed:
            session.remote(f'''import os,signal
try:os.kill({pid},signal.SIGCONT)
except ProcessLookupError:pass
print('HMI resumed after incomplete installation')
''','uart_recovery_resume_after_failure')
    mf.update(installed=True,source_only=False,qualification_pending=False)
    write(package/'manifest.json',json.dumps(mf,indent=2)+'\n')
    history=session.state.get('uart_recovery_history',[])
    predecessor=session.state.get('uart_recovery_candidate')
    if session.state.get('uart_recovery_installed') and predecessor!=str(package) and predecessor not in history:
        history.append(predecessor)
    session.state.update(uart_recovery_installed=True,uart_recovery_candidate=str(package),uart_recovery_history=history,
      uart_recovery_hmi_sha256=mf['hmi_sha256'],working_pair=list(PAIR),
      uart_recovery_installation_folder=str(out),uart_recovery_powered_test_complete=False)
    session.save()
    report=dict(installed=True,pair=list(PAIR),nucleo_full_readback_verified=True,uno_upload_verified=True,
      nucleo_rewritten=not bool(mf.get('reuse_identical_nucleo_image')),
      original_calibration_unchanged=True,hmi_sha256=mf['hmi_sha256'],start_commands=0,
      idle_qualification_complete=False,physical_powered_uart_recovery_verified=False)
    write(out/'report.json',json.dumps(report,indent=2)+'\n')
    deadline=time.monotonic()+45;last_error=None
    while time.monotonic()<deadline:
        try:
            after=get_status(op,url)
            if (after.get('fw_build'),after.get('mc_fw_build'))==PAIR:
                safe_off(after,PAIR)
                write(out/'after_status.json',json.dumps(after,indent=2)+'\n')
                print(json.dumps({k:after.get(k) for k in ['state','pwm','vdc','fw_build','mc_fw_build','bp_age_ms','bp_transport_fault','bp_recovered_drops','bp_fault']}),flush=True)
                return
        except Exception as e:last_error=str(e)
        time.sleep(.5)
    raise RuntimeError('Written images verified; live RPC did not recover: '+str(last_error))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,default=DEFAULT);p.add_argument('--qualify-only',action='store_true');a=p.parse_args()
    if a.qualify_only:print(json.dumps(qualify(a.candidate.resolve())[1]))
    else:install(a.candidate.resolve())

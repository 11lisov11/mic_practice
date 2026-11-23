"""Pinned install/restore and one-shot captures for the detached 1204 STOP fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

from collect_wifi_telemetry import get_status, get_logs, read_token
from prepare_local_stop_pwm_fixture import HERE, ROOT, PAIR
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL
from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status

CAL_SHA='a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17'
HMI_SHA='21bda96fae14b0fa13db27d1fb21edd6f059e6d2037199944bdae50999569276'
REMOTE='/home/arduino/.local/share/mic-ai/local-stop-hil-20261012'
VENV='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python'
NB='ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin'
PROD_N=HERE/'candidate_r5/nucleo/STM32CubeIDE/Debug'/NB
PROD_U=HERE/'uno_peer_r2/uno_build/UNOQ_MOTOR.ino.elf-zsk.bin'
PROD_HASHES=('afd0c72fc33c1519d9a85b6fd43356057a66048f82d20e1ebbbd56cd5e714714',
             'f35dfb3c583b1e6f4822d62f3e7971f3a7cac0e3beed76565f273dbfa203e949')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('install','restore','ready','run'))
    p.add_argument('--session',type=Path,required=True)
    p.add_argument('--fixture',type=Path,default=HERE/'pwm_fixture_r1')
    p.add_argument('--confirm-isolated-zero-bus',action='store_true')
    a=p.parse_args();session=a.session.resolve();fixture=a.fixture.resolve()
    state_path=session/'session.json'
    if a.action=='install':
        if not a.confirm_isolated_zero_bus:p.error('Operator-confirmed J1/U/V/W disconnected, J4 off, measured bus <=2 V')
        session.mkdir(parents=True,exist_ok=False)
        state=dict(schema='mic_ai.local_stop_zero_bus_session.v1',installed=False,
                   restored=False,fixture=str(fixture),operator_confirmed_isolation=True,
                   operator_measured_bus_v=0,commands=[],operations=[],hv_release_approved=False)
    else:state=json.loads(state_path.read_text())
    def save():state_path.write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    ssh=['ssh','-p','2222','-i',str(ROOT/'.unoq_ssh/id_ed25519'),'-o',
         'UserKnownHostsFile='+str(ROOT/'.unoq_ssh/known_hosts'),'-o','StrictHostKeyChecking=yes','arduino@192.168.1.138']
    scp=['scp','-P','2222','-i',str(ROOT/'.unoq_ssh/id_ed25519'),'-o',
         'UserKnownHostsFile='+str(ROOT/'.unoq_ssh/known_hosts'),'-o','StrictHostKeyChecking=yes']
    def run(cmd,label,source=None,timeout=150):
        save()
        result=subprocess.run([str(x) for x in cmd],input=source,capture_output=True,text=True,
                              encoding='utf-8',errors='replace',timeout=timeout)
        (session/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        state['operations'].append(dict(label=label,exit_code=result.returncode));save()
        if result.returncode:raise RuntimeError(label+' failed')
        return result.stdout
    def remote_code(source,label):return run(ssh+[VENV+' -'],label,source,timeout=40)
    def remote_hashes(label):
        result=remote_code('''from pathlib import Path
import hashlib
for p in ('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py','/home/arduino/.config/mic-ai/vbus_calibration.json'):
 print(hashlib.sha256(Path(p).read_bytes()).hexdigest())
''',label).splitlines()
        assert result==[HMI_SHA,CAL_SHA],result
    opener=build_opener(ProxyHandler({}));token=read_token(str(ROOT/'.unoq_ssh/control_token'))
    def idle(url,pair):
        s=get_status(opener,url)
        assert (s['fw_build'],s['mc_fw_build'])==pair,s
        assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0
        assert 0<=s['vdc']<=2 and 0<=s['bp_vbus_raw']<=20
        assert not(s['bp_status']&0x22) and s['bp_ext']==0
        assert s['bp_age_ms']<300 and s['bp_transport_fault']==0
        return s
    def nuc_flash(image,label):
        state['nucleo_may_be_modified']=True;save()
        run([PROGRAMMER,'-c','port=SWD','mode=UR','sn='+SERIAL,'-w',image,'0x08000000','-v','-rst'],label,timeout=90)
        target=session/(label+'_readback.bin')
        run([PROGRAMMER,'-c','port=SWD','mode=HOTPLUG','sn='+SERIAL,'-u','0x08000000',str(image.stat().st_size),target],label+'_readback',timeout=60)
        assert sha(target)==sha(image),label
    def uno_flash(image,label):
        # A disconnected ADB transport fails before any flash or restoration attempt.
        assert run(['adb','-s','3880458060','get-state'],label+'_adb_state',timeout=15).strip()=='device'
        state['uno_may_be_modified']=True;save()
        run(['arduino-cli','upload','-p','COM10','-b','arduino:zephyr:unoq','-i',image,
             '--upload-property','upload.artifacts.sketch='+str(image),
             '--upload-property','upload.port.properties.serialNumber=3880458060',
             '--upload-property','build.variant.path='+str(ROOT/'tools'),
             '--upload-property','openocd_cfg=flash_verify_unoq_sketch.cfg'],label,timeout=180)
    def stop_shadow():
        remote_code(f'''from pathlib import Path
import os,signal
root=Path({REMOTE!r}); pidfile=root/'hmi.pid'
if pidfile.exists():
 pid=int(pidfile.read_text()); proc=Path('/proc')/str(pid)
 if proc.exists():
  assert proc.stat().st_uid==os.getuid()
  assert str(root/'server.py').encode() in (proc/'cmdline').read_bytes().split(b'\\x00')
  os.kill(pid,signal.SIGTERM)
 print('Fixture HMI stopped')
''','stop_fixture_hmi')
    def restore():
        assert (sha(PROD_U),sha(PROD_N))==PROD_HASHES
        if state.get('installed'):
            h=WifiHmi('http://192.168.1.138:8081',token,state['commands'],via_wsl=False)
            h.fail_safe_stop();h.close()
        if state.get('nucleo_may_be_modified'):nuc_flash(PROD_N,'restore_nucleo')
        if state.get('uno_may_be_modified'):uno_flash(PROD_U,'restore_uno')
        stop_shadow()
        h=WifiHmi('http://192.168.1.138:8080',token,state['commands'],via_wsl=False)
        after=wait_status(h,lambda s:(s.get('fw_build'),s.get('mc_fw_build'))==(2026101205,2026101204)
                          and s.get('pwm')==0 and s.get('hmi_hv_armed')==0,60,'restored production pair')
        h.close();remote_hashes('restored_hmi_calibration')
        state['after_restore']=after;state['restored']=True;state['installed']=False;save()
    try:
        if a.action=='install':
            assert (sha(PROD_U),sha(PROD_N))==PROD_HASHES
            for report in (HERE/'pwm_fixture_selftest_r5/report.json',HERE/'pwm_fixture_code_r1/report.json',fixture/'uno_build/llext-check.json'):
                assert json.loads(report.read_text())['pass'] is True
            for directory,file,build in ((fixture/'uno_build','unoq_mcsdk_scalar.build-manifest.json',PAIR[0]),
                 (fixture/'nucleo/STM32CubeIDE/Debug','ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json',PAIR[1])):
                manifest=json.loads((directory/file).read_text(encoding='utf-8-sig'))
                assert manifest['firmware_build_id']==build
                for item in manifest['artifacts']:assert sha(directory/item['file'])==item['sha256'].lower()
            before=idle('http://192.168.1.138:8080',(2026101205,2026101204));state['before']=before
            (session/'before_logs.txt').write_text(get_logs(opener,'http://192.168.1.138:8080',token,2),encoding='utf-8')
            remote_hashes('before_hmi_calibration')
            raw=session/'production_nucleo_before.bin'
            run([PROGRAMMER,'-c','port=SWD','mode=HOTPLUG','sn='+SERIAL,'-u','0x08000000',str(PROD_N.stat().st_size),raw],'verify_installed_nucleo',timeout=60)
            assert sha(raw)==PROD_HASHES[1]
            # Preserve the installed HMI; a separate LV-only fixture process uses port 8081.
            expected_hmi=sha(fixture/'web_hmi/server.py')
            remote_code(f"from pathlib import Path\nimport hashlib\np=Path({REMOTE!r})\nif p.exists():\n assert not (p/'hmi.pid').exists()\n assert hashlib.sha256((p/'server.py').read_bytes()).hexdigest()=={expected_hmi!r}\nelse:p.mkdir(parents=True)\n",'create_fixture_hmi_directory')
            run(scp+[fixture/'web_hmi/server.py','arduino@192.168.1.138:'+REMOTE+'/server.py'],'stage_fixture_hmi')
            uno_flash(fixture/'uno_build/UNOQ_MOTOR.ino.elf-zsk.bin','install_fixture_uno')
            nuc_flash(fixture/'nucleo/STM32CubeIDE/Debug'/NB,'install_fixture_nucleo')
            spawn=f'''from pathlib import Path
import subprocess
root=Path({REMOTE!r});log=(root/'hmi.log').open('ab')
args=[{VENV!r},str(root/'server.py'),'--bind','0.0.0.0','--port','8081','--router','/var/run/arduino-router.sock','--standalone-lv','--lv-arm-max-vdc','2','--start-runlimit-sec','3','--control-token-file','/home/arduino/.config/mic-ai/control_token','--log-file',str(root/'events.log')]
p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=str(root))
(root/'hmi.pid').write_text(str(p.pid));print(p.pid)
'''
            remote_code(spawn,'start_fixture_hmi')
            h=WifiHmi('http://192.168.1.138:8081',token,state['commands'],via_wsl=False)
            status=wait_status(h,lambda s:(s.get('fw_build'),s.get('mc_fw_build'))==PAIR and s.get('bp_softstart_ready')==1,60,'fixture pair settled')
            idle('http://192.168.1.138:8081',PAIR)
            state['fixture_status']=status;state['installed']=True;save();h.close()
            print(json.dumps({'installed':True,'pair':PAIR,'pwm':status['pwm'],'vdc':status['vdc'],'hardware_start_commands':0},indent=2))
        elif a.action=='restore':
            restore();print(json.dumps({'restored':state['restored'],'pair':[2026101205,2026101204]}))
        elif a.action=='ready':
            assert state['installed'] and not state['restored']
            idle('http://192.168.1.138:8081',PAIR)
            h=WifiHmi('http://192.168.1.138:8081',token,state['commands'],via_wsl=False)
            h.command('STOP')
            for _ in range(3):
                h.command('CLEAR');time.sleep(.35)
                s=h.status()
                if s['bp_fault']==0 and s['estop']==0:break
            assert s['bp_fault']==0 and s['estop']==0 and s['hmi_local_stop_latched']==0
            h.command('MODE VF');h.command('SET FREQ 5')
            state['ready_status']=h.status();save();h.close()
            print(json.dumps({'ready':True,'pwm':state['ready_status']['pwm'],'armed':state['ready_status']['hmi_hv_armed']}))
        else:
            assert state['installed'] and not state['restored']
            idle('http://192.168.1.138:8081',PAIR)
            from saleae import automation
            from saleae_pwm_analyze import analyze_csv,load_csv
            import threading,winsound
            folder=session/('run_'+str(time.time_ns()));folder.mkdir()
            h=WifiHmi('http://192.168.1.138:8081',token,state['commands'],via_wsl=False)
            h.post('/api/hv-arm',{'action':'arm','confirm':'ARM LV HV OFF'},'isolated ARM')
            with automation.Manager.connect(port=10430,connect_timeout_seconds=5) as manager:
                assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
                with manager.start_capture(device_id='A7D1BB81883C0092',
                      device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(6)),digital_sample_rate=4_000_000),
                      capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=5))) as cap:
                    time.sleep(.2)
                    started=time.monotonic()
                    h.post('/api/start-sequence',{'runlimit_s':3},'isolated START 3s')
                    winsound.Beep(1600,150)
                    print('PWM_STARTED_PRESS_B1_NOW',flush=True)
                    rows=[]
                    while time.monotonic()-started<4.4:
                        rows.append({'elapsed_from_start_request_s':time.monotonic()-started,'status':h.status()})
                    cap.wait();cap.save_capture(str(folder/'capture.sal'))
                    cap.export_raw_data_csv(directory=str(folder/'csv'),digital_channels=list(range(6)))
            h.fail_safe_stop();h.close();save()
            (folder/'status.json').write_text(json.dumps(rows,indent=2)+'\n')
            csv=folder/'csv/digital.csv'
            times,values=load_csv(csv,list(range(6)))
            edges=[times[i] for c in range(6) for i in range(1,len(times)) if values[c][i]!=values[c][i-1]]
            last=max(edges,default=times[0]);tail=[i for i,t in enumerate(times) if t>=last+1/4_000_000]
            analysis=analyze_csv(csv,expect_pwm=True,selected_sample_rate_hz=4_000_000,max_sample_period_ns=250)
            local=[r for r in rows if r['status'].get('hmi_local_stop_latched')==1]
            checks={'six_outputs_were_active':all(analysis['channels'][str(c)]['edges']>100 for c in range(6)),
                    'no_pwm_overlap':analysis['no_overlap_pass'],
                    'six_outputs_low_tail':bool(tail) and all(values[c][i]==0 for c in range(6) for i in tail),
                    'off_tail_at_least_500ms':times[-1]-last>=.5,
                    'local_stop_telemetry':bool(local) and all(r['status']['pwm']==0 and r['status']['bp_fault']==1 for r in local),
                    'local_stop_before_3s_limit':bool(local) and local[0]['elapsed_from_start_request_s']<3,
                    'zero_bus':all(0<=r['status']['vdc']<=2 for r in rows),
                    'no_uart_errors':all(r['status']['bp_bad_cnt']==0 and r['status']['bp_transport_fault']==0 for r in rows)}
            result={'pass':all(checks.values()),'checks':checks,'last_pwm_edge_s':last,'low_tail_s':times[-1]-last,
                    'physical_button_edge_measured':False,'exact_button_to_off_latency_measured':False,
                    'production_image_active_pwm_measured':False,'hv_release_approved':False,
                    'scope':'detached 1204-derived fixture, normal Uno supervision; six PWM channels only'}
            (folder/'report.json').write_text(json.dumps(result,indent=2)+'\n');state['last_run']=str(folder);save()
            print(json.dumps(result,indent=2))
    except Exception as exc:
        state['error']=str(exc);save()
        if a.action in ('ready','run'):
            try:
                guard=WifiHmi('http://192.168.1.138:8081',token,state['commands'],via_wsl=False)
                guard.fail_safe_stop();guard.close();save()
            except Exception as stop_error:state['stop_error']=str(stop_error);save()
        if a.action=='install' and (state.get('uno_may_be_modified') or state.get('nucleo_may_be_modified')):
            try:restore()
            except Exception as recovery:state['restore_error']=str(recovery);save()
        raise
    finally:save()


if __name__=='__main__':main()

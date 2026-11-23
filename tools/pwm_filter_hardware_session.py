"""Pinned detached PWM qualification and restoration of the new working pair."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.request import ProxyHandler, build_opener
from collect_wifi_telemetry import get_status, get_logs, read_token
from run_wifi_nucleo_pwm_bench import WifiHmi,wait_status
from run_mcsdk_logic_bench import PROGRAMMER,SERIAL
from install_passive_break_decoder_fix import validate_idle,FIRST_FIELDS,ERROR_FIELDS

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r3'
BASE_HMI='992b3c20c8573681f195de3a208a461359c22673b83e3f2d578f87e16ce212d1'
CAL_SHA='a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17'
REMOTE='/home/arduino/.local/share/mic-ai/pwm-filter-hil-20261014'
HMI_ROOT='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi'
VENV=HMI_ROOT+'/.venv/bin/python'
NB='ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin'
PAIR=(2026101498,2026101499)
PROD=(2026101405,2026101404)
OLDPAIR=(2026101205,2026101204)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def configure(package):
    global PACKAGE,PAIR,PROD,OLDPAIR,BASE_HMI,REMOTE
    PACKAGE=package
    manifest=json.loads((package/'manifest.json').read_text())
    PAIR=tuple(manifest['fixture_pair']);PROD=tuple(manifest['production_pair'])
    OLDPAIR=tuple(manifest.get('predecessor_pair',(2026101205,2026101204)))
    BASE_HMI=manifest.get('predecessor_hmi_sha256',BASE_HMI)
    if package.name!='pwm_filter_pair_r3':REMOTE='/home/arduino/.local/share/mic-ai/pwm-filter-hil-20261014-'+package.name

class Session:
    def __init__(self,folder,package=None):
        global PROD
        self.folder=folder;self.path=folder/'session.json'
        self.state=json.loads(self.path.read_text()) if self.path.exists() else dict(operations=[],commands=[],hv_release_approved=False)
        if package is not None:configure(package)
        elif self.state.get('package'):configure(Path(self.state['package']))
        self.state['package']=str(PACKAGE)
        folder.mkdir(exist_ok=True,parents=True)
        self.ssh=['ssh','-p','2222','-i',str(ROOT/'.unoq_ssh/id_ed25519'),'-o','UserKnownHostsFile='+str(ROOT/'.unoq_ssh/known_hosts'),
                  '-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=5','arduino@192.168.1.138']
        self.scp=['scp','-P','2222']+self.ssh[3:-1]
        self.token=read_token(str(ROOT/'.unoq_ssh/control_token'));self.opener=build_opener(ProxyHandler({}))
        package_manifest=json.loads((PACKAGE/'manifest.json').read_text())
        self.proof=json.loads((PACKAGE/package_manifest.get('qualification_report','qualification/report.json')).read_text());assert self.proof['pass']
        for p in self.proof['packages'].values():
            for relative,digest in p['artifacts_sha256'].items():assert sha(PACKAGE/relative)==digest
        self.hmi_sha=sha(PACKAGE/'production/web_hmi/server.py')
        source_manifest=json.loads((PACKAGE/'production/manifest.json').read_text())
        assert self.hmi_sha==source_manifest['hmi_sha256']
        if source_manifest.get('reject_instrumentation'):
            reject_proof=json.loads((PACKAGE/package_manifest.get('reject_selftest_report','reject_selftest_r1/report.json')).read_text())
            assert reject_proof['pass'] and reject_proof['hmi_sha256']==self.hmi_sha
            assert reject_proof['actual_parser_source_sha256']==sha(PACKAGE/'production/UNOQ_MOTOR/UNOQ_MOTOR.ino')
            assert reject_proof['header_sha256']==sha(PACKAGE/'production/UNOQ_MOTOR/break_wire.h')
        if source_manifest.get('sender_requires_published_safe_off'):
            send_proof=json.loads((PACKAGE/'stop_sync_selftest_r2/report.json').read_text())
            assert send_proof['pass'] and send_proof['mutation_detected']
            assert send_proof['mcu_source_sha256']==sha(PACKAGE/'fixture/nucleo/Src/main.c')
        if self.state.get('normal_start_hmi_candidate'):
            normal=Path(self.state['normal_start_hmi_candidate'])
            mf=json.loads((normal/'manifest.json').read_text())
            tests=json.loads((normal/'selftest.json').read_text())
            guards=json.loads((normal/'guards_r1/report.json').read_text())
            assert mf['base_hmi_sha256']==self.hmi_sha and mf['pair']==list(PROD)
            assert tests['pass'] and guards['pass'] and len(guards['suites'])==5
            assert sha(normal/'web_hmi/server.py')==mf['hmi_sha256']==tests['hmi_sha256']==self.state['normal_start_hmi_sha256']
            self.hmi_sha=mf['hmi_sha256']
        if self.state.get('uart_recovery_installed'):
            paths=self.state.get('uart_recovery_history',[])+[self.state['uart_recovery_candidate']]
            for path in paths:
                recovery=Path(path)
                mf=json.loads((recovery/'manifest.json').read_text())
                proof=json.loads((recovery/'qualification.json').read_text())
                guards=json.loads((recovery/mf.get('hmi_guard_report','hmi_guards/report.json')).read_text())
                assert mf['installed'] and mf['predecessor_pair']==list(PROD)
                assert proof['pass'] and guards['pass'] and len(guards['suites'])==5
                assert sha(recovery/'web_hmi/server.py')==mf['hmi_sha256']==proof['hmi_sha256']
                if mf.get('manual_scalar'):
                    manual=json.loads((recovery/mf['manual_selftest_report']).read_text())
                    assert manual['pass'] and manual['hmi_sha256']==guards['hmi_sha256']==mf['hmi_sha256']
                    for name,digest in mf['hmi_static_sha256'].items():assert sha(recovery/'web_hmi/static'/name)==digest
                for relative,digest in proof['artifacts_sha256'].items():assert sha(recovery/relative)==digest
                self.hmi_sha=mf['hmi_sha256'];PROD=tuple(mf['pair'])
            assert self.hmi_sha==self.state['uart_recovery_hmi_sha256']
        self.save()
    def save(self):self.path.write_text(json.dumps(self.state,indent=2)+'\n')
    def run(self,cmd,label,source=None,timeout=90):
        self.save();r=subprocess.run([str(x) for x in cmd],input=source,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        (self.folder/(label+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        self.state['operations'].append(dict(label=label,exit_code=r.returncode));self.save()
        if r.returncode:raise RuntimeError(label+' failed; retained log available')
        return r.stdout
    def remote(self,source,label):return self.run(self.ssh+[VENV+' -'],label,source,40)
    def hmi(self,fixture=True):return WifiHmi('http://192.168.1.138:'+('8081' if fixture else '8080'),self.token,self.state['commands'],via_wsl=False)
    def idle(self,fixture=True,pair=None):
        s=get_status(self.opener,'http://192.168.1.138:'+('8081' if fixture else '8080'))
        assert (s['fw_build'],s['mc_fw_build'])==(pair or (PAIR if fixture else PROD))
        assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0
        assert 0<=s['vdc']<=2 and 0<=s['bp_vbus_raw']<=20 and s['bp_vbus_valid']==1
        assert not(s['bp_status']&0x22) and s['bp_ext']==0 and s['bp_age_ms']<300 and s['bp_transport_fault']==0
        return s
    def hashes(self,label):
        result=self.remote(f'''from pathlib import Path
import hashlib
for path in ({HMI_ROOT+'/server.py'!r},'/home/arduino/.config/mic-ai/vbus_calibration.json'):
 print(hashlib.sha256(Path(path).read_bytes()).hexdigest())
''',label).splitlines()
        assert result==[self.hmi_sha,CAL_SHA]
    def install_hmi(self):
        assert not self.state.get('hmi_installed')
        before=self.idle(False,OLDPAIR)
        assert before['mc_diag_valid']==1 and before['hmi_hv_started']==0 and before['hmi_powered_trial_enabled']==0
        self.state['before']=before;self.save()
        (self.folder/'before_logs.txt').write_text(get_logs(self.opener,'http://192.168.1.138:8080',self.token,2))
        stage_name=PACKAGE.name+'.staged';backup_name='server.py.before_'+PACKAGE.name
        common=f'''from pathlib import Path
import hashlib,os,signal,shutil,subprocess,json
root=Path({HMI_ROOT!r});target=root/'server.py';stage=root/{stage_name!r};backup=root/{backup_name!r}
cal=Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def prop(name):return subprocess.check_output(['systemctl','show','unoq-hmi.service','-p',name,'--value'],text=True).strip()
def owned_pid():
 assert prop('User')=='arduino' and prop('Restart')=='always'
 pid=int(prop('MainPID'));assert pid>1
 proc=Path('/proc')/str(pid)
 assert proc.stat().st_uid==os.getuid() and (proc/'cwd').resolve()==root
 assert b'server.py' in (proc/'cmdline').read_bytes().split(bytes([0]))
 return pid
assert digest(cal)=={CAL_SHA!r}
'''
        self.remote(common+f'assert digest(target)=={BASE_HMI!r} and not stage.exists() and not backup.exists()\nowned_pid()\n','hmi_precheck')
        self.run(self.scp+[PACKAGE/'production/web_hmi/server.py','arduino@192.168.1.138:'+HMI_ROOT+'/'+stage_name],'stage_production_hmi',timeout=40)
        self.remote(common+f'''assert digest(target)=={BASE_HMI!r} and digest(stage)=={self.hmi_sha!r} and not backup.exists()
pid=owned_pid();compile(stage.read_text(),str(stage),'exec');shutil.copy2(target,backup)
assert digest(backup)=={BASE_HMI!r};stage.chmod(target.stat().st_mode);stage.replace(target)
assert digest(target)=={self.hmi_sha!r}
os.kill(pid,signal.SIGTERM);print('Tested new HMI installed; previous file backed up')
''','install_production_hmi')
        self.state['hmi_installed']=True;self.save()
        h=self.hmi(False)
        after=wait_status(h,lambda s:(s.get('fw_build'),s.get('mc_fw_build'))==OLDPAIR and s.get('bp_age_ms',9999)<300,30,'new HMI on previous MCU pair')
        h.close();self.idle(False,OLDPAIR)
        assert all(before.get(k)==after.get(k) for k in FIRST_FIELDS+ERROR_FIELDS)
        self.hashes('hmi_calibration_verified')
        self.state['after_hmi']=after;self.save()
    def nuc_flash(self,name,label):
        assert not self.state.get('uart_recovery_installed'),'Use the permanent working bundle; historical fixture flashing is disabled'
        image=PACKAGE/name/'nucleo/STM32CubeIDE/Debug'/NB
        self.state['nucleo_may_be_modified']=True;self.save()
        self.run([PROGRAMMER,'-c','port=SWD','mode=UR','sn='+SERIAL,'-w',image,'0x08000000','-v','-rst'],label)
        target=self.folder/(label+'_readback.bin')
        self.run([PROGRAMMER,'-c','port=SWD','mode=HOTPLUG','sn='+SERIAL,'-u','0x08000000',image.stat().st_size,target],label+'_readback')
        assert sha(target)==sha(image)
        self.state[label+'_byte_verified']=True;self.save()
    def uno_flash(self,name,label):
        assert not self.state.get('uart_recovery_installed'),'Use the permanent working bundle; historical fixture flashing is disabled'
        image=PACKAGE/name/'uno_build/UNOQ_MOTOR.ino.elf-zsk.bin'
        assert self.run(['adb','-s','3880458060','get-state'],label+'_adb',timeout=15).strip()=='device'
        self.state['uno_may_be_modified']=True;self.save()
        self.run(['arduino-cli','upload','-p','COM10','-b','arduino:zephyr:unoq','-i',image,
          '--upload-property','upload.artifacts.sketch='+str(image),
          '--upload-property','upload.port.properties.serialNumber=3880458060',
          '--upload-property','build.variant.path='+str(ROOT/'tools'),
          '--upload-property','openocd_cfg=flash_verify_unoq_sketch.cfg'],label,timeout=180)
        self.state[label+'_verified']=True;self.save()
    def install_fixture(self):
        assert self.state.get('hmi_installed') and not self.state.get('uno_may_be_modified')
        self.idle(False,OLDPAIR);self.hashes('pre_fixture_hashes')
        expected=sha(PACKAGE/'fixture/web_hmi/server.py')
        self.remote(f"from pathlib import Path\np=Path({REMOTE!r})\nassert not p.exists()\np.mkdir(parents=True)\n",'create_fixture_dir')
        self.run(self.scp+[PACKAGE/'fixture/web_hmi/server.py','arduino@192.168.1.138:'+REMOTE+'/server.py'],'stage_fixture_hmi',timeout=40)
        self.uno_flash('fixture','fixture_uno');self.nuc_flash('fixture','fixture_nucleo')
        self.start_fixture(expected)
    def start_fixture(self,expected):
        self.remote(f'''from pathlib import Path
import subprocess,hashlib
root=Path({REMOTE!r});assert hashlib.sha256((root/'server.py').read_bytes()).hexdigest()=={expected!r}
log=(root/'hmi.log').open('ab')
p=subprocess.Popen([{VENV!r},str(root/'server.py'),'--bind','0.0.0.0','--port','8081','--router','/var/run/arduino-router.sock','--standalone-lv','--lv-arm-max-vdc','2','--start-runlimit-sec','3','--control-token-file','/home/arduino/.config/mic-ai/control_token','--log-file',str(root/'events.log')],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=str(root))
(root/'hmi.pid').write_text(str(p.pid));print(p.pid)
''','start_fixture_hmi')
        self.state['fixture_programmed']=True;self.save()
        self.settle_fixture()
    def resume_fixture(self):
        assert self.state.get('fixture_uno_verified') and not self.state.get('fixture_programmed')
        image=PACKAGE/'fixture/nucleo/STM32CubeIDE/Debug'/NB
        target=self.folder/'fixture_nucleo_readback.bin'
        self.run([PROGRAMMER,'-c','port=SWD','mode=HOTPLUG','sn='+SERIAL,'-u','0x08000000',image.stat().st_size,target],'fixture_nucleo_readback')
        assert sha(target)==sha(image),'Interrupted Nucleo command did not install expected image'
        self.state['fixture_nucleo_byte_verified']=True;self.save()
        self.start_fixture(sha(PACKAGE/'fixture/web_hmi/server.py'))
    def settle_fixture(self):
        h=self.hmi()
        try:s=wait_status(h,lambda s:(s.get('fw_build'),s.get('mc_fw_build'))==PAIR and s.get('bp_softstart_ready')==1 and s.get('bp_age_ms',9999)<300,45,'new fixture RPC and UART')
        finally:h.close()
        self.idle();self.state['fixture_status']=s;self.state['installed']=True;self.save()
    def ready(self):
        assert self.state.get('installed') and not self.state.get('restored')
        before=self.idle();self.state['before_clear']=before;self.save()
        h=self.hmi()
        try:
            if before['bp_fault'] or before['estop']:
                # Only the stopped zero-bus programming cutover is acknowledged once.
                assert before['pwm']==0 and before['vdc']==0 and before['bp_transport_fault']==0
                h.command('STOP');h.command('CLEAR')
                wait_status(h,lambda s:s.get('bp_fault')==0 and s.get('estop')==0,8,'single programming-cutover CLEAR')
            h.command('MODE VF');h.command('SET FREQ 5')
            after=h.status();assert after['bp_fault']==0 and after['estop']==0 and after['hmi_local_stop_latched']==0
            self.state['ready_status']=after;self.save()
        finally:h.close()
    def capture(self):
        assert self.state.get('ready_status') and self.state.get('installed') and not self.state.get('restored')
        before=self.idle();self.state['pre_capture_status']=before;self.save()
        from saleae import automation
        from saleae_pwm_analyze import analyze_csv,load_csv
        folder=self.folder/('run_'+str(time.time_ns()));folder.mkdir()
        h=self.hmi();rows=[]
        try:
            with automation.Manager.connect(port=10430,connect_timeout_seconds=5) as manager:
                assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
                # Start a capture before arming, so a busy Logic UI cannot cause a blind run.
                with manager.start_capture(device_id='A7D1BB81883C0092',device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(6)),digital_sample_rate=4_000_000),capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=8))) as cap:
                    h.post('/api/hv-arm',{'action':'arm','confirm':'ARM LV HV OFF'},'detached ARM')
                    started=time.monotonic();h.post('/api/start-sequence',{'runlimit_s':3},'detached START 3s')
                    print('PWM_STARTED_AUTO_STOP_3S',flush=True)
                    while time.monotonic()-started<5.5:
                        h.post('/api/operator-heartbeat',{},'detached operator heartbeat')
                        rows.append({'elapsed_s':time.monotonic()-started,'status':h.status()});time.sleep(.05)
                    cap.wait();cap.save_capture(str(folder/'capture.sal'))
                    cap.export_raw_data_csv(directory=str(folder/'csv'),digital_channels=list(range(6)))
        finally:
            self.state['stop_result']=h.fail_safe_stop();h.close();self.save()
            (folder/'status.json').write_text(json.dumps(rows,indent=2)+'\n')
        csv=folder/'csv/digital.csv';analysis=analyze_csv(csv,expect_pwm=True,selected_sample_rate_hz=4_000_000,max_sample_period_ns=250)
        (folder/'waveform.json').write_text(json.dumps(analysis,indent=2)+'\n')
        times,values=load_csv(csv,list(range(6)))
        edges=[times[i] for c in range(6) for i in range(1,len(times)) if values[c][i]!=values[c][i-1]]
        first,last=min(edges,default=0),max(edges,default=0)
        tail=[i for i,t in enumerate(times) if t>last+1/4_000_000]
        after=self.idle();baseline=before
        checks=dict(six_active=all(analysis['channels'][str(c)]['edges']>100 for c in range(6)),
           no_overlap=analysis['no_overlap_pass'],six_low_tail=bool(tail) and all(values[c][i]==0 for c in range(6) for i in tail),
           off_tail_500ms=times[-1]-last>=.5,run_at_most_3s=last-first<=3.05,
           zero_bus=bool(rows) and all(0<=r['status']['vdc']<=2 for r in rows),
           no_new_uart_errors=bool(rows) and all(all(r['status'].get(k)==baseline.get(k) for k in ERROR_FIELDS) for r in rows),
           carrier_16k=all(abs(analysis['channels'][str(c)]['freq_hz_from_rising']-16000)<100 for c in range(6)))
        result=dict(pass_=all(checks.values()),checks=checks,active_span_s=last-first,low_tail_s=times[-1]-last,
          button_latency_measured=False,production_image_active_pwm_measured=False,hv_release_approved=False,after=after)
        result['pass']=result.pop('pass_');(folder/'report.json').write_text(json.dumps(result,indent=2)+'\n')
        self.state['last_run']=str(folder);self.state['capture_pass']=result['pass'];self.save()
        print(json.dumps({k:v for k,v in result.items() if k!='after'},indent=2));assert result['pass'],'Detached waveform test failed'
    def stop_shadow(self):
        self.remote(f'''from pathlib import Path
import os,signal,time
root=Path({REMOTE!r});p=root/'hmi.pid'
if p.exists():
 pid=int(p.read_text());proc=Path('/proc')/str(pid)
 if proc.exists():
  assert proc.stat().st_uid==os.getuid() and str(root/'server.py').encode() in (proc/'cmdline').read_bytes().split(bytes([0]))
  os.kill(pid,signal.SIGTERM)
  for attempt in range(30):
   if not proc.exists():break
   time.sleep(.1)
print('Owned fixture HMI stopped')
''','stop_fixture_hmi')
    def pause_primary(self):
        pid=int(self.remote(f'''from pathlib import Path
import os,signal,subprocess,hashlib
root=Path({HMI_ROOT!r})
assert hashlib.sha256((root/'server.py').read_bytes()).hexdigest()=={self.hmi_sha!r}
prop=lambda name:subprocess.check_output(['systemctl','show','unoq-hmi.service','-p',name,'--value'],text=True).strip()
assert prop('User')=='arduino' and prop('Restart')=='always'
pid=int(prop('MainPID'));proc=Path('/proc')/str(pid)
assert pid>1 and proc.stat().st_uid==os.getuid() and (proc/'cwd').resolve()==root
assert b'server.py' in (proc/'cmdline').read_bytes().split(bytes([0]))
os.kill(pid,signal.SIGSTOP);print(pid)
''','pause_owned_hmi_before_mcu_swap').strip())
        self.state['paused_primary_pid']=pid;self.save()
    def resume_primary(self):
        pid=self.state.get('paused_primary_pid');assert type(pid) is int and pid>1
        self.remote(f'''from pathlib import Path
import os,signal,hashlib
root=Path({HMI_ROOT!r});proc=Path('/proc')/str({pid})
assert proc.exists() and proc.stat().st_uid==os.getuid() and (proc/'cwd').resolve()==root
assert b'server.py' in (proc/'cmdline').read_bytes().split(bytes([0]))
assert hashlib.sha256((root/'server.py').read_bytes()).hexdigest()=={self.hmi_sha!r}
os.kill({pid},signal.SIGCONT);print('Owned primary HMI resumed')
''','resume_owned_hmi_after_mcu_swap')
        self.state['paused_primary_pid']=None;self.save()
    def restore(self):
        assert self.state.get('fixture_programmed') and not self.state.get('restored')
        h=self.hmi();h.fail_safe_stop();h.close();self.idle()
        self.stop_shadow();self.pause_primary()
        try:
            if not self.state.get('production_nucleo_byte_verified'):self.nuc_flash('production','production_nucleo')
            if not self.state.get('production_uno_verified'):self.uno_flash('production','production_uno')
            time.sleep(7) # Uno's Bridge.begin startup deliberately waits six seconds.
        finally:self.resume_primary()
        self.settle_production()
    def settle_production(self):
        h=self.hmi(False)
        try:s=wait_status(h,lambda s:(s.get('fw_build'),s.get('mc_fw_build'))==PROD and s.get('pwm')==0 and s.get('hmi_hv_armed')==0 and s.get('bp_age_ms',9999)<300,45,'new working pair RPC')
        finally:h.close()
        self.idle(False);self.hashes('new_working_pair_hmi_calibration')
        self.state['restored']=True;self.state['installed']=False;self.state['after_restore']=s;self.save()
    def acknowledge_swap_timeout(self):
        assert self.state.get('production_nucleo_byte_verified') and self.state.get('production_uno_verified')
        h=self.hmi(False)
        try:
            before=h.status()
            assert (before['fw_build'],before['mc_fw_build'])==PROD
            assert before['state']=='SAFE' and before['pwm']==0 and before['hmi_hv_armed']==0
            assert before['vdc']==0 and before['bp_vbus_raw']==0 and before['bp_vbus_valid']==1
            assert not(before['bp_status']&0x22) and before['bp_ext']==0 and before['bp_age_ms']<300
            assert before['bp_transport_fault']==6 and before['mc_last_bad_reason']==13
            assert all(before.get(k)==0 for k in ('bp_bad_integrity','bp_bad_sequence','uno_rx_hw_errors','uno_rx_hw_flags','uno_rx_dropped'))
            self.state['programming_timeout_before_clear']=before;self.save()
            (self.folder/'programming_timeout_before_clear.json').write_text(json.dumps(before,indent=2)+'\n')
            h.command('CLEAR')
            after=wait_status(h,lambda d:d.get('bp_transport_fault')==0 and d.get('pwm')==0 and d.get('hmi_hv_armed')==0,8,'single stopped programming timeout acknowledgement')
            self.state['programming_timeout_acknowledged']=True;self.state['programming_timeout_after_clear']=after;self.save()
        finally:h.close()
        self.settle_production()
    def observe(self):
        assert self.state.get('restored')
        rows=[];start=time.monotonic()
        while True:
            s=self.idle(False);rows.append({'elapsed_s':time.monotonic()-start,'status':s})
            if rows[-1]['elapsed_s']-rows[0]['elapsed_s']>=30:break
            time.sleep(1)
        assert all(all(r['status'].get(k)==rows[0]['status'].get(k) for k in ERROR_FIELDS) for r in rows)
        assert rows[-1]['status']['bp_good_cnt']-rows[0]['status']['bp_good_cnt']>=100
        self.hashes('final_hmi_calibration_hashes');(self.folder/'production_idle.json').write_text(json.dumps(rows,indent=2)+'\n')
        self.state['idle_30s_pass']=True;self.save()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('install_hmi','install_fixture','resume_fixture','settle_fixture','ready','capture','restore','settle_production','observe','resume_primary','acknowledge_swap_timeout'));p.add_argument('--session',required=True,type=Path);p.add_argument('--package',type=Path)
    a=p.parse_args();s=Session(a.session.resolve(),a.package.resolve() if a.package else None)
    try:getattr(s,a.action)();print(json.dumps({'action':a.action,'completed':True}))
    except Exception as exc:s.state['error']=str(exc);s.save();raise

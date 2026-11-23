"""Install the selected Uno release on the J1-OFF, <20V USB bench.
Never flash/reset Nucleo or send START/CLEAR/ARM. Preserve backups and calibration.
Do not rerun after a partial installation; inspect its durable report first.
"""
import argparse,ast,json,hashlib,subprocess,shlex,time
from pathlib import Path
import prepare_rpc_stage_trace as p
import prepare_rpc_capture_pages as pages
import install_bkin_boot_armed_pair as io
from unoq_wifi_hmi_deploy import ssh_base,scp_base
from install_sd_break_filter_usb_pair import tunneled
from wifi_stop_tail_probe import parse_registers

OLD=(2026111809,2026111810);NEW=(2026112011,2026111810)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def safe(s,pair):
    assert (s['fw_build'],s['mc_fw_build'])==pair
    assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0
    assert not s['bp_status']&0x22
    assert s['bp_vbus_valid']==1 and 0<=s['vdc']<20 and 0<=s['bp_vdc']<20
    assert 0<=s['mc_age_ms']<300 and s['rpc_schema_version']==3
    assert all(s.get(k)==0 for k in ('precharge','pfc','brake','bp_ext'))
    # OFF programming, not a motor-start gate. Archive existing fault latches.

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirmed-j1-off-meter-below20-usb',action='store_true')
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--capture-pages',action='store_true',help='Install 2013 over 2011')
    a=parser.parse_args()
    target = pages.OUT if a.capture_pages else p.OUT
    predecessor = pages.BASE if a.capture_pages else p.BASE
    old_pair = NEW if a.capture_pages else OLD
    new_pair = (int(pages.NEW_UNO), NEW[1]) if a.capture_pages else NEW
    build = new_pair[0]
    manifest=json.loads((target/'release_manifest.json').read_text())
    assert manifest['built'] and not manifest['installed']
    assert json.loads((target/'verification/report.json').read_text())['passed']
    assert json.loads((target/'build/uno/llext-check.json').read_text())['pass']
    if a.capture_pages:
        assert tuple(manifest['pair']) == new_pair and manifest['pc_capture_tests_passed']
        image = target/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'
        assert sha(image) == manifest['image_sha256']
        assert sha(target/'web_hmi/server.py') == manifest['server_sha256']
    else:
        assert manifest['diagnostic_only_not_confirmed_fix']
        assert (manifest['Uno'], manifest['Nucleo_unchanged']) == new_pair
        for rel,digest in json.loads((target/'source_and_release_sha256.json').read_text()).items():
            assert sha(target/rel)==digest,rel
        image=target/manifest['artifact']
        assert sha(image)==manifest['sha256']
    if a.verify_only:print('Package verified, no hardware IO');return 0
    if not a.confirmed_j1_off_meter_below20_usb:parser.error('Operator confirmation required')
    out=target/'installation_r1';assert out.exists() and not (out/'report.json').exists()
    backup=json.loads((out/'backup_report.json').read_text());assert backup['native_verified'] and backup['Uno_RAM_bytes']==786432
    verify=p.ROOT/'tools'/f'verify_restart_unoq_{build}.cfg'
    assert not verify.exists()
    readback_path=f'/tmp/mic_rpc_{build}_flash_readback_r1.bin'
    original=(p.ROOT/'tools/verify_restart_unoq_sketch.cfg').read_text()
    marker='    echo "UNO Q verification PASSED'
    assert original.count(marker)==1
    verify.write_text(original.replace(marker,
        f'    dump_image {readback_path} 0x08100000 {image.stat().st_size}\n'+marker))
    r=dict(passed=False,pair=new_pair,uno_flash_commands=0,native_flash_commands=0,native_reset_commands=0,
           START=0,CLEAR=0,ARM=0,operator_confirmation='User ready: J1OFF, meter<20V, UnoUSB; no wiring change',commands=[])
    def save():(out/'report.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
    def run(cmd,label,timeout=30):
        result=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        (out/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        r['commands'].append(dict(label=label,exit_code=result.returncode));save()
        assert result.returncode==0,label+' failed; see log'
        return result.stdout.strip()
    adb=['adb','-s',io.UNO_SERIAL];ssh=tunneled(ssh_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
    scp=tunneled(scp_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
    io.URL='http://127.0.0.1:18080';closed=False
    def route(action):
        code="""import sys
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
r=RouterClient('/var/run/arduino-router.sock').call('$/serial/ACTION',['/dev/ttyHS1'],timeout=5,retries=0)
assert r and r[2] is None and r[3] is True,r
print('serial ACTION acknowledged')
""".replace('ACTION',action)
        run(ssh+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(code)],'router_'+action,15)
    swd=[str(io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+io.STLINK_SERIAL]
    def registers(label):
        v=parse_registers(run(swd+['-r32','0x40012c00','104'],label,20))
        assert v[0x40012c44]&4096 and not v[0x40012c44]&32768
        return v
    try:
        assert run(adb+['get-state'],'adb_state',10)=='device'
        listing=json.loads(run(['arduino-cli','board','list','--format','json'],'USB_identities',20))
        ports=[x['port'] for x in listing['detected_ports'] if x['port'].get('properties',{}).get('serialNumber')==io.UNO_SERIAL]
        assert len(ports)==1;port=ports[0]['address']
        before=io.live_status();safe(before,old_pair)
        (out/'immediate_before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
        registers('native_OFF_immediate_before')
        cal='/home/arduino/.config/mic-ai/vbus_calibration.json'
        hmi='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py'
        r['calibration_before']=run(ssh+['sha256sum '+cal],'calibration_before',15).split()[0]
        current_hash=run(ssh+['sha256sum '+hmi],'HMI_hash_before',15).split()[0]
        assert current_hash==sha(predecessor/'web_hmi/server.py'),'Unexpected live server, preserve instead of overwriting'
        run(scp+['arduino@192.168.1.138:'+hmi,str(out/'server_before.py')],'save_HMI_before')
        prefix=f'/tmp/mic_rpc_{build}_install_r1_'
        candidate=target/'web_hmi/server.py'
        run(scp+[str(candidate),'arduino@192.168.1.138:'+prefix+'server.py'],'stage_server')
        assert run(ssh+['sha256sum '+prefix+'server.py'],'staged_HMI_hash',15).split()[0]==sha(candidate)
        cfg=dict(offline_programming_only=True,native_BKE=True,native_MOE=False,
                 calibration_sha256=r['calibration_before'],prospective_identity=dict(before,fw_build=new_pair[0],mc_fw_build=new_pair[1]),
                 files=[dict(remote=prefix+'server.py',destination='server.py',sha256=sha(candidate))])
        config=out/'deploy_config.json';config.write_text(json.dumps(cfg))
        tree=ast.parse((p.ROOT/'tools/finish_rollback_3014_hmi.py').read_text(encoding='utf-8'))
        remote=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REMOTE' for t in n.targets))
        helper=out/'deploy_HMI.py';helper.write_text(remote.replace("'rollback_3014_'",f"'rpc_{build}_'").replace('CONFIG',repr(prefix+'deploy_config.json')),encoding='utf-8')
        for f in (config,helper):run(scp+[str(f),'arduino@192.168.1.138:'+prefix+f.name],'stage_'+f.name)
        code="import importlib.util,json,pathlib; c=json.loads(pathlib.Path("+repr(prefix+'deploy_config.json')+").read_text()); s=importlib.util.spec_from_file_location('candidate',c['files'][0]['remote']); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert m.VbusCalibrationStore('"+cal+"').is_valid(c['prospective_identity']); print('calibration compatibility OK')"
        run(ssh+['python3 -c '+shlex.quote(code)],'candidate_calibration_check',20)
        safe(io.live_status(),old_pair);registers('native_OFF_before_write')
        route('close');closed=True
        upload=['arduino-cli','upload','-p',port,'-b','arduino:zephyr:unoq','-i',str(image),
                '--upload-property','upload.artifacts.sketch='+str(image),
                '--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL,
                '--upload-property','build.variant.path='+str(p.ROOT/'tools')]
        r['uno_flash_commands']=1;save()
        run(upload+['--upload-property','openocd_cfg=flash_verify_unoq_history_hold.cfg'],'flash_Uno_once',90)
        assert 'VERIFIED AND HELD' in (out/'flash_Uno_once.log').read_text(encoding='utf-8')
        run(upload+['--upload-property','openocd_cfg='+verify.name],'verify_readback_restart_Uno',90)
        assert 'verification PASSED' in (out/'verify_readback_restart_Uno.log').read_text(encoding='utf-8')
        run(adb+['pull',readback_path,str(out/'Uno_flash_readback.bin')],'pull_Uno_flash_readback',30)
        assert (out/'Uno_flash_readback.bin').read_bytes()==image.read_bytes()
        r['uno_readback_verified']=True;r['Uno_readback_sha256']=sha(out/'Uno_flash_readback.bin');save()
        route('open');closed=False
        r['HMI_deployment']=json.loads(run(ssh+['python3 '+shlex.quote(prefix+helper.name)],'deploy_HMI',20))
        r['calibration_after']=run(ssh+['sha256sum '+cal],'calibration_after',15).split()[0]
        assert r['calibration_after']==r['calibration_before'];r['calibration_unchanged']=True
        run(scp+['arduino@192.168.1.138:'+hmi,str(out/'server_readback.py')],'HMI_readback')
        assert (out/'server_readback.py').read_bytes()==candidate.read_bytes();r['HMI_readback_verified']=True
        expected=p.BASE/'release/nucleo_2026111810_expected_readback.bin'
        run(swd+['-u','0x08000000',str(expected.stat().st_size),str(out/'native_flash_after.bin')],'native_flash_after',20)
        assert (out/'native_flash_after.bin').read_bytes()==expected.read_bytes();r['native_image_unchanged_verified']=True
        registers('native_OFF_after')
        for i in range(4):
            try:
                after=io.live_status();safe(after,new_pair)
                (out/'after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
                r['runtime_pair_verified']=True;r['passed']=True;break
            except Exception as e:r['runtime_pending']=str(e);time.sleep(1)
        manifest['installed']=True;manifest['readback_verified']=True
        (target/'release_manifest.json').write_text(json.dumps(manifest,indent=2))
    except Exception as e:r['error']=str(e)
    finally:
        if closed:
            try:route('open')
            except Exception as e:r['router_restore_error']=str(e)
        save()
    print(json.dumps({k:v for k,v in r.items() if k!='commands'}))
    return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

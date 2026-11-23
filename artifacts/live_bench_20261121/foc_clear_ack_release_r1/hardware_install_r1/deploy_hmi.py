
import hashlib,importlib.util,json,os,pathlib,signal,subprocess,time
root=pathlib.Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
cfg=json.loads(pathlib.Path('/tmp/mic_ack2112_4d86cea9d35348408cf7e98fbd26bcb5_deploy_config.json').read_text())
assert cfg['offline_programming_only'] and cfg['native_BKE'] and not cfg['native_MOE']
files=[]
for entry in cfg['files']:
 p=pathlib.Path(entry['remote']);data=p.read_bytes()
 assert hashlib.sha256(data).hexdigest()==entry['sha256']
 files.append((root/entry['destination'],data))
cal=pathlib.Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
before=cal.read_bytes();assert hashlib.sha256(before).hexdigest()==cfg['calibration_sha256']
spec=importlib.util.spec_from_file_location('rollback_candidate',cfg['files'][0]['remote'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
# Compatibility of the original record with the exact intended pair; no live
# reading is fabricated and no saved calibration/identity field is rewritten.
assert module.VbusCalibrationStore(str(cal)).is_valid(cfg['prospective_identity'])
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
restart=subprocess.check_output(['systemctl','show','-p','Restart','--value','unoq-hmi.service'],text=True).strip()
proc=pathlib.Path('/proc')/str(pid)
assert pid>1 and restart=='always' and proc.stat().st_uid==os.geteuid()
assert (proc/'cwd').resolve()==root
assert 'server.py' in (proc/'cmdline').read_bytes().decode().split('\0')
backup=root/'backups'/('ack_2112_'+time.strftime('%Y%m%d_%H%M%S'))
backup.mkdir(exist_ok=False)
for target,data in files:
 (backup/target.name).write_bytes(target.read_bytes())
 pending=target.with_name(target.name+'.rollback-pending')
 pending.write_bytes(data);pending.chmod(target.stat().st_mode&0o777);os.replace(pending,target)
assert all(target.read_bytes()==data for target,data in files)
assert cal.read_bytes()==before
os.kill(pid,signal.SIGTERM)
print(json.dumps(dict(deployed=True,backup=str(backup),calibration_unchanged=True,
 runtime_verified=False,hmi_restarts=1,flash_commands=0,motor_commands=0)))

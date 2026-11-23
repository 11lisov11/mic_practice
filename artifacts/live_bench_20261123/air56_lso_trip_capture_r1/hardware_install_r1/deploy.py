import hashlib,importlib.util,json,os,pathlib,signal,subprocess,sys
cfg=json.loads(pathlib.Path(sys.argv[1]).read_text())
root=pathlib.Path(cfg['root'])
cal=pathlib.Path(cfg['cal'])
sha=lambda b:hashlib.sha256(b).hexdigest()
original=cal.read_bytes()
assert sha(original)==cfg['cal_sha']
source=pathlib.Path(cfg['candidate'])
data=source.read_bytes()
assert sha(data)==cfg['server_sha']
compile(data,str(source),'exec')
spec=importlib.util.spec_from_file_location('lso_candidate',source)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
cal_ok=module.VbusCalibrationStore(str(cal)).is_valid(cfg['prospective_identity'])
if sys.argv[2]=='check':
    print(json.dumps(dict(server_verified=True,calibration_valid_for_pair=cal_ok)))
    raise SystemExit(0)
target=root/'server.py'
old=target.read_bytes()
assert sha(old)==cfg['old_server_sha']
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
restart=subprocess.check_output(['systemctl','show','-p','Restart','--value','unoq-hmi.service'],text=True).strip()
proc=pathlib.Path('/proc')/str(pid)
assert pid>1 and restart=='always' and proc.stat().st_uid==os.geteuid()
assert (proc/'cwd').resolve()==root and 'server.py' in (proc/'cmdline').read_bytes().decode().split(chr(0))
backup=root/'backups'/cfg['backup']
backup.mkdir()
(backup/'server.py').write_bytes(old)
pending=root/('.server.py.'+cfg['backup'])
pending.write_bytes(data)
pending.chmod(target.stat().st_mode&0o777)
os.replace(pending,target)
assert target.read_bytes()==data and cal.read_bytes()==original
os.kill(pid,signal.SIGTERM)
print(json.dumps(dict(deployed=True,backup=str(backup),server_sha256=sha(data),
    calibration_unchanged=True,calibration_valid_for_pair=cal_ok)))

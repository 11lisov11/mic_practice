import os,pathlib,signal,subprocess,json,hashlib
root=pathlib.Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
restart=subprocess.check_output(['systemctl','show','-p','Restart','--value','unoq-hmi.service'],text=True).strip()
p=pathlib.Path('/proc')/str(pid)
assert pid>1 and restart=='always' and p.stat().st_uid==os.geteuid()
assert (p/'cwd').resolve()==root and 'server.py' in (p/'cmdline').read_bytes().decode().split('\0')
print(json.dumps({'HMI_terminated_pid':pid,'Linux_boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'server_sha256':hashlib.sha256((root/'server.py').read_bytes()).hexdigest(),'MCU_resets':0,'START':0,'CLEAR':0}),flush=True)
os.kill(pid,signal.SIGTERM)

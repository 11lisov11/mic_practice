import os,pathlib,signal,subprocess,json
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
restart=subprocess.check_output(['systemctl','show','-p','Restart','--value','unoq-hmi.service'],text=True).strip()
p=pathlib.Path('/proc')/str(pid)
assert pid>1 and restart=='always' and p.stat().st_uid==os.geteuid()
assert (p/'cwd').resolve()==pathlib.Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
assert 'server.py' in (p/'cmdline').read_bytes().decode().split('\0')
os.kill(pid,signal.SIGTERM)
print(json.dumps(dict(HMI_terminated_pid=pid,HMI_restarts=1,MCU_resets=0,START=0,CLEAR=0)))

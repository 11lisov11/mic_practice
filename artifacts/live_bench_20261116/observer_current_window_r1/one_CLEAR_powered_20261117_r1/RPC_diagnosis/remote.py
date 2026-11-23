import sys,json,pathlib,subprocess
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
d=dict(Linux_boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip())
for name in ('unoq-hmi.service','arduino-router.service'):
 d[name]=subprocess.run(['systemctl','show','-p','MainPID','-p','NRestarts','-p','SubState',name],capture_output=True,text=True,timeout=4).stdout
 d[name+'_journal']=subprocess.run(['journalctl','-u',name,'-n','70','--no-pager'],capture_output=True,text=True,timeout=4).stdout
c=RouterClient('/var/run/arduino-router.sock');d['direct_GET']=c.call('get',[],timeout=3,retries=0)
print(json.dumps(d))

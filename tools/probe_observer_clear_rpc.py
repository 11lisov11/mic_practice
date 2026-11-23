"""Read-only direct RPC/service snapshot before the single authorized CLEAR."""
import json,shlex,subprocess
import prepare_observer_current_window as p
CODE='''import sys,json,pathlib,subprocess
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
d=dict(Linux_boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip())
for name in ('unoq-hmi.service','arduino-router.service'):
 r=subprocess.run(['systemctl','show','-p','MainPID','-p','NRestarts','-p','SubState',name],capture_output=True,text=True,timeout=4)
 d[name]=r.stdout
c=RouterClient('/var/run/arduino-router.sock');d['direct_GET']=c.call('get',[],timeout=3,retries=0)
print(json.dumps(d))
'''
def main():
    out=p.OUT/'one_CLEAR_idle_r1/RPC_probe';out.mkdir(exist_ok=False)
    p.write(out/'remote_read.py',CODE)
    r=subprocess.run(['adb','-s','3880458060','shell','/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=18)
    p.write(out/'raw_response.json',r.stdout);p.write(out/'stderr.txt',r.stderr)
    r.check_returncode();d=json.loads(r.stdout)
    reply=d['direct_GET']
    print(json.dumps(dict(Linux_boot_id=d['Linux_boot_id'],services={k:v for k,v in d.items() if k.endswith('service')},
        direct_RPC_received=reply is not None,RPC_error=None if reply is None else reply[2],hardware_commands=0,CLEAR=0)))
if __name__=='__main__':main()

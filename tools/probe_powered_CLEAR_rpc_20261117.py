"""WiFi GET-only RPC/service diagnosis, no board/motor/serial-route writes."""
import json,shlex,subprocess
import prepare_observer_current_window as p
from unoq_wifi_hmi_deploy import ssh_base
CODE='''import sys,json,pathlib,subprocess
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
d=dict(Linux_boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip())
for name in ('unoq-hmi.service','arduino-router.service'):
 d[name]=subprocess.run(['systemctl','show','-p','MainPID','-p','NRestarts','-p','SubState',name],capture_output=True,text=True,timeout=4).stdout
 d[name+'_journal']=subprocess.run(['journalctl','-u',name,'-n','70','--no-pager'],capture_output=True,text=True,timeout=4).stdout
c=RouterClient('/var/run/arduino-router.sock');d['direct_GET']=c.call('get',[],timeout=3,retries=0)
print(json.dumps(d))
'''
def main():
    out=p.OUT/'one_CLEAR_powered_20261117_r1/RPC_diagnosis';out.mkdir(exist_ok=False)
    p.write(out/'remote.py',CODE)
    ssh=ssh_base('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
    r=subprocess.run(ssh+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=22)
    p.write(out/'raw_response.json',r.stdout);p.write(out/'stderr.txt',r.stderr);r.check_returncode()
    d=json.loads(r.stdout);reply=d['direct_GET']
    print(json.dumps(dict(Linux_boot_id=d['Linux_boot_id'],services={k:v for k,v in d.items() if k.endswith('.service')},
        RPC_received=reply is not None,RPC_error=reply[2] if reply else None,CLEAR=0,START=0,RESET=0)))
if __name__=='__main__':main()

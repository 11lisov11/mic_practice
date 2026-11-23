"""Archive idle RPC outage without START, CLEAR, restart, halt or reset."""
import json,subprocess,shlex
import prepare_rpc_route_recovery as p

CODE='''import sys,json,subprocess
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
c=RouterClient('/var/run/arduino-router.sock')
r=c.call('get',[],timeout=4,retries=0)
print(json.dumps({'raw_RPC':r}))
'''
def main():
    out=p.OUT/'idle_timeout_diagnosis_r1';out.mkdir(exist_ok=False)
    r=subprocess.run(['adb','-s','3880458060','shell',
        '/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=12)
    p.write(out/'direct_RPC.json',r.stdout);p.write(out/'direct_RPC.stderr',r.stderr)
    for name,command in (
        ('processes','ps -eo pid,ppid,stat,etime,args'),
        ('router_journal','journalctl -u arduino-router --no-pager -n 120'),
        ('serial','ls -l /proc/$(pidof arduino-router)/fd'),
        ('native_usb','lsusb')):
        x=subprocess.run(['adb','-s','3880458060','shell',command],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=12)
        p.write(out/(name+'.log'),x.stdout+x.stderr)
    data=json.loads(r.stdout) if r.returncode==0 else {}
    reply=data.get('raw_RPC')
    report=dict(START=0,CLEAR=0,RESET=0,halt=0,service_restart=0,flash=0,
        direct_reply=reply is not None,direct_error=reply[2] if reply else None,
        direct_body_bytes=len(reply[3]) if reply and isinstance(reply[3],str) else None)
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()

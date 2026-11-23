"""One safety STOP and direct GET via SSH; never CLEAR/START/reset services."""
import json,pathlib,shlex,subprocess
from unoq_wifi_hmi_deploy import ssh_base

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/live_bench_20261116/clear_recovery_r1/powered_FOC_NIS_5Hz_r1/direct_router_recovery_r1'
CODE="""import sys,json
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient,RpcBridge
c=RouterClient('/var/run/arduino-router.sock')
stop=c.call('cmd',['STOP'],timeout=1,retries=0)
r=c.call('get',[],timeout=4,retries=0)
s=RpcBridge._parse_status_string(r[3]) if r and r[2] is None and isinstance(r[3],str) else None
print(json.dumps(dict(STOP_response=stop,raw_RPC=r,status=s)))
"""

def main():
    OUT.mkdir(exist_ok=False);(OUT/'remote_read.py').write_text(CODE,encoding='utf-8')
    ssh=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
    r=subprocess.run(ssh+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)],
        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=18)
    (OUT/'stdout.json').write_text(r.stdout,encoding='utf-8');(OUT/'stderr.txt').write_text(r.stderr,encoding='utf-8')
    d=json.loads(r.stdout) if r.returncode==0 else {};s=d.get('status') or {}
    print(json.dumps(dict(SSH_exit=r.returncode,STOP_RPC_received=d.get('STOP_response') is not None,
        status_received=bool(s),values={k:s.get(k) for k in ('state','pwm','run_id','run_elapsed_ms','run_reason','algorithm_fault','mc_fault','vdc')})))

if __name__=='__main__':main()

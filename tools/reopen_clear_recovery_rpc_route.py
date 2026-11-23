"""J1 OFF: reopen Linux router serial endpoint once, preserve both MCU RAMs."""
import json,pathlib,shlex,subprocess
from unoq_wifi_hmi_deploy import ssh_base
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/live_bench_20261116/clear_recovery_r1/powered_FOC_NIS_5Hz_r1/router_route_recovery_r1'
CODE=r'''import json,socket,msgpack,sys
def route(action):
 s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(5);s.connect('/var/run/arduino-router.sock')
 s.sendall(msgpack.packb([0,1,'$/serial/'+action,['/dev/ttyHS1']],use_bin_type=True));u=msgpack.Unpacker(raw=False)
 try:
  while True:
   b=s.recv(65536);assert b;u.feed(b)
   for r in u:
    if r[0]==1 and r[1]==1:return r
 finally:s.close()
a=route('close');print(json.dumps(dict(close=a)),flush=True)
if a[2] is None and a[3] is True:
 b=route('open');print(json.dumps(dict(open=b)),flush=True)
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient,RpcBridge
c=RouterClient('/var/run/arduino-router.sock');r=c.call('get',[],timeout=4,retries=0)
s=RpcBridge._parse_status_string(r[3]) if r and r[2] is None and isinstance(r[3],str) else None
print(json.dumps(dict(raw_RPC=r,status=s)))
'''
def main():
 OUT.mkdir(exist_ok=False);(OUT/'remote.py').write_text(CODE,encoding='utf-8')
 ssh=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
 r=subprocess.run(ssh+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=18)
 (OUT/'stdout.jsonl').write_text(r.stdout,encoding='utf-8');(OUT/'stderr.txt').write_text(r.stderr,encoding='utf-8')
 d=[json.loads(x) for x in r.stdout.splitlines()];last=d[-1] if d else {};s=last.get('status') or {}
 print(json.dumps(dict(exit=r.returncode,route_results=d[:2],status_received=bool(s),pwm=s.get('pwm'),run_id=s.get('run_id'),START=0,CLEAR=0,MCU_resets=0)))
if __name__=='__main__':main()

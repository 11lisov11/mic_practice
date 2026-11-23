import json,socket,msgpack,sys
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

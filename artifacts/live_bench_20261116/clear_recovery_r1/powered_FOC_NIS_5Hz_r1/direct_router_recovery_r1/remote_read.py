import sys,json
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient,RpcBridge
c=RouterClient('/var/run/arduino-router.sock')
stop=c.call('cmd',['STOP'],timeout=1,retries=0)
r=c.call('get',[],timeout=4,retries=0)
s=RpcBridge._parse_status_string(r[3]) if r and r[2] is None and isinstance(r[3],str) else None
print(json.dumps(dict(STOP_response=stop,raw_RPC=r,status=s)))

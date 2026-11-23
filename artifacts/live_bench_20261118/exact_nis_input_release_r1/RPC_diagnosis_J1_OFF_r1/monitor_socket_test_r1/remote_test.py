import sys,json,time,pathlib
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
c=RouterClient('/var/run/arduino-router.sock')
r={'START':0,'CLEAR':0,'MCU_reset':0,'serial_reopens':0}
r['monitor_connected_before']=c.call('mon/connected',[],timeout=2,retries=0)
r['direct_GET_before']=c.call('get',[],timeout=2,retries=0)
r['monitor_clients_closed']=c.call('mon/reset',[],timeout=3,retries=0)
r['monitor_connected_after']=c.call('mon/connected',[],timeout=2,retries=0)
r['GET_after']=c.call('get',[],timeout=3,retries=0)
print(json.dumps(r))

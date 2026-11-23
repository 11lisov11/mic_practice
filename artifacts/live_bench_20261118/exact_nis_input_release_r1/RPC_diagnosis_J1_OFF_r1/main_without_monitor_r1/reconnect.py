import sys,json,time
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
c=RouterClient('/var/run/arduino-router.sock')
r={'START':0,'CLEAR':0,'MCU_reset':0}
r['monitor_before']=c.call('mon/connected',[],timeout=2,retries=0)
assert r['monitor_before'] and r['monitor_before'][2] is None and r['monitor_before'][3] is False,'Monitor reconnected; stop controlled comparison'
try:
 r['serial_close']=c.call('$/serial/close',['/dev/ttyHS1'],timeout=5,retries=0)
 assert r['serial_close'] and r['serial_close'][2] is None and r['serial_close'][3] is True
 time.sleep(.5)
finally:
 r['serial_open']=c.call('$/serial/open',['/dev/ttyHS1'],timeout=5,retries=0)
 print(json.dumps(r),flush=True)
assert r['serial_open'] and r['serial_open'][2] is None and r['serial_open'][3] is True

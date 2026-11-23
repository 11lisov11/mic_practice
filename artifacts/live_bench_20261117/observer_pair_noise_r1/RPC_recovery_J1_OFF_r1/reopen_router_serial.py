import sys,json,time,pathlib
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
c=RouterClient('/var/run/arduino-router.sock')
r={'J1_OFF_confirmed':True,'START':0,'CLEAR':0,'MCU_reset':0,'Linux_boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
try:
 r['close_reply']=c.call('$/serial/close',['/dev/ttyHS1'],timeout=5,retries=0)
 assert r['close_reply'] and r['close_reply'][2] is None and r['close_reply'][3] is True
 time.sleep(.5)
finally:
 r['open_reply']=c.call('$/serial/open',['/dev/ttyHS1'],timeout=5,retries=0)
 print(json.dumps(r),flush=True)
assert r['open_reply'] and r['open_reply'][2] is None and r['open_reply'][3] is True

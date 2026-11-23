import os,sys,time,json,termios,select,fcntl,msgpack,pathlib
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
root=pathlib.Path(sys.argv[1]);root.mkdir()
c=RouterClient('/var/run/arduino-router.sock');fd=None;closed=False;events=[];wire=bytearray();requests=[]
def route(action):
 r=c.call('$/serial/'+action,['/dev/ttyHS1'],timeout=5,retries=0);assert r and r[2] is None and r[3] is True,r
try:
 route('close');closed=True
 fd=os.open('/dev/ttyHS1',os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 a=termios.tcgetattr(fd);a[0]=a[1]=a[3]=0;a[2]=termios.CS8|termios.CREAD|termios.CLOCAL;a[4]=a[5]=termios.B115200;a[6][termios.VMIN]=0;a[6][termios.VTIME]=0;termios.tcsetattr(fd,termios.TCSANOW,a)
 unpack=msgpack.Unpacker(raw=False,strict_map_key=False);start=time.monotonic();sent_history=sent_get=False
 while time.monotonic()-start<18:
  now=time.monotonic()-start
  if now>=3 and not sent_history:
   os.write(fd,msgpack.packb([0,0x666001,'history',[0,0]],use_bin_type=False));sent_history=True;requests.append({'method':'history','at':now})
  if now>=7 and not sent_get:
   os.write(fd,msgpack.packb([0,0x666002,'get',[]],use_bin_type=False));sent_get=True;requests.append({'method':'get','at':now})
  ready,_,_=select.select([fd],[],[],.05)
  if not ready:continue
  data=os.read(fd,8192)
  if not data:continue
  wire.extend(data);unpack.feed(data)
  try:
   for item in unpack:
    if not isinstance(item,list) or len(item)!=4:continue
    if item[0]==0 and isinstance(item[2],str):
     method=item[2];events.append({'type':'MCU_call','at':time.monotonic()-start,'method':method,'params':item[3] if method=='$/register' else None})
     if method in ('$/register','$/reset','$/monitor/write'):answer=[1,item[1],None,True]
     elif method=='$/version':answer=[1,item[1],None,'diagnostic-readonly-peer']
     else:answer=[1,item[1],[2,'unsupported diagnostic method'],None]
     os.write(fd,msgpack.packb(answer,use_bin_type=False))
    elif item[0]==1:
     value=item[3];row={'type':'MCU_response','id':item[1],'at':time.monotonic()-start,'error':item[2],'size':len(value) if isinstance(value,str) else None}
     events.append(row)
     if item[1] in (0x666001,0x666002):
      (root/('history_response.json' if item[1]==0x666001 else 'get_response.json')).write_text(json.dumps(item))
  except Exception as e:
   events.append({'type':'parse_error','error':repr(e),'at':time.monotonic()-start});unpack=msgpack.Unpacker(raw=False,strict_map_key=False)
finally:
 if fd is not None:os.close(fd)
 if closed:route('open')
 (root/'wire_RX.bin').write_bytes(wire);(root/'events.json').write_text(json.dumps(events,indent=2));(root/'report.json').write_text(json.dumps({'START':0,'CLEAR':0,'RESET':0,'motor_UART_untouched':True,'sole_internal_UART_owner':True,'router_reopened':closed,'requests':requests,'received_bytes':len(wire)},indent=2))
 print(json.dumps({'received_bytes':len(wire),'events':events,'router_reopened':closed}),flush=True)

"""One documented router0.5.3 close/open, only on confirmed J1OFF/UnoUSB bench."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
from unoq_wifi_hmi_deploy import ssh_base
from install_sd_break_filter_usb_pair import tunneled

CODE='''import socket,json,time,msgpack
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(5);s.connect('/var/run/arduino-router.sock');u=msgpack.Unpacker(raw=False)
def call(i,m):
 s.sendall(msgpack.packb([0,i,m,['/dev/ttyHS1']],use_bin_type=True))
 while True:
  b=s.recv(65536)
  if not b:raise RuntimeError('router closed')
  u.feed(b)
  for x in u:
   if x[0]==1 and x[1]==i:return x
c=call(1,'$/serial/close');time.sleep(.2);o=call(2,'$/serial/open')
assert c==[1,1,None,True] and o==[1,2,None,True]
print(json.dumps({'close':c,'open':o,'motor_commands':0,'flash_commands':0,'reset_commands':0}))
'''
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-j1-off-meter-below-20v-uno-usb',action='store_true')
    p.add_argument('--log',type=Path,required=True);a=p.parse_args()
    if not a.confirm_j1_off_meter_below_20v_uno_usb:p.error('Confirmed physical programming state required')
    assert not a.log.exists(),'Keep original evidence'
    root=Path(__file__).resolve().parents[1]
    cmd=tunneled(ssh_base)('192.168.1.138',2222,'arduino',root/'.unoq_ssh/id_ed25519',root/'.unoq_ssh/known_hosts')
    command='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)
    r=subprocess.run(cmd+[command],capture_output=True,text=True,timeout=20)
    a.log.write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
if __name__=='__main__':main()

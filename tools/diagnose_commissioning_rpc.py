"""Read-only RPC and MCU boot snapshot on the confirmed discharged USB bench."""
import subprocess,shlex,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/live_bench_20261029/standstill_commissioning_r1/hardware_install_r1'
CODE='''import sys,json,time
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
c=RouterClient('/var/run/arduino-router.sock')
t=time.monotonic();r=c.call('get',[],timeout=2,retries=0)
print(json.dumps(dict(elapsed=time.monotonic()-t,response=r if not r or r[2] is not None else ['response-ok',len(str(r[3]))])))
'''
def main():
 code='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)
 r=subprocess.run(['adb','-s','3880458060','shell',code],capture_output=True,text=True,timeout=10)
 (OUT/'direct_router_get.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr)
 base=Path.home()/'AppData/Local/Arduino15/packages/arduino'
 cmd=[str(base/'tools/remoteocd/0.1.1/remoteocd.exe'),'upload','--adb-path','adb','-s','3880458060',
  '-f',str(ROOT/'tools/unoq_boot_snapshot.cfg'),str(base/'hardware/zephyr/0.90.0/firmwares/zephyr-arduino_uno_q_stm32u585xx.elf'),
  str(OUT.parent/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')]
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=35)
 (OUT/'uno_boot_snapshot.log').write_text(r.stdout+r.stderr,encoding='utf-8')
 print(json.dumps(dict(snapshot_exit=r.returncode,log=str(OUT/'uno_boot_snapshot.log'))))
if __name__=='__main__':main()

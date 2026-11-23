"""Repair RPC on the separately confirmed discharged USB bench.

Programming evidence comes from passive, fresh ST-Link reads and exact old image
readback because the old RPC task has an insufficient stack. START protections
and the live HMI installation checks remain unchanged. No fabricated RPC status.
"""
import argparse,json,subprocess,shlex,time,uuid
from pathlib import Path
from types import SimpleNamespace
import prepare_standstill_stack as p
import install_bkin_boot_armed_pair as io
import install_research_suite as hmi
import install_current_shunt_monitor as base
from probe_native_programming_state import probe
from seal_standstill_commissioning import sha
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base,scp_base
OLD=(2026102933,2026102934)
GUARD=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
 '((2026101805,2026101804),(2026101807,2026101806))',str((OLD,p.NEW)))
scope={'math':__import__('math')};exec(GUARD,scope);precheck=scope['precheck'];base.GUARD=GUARD
hmi.p=SimpleNamespace(ROOT=p.ROOT,OUT=p.OUT,NEW=p.NEW,OLD=OLD,read=p.read,write=p.write,once=p.once,sha=sha)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--confirm-existing-j1-off-meter-below20-both-usb',action='store_true')
 ap.add_argument('--use-existing-user-authorized-usb-policy',action='store_true',
  help='Only with existing human instruction that available USB boards authorize programming after checking power; J1 must already be confirmed OFF. Fresh passive SWD must show <=12V.')
 ap.add_argument('--uno-only-preserve-native',action='store_true')
 ap.add_argument('--outdir',type=Path);a=ap.parse_args()
 if not (a.confirm_existing_j1_off_meter_below20_both_usb or a.use_existing_user_authorized_usb_policy):ap.error('Existing human authorization and OFF state required')
 out=(a.outdir or p.OUT/'hardware_install_r1').resolve();assert p.OUT in out.parents;out.mkdir(exist_ok=False)
 report=dict(passed=False,uno_flash_commands=0,nucleo_flash_commands=0,start_commands=0,clear_commands=0,
  programming_guard='fresh independent passive SWD + exact predecessor readback + physical meter confirmation')
 def run(cmd,label,timeout=100):return io.run(cmd,label,out,report,timeout)
 def control_serial(action):
  code='''import socket,msgpack,json
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(5);s.connect('/var/run/arduino-router.sock');u=msgpack.Unpacker(raw=False)
s.sendall(msgpack.packb([0,1,"$/serial/'''+action+'''",['/dev/ttyHS1']],use_bin_type=True))
while True:
 b=s.recv(65536);assert b;u.feed(b)
 for r in u:
  if r[0]==1 and r[1]==1:
   assert r[2] is None and r[3] is True,r
   print(json.dumps(dict(action="'''+action+'''",ok=True,motor_commands=0)));raise SystemExit(0)
'''
  return run(ssh+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(code)],'router_serial_'+action,12)
 try:
  m=json.loads(p.read(p.OUT/'manifest.json'));assert m['built'] and not m['installed']
  for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==h,rel
  for rel,h in m['artifacts'].items():assert sha(p.OUT/rel)==h,rel
  io.board_ports();report['native_preflight']=probe(p.BASE,out/'passive_native_guard',
   'existing user available-USB programming policy; J1 previously confirmed OFF; no new multimeter value claimed'
    if a.use_existing_user_authorized_usb_policy else 'user below20V by multimeter / J1 OFF / both USB')
  if a.use_existing_user_authorized_usb_policy:
   evidence=report['native_preflight']
   report['programming_guard']='existing user-authorized available-USB policy; previously confirmed J1 OFF; fresh passive SWD <=12V, MOE=0, exact predecessor image and advancing uptime'
   report['programming_authorization_source']='User: if boards are available, I connected them; check power and proceed. Latest physical instruction confirmed J1 OFF.'
   # Same independent checks as the original programming path; additionally
   # tighten voltage to12V. Do not label this as a new multimeter reading.
   assert evidence['passed'] and all(row['bus_volts']<=12 for row in evidence['rows']),evidence
  io.URL='http://127.0.0.1:18080';io.ssh_base=tunneled(ssh_base)
  for local,remote in ((18080,8080),(12222,2222)):subprocess.run(['adb','-s',io.UNO_SERIAL,'forward',f'tcp:{local}',f'tcp:{remote}'],check=True,capture_output=True)
  ssh=io.ssh_base('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  scp=tunneled(scp_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  report['calibration_before']=io.calibration_hash(out,report)
  run([str(io.PROGRAMMER),'-c','port=SWD','mode=HotPlug','sn='+io.STLINK_SERIAL,
    '-u','0x20000000','32768',str(out/'native_sram_before.bin'),'-halt','-score'],'preserve_halt_native',25)
  report['native_halted']=True
  control_serial('close');report['router_serial_closed']=True
  port=io.board_ports()[0]
  def upload(image,cfg=None):
   cmd=['arduino-cli','upload','-p',port,'-b','arduino:zephyr:unoq','-i',str(image),
    '--upload-property','upload.artifacts.sketch='+str(image),'--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL]
   if cfg:cmd+=['--upload-property','build.variant.path='+str(p.ROOT/'tools'),'--upload-property','openocd_cfg='+cfg]
   return cmd
  old=p.BASE/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'
  run(upload(old,'verify_restart_unoq_sketch.cfg'),'verify_old_uno',60)
  native=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
  if a.uno_only_preserve_native:
   assert OLD[1]==p.NEW[1]
   assert native.with_suffix('.bin').read_bytes()==(p.BASE/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin').read_bytes()
   report['nucleo_readback_verified']=True
   report['nucleo_preserved_without_flash']=True
  else:
   report['nucleo_flash_commands']=1
   run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','sn='+io.STLINK_SERIAL,'-halt','-w',str(native),'-v','-halt','-score'],'flash_verify_halt_native',60)
   report['nucleo_readback_verified']=True
  image=p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin';report['uno_flash_commands']=1
  run(upload(image),'flash_uno',60);run(upload(image,'verify_restart_unoq_sketch.cfg'),'verify_new_uno',60)
  assert 'UNO Q verification PASSED' in p.read(out/'verify_new_uno.log');report['uno_readback_verified']=True
  control_serial('open');report['router_serial_closed']=False
  run([str(io.PROGRAMMER),'-c','port=SWD','mode=HotPlug','sn='+io.STLINK_SERIAL,'-rst'],'boot_new_native',20)
  report['native_halted']=False
  end=time.monotonic()+40;last=''
  while time.monotonic()<end:
   try:
    s=io.live_status();ok,why=precheck(s);assert ok,why;assert (s['fw_build'],s['mc_fw_build'])==p.NEW
    report['before_hmi']=s;break
   except Exception as exc:last=str(exc);time.sleep(.5)
  else:raise RuntimeError('New stack image verified; RPC not established: '+last)
  helper=out/'remote_hmi_installer.py';p.write(helper,hmi.remote_installer());prefix='/tmp/mic_stack_'+uuid.uuid4().hex
  files=[(p.OUT/'web_hmi/server.py',prefix+'_server.py'),(p.OUT/'web_hmi/static/app.js',prefix+'_app.js'),(helper,prefix+'_install.py')]
  for local,dest in files:run(scp+[str(local),'arduino@192.168.1.138:'+dest],'stage_'+local.name,30)
  command=['python3',files[2][1],'--candidate',files[0][1],'--sha256',sha(files[0][0]),'--app-js',files[1][1],
   '--app-js-sha256',sha(files[1][0]),'--max-vdc','20','--confirm-mains-off']
  run(ssh+[shlex.join(command+['--check-only'])],'hmi_precheck',35);run(ssh+[shlex.join(command)],'install_hmi',50)
  report['hmi_installed']=True;report['calibration_after']=io.calibration_hash(out,report)
  assert report['calibration_after']==report['calibration_before'];report['calibration_unchanged']=True
  s=io.live_status();ok,why=precheck(s);assert ok,why;assert (s['fw_build'],s['mc_fw_build'])==p.NEW
  report.update(passed=True,after=s)
 except Exception as exc:report['error']=str(exc)
 finally:
  if report.get('router_serial_closed'):
   try:control_serial('open');report['router_serial_closed']=False
   except Exception as exc:report['serial_reopen_error']=str(exc)
  if report.get('native_halted') and not report['nucleo_flash_commands']:
   try:
    run([str(io.PROGRAMMER),'-c','port=SWD','mode=HotPlug','sn='+io.STLINK_SERIAL,'-rst'],'restore_native_after_preflight_abort',20)
    report['native_halted']=False
   except Exception as exc:report['native_restore_error']=str(exc)
  p.write(out/'install_report.json',json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:report.get(k) for k in ('passed','uno_flash_commands','nucleo_flash_commands','uno_readback_verified','nucleo_readback_verified','calibration_unchanged','error')}))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

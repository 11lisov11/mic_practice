"""Install exactly sealed 2921/2922 with readback, no START/CLEAR.

Nucleo is programmed and left halted; Uno is programmed and read back; only then
Nucleo boots. This avoids manufacturing a native watchdog latch during Uno flash.
Existing protection constants and RAM/disk evidence are never cleared by command.
"""
import argparse,hashlib,json,shlex,subprocess,time,uuid
from pathlib import Path
from types import SimpleNamespace
import prepare_multi_algorithm as p
import install_current_shunt_monitor as base
import install_research_suite as hmi
import install_bkin_boot_armed_pair as io
from install_sd_break_filter_usb_pair import tunneled,restart_owned_hmi
from unoq_wifi_hmi_deploy import ssh_base,scp_base

OLD=(2026102911,2026102912)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
GUARD=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
 '((2026101805,2026101804),(2026101807,2026101806))',str((OLD,p.NEW)))
guard_globals={'math':__import__('math')};exec(GUARD,guard_globals)
precheck=guard_globals['precheck']
hmi.p=SimpleNamespace(ROOT=p.ROOT,OUT=p.OUT,OLD=OLD,NEW=p.NEW,read=p.read,once=p.once,write=p.write,sha=sha)
base.GUARD=GUARD

def verify():
 m=json.loads(p.read(p.OUT/'manifest.json'))
 assert m['pair']==list(p.NEW) and m['built'] and m['physical_qualification'] is False
 assert not m['thresholds_changed'] and not m['adc_guard_changed']
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==h,rel
 for rel,h in m['artifacts'].items():assert sha(p.OUT/rel)==h,rel
 for rel,h in json.loads(p.read(p.OUT/'archive_references.json')).items():assert sha(Path(rel))==h,rel
 uno=p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'
 assert sha(uno)==sha(p.OUT/'release/unoq_2026102921_multi.elf-zsk.bin')
 native=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
 # Verify HEX addressing/content against the independently sealed BIN.
 from build_multi_native import BIN
 converted=p.OUT/'hardware_install_r1/native_hex_content.bin'
 subprocess.run([str(BIN/'arm-none-eabi-objcopy.exe'),'-I','ihex','-O','binary',str(native),str(converted)],check=True)
 assert sha(converted)==sha(p.OUT/'release/nucleo_2026102922_multi.bin')
 assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 return uno,native

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--confirm-existing-j1-off-below-20v-usb',action='store_true')
 args=parser.parse_args()
 if not args.confirm_existing_j1_off_below_20v_usb:parser.error('Existing confirmed discharged USB state is required')
 out=p.OUT/'hardware_install_r1';assert (out/'before_status.json').exists()
 previous=out/'install_report.json'
 if previous.exists():
  record=json.loads(p.read(previous))
  assert not record.get('uno_flash_commands') and not record.get('nucleo_flash_commands'),'Resume the recorded phase instead of repeating programming'
  shutil=__import__('shutil');shutil.copy2(previous,out/'preflight_attempt1_report.json')
  if (out/'hmi_precheck.log').exists():shutil.copy2(out/'hmi_precheck.log',out/'hmi_precheck_attempt1.log')
 report=dict(passed=False,order=['nucleo_write_verify_halt','uno_write_verify_boot','nucleo_boot'],
  pair=list(p.NEW),uno_flash_commands=0,nucleo_flash_commands=0,start_commands=0,clear_commands=0,
  halted_native=False,native_boot_released=False,existing_operator_programming_state=True)
 def run(cmd,name,timeout=240):return io.run(cmd,name,out,report,timeout)
 def safe(pair):
  s=io.live_status();ok,why=precheck(s)
  assert ok,why;assert (s['fw_build'],s['mc_fw_build'])==pair
  return s
 def checkpoint():p.write(out/'install_report.json',json.dumps(report,ensure_ascii=False,indent=2))
 def wait_safe(pair):
  deadline=time.monotonic()+30;last=''
  while time.monotonic()<deadline:
   try:return safe(pair)
   except Exception as exc:last=str(exc);time.sleep(.6)
  report['owned_hmi_reconnect']=restart_owned_hmi()
  for _ in range(15):
   try:return safe(pair)
   except Exception as exc:last=str(exc);time.sleep(.6)
  raise RuntimeError('Runtime pending: '+last)
 try:
  uno,native=verify();adb=['adb','-s',io.UNO_SERIAL]
  assert subprocess.check_output(adb+['get-state'],text=True).strip()=='device'
  for local,remote in ((18080,8080),(12222,2222)):
   subprocess.run(adb+['forward',f'tcp:{local}',f'tcp:{remote}'],check=True,capture_output=True)
  io.URL='http://127.0.0.1:18080';io.ssh_base=tunneled(ssh_base)
  report['before']=safe(OLD);report['calibration_before']=io.calibration_hash(out,report)
  # Preserve all existing archived capture files, including original raw traces.
  inventory={}
  paths=subprocess.check_output(['rg','--files','-uu','-g','trace.bin','-g','decoded.json','-g','*.sal','artifacts'],cwd=p.ROOT,text=True).splitlines()
  for rel in paths:
   path=p.ROOT/rel
   if p.OUT not in path.parents:inventory[rel]=sha(path)
  p.write(out/'preserved_captures_sha256.json',json.dumps(inventory,indent=2))
  report['preserved_capture_files']=len(inventory)
  uno_port,native_port=io.board_ports();report['ports']=[uno_port,native_port]
  ssh=io.ssh_base('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  scp=tunneled(scp_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  remote=out/'remote_hmi_installer.py';p.write(remote,hmi.remote_installer())
  prefix='/tmp/mic_multi_'+uuid.uuid4().hex
  files=[(p.OUT/'web_hmi/server.py',prefix+'_server.py'),(p.OUT/'web_hmi/static/app.js',prefix+'_app.js'),(remote,prefix+'_install.py')]
  for local,dest in files:run(scp+[str(local),'arduino@192.168.1.138:'+dest],'stage_'+local.name,45)
  cmd=['python3',files[2][1],'--candidate',files[0][1],'--sha256',sha(files[0][0]),'--app-js',files[1][1],
       '--app-js-sha256',sha(files[1][0]),'--max-vdc','20','--confirm-mains-off']
  # The candidate calibration validator intentionally knows the NEW identity.
  # Install HMI after both exact images boot; never rewrite points or fake IDs.
  report['before_flash']=safe(OLD)
  report['nucleo_flash_commands']=1
  output=run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','sn='+io.STLINK_SERIAL,
       '-halt','-w',str(native),'-v','-halt','-score'],'flash_verify_halt_nucleo')
  report['nucleo_readback_verified']=True;report['halted_native']=True
  checkpoint()
  # Firmware reset/halt is part of programming, never a motor command or CLEAR.
  upload=['arduino-cli','upload','-p',uno_port,'-b','arduino:zephyr:unoq','-i',str(uno),
      '--upload-property','upload.artifacts.sketch='+str(uno),
      '--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL]
  report['uno_flash_commands']=1;run(upload,'flash_uno')
  run(upload+['--upload-property','build.variant.path='+str(p.ROOT/'tools'),
      '--upload-property','openocd_cfg=verify_restart_unoq_sketch.cfg'],'verify_uno')
  assert 'UNO Q verification PASSED; restarting unchanged images' in p.read(out/'verify_uno.log')
  report['uno_readback_verified']=True
  checkpoint()
  time.sleep(3)
  run([str(io.PROGRAMMER),'-c','port=SWD','mode=HOT','sn='+io.STLINK_SERIAL,'-rst'],'boot_verified_nucleo',40)
  report['native_boot_released']=True
  checkpoint()
  report['after_images_before_hmi']=wait_safe(p.NEW)
  run(ssh+[shlex.join(cmd+['--check-only'])],'hmi_precheck',45)
  safe(p.NEW);run(ssh+[shlex.join(cmd)],'install_hmi',60);report['hmi_installed']=True
  report['calibration_after']=io.calibration_hash(out,report)
  assert report['calibration_before']==report['calibration_after'];report['calibration_unchanged']=True
  report['after']=wait_safe(p.NEW);report['passed']=True
  for rel,h in inventory.items():assert sha(p.ROOT/rel)==h,rel
  report['archived_captures_unchanged']=True
 except Exception as exc:report['error']=str(exc)
 finally:p.write(out/'install_report.json',json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:report.get(k) for k in ('passed','uno_flash_commands','nucleo_flash_commands',
   'uno_readback_verified','nucleo_readback_verified','calibration_unchanged','archived_captures_unchanged','error')}))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

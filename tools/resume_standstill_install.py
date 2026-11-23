"""Complete an already verified install; no second flash writes or motor commands."""
import json,shlex,subprocess,time,uuid
import install_standstill_commissioning as wrap
from unoq_wifi_hmi_deploy import ssh_base,scp_base
from install_sd_break_filter_usb_pair import tunneled
p=wrap.p;io=wrap.install.io
def main():
 out=p.OUT/'hardware_install_r1';old=json.loads(p.read(out/'install_report.json'))
 assert old.get('uno_readback_verified') and old.get('nucleo_readback_verified')
 assert not old.get('hmi_installed')
 report=dict(passed=False,additional_flash_commands=0,start_commands=0,clear_commands=0,arm_commands=0)
 def run(cmd,label,timeout=90):return io.run(cmd,label,out,report,timeout)
 try:
  io.URL='http://127.0.0.1:18080';io.ssh_base=tunneled(ssh_base)
  uno,native=wrap.verify();port=io.board_ports()[0]
  try:
   s=io.live_status();ok,why=wrap.install.precheck(s)
   already_recovered=ok and (s['fw_build'],s['mc_fw_build'])==p.NEW
  except Exception:already_recovered=False
  # The router explicitly reports get unregistered, MCU has no core fault.
  # Reboot verified MCU images once so it registers against the reopened port.
  if already_recovered:
   report['runtime_recovered_without_additional_mcu_restart']=True
  else:
   run([str(io.PROGRAMMER),'-c','port=SWD','mode=HOT','sn='+io.STLINK_SERIAL,'-halt','-score'],'rpc_recovery_native_halt',20)
   run(['arduino-cli','upload','-p',port,'-b','arduino:zephyr:unoq','-i',str(uno),
    '--upload-property','upload.artifacts.sketch='+str(uno),'--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL,
    '--upload-property','build.variant.path='+str(p.ROOT/'tools'),'--upload-property','openocd_cfg=verify_restart_unoq_sketch.cfg'],
    'rpc_recovery_verified_uno_restart',60)
   report['verified_uno_restart_commands']=1
   time.sleep(3)
   run([str(io.PROGRAMMER),'-c','port=SWD','mode=HOT','sn='+io.STLINK_SERIAL,'-rst'],'rpc_recovery_native_boot',20)
  end=time.monotonic()+35;last=''
  while time.monotonic()<end:
   try:
    s=io.live_status();ok,why=wrap.install.precheck(s)
    assert ok,why;assert (s['fw_build'],s['mc_fw_build'])==p.NEW
    report['before_hmi']=s;break
   except Exception as exc:last=str(exc);time.sleep(.5)
  else:raise RuntimeError('Verified restart did not restore RPC: '+last)
  ssh=io.ssh_base('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  scp=tunneled(scp_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  helper=out/'remote_hmi_installer.py';prefix='/tmp/mic_ident_'+uuid.uuid4().hex
  files=[(p.OUT/'web_hmi/server.py',prefix+'_server.py'),(p.OUT/'web_hmi/static/app.js',prefix+'_app.js'),(helper,prefix+'_install.py')]
  for local,remote in files:run(scp+[str(local),'arduino@192.168.1.138:'+remote],'recovery_stage_'+local.name,30)
  command=['python3',files[2][1],'--candidate',files[0][1],'--sha256',wrap.sha(files[0][0]),
    '--app-js',files[1][1],'--app-js-sha256',wrap.sha(files[1][0]),'--max-vdc','20','--confirm-mains-off']
  run(ssh+[shlex.join(command+['--check-only'])],'recovery_hmi_precheck',40)
  run(ssh+[shlex.join(command)],'recovery_install_hmi',50);report['hmi_installed']=True
  report['calibration_after']=io.calibration_hash(out,report)
  assert report['calibration_after']==old['calibration_before'];report['calibration_unchanged']=True
  s=io.live_status();ok,why=wrap.install.precheck(s);assert ok,why
  assert (s['fw_build'],s['mc_fw_build'])==p.NEW;report['after']=s
  inventory=json.loads(p.read(out/'preserved_captures_sha256.json'))
  for rel,digest in inventory.items():assert wrap.sha(p.ROOT/rel)==digest,rel
  report.update(passed=True,archived_captures_unchanged=True,preserved_capture_files=len(inventory))
 except Exception as exc:report['error']=str(exc)
 p.write(out/'runtime_recovery.json',json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:report.get(k) for k in ('passed','additional_flash_commands','verified_uno_restart_commands','hmi_installed','calibration_unchanged','error')}))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

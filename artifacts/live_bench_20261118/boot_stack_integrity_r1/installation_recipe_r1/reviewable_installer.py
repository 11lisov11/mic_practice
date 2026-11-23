"""Install sealed 2026111611/1612, J1 OFF and bus below20V, USB boards; never START/CLEAR/ARM.

Preserve native RAM, previous flash, current Linux/HMI backup and calibration.
MCU programming uses ST-LINK and the installed Arduino upload/verify recipes.
"""
import argparse,ast,hashlib,json,shlex,subprocess,time,uuid
from pathlib import Path
import prepare_boot_stack_integrity as p
import install_bkin_boot_armed_pair as io
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base,scp_base
from wifi_stop_tail_probe import parse_registers

OLD=(2026111807,2026111806)
NEW=p.NEW

def package_check():
 m=json.loads(p.read(p.OUT/'manifest.json'))
 assert m['built'] and m['pair']==list(NEW) and not m['installed']
 assert m['control_and_observer_Q_R_math_unchanged']
 assert (m['raw_trip_A'],m['ADC_UPDATE_limit_ticks'],m['OFF_fast_budget_cycles'],m['estimate_age_limit_ms'])==(1.35,2048,4000,2)
 assert m['RUN_existing_deadline_cycles']==5312
 for name in ('core','adapter','model'):
  assert json.loads(p.read(p.OUT/f'verification/{name}_report.json'))['passed']
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in json.loads(p.read(p.OUT/'installation_assets.json')).items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in json.loads(p.read(p.OUT/'preserved_all_hashes.json')).items():assert p.sha(p.ROOT/rel)==h,rel
 for rel in ('nucleo/Inc/motor_control.h','nucleo/Inc/foc_experiment.h','nucleo/Src/current_shunt.c','nucleo/Inc/current_adc_deadline.h'):
  assert p.sha(p.OUT/rel)==p.sha(p.BASE/rel),rel
 return m


def safe(s,pair):
 assert (s.get('fw_build'),s.get('mc_fw_build'))==pair,'unexpected pair'
 assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0,'controller not OFF'
 assert not(s['bp_status']&0x22),'native running/enable bit active'
 assert s['rpc_schema_version']==3 and s['mc_capabilities']==1 and s['bp_mcsdk_telemetry']==1
 assert 0<=s['mc_age_ms']<300,'reply is stale'
 if pair!=OLD:
  assert all(s.get(k)==0 for k in ('mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence','uno_rx_hw_errors','uno_rx_dropped')),'new UART unhealthy'
 # Old UART faults are archived solely for OFF programming repair, never START.
 # Saved MCSDK/transport/RPC history is archived, not cleared. This stopped
 # programming check never authorizes a START or skips any firmware guard.
 assert all(s.get(k)==0 for k in ('precharge','pfc','brake','bp_ext')),'service output active'
 assert 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20,'bus not discharged'

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--verify-only',action='store_true')
 parser.add_argument('--confirmed-j1-off-current-usb-low-bus',action='store_true')
 parser.add_argument('--outdir',type=Path)
 a=parser.parse_args();m=package_check()
 if a.verify_only:print(json.dumps(dict(package_verified=True,pair=NEW,hardware_commands=0)));return 0
 if not a.confirmed_j1_off_current_usb_low_bus:parser.error('Existing operator preparation confirmation required')
 if a.outdir is None:parser.error('--outdir required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 r=dict(passed=False,pair=list(NEW),START=0,CLEAR=0,ARM=0,
  uno_flash_commands=0,nucleo_flash_commands=0,thresholds_changed=False,
  operator_confirmation='J1 OFF explicitly confirmed; exact PCUSB identities and fresh valid low-bus ADC/SWD observed; 15V and wiring unchanged; no START/CLEAR',
  physical_TP23_connection_independently_verified=False)
 def save():p.write(out/'report.json',json.dumps(r,ensure_ascii=False,indent=2))
 def run(command,label,timeout=60):
  result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
  p.write(out/(label+'.log'),result.stdout+result.stderr)
  r.setdefault('commands',[]).append(dict(label=label,exit_code=result.returncode));save()
  if result.returncode:raise RuntimeError(label+' failed; see log')
  return result.stdout
 router_closed=False
 try:
  adb=['adb','-s',io.UNO_SERIAL]
  assert run(adb+['get-state'],'adb_state',10).strip()=='device'
  for local,remote in ((18080,8080),(12222,2222)):
   run(adb+['forward',f'tcp:{local}',f'tcp:{remote}'],'forward_'+str(local),10)
  io.URL='http://127.0.0.1:18080';io.ssh_base=tunneled(ssh_base)
  ssh=io.ssh_base('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  scp=tunneled(scp_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  uno_port,_=io.board_ports()
  before=io.live_status();safe(before,OLD)
  p.write(out/'before.json',json.dumps(before,ensure_ascii=False,indent=2));r['before_pair']=list(OLD)
  for key,filename in (('mc_observer_trace_hex','observer_before.bin'),('mc_adc_peak_hex','ADC_before.bin')):
   value=before.get(key,'-')
   if value and value!='-':
    raw=bytes.fromhex(value);(out/filename).write_bytes(raw)
    r.setdefault('preserved_live_records',{})[filename]=p.sha(out/filename)

  swd=[str(io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+io.STLINK_SERIAL]
  def registers(label):
   raw=run(swd+['-r32','0x48000000','40','-r32','0x48000400','40','-r32','0x40012c00','104'],label,20)
   regs=parse_registers(raw)
   assert regs[0x40012c44]&4096 and not regs[0x40012c44]&32768,'BKE/MOE not safe'
   return regs
  regs=registers('registers_before')
  run(swd+['-u','0x20000000','32768',str(out/'native_RAM_before.bin')],'save_RAM_before',20)
  previous_expected=p.BASE/f'release/nucleo_{OLD[1]}_expected_readback.bin'
  run(swd+['-u','0x08000000',str(previous_expected.stat().st_size),str(out/f'native_flash_{OLD[1]}_before.bin')],'save_flash_before',20)
  assert (out/f'native_flash_{OLD[1]}_before.bin').read_bytes()==previous_expected.read_bytes()
  r['previous_native_image_verified']=True
  cal='/home/arduino/.config/mic-ai/vbus_calibration.json'
  r['calibration_before']=run(ssh+['sha256sum '+cal],'calibration_before',15).split()[0]
  assert len(r['calibration_before'])==64
  prefix='/tmp/mic_stack1810_'+uuid.uuid4().hex+'_'
  # Reuse the checked atomic deployment logic; it compares original calibration
  # against prospective verified identities, never fabricating live telemetry.
  tree=ast.parse(p.read(p.ROOT/'tools/finish_rollback_3014_hmi.py'))
  remote=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='REMOTE' for x in n.targets))
  remote=remote.replace("'rollback_3014_'","'stack_1810_'")
  cfg=dict(offline_programming_only=True,native_BKE=True,native_MOE=False,
   calibration_sha256=r['calibration_before'],prospective_identity=dict(before,fw_build=NEW[0],mc_fw_build=NEW[1]),files=[])
  for relative in ('server.py','static/app.js','static/index.html'):
   local=p.OUT/'web_hmi'/relative;target=prefix+local.name
   run(scp+[str(local),'arduino@192.168.1.138:'+target],'stage_'+local.name,30)
   got=run(ssh+['sha256sum '+shlex.quote(target)],'hash_'+local.name,15).split()[0]
   assert got==p.sha(local)
   cfg['files'].append(dict(remote=target,destination=relative,sha256=got))
  config=out/'deploy_config.json';p.write(config,json.dumps(cfg))
  helper=out/'deploy_hmi.py';p.write(helper,remote.replace('CONFIG',repr(prefix+config.name)))
  for local in (config,helper):run(scp+[str(local),'arduino@192.168.1.138:'+prefix+local.name],'stage_'+local.name,30)
  # Validate calibration/schema compatibility before either MCU is written.
  code="import importlib.util,json,pathlib; c=json.loads(pathlib.Path("+repr(prefix+config.name)+").read_text()); s=importlib.util.spec_from_file_location('candidate',c['files'][0]['remote']); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert m.VbusCalibrationStore('"+cal+"').is_valid(c['prospective_identity']); print('candidate calibration compatibility verified; no files changed')"
  run(ssh+['python3 -c '+shlex.quote(code)],'candidate_calibration_check',20)
  safe(io.live_status(),OLD)
  def route(action):
   code="import socket,msgpack; s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(5); s.connect('/var/run/arduino-router.sock'); u=msgpack.Unpacker(raw=False); s.sendall(msgpack.packb([0,1,'$/serial/"+action+"',['/dev/ttyHS1']],use_bin_type=True))\nwhile True:\n b=s.recv(65536);assert b;u.feed(b)\n for r in u:\n  if r[0]==1 and r[1]==1:\n   assert r[2] is None and r[3] is True,r\n   print('route "+action+" OK');raise SystemExit(0)"
   run(ssh+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(code)],'router_'+action,15)
  route('close');router_closed=True
  image=p.OUT/f'release/uno_{NEW[0]}_stack_epoch.elf-zsk.bin'
  upload=['arduino-cli','upload','-p',uno_port,'-b','arduino:zephyr:unoq','-i',str(image),
   '--upload-property','upload.artifacts.sketch='+str(image),'--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL]
  r['uno_flash_commands']=1;save();run(upload+['--upload-property','build.variant.path='+str(p.ROOT/'tools'),'--upload-property','openocd_cfg=flash_verify_unoq_history_hold.cfg'],'flash_uno',90)
  assert 'VERIFIED AND HELD' in p.read(out/'flash_uno.log')
  r['uno_held_for_paired_baud_change']=True;save()
  r['nucleo_flash_commands']=1;save()
  native=p.OUT/f'release/nucleo_{NEW[1]}_stack_guard.hex'
  run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','sn='+io.STLINK_SERIAL,'-w',str(native),'-v','-rst'],'flash_verify_nucleo',60)
  expected=p.OUT/f'release/nucleo_{NEW[1]}_expected_readback.bin'
  run(swd+['-u','0x08000000',str(expected.stat().st_size),str(out/f'native_flash_{NEW[1]}_readback.bin')],'readback_native',20)
  assert (out/f'native_flash_{NEW[1]}_readback.bin').read_bytes()==expected.read_bytes()
  r['native_readback_verified']=True;r['native_flash_sha256']=p.sha(out/f'native_flash_{NEW[1]}_readback.bin');save()
  run(upload+['--upload-property','build.variant.path='+str(p.ROOT/'tools'),
   '--upload-property','openocd_cfg=verify_restart_unoq_sketch.cfg'],'verify_uno',90)
  assert 'UNO Q verification PASSED; restarting unchanged images' in p.read(out/'verify_uno.log')
  r['uno_readback_verified']=True;save()
  route('open');router_closed=False
  # Deploy the exact matching server and reconnect its one owned client once.
  deployed=run(ssh+['python3 '+shlex.quote(prefix+helper.name)],'deploy_hmi',20)
  r['hmi_deployment']=json.loads(deployed)
  r['calibration_after']=run(ssh+['sha256sum '+cal],'calibration_after',15).split()[0]
  assert r['calibration_before']==r['calibration_after'];r['calibration_unchanged']=True;save()
  regs=registers('registers_after')
  r['native_BKE']=bool(regs[0x40012c44]&4096)
  r['native_MOE']=bool(regs[0x40012c44]&32768)
  deadline=time.monotonic()+40
  while time.monotonic()<deadline:
   try:
    after=io.live_status();safe(after,NEW)
    p.write(out/'after.json',json.dumps(after,ensure_ascii=False,indent=2))
    assert after.get('repeat_break',{}).get('available') and after['repeat_break']['fresh'],'repeat metadata pending'
    assert after.get('observer_trace')==dict(available=False,reason='not_received'),'observer recorder not empty'
    assert after['hmi_vbus_hv_calibrated']==1
    r.update(passed=True,SD=after.get('mc_sd_live'),repeat_break=after['repeat_break'],zero_ready=after['mc_current_zero_ready']);break
   except Exception as exc:r['runtime_pending']=str(exc);time.sleep(1)
  if not r['passed']:raise RuntimeError('Images verified; runtime status pending: '+r.get('runtime_pending',''))
 except Exception as exc:r['error']=str(exc)
 finally:
  if router_closed:
   try:route('open')
   except Exception as exc:r['router_reopen_error']=str(exc)
  save()
 print(json.dumps({k:r.get(k) for k in ('passed','native_readback_verified','uno_readback_verified','calibration_unchanged','native_BKE','native_MOE','repeat_break','error')},ensure_ascii=True))
 return 0 if r['passed'] else 1


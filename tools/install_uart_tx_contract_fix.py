"""Uno-only repair of proved TC-vs-TXE startup storm; native1806 never flashed."""
import ast,json,shlex,subprocess,time,uuid,sys
import prepare_uart_tx_contract_fix as p
import install_bkin_boot_armed_pair as io
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base,scp_base
from probe_native_programming_state import probe

def main():
 assert '--confirmed-j1-off-current-usb' in sys.argv
 m=json.loads(p.read(p.OUT/'release_manifest.json'));assert m['pair']==list(p.NEW) and not m['installed']
 for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h
 for rel,h in m['source_hashes'].items():assert p.sha(p.OUT/rel)==h
 for rel in m['tests']:assert json.loads(p.read(p.OUT/rel))['passed']
 for rel,h in json.loads(p.read(p.OUT/'preserved_inputs_sha256.json')).items():assert p.sha(p.ROOT/rel)==h,rel
 assert json.loads(p.read(p.BASE/'post_flash_RPC_r1/Uno_passive/report.json'))['core_running']
 assert not (p.OUT/'installation_acceptance.json').exists()
 out=p.OUT/'hardware_install_r1';out.mkdir(exist_ok=False)
 r=dict(passed=False,pair=p.NEW,nucleo_flash_commands=0,uno_flash_commands=0,START=0,CLEAR=0,ARM=0,thresholds_changed=False)
 def save():p.write(out/'report.json',json.dumps(r,indent=2)+'\n')
 def run(cmd,label,timeout=30):
  x=subprocess.run(cmd,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=timeout)
  p.write(out/(label+'.log'),x.stdout+x.stderr);x.check_returncode();return x.stdout+x.stderr
 closed=False
 try:
  # The failed Uno application cannot supply RPC. Exact native flash, fresh ADC,
  # progressing tick and MOE=0 prove OFF independently for programming only.
  proof=probe(p.BASE,out/'native_readiness','User confirmed J1OFF, both PCUSB,15V unchanged; repair only, no START')
  assert all(x['bdtr']&4096 and not x['moe'] and x['bus_volts']<20 for x in proof['rows'])
  swd=[str(io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+io.STLINK_SERIAL]
  run(swd+['-u','0x20000000','32768',str(out/'native_RAM_before.bin')],'native_RAM_before')
  adb=['adb','-s',io.UNO_SERIAL]
  for local,remote in ((18080,8080),(12222,2222)):run(adb+['forward',f'tcp:{local}',f'tcp:{remote}'],'forward_'+str(local))
  ssh=tunneled(ssh_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  scp=tunneled(scp_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  cal='/home/arduino/.config/mic-ai/vbus_calibration.json'
  r['calibration_before']=run(ssh+['sha256sum '+cal],'cal_before').split()[0]
  assert r['calibration_before']=='a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17'
  before=json.loads(p.read(p.BASE/'hardware_install_r1/before.json'))
  identity=dict(before,fw_build=p.NEW[0],mc_fw_build=p.NEW[1]) # intended identity, never live telemetry
  cfg=dict(offline_programming_only=True,native_BKE=True,native_MOE=False,
   calibration_sha256=r['calibration_before'],prospective_identity=identity,files=[])
  prefix='/tmp/uart1807_'+uuid.uuid4().hex+'_'
  for rel in ('server.py','static/app.js','static/index.html'):
   local=p.OUT/'web_hmi'/rel;remote=prefix+local.name
   run(scp+[str(local),'arduino@192.168.1.138:'+remote],'stage_'+local.name)
   assert run(ssh+['sha256sum '+shlex.quote(remote)],'hash_'+local.name).split()[0]==p.sha(local)
   cfg['files'].append(dict(remote=remote,destination=rel,sha256=p.sha(local)))
  config=out/'deploy_config.json';p.write(config,json.dumps(cfg))
  tree=ast.parse(p.read(p.ROOT/'tools/finish_rollback_3014_hmi.py'))
  helper_text=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REMOTE' for t in n.targets))
  helper=out/'deploy.py';p.write(helper,helper_text.replace("'rollback_3014_'","'uart_1807_'").replace('CONFIG',repr(prefix+config.name)))
  for local in (config,helper):run(scp+[str(local),'arduino@192.168.1.138:'+prefix+local.name],'stage_'+local.name)
  code="import importlib.util,json,pathlib; c=json.loads(pathlib.Path("+repr(prefix+config.name)+").read_text()); s=importlib.util.spec_from_file_location('candidate',c['files'][0]['remote']); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert m.VbusCalibrationStore('"+cal+"').is_valid(c['prospective_identity']);print('calibration compatible')"
  run(ssh+['python3 -c '+shlex.quote(code)],'candidate_calibration')
  def route(action):
   code="import socket,msgpack; s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(5); s.connect('/var/run/arduino-router.sock');u=msgpack.Unpacker(raw=False);s.sendall(msgpack.packb([0,1,'$/serial/"+action+"',['/dev/ttyHS1']],use_bin_type=True))\nwhile True:\n b=s.recv(65536);assert b;u.feed(b)\n for x in u:\n  if x[0]==1 and x[1]==1:\n   assert x[2] is None and x[3] is True,x\n   print('route "+action+" OK');raise SystemExit(0)"
   run(ssh+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(code)],'route_'+action)
  port,_=io.board_ports();route('close');closed=True
  image=p.OUT/'release/uno_2026111807_fifo_txe.elf-zsk.bin'
  upload=['arduino-cli','upload','-p',port,'-b','arduino:zephyr:unoq','-i',str(image),
   '--upload-property','upload.artifacts.sketch='+str(image),'--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL]
  r['uno_flash_commands']=1;save()
  run(upload+['--upload-property','build.variant.path='+str(p.ROOT/'tools'),'--upload-property','openocd_cfg=flash_verify_unoq_history_hold.cfg'],'flash_uno',90)
  run(upload+['--upload-property','build.variant.path='+str(p.ROOT/'tools'),'--upload-property','openocd_cfg=verify_restart_unoq_sketch.cfg'],'verify_uno',90)
  assert 'UNO Q verification PASSED; restarting unchanged images' in p.read(out/'verify_uno.log')
  r['uno_readback_verified']=True
  expected=p.OUT/'release/nucleo_2026111806_expected_readback.bin'
  actual=out/'native_unchanged_readback.bin'
  run(swd+['-u','0x08000000',str(expected.stat().st_size),str(actual)],'native_unchanged')
  assert actual.read_bytes()==expected.read_bytes();r['native_readback_verified']=True
  route('open');closed=False
  r['hmi_deployment']=json.loads(run(ssh+['python3 '+shlex.quote(prefix+helper.name)],'deploy_hmi'))
  r['calibration_after']=run(ssh+['sha256sum '+cal],'cal_after').split()[0]
  assert r['calibration_before']==r['calibration_after'];r['calibration_unchanged']=True
  r['passed']=True
 except Exception as e:r['error']=str(e)
 finally:
  if closed:
   try:route('open')
   except Exception as e:r['reopen_error']=str(e)
  save()
 if r.get('uno_readback_verified') and r.get('native_readback_verified'):
  p.write(p.OUT/'installation_acceptance.json',json.dumps(dict(installed=True,pair=p.NEW,uno_readback_verified=True,
   native_readback_verified=True,native_reflashed=False,runtime_verified=False,START=0,CLEAR=0,ARM=0),indent=2)+'\n')
 print(json.dumps({k:r.get(k) for k in ('passed','pair','uno_readback_verified','native_readback_verified','nucleo_flash_commands','calibration_unchanged','error')}))
 return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

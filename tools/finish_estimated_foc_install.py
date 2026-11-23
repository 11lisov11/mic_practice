"""Correct only the native image, preserve verified Uno, then install matching HMI."""
import json,shlex,subprocess,time,uuid
from types import SimpleNamespace
import prepare_estimated_foc_trial as p
import install_bkin_boot_armed_pair as io
import install_current_shunt_monitor as base
import install_research_suite as hmi
from probe_native_programming_state import probe
from seal_standstill_commissioning import sha
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base,scp_base

def main():
 out=p.OUT/'hardware_install_r2';out.mkdir(exist_ok=False)
 report=dict(passed=False,uno_flash_commands=0,nucleo_flash_commands=0,
  start_commands=0,clear_commands=0,existing_uno_readback_verified=True)
 def run(cmd,label,timeout=60):return io.run(cmd,label,out,report,timeout)
 old=(2026102951,2026102940)
 guard=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
  '((2026101805,2026101804),(2026101807,2026101806))',str((old,p.NEW)))
 scope={'math':__import__('math')};exec(guard,scope);check=scope['precheck'];base.GUARD=guard
 hmi.p=SimpleNamespace(ROOT=p.ROOT,OUT=p.OUT,NEW=p.NEW,OLD=old,read=p.read,write=p.write,once=p.once,sha=sha)
 try:
  assert json.loads(p.read(p.OUT/'verification/elf_identity.json'))['passed']
  prior=json.loads(p.read(p.ROOT/'artifacts/live_bench_20261029/estimated_foc_trial_r1/hardware_install_r1/install_report.json'))
  assert prior['uno_readback_verified'] and prior['uno_flash_commands']==1
  for rel,digest in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==digest,rel
  predecessor=p.ROOT/'artifacts/live_bench_20261029/estimated_foc_trial_r1'
  report['passive_guard']=probe(predecessor,out/'passive_native_guard',
   'existing authorized USB programming; last J1/J4 OFF; live passive low bus, MOE0 and old image checked')
  assert all(x['bus_volts']<=12 for x in report['passive_guard']['rows'])
  for local,remote in ((18080,8080),(12222,2222)):
   subprocess.run(['adb','-s',io.UNO_SERIAL,'forward',f'tcp:{local}',f'tcp:{remote}'],capture_output=True,check=True)
  io.URL='http://127.0.0.1:18080';io.ssh_base=tunneled(ssh_base)
  ssh=io.ssh_base('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  scp=tunneled(scp_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
  s=io.live_status();assert (s['fw_build'],s['mc_fw_build'])==old
  assert check(s)[0],check(s);report['before']=s
  report['calibration_before']=io.calibration_hash(out,report)
  run([str(io.PROGRAMMER),'-c','port=SWD','mode=HotPlug','sn='+io.STLINK_SERIAL,
       '-u','0x20000000','32768',str(out/'native_sram_before.bin')],'preserve_native_sram',25)
  report['nucleo_flash_commands']=1
  image=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
  run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','sn='+io.STLINK_SERIAL,
       '-w',str(image),'-v','-rst'],'flash_verify_native',60)
  report['nucleo_readback_verified']=True
  deadline=time.monotonic()+25
  while time.monotonic()<deadline:
   try:
    s=io.live_status()
    if (s['fw_build'],s['mc_fw_build'])==p.NEW and check(s)[0]:break
   except Exception:pass
   time.sleep(.3)
  else:raise RuntimeError('Correct native image written; new status not confirmed')
  report['before_hmi']=s
  helper=out/'remote_hmi_installer.py';p.write(helper,hmi.remote_installer());prefix='/tmp/mic_foc_'+uuid.uuid4().hex
  files=[(p.OUT/'web_hmi/server.py',prefix+'_server.py'),(p.OUT/'web_hmi/static/app.js',prefix+'_app.js'),(helper,prefix+'_install.py')]
  for local,remote in files:run(scp+[str(local),'arduino@192.168.1.138:'+remote],'stage_'+local.name,30)
  cmd=['python3',files[2][1],'--candidate',files[0][1],'--sha256',sha(files[0][0]),
       '--app-js',files[1][1],'--app-js-sha256',sha(files[1][0]),'--max-vdc','20','--confirm-mains-off']
  run(ssh+[shlex.join(cmd+['--check-only'])],'hmi_precheck',35)
  run(ssh+[shlex.join(cmd)],'install_hmi',50);report['hmi_installed']=True
  report['calibration_after']=io.calibration_hash(out,report)
  assert report['calibration_after']==report['calibration_before']
  report['calibration_unchanged']=True;report['after']=io.live_status();report['passed']=True
 except Exception as e:report['error']=str(e)
 p.write(out/'install_report.json',json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:report.get(k) for k in ('passed','uno_flash_commands','nucleo_flash_commands','nucleo_readback_verified','calibration_unchanged','hmi_installed','error')}))
 return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

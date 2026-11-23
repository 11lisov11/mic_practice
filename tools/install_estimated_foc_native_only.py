"""Native-only correction on an authorized OFF USB bench; preserve Uno and HMI."""
import argparse,json,time
from pathlib import Path
import prepare_estimated_foc_trial as p
import install_bkin_boot_armed_pair as io
from probe_native_programming_state import probe
from seal_standstill_commissioning import sha
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--predecessor',type=Path,required=True);a=ap.parse_args()
 out=p.OUT/'hardware_install_r1';out.mkdir(exist_ok=False)
 report=dict(passed=False,uno_flash_commands=0,nucleo_flash_commands=0,start_commands=0,clear_commands=0)
 def run(cmd,label,timeout=40):return io.run(cmd,label,out,report,timeout)
 try:
  assert json.loads(p.read(p.OUT/'verification/elf_identity.json'))['passed']
  manifest=json.loads(p.read(p.OUT/'manifest.json'));assert manifest['built'] and not manifest['installed']
  for rel,digest in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==digest,rel
  report['before']=probe(a.predecessor.resolve(),out/'passive_guard','same authorized discharged USB state, no new meter value claimed')
  assert all(x['bus_volts']<=12 for x in report['before']['rows'])
  io.ssh_base=tunneled(ssh_base);io.URL='http://127.0.0.1:18080'
  report['calibration_before']=io.calibration_hash(out,report)
  run([str(io.PROGRAMMER),'-c','port=SWD','mode=HotPlug','sn='+io.STLINK_SERIAL,'-u','0x20000000','32768',str(out/'native_sram_before.bin')],'preserve_native_sram')
  report['nucleo_flash_commands']=1
  run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','sn='+io.STLINK_SERIAL,'-w',str(p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'),'-v','-rst'],'flash_verify_native')
  report['nucleo_readback_verified']=True
  until=time.monotonic()+8
  while True:
   time.sleep(.3);s=io.live_status()
   assert (s['fw_build'],s['mc_fw_build'])==p.NEW and s['state']=='SAFE' and s['pwm']==0
   if s.get('foc_experiment_flags',0)&1 or s.get('foc_timing_fault',0) or time.monotonic()>until:break
  report['after']=s
  report['calibration_after']=io.calibration_hash(out,report)
  assert report['calibration_after']==report['calibration_before']
  report.update(passed=True,calibration_unchanged=True)
 except Exception as e:report['error']=str(e)
 p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:report.get(k) for k in ('passed','nucleo_flash_commands','nucleo_readback_verified','calibration_unchanged','error')}))
 if report.get('after'):
  print(json.dumps({k:report['after'].get(k) for k in ('mc_current_zero_ready','foc_experiment_flags','foc_timing_fault','foc_timing_cases','algorithm_fast_cycles','algorithm_observer_cycles','mc_fw_build')}))
 return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

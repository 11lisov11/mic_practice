"""Install one checked, bounded SDA recovery pair; no motor starts or CLEAR."""
import json,sys,subprocess,importlib.util
from pathlib import Path
import install_nucleo_i2c_idle as parent
import prepare_sda_idle_bus_clear as p
install=parent.install;parent.p=p
install.ROOT,install.C,install.OLD,install.NEW=p.ROOT,p.OUT,p.OLD,p.NEW
install.GUARD=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace('((2026101805,2026101804),(2026101807,2026101806))','((2026102705,2026102706),(2026102707,2026102708))');exec(install.GUARD,install.__dict__)
def verify_package():
 c=p.OUT;m=json.loads(p.read(c/'manifest.json'))
 assert m['schema']=='mic_ai.sda_idle_bus_clear.v1' and m['pair_compatibility_ids']==list(p.NEW) and m['built'] and m['selftest_pass']
 for k in ('sensor_feedback_control','motor_control_changed','thresholds_changed','calibration_changed','uart_command_protocol_changed','bkin_changed','adc_trigger_changed','pwm_ccr123_changed','deadtime_changed','watchdogs_changed'):assert m[k] is False,k
 assert m['bus_clear_once_per_boot'] and m['bus_clear_max_clocks']==9 and m['bus_clear_off_and_below_20v_only']
 for name in ('source_sha256','build_sha256','verification_sha256'):
  for rel,digest in m[name].items():assert p.sha(c/rel)==digest,rel
 for rel,digest in m['historical_records_preserved'].items():assert p.sha(c/'preserved_records'/rel)==digest
 images=[]
 for folder,name,fw in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
  b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==fw
  for f in b['artifacts']:assert p.sha(c/'build'/folder/f['file'])==f['sha256'].lower()
  images.append(c/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
 assert json.loads(p.read(c/'verification/report.json'))['passed'];return tuple(images)
install.verify_package=verify_package
def main():
 if '--verify-package-only' in sys.argv:return parent.main()
 if '--confirm-j1-off-meter-below-20v-both-usb' in sys.argv and '--outdir' in sys.argv:
  verify_package();adb=['adb','-s',install.io.UNO_SERIAL]
  assert subprocess.check_output(adb+['get-state'],text=True).strip()=='device'
  subprocess.run(adb+['forward','tcp:18080','tcp:8080'],check=True,capture_output=True);install.io.URL='http://127.0.0.1:18080'
  spec=importlib.util.spec_from_file_location('preserve_live',p.ROOT/'tools/pe_release_capture/preserve_live.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  original=module.complete
  module.complete=lambda s:original(s) and s.get('enc_release_decode_valid')==1 and (s.get('enc_fault_first_hex','-')=='-' or s.get('enc_release_first_hex','-')!='-')
  out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
  def guard(s):
   if (s.get('fw_build'),s.get('mc_fw_build'))!=p.OLD:return False,'unexpected installed pair'
   return install.precheck(s)
  # The installed2705 HMI omitted2706 from the SD ABI whitelist. Re-decode its
  # unmodified raw flags locally using the checked decoder, before any reset.
  # Keep original responses too; a ready SD record still requires full archive.
  from ipm_break_wifi_selftest import load_module
  hmi=load_module(p.OUT/'web_hmi/server.py')
  raw_log=out.with_name(out.name+'_original_status.jsonl')
  assert not raw_log.exists(),'Preserve earlier raw responses'
  def read_for_archive():
   s=install.io.live_status()
   with raw_log.open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
   decoded=dict(s);decoded['mc_sd_live']=hmi.sd_live_status(s)
   return decoded
  module.preserve(read_for_archive,guard,out.with_name(out.name+'_preserved_live'))
 # A guard rejection can be a retained UART snapshot with healthy RPC. Never
 # close its router serial port: that unregisters live MCU-provided methods.
 # Keep the original failed runtime report for a separate, read-only audit.
 return install.main()
if __name__=='__main__':raise SystemExit(main())

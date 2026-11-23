"""Record checked images only in confirmed programming state; no motor actions."""
import json
import sys,subprocess
from pathlib import Path
import install_nucleo_i2c_idle as parent
import prepare_pe_release_capture as p
install=parent.install;parent.p=p
install.ROOT,install.C,install.OLD,install.NEW=p.ROOT,p.OUT,p.OLD,p.NEW
install.GUARD=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace('((2026101805,2026101804),(2026101807,2026101806))','((2026102703,2026102704),(2026102705,2026102706))')
exec(install.GUARD,install.__dict__)
def verify_package():
 c=p.OUT;m=json.loads(p.read(c/'manifest.json'))
 assert m['schema']=='mic_ai.pe_release_capture.v1' and m['pair_compatibility_ids']==list(p.NEW) and m['built'] and m['selftest_pass']
 assert m['original_capture_bytes']==160 and m['original_capture_format']==2 and m['extension_bytes']==100 and m['extension_parent_crc32c_link']
 for k in ('sensor_feedback_control','motor_control_changed','thresholds_changed','calibration_changed','uart_command_protocol_changed','bkin_changed','adc_trigger_changed','pwm_ccr123_changed','deadtime_changed','watchdogs_changed'):assert m[k] is False,k
 for table in ('source_sha256','build_sha256','verification_sha256'):
  assert m[table]
  for rel,h in m[table].items():assert p.sha(c/rel)==h,rel
 for name,h in m['historical_records_preserved'].items():assert p.sha(c/'preserved_records'/name)==h
 images=[]
 for folder,name,build in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
  b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==build
  if folder=='nucleo':assert b['build_errors']==b['build_warnings']==0
  for item in b['artifacts']:assert p.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
  images.append(c/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
 assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
 assert json.loads(p.read(c/'verification/report.json'))['passed']
 return tuple(images)
install.verify_package=verify_package
def main():
 if '--verify-package-only' in sys.argv:return parent.main()
 if '--confirm-j1-off-meter-below-20v-both-usb' in sys.argv and '--outdir' in sys.argv:
  verify_package()
  # This is inside the explicit programming-state path. Inventory alone never
  # sets that confirmation. Preserve all decoded RAM records before reset/flash.
  adb=['adb','-s',install.io.UNO_SERIAL]
  assert subprocess.check_output(adb+['get-state'],text=True).strip()=='device'
  subprocess.run(adb+['forward','tcp:18080','tcp:8080'],check=True,capture_output=True)
  install.io.URL='http://127.0.0.1:18080'
  import importlib.util
  spec=importlib.util.spec_from_file_location('pe_preserve_live',p.RES/'preserve_live.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve();archive=out.with_name(out.name+'_preserved_live')
  def guard(s):
   if (s.get('fw_build'),s.get('mc_fw_build'))!=p.OLD:return False,'unexpected installed pair'
   return install.precheck(s)
  module.preserve(install.io.live_status,guard,archive)
 return parent.main()
if __name__=='__main__':raise SystemExit(main())

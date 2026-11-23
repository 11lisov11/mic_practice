"""Install only in confirmed deenergized programming state; no motor command."""
import json
import install_nucleo_i2c_idle as parent
import prepare_nucleo_i2c_stop as p
install=parent.install
parent.p=p
install.ROOT,install.C,install.OLD,install.NEW=p.ROOT,p.OUT,p.OLD,p.NEW
install.GUARD=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace('((2026101805,2026101804),(2026101807,2026101806))','((2026102701,2026102702),(2026102703,2026102704))')
exec(install.GUARD,install.__dict__)
def verify_package():
 c=p.OUT;m=json.loads(p.read(c/'manifest.json'))
 assert m['schema']=='mic_ai.nucleo_i2c_stop_recovery.v1' and m['pair_compatibility_ids']==list(p.NEW)
 assert m['built'] and m['selftest_pass'] and m['capture_format']==2 and m['health_delivery_outputs_off_only']
 for k in ('sensor_feedback_control','motor_control_changed','thresholds_changed','calibration_changed','uart_command_protocol_changed','bkin_changed','adc_trigger_changed','pwm_ccr123_changed','deadtime_changed','watchdogs_changed'):assert m[k] is False,k
 for table in ('source_sha256','build_sha256','verification_sha256'):
  assert m[table]
  for rel,digest in m[table].items():assert p.sha(c/rel)==digest,rel
 images=[]
 for folder,name,build in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
  b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==build
  if folder=='nucleo':assert b['build_errors']==b['build_warnings']==0
  for item in b['artifacts']:assert p.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
  images.append(c/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
 b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
 for rel,digest in b['library_override_sha256'].items():assert p.sha(c/'libraries'/rel)==digest.lower()
 assert json.loads(p.read(c/'verification/report.json'))['passed'] and json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
 return tuple(images)
install.verify_package=verify_package
if __name__=='__main__':raise SystemExit(parent.main())

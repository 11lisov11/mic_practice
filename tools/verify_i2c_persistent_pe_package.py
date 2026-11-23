"""Read-only local image/hash verifier. No hardware libraries or install path."""
import json
import prepare_i2c_persistent_pe as p
def main():
 c=p.OUT;m=json.loads(p.read(c/'manifest.json'))
 assert m['schema']=='mic_ai.i2c_persistent_pe.v1' and m['pair_compatibility_ids']==list(p.NEW) and m['built'] and m['selftest_pass']
 assert not m['installed'] and m['successful_read_keeps_pe_enabled'] and m['error_cleanup_policy_unchanged']
 for k in ('sensor_feedback_control','motor_control_changed','thresholds_changed','calibration_changed','uart_command_protocol_changed','bkin_changed','adc_trigger_changed','pwm_ccr123_changed','deadtime_changed','watchdogs_changed'):assert m[k] is False,k
 for table in ('source_sha256','build_sha256','verification_sha256'):
  assert m[table]
  for rel,d in m[table].items():assert p.sha(c/rel)==d,rel
 for rel,d in m['historical_records_preserved'].items():assert p.sha(c/'preserved_records'/rel)==d,rel
 images=[]
 for folder,name,fw in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
  b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==fw
  for item in b['artifacts']:assert p.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
  file=c/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex');images.append(dict(file=str(file),sha256=p.sha(file)))
 assert json.loads(p.read(c/'verification/report.json'))['passed']
 print(json.dumps(dict(passed=True,hardware_commands=0,installed=False,images=images)))
if __name__=='__main__':main()

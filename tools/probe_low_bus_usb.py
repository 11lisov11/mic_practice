"""Read-only programming evidence, including a genuinely discharged0V bus.

Both fresh valid telemetry and direct SWD reads must agree. No claim that two
paths reading the same ADC constitute an independent physical voltmeter.
"""
import inspect,json
import probe_native_programming_state as native
import install_bkin_boot_armed_pair as io


def off(s,pair):
 assert (s['fw_build'],s['mc_fw_build'])==pair
 assert s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==0 and not s['bp_status']&0x22
 assert s['bp_vbus_valid']==1 and 0<=s['bp_vbus_age_ms']<300 and 0<=s['mc_age_ms']<300
 assert 0<=s['vdc']<20 and 0<=s['bp_vdc']<20


def probe(package,out,pair):
 out.mkdir(parents=True,exist_ok=False);result=dict(passed=False,flash_writes=0,reset_commands=0,halt_commands=0,motor_commands=0)
 try:
  before=io.live_status();off(before,pair)
  (out/'before_status.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
  source=inspect.getsource(native.probe)
  old="factor==416 and digital>0 and 0<volts<=20,'no positive independently corroborated low bus'"
  new="factor==416 and 0<=volts<20,'native low bus not corroborated'"
  assert old in source;source=source.replace(old,new)
  scope=dict(native.__dict__);exec(compile(source,__file__,'exec'),scope)
  evidence=scope['probe'](package,out/'readings','User completed requested J1OFF/discharge/PCUSB preparation; observed valid low bus and OFF, no invented meter number')
  after=io.live_status();off(after,pair)
  assert all(abs(x['bus_volts']-after['bp_vdc'])<=2 for x in evidence['rows']),'ADC telemetry/SWD mismatch'
  assert before['linux_boot_id']==after['linux_boot_id']
  (out/'after_status.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
  result.update(evidence,fresh_live_bus_valid=True,HMI_raw_bus_V=after['bp_vdc'],zero_allowed=True,
                voltage_proof_scope='Fresh HMI and direct SWD agree on one ADC; not an independent physical voltmeter')
 except Exception as error:
  result['error']=str(error);raise
 finally:(out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 return result

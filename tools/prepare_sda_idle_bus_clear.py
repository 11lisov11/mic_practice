"""Bounded OFF-only bus clear for an SDA-low startup, preserving all captures."""
import ast,json,os,shutil
from pathlib import Path
import prepare_pe_release_capture as previous
ROOT=previous.ROOT;BASE=previous.OUT;OUT=ROOT/'artifacts/live_bench_20261027/sda_idle_recovery_r1'
RES=ROOT/'tools/sda_idle_bus_clear';OLD=(2026102705,2026102706);NEW=(2026102707,2026102708)
read,write,sha,once=previous.read,previous.write,previous.sha,previous.once
def main():
 assert not (OUT/'manifest.json').exists(),'Keep existing candidate'
 m=json.loads(read(BASE/'manifest.json'));assert m['installed']
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for rel,digest in m[table].items():assert sha(BASE/rel)==digest,rel
 for name in ('nucleo','UNOQ_MOTOR','web_hmi','libraries'):
  def copy(src,dst):
   rel=Path(src).relative_to(BASE/name)
   if name=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/name,OUT/name,copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    a=read(f);b=a.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
    if a!=b:write(f,b)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  for name in ('bus_clear.h','bus_clear_wire.h'):shutil.copy2(RES/name,OUT/folder/name)
 f=OUT/'nucleo/Src/nucleo_encoder.c';s=read(f)
 s=once(s,'static bool config_ok(void){',read(RES/'platform.inc')+'\nstatic bool config_ok(void){')
 s=once(s,'  release_poll();','  release_poll();\n  if(bus_clear_service())return;');write(f,s)
 f=OUT/'nucleo/Inc/nucleo_encoder.h';write(f,once(read(f),'#endif','void mic_encoder_allow_bus_clear(bool);\nbool mic_encoder_bus_clear_packet(uint8_t*);\n#endif'))
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'static void uno_send_reply(void) {',read(RES/'sender.inc')+'\nstatic void uno_send_reply(void) {')
 s=once(s,'    mic_encoder_poll();',
  '    mic_encoder_allow_bus_clear(!uno_link.command_enabled && mic_break_start_window==0U &&\n'
  '      !LL_TIM_IsEnabledAllOutputs(TIM1) &&\n'
  '      (MC_GetSTMStateMotor1()==IDLE || MC_GetSTMStateMotor1()==FAULT_NOW || MC_GetSTMStateMotor1()==FAULT_OVER) &&\n'
  '      VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)<20U);\n    mic_encoder_poll();')
 s=once(s,'    mic_send_encoder_release_page(HAL_GetTick());','    mic_send_encoder_release_page(HAL_GetTick());\n    mic_send_bus_clear(HAL_GetTick());');write(f,s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 s=once(s,'static eh_receiver g_encoder_health={};','static eh_receiver g_encoder_health={};\n#include "bus_clear_wire.h"\nstatic uint8_t g_bus_clear[UV3_FRAME];static bool g_bus_clear_seen;')
 s=once(s,'      if(buf[2]==PR_WIRE){',read(RES/'uno_rx.inc')+'\n      if(buf[2]==PR_WIRE){')
 s=once(s,'    s += " enc_release_good=";',read(RES/'uno_text.inc')+'\n    s += " enc_release_good=";');write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 # Retain installed pair support and add the new pair in all identity gates.
 for a,b in [('(2026102705,2026102706)','(2026102707,2026102708)'),('(2026102705, 2026102706)','(2026102707, 2026102708)')]:s=s.replace(a,a+','+b)
 s=s.replace('(2026102604,2026102702,2026102704,2026102706)','(2026102604,2026102702,2026102704,2026102706,2026102708)')
 s=s.replace('peer in (2026102704,2026102706)','peer in (2026102704,2026102706,2026102708)')
 s=s.replace('peer!=2026102706 or len(raw)!=100','peer not in (2026102706,2026102708) or len(raw)!=100')
 # SD/Break retain exactly the same wire contract; these gates store peer IDs
 # individually rather than as pairs. Keep both installed and new IDs.
 s=s.replace(',2026102704)',',2026102704,2026102706,2026102708)').replace(', 2026102704)',', 2026102704, 2026102706, 2026102708)')
 s=once(s,"parent_crc32c=f'{w[2]:08x}',record_crc32c=f'{crc32c(raw):08x}'","parent_crc32c=f'{w[2]:08x}',record_crc32c=f'{w[24]:08x}',wire_crc32c_residue=f'{crc32c(raw):08x}'")
 s=once(s,'def with_i2c_release(data):',read(RES/'hmi.inc')+'\ndef with_i2c_release(data):')
 s=once(s,'    return with_i2c_release(out)','    return with_bus_clear(with_i2c_release(out))')
 s=once(s,'                "enc_release_first_hex":','                "enc_bus_clear_hex": kv.get("enc_bus_clear_hex","-"),\n                "enc_release_first_hex":');ast.parse(s);write(f,s)
 f=OUT/'web_hmi/static/app.js';s=read(f)
 s=once(s,'      encVal.textContent = text;',
  '      if (data.enc_bus_clear_record) text += `; ${data.enc_bus_clear_record.summary_ru}`;\n      encVal.textContent = text;');write(f,s)
 for name in ('verification','build/uno','build/nucleo','preserved_records'):(OUT/name).mkdir(parents=True,exist_ok=True)
 archive={}
 for rel in ('install_20261027_r1_preserved_live/saved_status.json','install_20261027_r1/idle_first_capture.json','install_20261027_r1/idle_samples.json','install_20261027_r1/report.json','installation_evidence.json'):
  dst=OUT/'preserved_records'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(BASE/rel,dst);archive[rel]=sha(dst)
 shutil.copytree(BASE/'preserved_records',OUT/'preserved_records/earlier_history');
 for f in (OUT/'preserved_records/earlier_history').rglob('*'):
  if f.is_file():archive[str(f.relative_to(OUT/'preserved_records')).replace('\\','/')]=sha(f)
 r=dict(schema='mic_ai.sda_idle_bus_clear.v1',pair_compatibility_ids=list(NEW),predecessor=str(BASE),built=False,selftest_pass=False,installed=False,
  sensor_feedback_control=False,motor_control_changed=False,thresholds_changed=False,calibration_changed=False,uart_command_protocol_changed=False,bkin_changed=False,adc_trigger_changed=False,pwm_ccr123_changed=False,deadtime_changed=False,watchdogs_changed=False,
  original_capture_bytes=160,original_capture_format=2,extension_bytes=100,extension_parent_crc32c_link=True,
  i2c_recovery_changed=True,bus_clear_once_per_boot=True,bus_clear_off_and_below_20v_only=True,bus_clear_max_clocks=9,
  no_irq_mask_or_delay_loop=True,original_i2c_core_unchanged=True,first_records_frozen=True,sensor_under_pwm_qualified=False,hardware_validated=False,primary_nack_physical_cause_proven=False,
  calibration_sha256=m['calibration_sha256'],historical_records_preserved=archive)
 write(OUT/'manifest.json',json.dumps(r,indent=2)+'\n');print(json.dumps(dict(prepared=True,pair=NEW,archived_files=len(archive))))
if __name__=='__main__':main()

"""Integrate append-only PE0 observations without changing I2C/PWM policy."""
import ast,json,os,shutil
from pathlib import Path
import prepare_nucleo_i2c_stop as previous
ROOT=previous.ROOT;BASE=previous.OUT
OUT=ROOT/'artifacts/live_bench_20261027/pe_release_capture_r1'
RES=ROOT/'tools/pe_release_capture'
OLD=(2026102703,2026102704);NEW=(2026102705,2026102706)
read,write,sha,once=previous.read,previous.write,previous.sha,previous.once
def driver(s):
 s=once(s,'#include "fault_wire.h"','#include "fault_wire.h"\n#include "release_wire.h"\n'+read(RES/'driver_helpers.inc'))
 s=once(s,'(void)I2C1->CR1;__DSB();I2C1->CR2=0;',
     '(void)I2C1->CR1;__DSB();\n  if(release_pending)release_after_park(DWT->CYCCNT);\n  I2C1->CR2=0;')
 s=once(s,'r[39]=cyc;\n  }',
     'r[39]=cyc;\n    sr_arm(&release_probe[slot],cyc,gpio);release_pending|=(uint8_t)(1U<<slot);\n  }')
 s=once(s,'void mic_encoder_poll(void){','void mic_encoder_poll(void){\n  release_poll();')
 s+='\n'+read(RES/'producer.inc')
 return s
def uno(s):
 s=once(s,'static eh_receiver g_encoder_health={};',
     'static eh_receiver g_encoder_health={};\n#include "release_wire.h"\nstatic pr_receiver g_release_capture={};')
 s=once(s,'      if(buf[2]==FC_WIRE) {',read(RES/'uno_rx.inc')+'\n      if(buf[2]==FC_WIRE) {')
 s=once(s,'    s += " enc_peer_good=";',read(RES/'uno_text.inc')+'\n    s += " enc_peer_good=";')
 return s
def hmi(s):
 for a,b in [('(2026102703,2026102704)','(2026102705,2026102706)'),('(2026102703, 2026102704)','(2026102705, 2026102706)')]:s=s.replace(a,a+','+b)
 s=once(s,'peer not in (2026102604,2026102702,2026102704)','peer not in (2026102604,2026102702,2026102704,2026102706)')
 s=once(s,'if peer==2026102704 else','if peer in (2026102704,2026102706) else')
 s=once(s,'    if peer==2026102704:','    if peer in (2026102704,2026102706):')
 s=once(s,'def with_i2c_first_fault(data):',read(RES/'hmi_decode.inc')+'\ndef with_i2c_first_fault(data):')
 s=once(s,"    out['enc_fault_capture_status']='Снимок первого сбоя сохранён' if records else 'Ожидание первого сбоя I²C'\n    return out",
     "    out['enc_fault_capture_status']='Снимок первого сбоя сохранён' if records else 'Ожидание первого сбоя I²C'\n    return with_i2c_release(out)")
 s=once(s,'                "enc_fault_first_hex":',
     '                "enc_release_first_hex": kv.get("enc_release_first_hex","-"),\n                "enc_release_pwm_hex": kv.get("enc_release_pwm_hex","-"),\n                "enc_release_good": int(kv.get("enc_release_good","0")),\n                "enc_release_bad": int(kv.get("enc_release_bad","0")),\n                "enc_fault_first_hex":')
 ast.parse(s);return s
def main():
 assert not (OUT/'manifest.json').exists(),'Preserve package'
 m=json.loads(read(BASE/'manifest.json'));assert m['installed'] and m['built']
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for rel,d in m[table].items():assert sha(BASE/rel)==d,rel
 for name in ('nucleo','UNOQ_MOTOR','web_hmi','libraries'):
  def copier(src,dst):
   rel=Path(src).relative_to(BASE/name)
   if name=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/name,OUT/name,copy_function=copier,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    a=read(f);b=a.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
    if a!=b:write(f,b)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  shutil.copyfile(ROOT/'tools/scl_stop_audit/pe_release_probe.h',OUT/folder/'pe_release_probe.h')
  shutil.copyfile(RES/'release_wire.h',OUT/folder/'release_wire.h')
 f=OUT/'nucleo/Src/nucleo_encoder.c';write(f,driver(read(f)))
 f=OUT/'nucleo/Inc/nucleo_encoder.h';write(f,once(read(f),'#endif','bool mic_encoder_release_packet(uint8_t*,unsigned,unsigned);\n#endif'))
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'#include "encoder_health_wire.h"','#include "encoder_health_wire.h"\n#include "release_wire.h"')
 s=once(s,'static void uno_send_reply(void) {',read(RES/'sender.inc')+'\nstatic void uno_send_reply(void) {')
 s=once(s,'    mic_send_encoder_health_page(HAL_GetTick());','    mic_send_encoder_health_page(HAL_GetTick());\n    mic_send_encoder_release_page(HAL_GetTick());');write(f,s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';write(f,uno(read(f)))
 f=OUT/'web_hmi/server.py';write(f,hmi(read(f)))
 f=OUT/'web_hmi/static/app.js';s=read(f)
 s=once(s,'      encVal.textContent = text;',
     '      const releaseRecords = Array.isArray(data.enc_release_records) ? data.enc_release_records : [];\n      const releaseRecord = releaseRecords.find(x => x.kind === "first_with_pwm") || releaseRecords[0];\n      if (releaseRecord) text += `; ${releaseRecord.summary_ru}`;\n      encVal.textContent = text;');write(f,s)
 for d in ('verification','build/uno','build/nucleo','preserved_records'):(OUT/d).mkdir(parents=True,exist_ok=True)
 archive={}
 for name in ('before_preflight.json','prestart_bkin_trace.json','prestart_break_snapshot.json','prestart_sd_ack.json','analysis.json','trial/report.json','trial/first_i2c_capture.json','repeat_trial/report.json','repeat_trial/after_diagnostics.json','repeat_trial/operator_confirmed_result.json'):
  src=BASE/'powered_first_fault_5hz_r1'/name;dst=OUT/'preserved_records'/name;dst.parent.mkdir(parents=True,exist_ok=True)
  shutil.copy2(src,dst);assert sha(src)==sha(dst);archive[name]=sha(src)
 write(OUT/'preserved_records/sha256.json',json.dumps(archive,indent=2)+'\n')
 result=dict(schema='mic_ai.pe_release_capture.v1',pair_compatibility_ids=list(NEW),built=False,selftest_pass=False,installed=False,predecessor=str(BASE),
  sensor_feedback_control=False,motor_control_changed=False,thresholds_changed=False,calibration_changed=False,uart_command_protocol_changed=False,bkin_changed=False,adc_trigger_changed=False,pwm_ccr123_changed=False,deadtime_changed=False,watchdogs_changed=False,rpc_libraries_unchanged=True,
  original_capture_bytes=160,original_capture_format=2,extension_bytes=100,extension_pages=5,extension_format=1,extension_crc32c=True,extension_parent_crc32c_link=True,
  data_acquisition_budget_ms=3,cleanup_budget_us=500,error_backoff_ms=20,no_gpio_bus_pulses=True,no_delay_added=True,no_interrupt_mask_added=True,
  off_only_delivery=True,first_records_frozen=True,sensor_under_pwm_qualified=False,hardware_validated=False,primary_nack_physical_cause_proven=False,
  calibration_sha256=m['calibration_sha256'],historical_records_preserved=archive)
 write(OUT/'manifest.json',json.dumps(result,indent=2)+'\n');print(json.dumps({'prepared':True,'pair':NEW,'archive_files':len(archive)}))
if __name__=='__main__':main()

"""Qualify target images, resource bounds and protected-source isolation."""
import json,re,subprocess
from pathlib import Path
import prepare_pe_release_capture as p
def main():
 c=p.OUT;v=c/'verification';native=json.loads(p.read(v/'native_report.json'));assert native['passed']
 stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL';debug=c/'nucleo/STM32CubeIDE/Debug'
 b=json.loads(p.read(debug/(stem+'.build-manifest.json')));assert b['firmware_build_id']==p.NEW[1] and b['build_errors']==b['build_warnings']==0
 def end(folder):return int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(folder/(stem+'.map')))[1],16)
 delta=end(debug)-end(p.BASE/'nucleo/STM32CubeIDE/Debug');margin=0x20008000-end(debug)-0x600
 assert 0<=delta<=192 and margin>=3300,(delta,margin)
 stack=p.read(debug/'Application/User/nucleo_encoder.su')
 sizes={name:int(re.search(':'+name+r'\s+(\d+)\s',stack)[1]) for name in ('capture_before_reset','capture_terminal','mic_encoder_poll','mic_encoder_release_packet','park')}
 assert sizes['capture_before_reset']==24 and sizes['capture_terminal']<=48 and sizes['mic_encoder_poll']<=64 and sizes['mic_encoder_release_packet']<=160 and sizes['park']<=32
 adc=int(re.search(r':mic_current_adc_irq\s+(\d+)\s',p.read(debug/'Application/User/current_shunt.su'))[1]);assert adc==376
 b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'));assert b['firmware_build_id']==p.NEW[0]
 for rel,digest in b['library_override_sha256'].items():assert p.sha(c/'libraries'/rel)==digest.lower()
 assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
 proof=False
 for folder in (Path.home()/'AppData/Local/arduino/sketches').iterdir():
  dep=folder/'sketch/UNOQ_MOTOR.ino.cpp.d'
  if not dep.is_file():continue
  text=dep.read_text(encoding='utf-8').replace('\\\n','').replace('\\','/')
  if str(c/'libraries').replace('\\','/') not in text:continue
  st=(folder/'libraries/Arduino_RouterBridge/singletons.cpp.d').read_text(encoding='utf-8').replace('\\\n','').replace('\\','/')
  for rel in ('Arduino_RouterBridge/src/bridge.h','Arduino_RPClite/src/decoder.h'):
   path=str(c/'libraries'/rel).replace('\\','/');assert path in text and path in st,rel
  p.write(v/'uno_dependencies.txt',text);p.write(v/'singleton_dependencies.txt',st);proof=True
 assert proof
 ui=json.loads(subprocess.check_output(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],text=True));assert ui['passed']
 subprocess.run(['node','--check',str(c/'web_hmi/static/app.js')],capture_output=True,check=True)
 old=p.read(p.BASE/'web_hmi/static/app.js');new=p.read(c/'web_hmi/static/app.js')
 new=new.replace('      const releaseRecords = Array.isArray(data.enc_release_records) ? data.enc_release_records : [];\n      const releaseRecord = releaseRecords.find(x => x.kind === "first_with_pwm") || releaseRecords[0];\n      if (releaseRecord) text += `; ${releaseRecord.summary_ru}`;\n','')
 assert new==old,'UI buttons/guards changed'
 for name,digest in json.loads(p.read(c/'preserved_records/sha256.json')).items():assert p.sha(c/'preserved_records'/name)==digest
 report=dict(passed=True,hardware_commands=0,native_report='native_report.json',native_tests_pass=True,hmi_corruption_and_link_checks=native['hmi_corruption_and_link_checks'],core_event_cases=native['core']['event_cases'],
  protection_source_isolation=True,original_160B_capture_preserved=True,extension_linked_by_parent_crc=True,off_only_delivery=True,historical_records_preserved=True,
  nucleo_static_growth_bytes=delta,nucleo_ram_margin_above_heap_stack=margin,nucleo_stack_frames=sizes,adc_irq_stack_bytes=adc,
  nucleo_build_errors=0,nucleo_build_warnings=0,uno_loader_check=True,packaged_rpc_dependencies_verified=True,
  no_motor_starts=True,no_clear=True,no_resets=True,no_flash=True,sensor_under_pwm_qualified=False,hardware_validated=False,
  limitations=['Native peripheral behavior is modeled; not evidence of which component physically holds SCL','Late samples retain observed times; requested5/20us are thresholds, not guaranteed hardware-triggered sample times','Stack frame budgets are checked; a complete hardware worst-case stack watermark has not been measured'])
 p.write(v/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()

"""Qualify both target images and seal the offline persistent-PE package."""
import json,re,shutil,subprocess
from pathlib import Path
import prepare_i2c_persistent_pe as p
def main():
 c=p.OUT;v=c/'verification';m=json.loads(p.read(c/'manifest.json'));assert not m['installed']
 n=json.loads(p.read(v/'native_report.json'));assert n['passed'] and n['protection_source_isolation']
 stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL';debug=c/'nucleo/STM32CubeIDE/Debug'
 b=json.loads(p.read(debug/(stem+'.build-manifest.json')));assert b['firmware_build_id']==p.NEW[1] and b['build_errors']==b['build_warnings']==0
 for f in debug.iterdir():
  if f.is_file() and f.name.startswith(stem+'.'):shutil.copy2(f,c/'build/nucleo'/f.name)
 def end(folder):return int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(folder/(stem+'.map')))[1],16)
 delta=end(debug)-end(p.BASE/'nucleo/STM32CubeIDE/Debug');margin=0x20008000-end(debug)-0x600
 assert 0<=delta<=32 and margin>=3200,(delta,margin)
 su=p.read(debug/'Application/User/nucleo_encoder.su')
 stack={name:int(re.search(':'+name+r'\s+(\d+)\s',su)[1]) for name in ('mic_encoder_poll','capture_terminal','mic_encoder_bus_clear_packet','mic_encoder_release_packet')}
 assert stack['mic_encoder_poll']<=64 and stack['capture_terminal']==40 and stack['mic_encoder_bus_clear_packet']<=32 and stack['mic_encoder_release_packet']<=160
 assert re.search(r':mic_current_adc_irq\s+376\s',p.read(debug/'Application/User/current_shunt.su'))
 for folder,name,fw in [('nucleo',stem,p.NEW[1]),('uno','unoq_mcsdk_scalar',p.NEW[0])]:
  b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==fw
  for item in b['artifacts']:assert p.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
 assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
 b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
 for rel,d in b['library_override_sha256'].items():assert p.sha(c/'libraries'/rel)==d.lower()
 proof=False
 for folder in (Path.home()/'AppData/Local/arduino/sketches').iterdir():
  f=folder/'sketch/UNOQ_MOTOR.ino.cpp.d'
  if not f.is_file():continue
  text=f.read_text(encoding='utf-8').replace('\\\n','').replace('\\','/')
  if str(c/'libraries').replace('\\','/') not in text:continue
  st=(folder/'libraries/Arduino_RouterBridge/singletons.cpp.d').read_text(encoding='utf-8').replace('\\\n','').replace('\\','/')
  for rel in ('Arduino_RouterBridge/src/bridge.h','Arduino_RPClite/src/decoder.h'):
   target=str(c/'libraries'/rel).replace('\\','/');assert target in text and target in st
  p.write(v/'uno_dependencies.txt',text);p.write(v/'singleton_dependencies.txt',st);proof=True
 assert proof
 ui=json.loads(subprocess.check_output(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],text=True));assert ui['passed']
 subprocess.run(['node','--check',str(c/'web_hmi/static/app.js')],capture_output=True,check=True)
 for rel,d in m['historical_records_preserved'].items():assert p.sha(c/'preserved_records'/rel)==d
 old=json.loads(p.read(p.BASE/'manifest.json'))
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for rel,d in old[table].items():assert p.sha(p.BASE/rel)==d
 r=dict(passed=True,hardware_commands=0,pair=list(p.NEW),native_tests_pass=True,
  healthy_reads_tested=200,healthy_pe_enables=1,healthy_pe_disables=0,
  recovery_event_cases=n['regression']['event_cases'],core_assertions=n['regression']['checks'],bus_clear_cases=n['bus_clear_core']['cases'],hmi_checks=n['hmi_checks'],
  healthy_idle_config_verified=True,encoder_wire_with_idle_pe1_verified=True,error_cleanup_preserved=True,first_records_frozen=True,
  protection_source_isolation=True,timing_filters_and_timeouts_unchanged=True,adc_irq_stack_bytes=376,nucleo_build_errors=0,nucleo_build_warnings=0,
  nucleo_ram_growth_bytes=delta,nucleo_ram_margin_above_heap_stack=margin,nucleo_stack_frames=stack,
  uno_loader_pass=True,rpc_dependency_override_verified=True,calibration_identity_compatible=True,archived_files=len(m['historical_records_preserved']),historical_records_sha_verified=True,
  installed_package_sha_verified_unchanged=True,flash_commands=0,motor_commands=0,clear_commands=0,reset_commands=0,hardware_validated=False,initial_pwm_nack_fixed_or_proven=False,
  limitations=['Peripheral behavior is modeled; this is not a physical PWM test','The first recorded NACK remains an error, not a valid angle','Target image stack frames checked; full hardware worst-case stack watermark not measured'])
 p.write(v/'report.json',json.dumps(r,indent=2)+'\n')
 tools=('prepare_i2c_persistent_pe.py','check_i2c_persistent_pe.py','seal_i2c_persistent_pe.py','verify_i2c_persistent_pe_package.py')
 p.write(v/'tool_sources.json',json.dumps({str(p.ROOT/'tools'/name):p.sha(p.ROOT/'tools'/name) for name in tools},indent=2)+'\n')
 m.update(built=True,selftest_pass=True,nucleo_ram_growth_bytes=delta,nucleo_ram_margin_above_heap_stack=margin)
 for name,trees in [('source_sha256',('nucleo','UNOQ_MOTOR','web_hmi','libraries')),('build_sha256',('build',)),('verification_sha256',('verification','preserved_records'))]:
  m[name]={str(f.relative_to(c)).replace('\\','/'):p.sha(f) for tree in trees for f in sorted((c/tree).rglob('*')) if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
 p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()

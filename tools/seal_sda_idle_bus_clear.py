"""Check both targets, unchanged protection paths and seal candidate images."""
import json,re,shutil,subprocess
import prepare_sda_idle_bus_clear as p
def main():
 c=p.OUT;v=c/'verification';m=json.loads(p.read(c/'manifest.json'));assert not m['installed']
 n=json.loads(p.read(v/'native_report.json'));assert n['passed'] and n['protected_sources_unchanged']
 stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL';debug=c/'nucleo/STM32CubeIDE/Debug'
 b=json.loads(p.read(debug/(stem+'.build-manifest.json')));assert b['firmware_build_id']==p.NEW[1] and b['build_errors']==b['build_warnings']==0
 for f in debug.iterdir():
  if f.is_file() and f.name.startswith(stem+'.'):shutil.copy2(f,c/'build/nucleo'/f.name)
 def end(folder):return int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(folder/(stem+'.map')))[1],16)
 delta=end(debug)-end(p.BASE/'nucleo/STM32CubeIDE/Debug');margin=0x20008000-end(debug)-0x600;assert 0<=delta<=128 and margin>=3200,(delta,margin)
 su=p.read(debug/'Application/User/nucleo_encoder.su');stack={name:int(re.search(':'+name+r'\s+(\d+)\s',su)[1]) for name in ('mic_encoder_poll','capture_terminal','mic_encoder_bus_clear_packet')}
 assert stack['mic_encoder_poll']<=64 and stack['capture_terminal']==40 and stack['mic_encoder_bus_clear_packet']<=32
 assert re.search(r':mic_current_adc_irq\s+376\s',p.read(debug/'Application/User/current_shunt.su'))
 for folder,name,fw in [('nucleo',stem,p.NEW[1]),('uno','unoq_mcsdk_scalar',p.NEW[0])]:
  b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==fw
  for f in b['artifacts']:assert p.sha(c/'build'/folder/f['file'])==f['sha256'].lower()
 assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
 b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
 for rel,digest in b['library_override_sha256'].items():assert p.sha(c/'libraries'/rel)==digest.lower()
 proof=False
 for folder in (p.Path.home()/'AppData/Local/arduino/sketches').iterdir():
  f=folder/'sketch/UNOQ_MOTOR.ino.cpp.d'
  if not f.is_file():continue
  text=f.read_text(encoding='utf-8').replace('\\\n','').replace('\\','/')
  if str(c/'libraries').replace('\\','/') not in text:continue
  st=(folder/'libraries/Arduino_RouterBridge/singletons.cpp.d').read_text(encoding='utf-8').replace('\\\n','').replace('\\','/')
  for rel in ('Arduino_RouterBridge/src/bridge.h','Arduino_RPClite/src/decoder.h'):
   target=str(c/'libraries'/rel).replace('\\','/');assert target in text and target in st
  proof=True
 assert proof
 ui=json.loads(subprocess.check_output(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],text=True));assert ui['passed']
 subprocess.run(['node','--check',str(c/'web_hmi/static/app.js')],check=True,capture_output=True)
 for rel,digest in m['historical_records_preserved'].items():assert p.sha(c/'preserved_records'/rel)==digest
 r=dict(passed=True,hardware_commands=0,native_tests_pass=True,core_cases=n['core']['cases'],old_core_cases=n['original_core_regression']['event_cases'],hmi_checks=n['hmi_checks'],protection_source_isolation=True,calibration_unchanged=True,nucleo_build_errors=0,nucleo_build_warnings=0,nucleo_ram_growth_bytes=delta,nucleo_ram_margin_above_heap_stack=margin,stack_frames=stack,adc_irq_stack_bytes=376,rpc_dependency_override_verified=True,uno_loader_pass=True,historical_records_preserved=True,physical_sensor_recovery_verified=False,initial_physical_trigger_proven=False)
 p.write(v/'report.json',json.dumps(r,indent=2)+'\n')
 m.update(built=True,selftest_pass=True,nucleo_ram_growth_bytes=delta,nucleo_ram_margin_above_heap_stack=margin)
 for name,trees in [('source_sha256',('nucleo','UNOQ_MOTOR','web_hmi','libraries')),('build_sha256',('build',)),('verification_sha256',('verification','preserved_records'))]:
  m[name]={str(f.relative_to(c)).replace('\\','/'):p.sha(f) for tree in trees for f in sorted((c/tree).rglob('*')) if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
 p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()

"""Seal the completed offline Nucleo diagnostic and its restoration image."""
import json,re,struct,subprocess,shutil
from pathlib import Path
import prepare_no_switch_diag as p
from no_switch_diag_io import decode,crc32c,eligible
GNU=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin')
def main():
 c=p.OUT;v=c/'verification';debug=c/'nucleo/STM32CubeIDE/Debug';stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 native=json.loads(p.read(v/'native_tests.json'));math=json.loads(p.read(v/'math_report.json'));assert native['passed'] and math['passed']
 host=json.loads(p.read(v/'host_selftest.json'));assert host['passed'] and host['actual_hardware_calls']==0
 b=json.loads(p.read(debug/(stem+'.build-manifest.json')));assert b['firmware_build_id']==p.BUILD and b['build_errors']==b['build_warnings']==0
 for item in b['artifacts']:assert p.sha(debug/item['file'])==item['sha256'].lower()
 for suffix in ('.hex','.bin','.elf','.map','.build-manifest.json'):
  shutil.copy2(debug/(stem+suffix),c/'build/nucleo'/(stem+suffix))
 raw=subprocess.check_output([str(GNU/'arm-none-eabi-nm.exe'),'-S','-n',str(debug/(stem+'.elf'))],text=True)
 symbols={}
 for line in raw.splitlines():
  a=line.split()
  if len(a)==4 and a[3] in ('mic_load_report','mic_load_request','fault_record','release_probe'):
   address,size=int(a[0],16),int(a[1],16);assert 0x20000000<=address<address+size<=0x20008000
   assert a[3] not in symbols;symbols[a[3]]=dict(address=address,bytes=size)
 assert symbols['mic_load_report']['bytes']==288 and symbols['mic_load_request']['bytes']==4 and symbols['fault_record']['bytes']==320
 p.write(v/'symbols.json',json.dumps(symbols,indent=2)+'\n')
 end=int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(debug/(stem+'.map')))[1],16)
 margin=0x20008000-end-0x600;assert margin>=2600,margin
 stacks={}
 for file in ('load_diag','current_shunt'):
  su=p.read(debug/f'Application/User/{file}.su')
  for name,amount in re.findall(r':(\w+)\s+(\d+)\s',su):stacks[name]=int(amount)
 # Bound individual diagnostic frames and retain >2.6KiB beyond the existing
 # heap/stack reservation. This is not a measured worst-case stack watermark.
 assert stacks['mic_load_poll']<=384 and stacks['mic_current_adc_irq']<=400 and stacks['mic_load_tim_update']<=64
 # Unlinked sections retain relocations as placeholders, so addresses assigned
 # by the two linkers cannot hide or invent changes to the actual arithmetic.
 proof={}
 for obj,names in [('Middlewares/MotorControl/acim_vf_control.o',('ACIM_VF_Controller','ACIM_VF_CalcAngle','ACIM_VF_FluxFreqCalc','ACIM_VF_ExecRamp')),('Middlewares/MotorControl/pwm.o',('PWM_SetPhasePWMOutputs',))]:
  for name in names:
   blobs=[]
   for tag,folder in [('production',p.BASE/'nucleo/STM32CubeIDE/Debug'),('diagnostic',debug)]:
    target=v/(name+'_'+tag+'.bin')
    q=subprocess.run([str(GNU/'arm-none-eabi-objcopy.exe'),'--dump-section','.text.'+name+'='+str(target),str(folder/obj)],capture_output=True,text=True)
    assert q.returncode==0 and target.stat().st_size>0,(name,q.stderr)
    blobs.append(target.read_bytes())
   assert blobs[0]==blobs[1],name
   proof[name]=dict(identical=True,bytes=len(blobs[0]),sha256=p.sha(v/(name+'_diagnostic.bin')))
 # Real decoder rejects torn pages/unknown identity and admission fails closed.
 w=[0]*72;w[:4]=[0x3147444c,1,p.BUILD,72];w[4]=w[69]=2;w[11]=170000000;w[26]=10;w[28]=0x1000;w[29]=1;w[38]=1;w[59]=200;w[71]=0x4c44454e
 def seal(a):
  a=a.copy();a[70]=crc32c(struct.pack('<64I',*a[5:69]));return struct.pack('<72I',*a)
 good=seal(w);assert eligible(decode(good));neg=0
 for i in range(5,69):
  z=bytearray(good);z[4*i]^=1
  try:decode(z)
  except ValueError:neg+=1
  else:raise AssertionError('Corrupt report accepted')
 for index,value in [(5,1),(7,1),(11,0),(26,20),(28,0x9000),(28,0),(29,0),(38,0),(39,1),(40,1),(59,0)]:
  z=w.copy();z[index]=value;assert not eligible(decode(seal(z)));neg+=1
 z=w.copy();z[4]=3
 try:decode(seal(z))
 except ValueError:neg+=1
 else:raise AssertionError('Torn sequence accepted')
 report=dict(passed=True,offline_only=True,hardware_tested=False,build=p.BUILD,target_errors=0,target_warnings=0,
  native_checks=native['core']['checks']+native['platform']['checks']+native['adc']['checks']+math['checks'],host_cases=len(host['cases']),
  actual_ADC_irq_model_samples=80000,ADC_model_samples_accepted=79999,actual_math_calls=80000,medium_ramp_calls=2500,
  target_math_sections=proof,RAM_margin_above_heap_stack_bytes=margin,stack_frames=stacks,decoder_negative_cases=neg,
  protection_functions_unchanged=True,UV_not_masked=True,actual_Vbus_not_forged=True,phase_pins_static_low=True,motor_ENABLE_rejected=True,
  I2C_state_machine_unchanged=True,source_and_previous_images_preserved=True,only_Nucleo_needs_programming=True,
  limitations=['Native register models are not electrical measurements','Target timing/rates/ADC-path coverage and I2C under load remain to be measured','The computation image is intentionally unsupported as a normal motor-control peer in the current HMI'])
 p.write(v/'report.json',json.dumps(report,indent=2)+'\n')
 m=json.loads(p.read(c/'manifest.json'));assert not m['installed']
 for rel,sha in m['preserved_records'].items():assert p.sha(c/'preserved_records'/rel)==sha
 for suffix in ('.hex','.bin','.elf','.build-manifest.json'):assert p.sha(c/'restore'/(stem+suffix))==p.sha(p.BASE/'build/nucleo'/(stem+suffix))
 m.update(built=True,offline_verified=True,hardware_tested=False,RAM_margin_above_heap_stack_bytes=margin,
  offline_report='verification/report.json',only_nucleo_update=True,normal_motor_control_disabled=True,
  actual_VF_math_machine_code_identical=True,private_MCSDK_ramp_ms=3000,private_normalizer='327/2; actual Vbus remains real',
  request_command='python tools/run_no_switch_diag.py --confirm-j1-j4-off-meter-below20-nucleo-usb --request-once --outdir <new-folder>',
  install_command='python tools/install_no_switch_diag.py --confirm-j1-j4-off-meter-below20-nucleo-usb --outdir <new-folder>')
 m['sealed_sha256']={str(f.relative_to(c)).replace('\\','/'):p.sha(f) for tree in ('nucleo','build','restore','verification','preserved_live','preserved_records') for f in sorted((c/tree).rglob('*')) if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
 m['tool_sha256']={str(f.relative_to(p.ROOT)).replace('\\','/'):p.sha(f) for f in [p.ROOT/'tools'/n for n in ('prepare_no_switch_diag.py','check_no_switch_diag.py','no_switch_diag_math_test.py','no_switch_diag_io.py','run_no_switch_diag.py','install_no_switch_diag.py','seal_no_switch_diag.py','no_switch_diag_host_selftest.py')]}
 p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()

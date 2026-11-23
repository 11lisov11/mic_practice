"""Seal the final timing/stack repair with model and exact source provenance."""
import json,subprocess,os,shutil
from pathlib import Path
import prepare_standstill_stack as p
from seal_standstill_commissioning import sha
def main():
 manifest=json.loads(p.read(p.OUT/'manifest.json'));assert not manifest['installed']
 assert (p.OUT/'nucleo/Inc/identify_core.h').read_bytes()==(p.ROOT/'tools/motor_commissioning/identify_fast_core.h').read_bytes()
 assert json.loads(p.read(p.OUT/'model/report.json'))['passed']
 assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 env=dict(os.environ);env['MIC_COMMISSIONING_TEST_DATA']=str(p.OUT/'model');v=p.OUT/'verification';v.mkdir(exist_ok=True)
 for label,args in [('native_tests',[str(p.ROOT/'.venv/Scripts/python.exe'),str(p.ROOT/'tools/test_standstill_stack.py')]),
  ('modulator',[str(p.ROOT/'.venv/Scripts/python.exe'),str(p.ROOT/'tools/test_identification_modulator.py')]),
  ('capture_tests',[str(p.ROOT/'.venv-research-gpu/Scripts/python.exe'),'-m','pytest',str(p.ROOT/'tests/test_acim_standstill_identification.py'),str(p.ROOT/'tests/test_commissioning_capture.py'),'-q']),
  ('javascript',['C:/Program Files/nodejs/node.exe','--check',str(p.OUT/'web_hmi/static/app.js')])]:
  r=subprocess.run(args,capture_output=True,text=True,env=env,cwd=p.ROOT);p.write(v/(label+'.log'),r.stdout+r.stderr);r.check_returncode()
 for name in ('main.c','current_shunt.c','stm32g4xx_mc_it.c','stm32g4xx_hal_msp.c'):
  assert p.read(p.BASE/'nucleo/Src'/name).replace('2026102934','2026102936')==p.read(p.OUT/'nucleo/Src'/name)
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,source in [('unoq_2026102935_stack.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'),
  ('nucleo_2026102936_stack.bin',p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin')]:shutil.copy2(source,release/name)
 hashes={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.log','.pyc'):hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(hashes,indent=2))
 model=json.loads(p.read(p.OUT/'model/report.json'))
 manifest.update(built=True,physical_qualification=False,native_timing_measured=False,deadline_cycles=5312,
  additional_preflight_kernel_limit_cycles=4800,model_validation_error=model['validation_error'],model_dc_points=30,model_ac_points=12,
  rpc_stack_old_bytes=500,rpc_stack_new_bytes=4096,old_minimum_get_chain_bytes=608,
  protective_registers_changed=False,adc_guard_changed=False,hardware_commands_sent=0,
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2));print(json.dumps(dict(built=True,pair=p.NEW,installed=False)))
if __name__=='__main__':main()

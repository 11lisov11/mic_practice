"""Seal identical electrical kernel with an OFF-only IRQ-context qualifier."""
import json,subprocess,shutil
from pathlib import Path
import prepare_standstill_irq_timing as p
from seal_standstill_commissioning import sha
from audit_production_pwm_filters import function
def main():
 manifest=json.loads(p.read(p.OUT/'manifest.json'));assert not manifest['installed']
 assert (p.BASE/'nucleo/Inc/identify_core.h').read_bytes()==(p.OUT/'nucleo/Inc/identify_core.h').read_bytes()
 model=json.loads(p.read(p.BASE/'model/report.json'));assert model['passed']
 assert model['kernel_sha256']==sha(p.OUT/'nucleo/Inc/identify_core.h')
 assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 v=p.OUT/'verification';v.mkdir(exist_ok=True)
 for label,cmd in [('native_host_tests',[str(p.ROOT/'.venv/Scripts/python.exe'),str(p.ROOT/'tools/test_standstill_irq_timing.py')]),
  ('javascript',['C:/Program Files/nodejs/node.exe','--check',str(p.OUT/'web_hmi/static/app.js')])]:
  r=subprocess.run(cmd,capture_output=True,text=True);p.write(v/(label+'.log'),r.stdout+r.stderr);r.check_returncode()
 for name in ('main.c','current_shunt.c','stm32g4xx_mc_it.c','stm32g4xx_hal_msp.c'):
  assert p.read(p.BASE/'nucleo/Src'/name).replace('2026102936','2026102938')==p.read(p.OUT/'nucleo/Src'/name)
 old=function(p.read(p.BASE/'nucleo/Src/mc_tasks.c'),'TSK_HighFrequencyTask')
 new=function(p.read(p.OUT/'nucleo/Src/mc_tasks.c'),'TSK_HighFrequencyTask')
 assert new.replace('    ma_native_profile_tick(); /* CPU-only work; never writes PWM. */\n','')==old
 p.write(p.OUT/'model_reference.json',json.dumps(dict(path=str(p.BASE/'model/report.json'),sha256=sha(p.BASE/'model/report.json'),
  identical_kernel_sha256=model['kernel_sha256'],passed=True,source_kind='synthetic'),indent=2))
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,f in [('unoq_2026102937_irq_timing.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'),
  ('nucleo_2026102938_irq_timing.bin',p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin')]:shutil.copy2(f,release/name)
 hashes={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.log','.pyc'):hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(hashes,indent=2))
 manifest.update(built=True,physical_qualification=False,native_timing_measured=False,deadline_cycles=5312,
  additional_preflight_kernel_limit_cycles=4800,rpc_updater_stack_bytes=4096,
  cpu_test_context='normal TIM1 update IRQ, MOE=0; no CCR writes or IRQ masks',
  adc_irq_changed=False,adc_window_geometry_changed=False,hardware_commands_sent=0,
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2));print(json.dumps(dict(built=True,pair=p.NEW,installed=False)))
if __name__=='__main__':main()

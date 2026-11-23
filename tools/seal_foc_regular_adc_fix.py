"""Seal asynchronous regular-ADC scheduling candidate; no board access."""
import hashlib,json,re,shutil,subprocess
from elftools.elf.elffile import ELFFile
import prepare_foc_regular_adc_fix as p
from build_multi_native import BIN
from test_foc_update_latency_fix import function
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def main():
 m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
 assert json.loads(p.read(p.OUT/'verification/selftest.json'))['passed']
 assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 assert json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))['firmware_build_id']==p.NEW[0]
 changed={'nucleo/Src/current_shunt.c','nucleo/Inc/current_shunt.h','nucleo/Src/regular_conversion_manager.c',
  'nucleo/Inc/regular_conversion_manager.h','nucleo/Src/mc_tasks.c','nucleo/Src/stm32g4xx_mc_it.c'}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
  for f in (p.OUT/folder).rglob('*'):
   if not f.is_file() or f.suffix not in ('.c','.h','.ino'):continue
   rel=f.relative_to(p.OUT).as_posix()
   if rel in changed:continue
   assert p.read(f)==p.read(p.BASE/rel).replace('2026103003','2026103005').replace('2026103004','2026103006'),rel
 old=p.read(p.BASE/'nucleo/Src/main.c');new=p.read(p.OUT/'nucleo/Src/main.c')
 for name in ('uno_rearm_break_irq','uno_handle_valid_frame','uno_clear_frame_is_safe','mic_local_stop_clear','mic_local_stop_enable_outputs'):
  assert function(old,name)==function(new,name),name
 assert re.findall(r'HAL_NVIC_SetPriority\([^;]+;',old)==re.findall(r'HAL_NVIC_SetPriority\([^;]+;',new)
 old=p.read(p.BASE/'nucleo/Src/stm32g4xx_mc_it.c');new=p.read(p.OUT/'nucleo/Src/stm32g4xx_mc_it.c')
 assert function(old,'TIMx_UP_M1_IRQHandler')==function(new,'TIMx_UP_M1_IRQHandler')
 assert function(old,'TIMx_BRK_M1_IRQHandler')==function(new,'TIMx_BRK_M1_IRQHandler')
 assert function(new,'ADC1_2_IRQHandler').replace('\n  RCM_ServiceAfterInjected();','')==function(old,'ADC1_2_IRQHandler')
 ef=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 from configure_multi_algorithm import load
 _,raw,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
 with ef.open('rb') as f:
  elf=ELFFile(f);syms={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
  def data(name,size):
   s=syms[name];sec=elf.get_section(s['st_shndx']);off=s['st_value']-sec['sh_addr'];return sec.data()[off:off+size]
  assert data('model',52)==raw and data('qualification',1)==bytes([128])
  ram=int(elf.get_section_by_name('.bss')['sh_size'])+int(elf.get_section_by_name('.data')['sh_size']);assert ram+1536<32768
  units=[]
  for cu in elf.get_dwarf_info().iter_CUs():
   a=cu.get_top_DIE().attributes.get('DW_AT_name')
   if a and 'live_bench_20261029' in a.value.decode(errors='replace'):
    n=a.value.decode(errors='replace').replace('\\','/');assert (p.OUT/'nucleo').as_posix() in n,n;units.append(n)
  for n in ('RCM_CurrentEpoch','RCM_ServiceAfterInjected','RCM_ExecRegularConv','rcm_fault'):assert n in syms,n
 dis=''
 for name in ('RCM_CurrentEpoch','RCM_ServiceAfterInjected','RCM_ExecRegularConv','mic_current_regular_window'):
  text=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d','--disassemble='+name,str(ef)],text=True)
  assert '<'+name+'>:' in text and 'cpsid' not in text and 'PRIMASK' not in text
  dis+=text
 p.write(p.OUT/'verification/regular_ADC_ARM.txt',dis)
 pending=p.read(p.OUT/'nucleo/Src/regular_conversion_manager.c')
 for name in ('RCM_CurrentEpoch','RCM_ServiceAfterInjected'):
  text=function(pending,name);assert 'while' not in text and '__disable_irq' not in text
 preserved={}
 for rel in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json'):
  preserved.update(json.loads(p.read(p.BASE/rel)))
 for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
 for folder in ('powered_FOC_CPU_IRQ_20261030_r1','powered_FOC_CPU_IRQ_20261030_r2',
                'autonomous_before_FOC_r1','autonomous_before_FOC_r2','FOC_CPU_IRQ_trial_preparation_r1'):
  for f in (p.BASE/folder).rglob('*'):
   if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=sha(f)
 for folder in ('powered_FOC_CPU_IRQ_20261030_r1','powered_FOC_CPU_IRQ_20261030_r2'):
  for rel,h in json.loads(p.read(p.BASE/folder/'saved_files_sha256.json')).items():assert sha(p.BASE/folder/rel)==h,rel
 for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert sha(p.BASE/rel)==h,rel
 p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2)+'\n')
 previous=json.loads(p.read(p.BASE/'verification/model_evidence.json'));model=p.ROOT/previous['source']
 assert sha(model)==previous['sha256']
 assert sha(p.OUT/'nucleo/Inc/motor_control.h')==json.loads(p.read(model))['actual_c_kernel_sha256']
 p.write(p.OUT/'verification/model_evidence.json',json.dumps(previous,indent=2)+'\n')
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,f in [('nucleo_2026103006_regular_adc.bin',ef.with_suffix('.bin')),
                ('unoq_2026103005_regular_adc.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')]:shutil.copy2(f,release/name)
 hashes={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.log'):hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(hashes,indent=2)+'\n')
 p.write(p.OUT/'verification/ELF_audit.json',json.dumps(dict(passed=True,exact_profile=True,
  source_units=units,static_RAM_bytes=ram,RAM_remaining_bytes=32768-ram,
  regular_start_from_ADC_tail_only=True,TIM_health_check_after_control=True,
  no_IRQ_masking_added=True,new_safety_cache_max_age_ms=1,OFF_blocking_api_preserved=True,
  trip_current_A=1.35,ADC_guard_ticks=2048,physical_spike_classification_unresolved=True),indent=2)+'\n')
 m.update(built=True,installed=False,selftests_passed=True,preserved_files_verified=len(preserved),
  actual_C_80000_frame_schedule_test_passed=True,recorded_spike_still_trips=True,
  real_hardware_5s_not_yet_proven=True,new_safety_cache_watchdog_ms=1,
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print(json.dumps({k:m[k] for k in ('pair','built','installed','preserved_files_verified','artifacts')}))
if __name__=='__main__':main()

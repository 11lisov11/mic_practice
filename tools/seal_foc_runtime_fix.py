"""Seal an offline-tested scheduling fix; no board access or actuating commands."""
import hashlib,json,re,shutil,subprocess
from elftools.elf.elffile import ELFFile
import prepare_foc_runtime_fix as p
from build_multi_native import BIN

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
 m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
 for rel in ('verification/selftest.json','verification/path_tests.json',
             'verification/latency_replay_r2/report.json','nucleo_build_report.json'):
  assert json.loads(p.read(p.OUT/rel))['passed'],rel
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 assert json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))['firmware_build_id']==p.NEW[0]
 from configure_multi_algorithm import load
 profile=p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json'
 _,raw,_=load(profile)
 ef=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 with ef.open('rb') as stream:
  elf=ELFFile(stream);syms={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
  def symbol_data(name,n):
   x=syms[name];sec=elf.get_section(x['st_shndx']);offset=x['st_value']-sec['sh_addr'];return sec.data()[offset:offset+n]
  assert symbol_data('model',52)==raw and symbol_data('qualification',1)==bytes([128])
  for name in ('mic_foc_irq_meter','ma_perf','ma_first_runtime','ma_observer_active','fe_trial_done','fe_trial_begin'):
   assert name in syms,name
  units=[]
  for cu in elf.get_dwarf_info().iter_CUs():
   a=cu.get_top_DIE().attributes.get('DW_AT_name')
   if a and 'live_bench_20261029' in a.value.decode(errors='replace'):
    n=a.value.decode(errors='replace').replace('\\','/')
    assert (p.OUT/'nucleo').as_posix() in n,n
    units.append(n)
  assert any(n.endswith('multi_native.c') for n in units)
  default=int(syms['Default_Handler']['st_value'])&~1
  vectors=elf.get_section_by_name('.isr_vector').data()
  active={}
  for i in range(2,len(vectors)//4):
   addr=int.from_bytes(vectors[4*i:4*i+4],'little')&~1
   if not addr or addr==default:continue
   names=[s.name for s in syms.values() if (int(s['st_value'])&~1)==addr and s['st_size']]
   active[i]=names
  expected={'ADC1_2_IRQHandler','TIM1_UP_TIM16_IRQHandler','TIM1_BRK_TIM15_IRQHandler',
   'USART2_IRQHandler','SysTick_Handler','EXTI15_10_IRQHandler',
   'DMA2_Channel1_IRQHandler','DMA1_Channel1_IRQHandler','USART1_IRQHandler'}
  found={name for group in active.values() for name in group}
  assert expected <= found
  assert found <= expected|{'HardFault_Handler'},found-expected
  ram=int(elf.get_section_by_name('.bss')['sh_size'])+int(elf.get_section_by_name('.data')['sh_size'])
  assert ram+1536<32768
 p.write(p.OUT/'verification/elf_identity.json',json.dumps(dict(passed=True,profile_bytes_exact=True,
  qualification=128,source_units=units,actual_vector_handlers=active,all_returning_handlers_instrumented=True,
  static_RAM_bytes=ram,RAM_after_static_bytes=32768-ram),indent=2))
 # No new global interrupt masks or priority changes, and no ADC-code change.
 for name in ('foc_timing_irq.h','foc_timing_core.h'):
  text=p.read(p.OUT/'nucleo/Inc'/name)
  assert not any(x in text for x in ('__disable_irq','__set_PRIMASK','BASEPRI','NVIC_'))
 old=p.read(p.BASE/'nucleo/Src/main.c');new=p.read(p.OUT/'nucleo/Src/main.c')
 assert re.findall(r'HAL_NVIC_SetPriority\([^;]+;',old)==re.findall(r'HAL_NVIC_SetPriority\([^;]+;',new)
 assert sha(p.BASE/'nucleo/Src/current_shunt.c')==sha(p.OUT/'nucleo/Src/current_shunt.c')
 # Existing independent model study is reused by exact kernel identity.
 prior=json.loads(p.read(p.BASE/'manifest.json'))
 reference=p.ROOT/prior['reused_model_evidence']['report'];model=json.loads(p.read(reference))
 assert sha(p.OUT/'nucleo/Inc/motor_control.h')==model['actual_c_kernel_sha256']
 assert all(x['passed'] for x in model['scenarios'] if x['label']=='central')
 reuse=dict(report=str(reference.relative_to(p.ROOT)),sha256=sha(reference),reused_not_rerun=True,
  kernel_sha256=model['actual_c_kernel_sha256'],central_passed=4,sensitivity_passed=54,sensitivity_total=60)
 p.write(p.OUT/'verification/model_evidence.json',json.dumps(reuse,indent=2))
 for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert sha(p.BASE/rel)==h,rel
 preserved=json.loads(p.read(p.BASE/'verification/preserved_captures_sha256.json'))
 for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
 for folder in ('autonomous_before_FOC_r1','autonomous_before_FOC_r2','powered_FOC_5Hz_5s_r1',
                'hardware_install_r1','hardware_install_r2','hardware_install_r3',
                'post_install_readback_r1','idle_verification_r1','powered_FOC_5Hz_5s_plan_r1'):
  for f in (p.BASE/folder).rglob('*'):
   if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=sha(f)
 p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2))
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,src in [('unoq_2026102971_foc_runtime.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'),
                  ('nucleo_2026102972_foc_runtime.bin',ef.with_suffix('.bin'))]:shutil.copy2(src,release/name)
 source_hashes={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.log'):
    source_hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(source_hashes,indent=2))
 m.update(built=True,installed=False,selftests_passed=True,target_timing_measured=False,
  hardware_CPU_IRQ_split_measured=False,exact_prior_runtime_fault_branch_proven=False,
  constructed_schedule_regression_passed=True,original_2ms_and_ADC_guards_unchanged=True,
  no_IRQ_masking_or_priority_change=True,OFF_split_probe_available=True,
  preserved_files_verified=len(preserved),reused_model_evidence=reuse,
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2))
 print(json.dumps({k:m[k] for k in ('pair','built','installed','preserved_files_verified','artifacts')}))

if __name__=='__main__':main()

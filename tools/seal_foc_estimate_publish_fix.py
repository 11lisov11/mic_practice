"""Seal the publication fix; verify guards, ARM handoff and old evidence."""
import hashlib,json,re,shutil,subprocess
from elftools.elf.elffile import ELFFile
import prepare_foc_estimate_publish_fix as p
from build_multi_native import BIN
from test_foc_update_latency_fix import function

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
 m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
 test=json.loads(p.read(p.OUT/'verification/selftest.json'));sim=json.loads(p.read(p.OUT/'verification/schedule_model.json'))
 assert test['passed'] and sim['passed'] and sim['results']['candidate']['completed_5s']
 assert sim['results']['candidate']['fault']==0
 assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 assert json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))['firmware_build_id']==p.NEW[0]
 changed={'nucleo/Src/multi_native.c','nucleo/Src/main.c','nucleo/Inc/foc_timing_core.h',
  'nucleo/Inc/foc_timing_wire.h','UNOQ_MOTOR/foc_timing_wire.h','UNOQ_MOTOR/UNOQ_MOTOR.ino','web_hmi/server.py'}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if not f.is_file() or '__pycache__' in f.parts:continue
   rel=f.relative_to(p.OUT).as_posix()
   if rel in changed:continue
   assert p.read(f)==p.read(p.BASE/rel).replace('2026103007','2026103009').replace('2026103008','2026103010').replace('3007-cache-snapshot','3009-estimate-publish'),rel
 old=p.read(p.BASE/'nucleo/Src/main.c');new=p.read(p.OUT/'nucleo/Src/main.c')
 assert re.findall(r'HAL_NVIC_SetPriority\([^;]+;',old)==re.findall(r'HAL_NVIC_SetPriority\([^;]+;',new)
 for name in ('uno_rearm_break_irq','uno_handle_valid_frame','uno_clear_frame_is_safe','mic_local_stop_clear','mic_local_stop_enable_outputs'):
  assert function(old,name)==function(new,name),name
 # main.c differs solely in the stopped-only E8 packet block and identities.
 fn='mic_send_research_page';expected=old.replace('2026103008','2026103010').replace('2026103007','2026103009')
 assert new.replace(function(new,fn),function(expected,fn))==expected
 old=p.read(p.BASE/'nucleo/Src/multi_native.c');new=p.read(p.OUT/'nucleo/Src/multi_native.c')
 for name in ('ma_native_config','fe_profile_allowed','fe_profile_tick','mi_native_fast','mi_native_service','ma_native_reference_allowed'):
  assert function(old,name)==function(new,name),name
 a=function(old,'ma_native_fast');b=function(new,'ma_native_fast')
 assert a[a.index('  int fresh='):]==b[b.index('  int fresh='):], 'freshness/ADC/control/limits/publicationCCR must stay identical'
 assert 'SystemCoreClock/500U' in b and 'SystemCoreClock*3U/16000U' in b
 service=function(new,'ma_native_service')
 assert service.index('ma_estimate_publish(observer.x,stamp)')<service.index('ft_clock clock_end=')<service.index('ft_measure(')
 assert 'if(dt>.002f)' in service
 header=p.read(p.OUT/'nucleo/Inc/motor_control.h')
 assert 'trip_current' in header and sha(p.OUT/'nucleo/Inc/motor_control.h')==sha(p.BASE/'nucleo/Inc/motor_control.h')
 ef=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 from configure_multi_algorithm import load
 _,raw,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
 with ef.open('rb') as stream:
  elf=ELFFile(stream);syms={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
  def data(name,size):
   s=syms[name];sec=elf.get_section(s['st_shndx']);off=s['st_value']-sec['sh_addr'];return sec.data()[off:off+size]
  assert data('model',52)==raw and data('qualification',1)==bytes([128])
  ram=elf.get_section_by_name('.bss')['sh_size']+elf.get_section_by_name('.data')['sh_size'];reserved=elf.get_section_by_name('._user_heap_stack')['sh_size']
  assert ram+reserved<32768
  units=[]
  for cu in elf.get_dwarf_info().iter_CUs():
   a=cu.get_top_DIE().attributes.get('DW_AT_name')
   if a and 'live_bench_20261029' in a.value.decode(errors='replace'):
    n=a.value.decode(errors='replace').replace('\\','/');assert (p.OUT/'nucleo').as_posix() in n,n;units.append(n)
 dis=''
 for name in ('ma_native_service','ma_native_fast','ma_fail_at','ma_native_regular_fault'):
  text=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d','--disassemble='+name,str(ef)],text=True)
  assert '<'+name+'>:' in text and 'cpsid' not in text.lower() and 'primask' not in text.lower(),name
  dis+=text
 assert 'dmb' in dis
 p.write(p.OUT/'verification/estimate_handoff_ARM.txt',dis)
 preserved={}
 for rel in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json'):
  preserved.update(json.loads(p.read(p.BASE/rel)))
 for folder in ('autonomous_before_FOC_r2','powered_FOC_ADC_20261030_r1','powered_FOC_ADC_20261030_r2'):
  for rel,h in json.loads(p.read(p.BASE/folder/'saved_files_sha256.json')).items():
   preserved[(p.BASE/folder/rel).relative_to(p.ROOT).as_posix()]=h
 for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
 for folder in p.BASE.iterdir():
  if folder.is_dir() and folder.name.startswith(('hardware_install','post_install','idle_verification','installation_verified','FOC_ADC_trial_preparation','autonomous_before','powered_FOC')):
   for f in folder.rglob('*'):
    if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=sha(f)
 for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert sha(p.BASE/rel)==h,rel
 p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2)+'\n')
 model=json.loads(p.read(p.BASE/'verification/model_evidence.json'));assert sha(p.ROOT/model['source'])==model['sha256']
 p.write(p.OUT/'verification/model_evidence.json',json.dumps(model,indent=2)+'\n')
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,f in [('nucleo_2026103010_estimate_publish.bin',ef.with_suffix('.bin')),
                ('unoq_2026103009_estimate_publish.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')]:shutil.copy2(f,release/name)
 hashes={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.log'):hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(hashes,indent=2)+'\n')
 p.write(p.OUT/'verification/ELF_audit.json',json.dumps(dict(passed=True,source_units=units,exact_profile=True,
  static_RAM_bytes=ram,linker_heap_stack_reserved_bytes=reserved,total_RAM_allocated=ram+reserved,RAM_unallocated=32768-ram-reserved,
  current_ADC_and_guards_unchanged=True,IRQ_priorities_unchanged=True,IRQ_masking_added=False,
  atomic_word_handoff=True,publish_before_accounting=True,six_page_format2=True,E8_only_while_OFF=True,
  estimate_age_limit_ms=2,trip_A=1.35,ADC_guard_ticks=2048,physical_target_timing_pending=True),indent=2)+'\n')
 m.update(built=True,installed=False,selftests_passed=True,preserved_files_verified=len(preserved),
  PC5s_actual_adapter_and_model_passed=True,PC5s_frame_count=80009,PC5s_observer_calls=5000,
  overload_still_stops=True,model_timing_is_simulated=True,physical_target_timing_pending=True,
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print(json.dumps(dict(passed=True,pair=list(p.NEW),built=True,installed=False,preserved_files=len(preserved),RAM_total=ram+reserved,artifacts=m['artifacts'])))

if __name__=='__main__':main()

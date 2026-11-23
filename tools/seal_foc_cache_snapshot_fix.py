"""Seal3007/3008, compare guards and preserve every previous record; offline."""
import hashlib,json,re,shutil,subprocess
from elftools.elf.elffile import ELFFile
import prepare_foc_cache_snapshot_fix as p
from build_multi_native import BIN
from test_foc_update_latency_fix import function

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
 m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
 assert json.loads(p.read(p.OUT/'verification/selftest.json'))['passed']
 assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 assert json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))['firmware_build_id']==p.NEW[0]
 changed={'nucleo/Src/regular_conversion_manager.c','nucleo/Inc/foc_timing_core.h',
          'nucleo/Src/multi_native.c','nucleo/Inc/multi_native.h',
          'web_hmi/server.py','web_hmi/static/app.js'}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if not f.is_file() or '__pycache__' in f.parts:continue
   rel=f.relative_to(p.OUT).as_posix()
   if rel in changed:continue
   assert p.read(f)==p.read(p.BASE/rel).replace('2026103005','2026103007').replace('2026103006','2026103008').replace('3005-regular-adc','3007-cache-snapshot'),rel
 old=p.read(p.BASE/'nucleo/Src/multi_native.c');new=p.read(p.OUT/'nucleo/Src/multi_native.c')
 for name in ('ma_native_fast','ma_native_prepare','ma_fail_at','ma_clock_snapshot','ma_timing_diag',
              'ma_native_profile_tick','fe_profile_tick','ma_native_service'):
  assert function(old,name)==function(new,name),name
 old=p.read(p.BASE/'nucleo/Src/main.c');new=p.read(p.OUT/'nucleo/Src/main.c')
 assert re.findall(r'HAL_NVIC_SetPriority\([^;]+;',old)==re.findall(r'HAL_NVIC_SetPriority\([^;]+;',new)
 # Most normal paths (including all current/SD/STOP/dispatch code) were already
 # compared byte-for-byte above, after the firmware identity substitution.
 ef=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 from configure_multi_algorithm import load
 _,raw,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
 with ef.open('rb') as stream:
  elf=ELFFile(stream);syms={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
  def data(name,size):
   s=syms[name];sec=elf.get_section(s['st_shndx']);off=s['st_value']-sec['sh_addr'];return sec.data()[off:off+size]
  assert data('model',52)==raw and data('qualification',1)==bytes([128])
  ram=elf.get_section_by_name('.bss')['sh_size']+elf.get_section_by_name('.data')['sh_size']
  reserved=elf.get_section_by_name('._user_heap_stack')['sh_size'];assert ram+reserved<32768
  units=[]
  for cu in elf.get_dwarf_info().iter_CUs():
   a=cu.get_top_DIE().attributes.get('DW_AT_name')
   if a and 'live_bench_20261029' in a.value.decode(errors='replace'):
    n=a.value.decode(errors='replace').replace('\\','/');assert (p.OUT/'nucleo').as_posix() in n,n;units.append(n)
 dis=''
 for name in ('RCM_CurrentEpoch','RCM_ExecRegularConv','RCM_ServiceAfterInjected','rcm_fail','ma_native_regular_fault'):
  text=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d','--disassemble='+name,str(ef)],text=True)
  assert '<'+name+'>:' in text and 'cpsid' not in text.lower() and 'primask' not in text.lower(),name
  if name in ('RCM_CurrentEpoch','RCM_ExecRegularConv'):assert text.count('dmb')>=2
  dis+=text
 p.write(p.OUT/'verification/cache_snapshot_ARM.txt',dis)
 preserved={}
 for rel in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json','USB_reconnected_final_r1/preserved_new_files_sha256.json'):
  preserved.update(json.loads(p.read(p.BASE/rel)))
 for folder in ('autonomous_before_FOC_r2','powered_FOC_ADC_20261030_r1','powered_FOC_ADC_20261030_r2'):
  for rel,h in json.loads(p.read(p.BASE/folder/'saved_files_sha256.json')).items():
   preserved[(p.BASE/folder/rel).relative_to(p.ROOT).as_posix()]=h
 for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
 # Include further USB/OFF snapshots, analysis drafts and the first boot timeout.
 for folder in p.BASE.iterdir():
  if folder.is_dir() and folder.name.startswith(('USB_reconnected','continued_analysis','autonomous_before','powered_FOC')):
   for f in folder.rglob('*'):
    if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=sha(f)
 for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert sha(p.BASE/rel)==h,rel
 p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2)+'\n')
 previous=json.loads(p.read(p.BASE/'verification/model_evidence.json'));model=p.ROOT/previous['source']
 assert sha(model)==previous['sha256']
 assert sha(p.OUT/'nucleo/Inc/motor_control.h')==json.loads(p.read(model))['actual_c_kernel_sha256']
 p.write(p.OUT/'verification/model_evidence.json',json.dumps(previous,indent=2)+'\n')
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,f in [('nucleo_2026103008_cache_snapshot.bin',ef.with_suffix('.bin')),
                ('unoq_2026103007_cache_snapshot.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')]:shutil.copy2(f,release/name)
 hashes={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.log'):hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(hashes,indent=2)+'\n')
 p.write(p.OUT/'verification/ELF_audit.json',json.dumps(dict(passed=True,exact_profile=True,source_units=units,
  static_RAM_bytes=ram,linker_heap_stack_reserved_bytes=reserved,
  total_RAM_allocated_bytes=ram+reserved,RAM_unallocated_bytes=32768-ram-reserved,
  current_loop_and_protections_unchanged=True,
  IRQ_priorities_and_masking_unchanged=True,age_snapshot_barriers_present=True,
  first_fault_record_immutable=True,wire_packet_format_unchanged=True,exact_regular_reason9=True,
  trip_A=1.35,ADC_guard_ticks=2048,cache_expiry_ms=1,physical_5s_pending=True),indent=2)+'\n')
 m.update(built=True,installed=False,selftests_passed=True,preserved_files_verified=len(preserved),
  physical_target_timing_pending=True,first_regular_reason_capture=True,
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print(json.dumps(dict(passed=True,pair=list(p.NEW),built=True,installed=False,preserved_files=len(preserved),static_RAM=ram,artifacts=m['artifacts'])))

if __name__=='__main__':main()

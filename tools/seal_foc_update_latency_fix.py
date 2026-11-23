"""Seal built snapshot fix, audit ARM blackout and preserve all old captures."""
import hashlib,json,re,shutil,subprocess
from elftools.elf.elffile import ELFFile
import prepare_foc_update_latency_fix as p
import test_foc_runtime_fix as common
from build_multi_native import BIN

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def main():
 m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
 for name in ('verification/selftest.json','verification/path_tests.json','nucleo_build_report.json'):
  assert json.loads(p.read(p.OUT/name))['passed'],name
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 assert json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))['firmware_build_id']==p.NEW[0]
 common.p=p
 fixture=p.read(p.BASE/'verification/native_fast.cpp').replace('2026103002','2026103004')
 common.compile_run(p.OUT/'verification','native_adapter',fixture)
 changed={'nucleo/Src/current_shunt.c','nucleo/Src/main.c','nucleo/Inc/current_shunt.h','nucleo/Inc/current_snapshot.h'}
 unchanged=[]
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
  for f in (p.OUT/folder).rglob('*'):
   if not f.is_file() or f.suffix not in ('.c','.h','.ino'):continue
   rel=f.relative_to(p.OUT).as_posix()
   if rel in changed:continue
   assert p.read(f)==p.read(p.BASE/rel).replace('2026103001','2026103003').replace('2026103002','2026103004'),rel
   unchanged.append(rel)
 from test_foc_update_latency_fix import function
 old=p.read(p.BASE/'nucleo/Src/main.c');new=p.read(p.OUT/'nucleo/Src/main.c')
 for name in ('uno_rearm_break_irq','uno_handle_valid_frame','uno_clear_frame_is_safe','mic_local_stop_enable_outputs','mic_local_stop_clear'):
  assert function(old,name)==function(new,name),name
 assert re.findall(r'HAL_NVIC_SetPriority\([^;]+;',old)==re.findall(r'HAL_NVIC_SetPriority\([^;]+;',new)
 from configure_multi_algorithm import load
 _,raw,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
 ef=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 with ef.open('rb') as stream:
  e=ELFFile(stream);syms={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
  def data(name,n):
   s=syms[name];sec=e.get_section(s['st_shndx']);return sec.data()[s['st_value']-sec['sh_addr']:s['st_value']-sec['sh_addr']+n]
  assert data('model',52)==raw and data('qualification',1)==bytes([128])
  assert syms['state']['st_size']==296 and syms['state_sequence']['st_size']==4
  ram=int(e.get_section_by_name('.bss')['sh_size'])+int(e.get_section_by_name('.data')['sh_size']);assert ram+1536<32768
  units=[]
  for cu in e.get_dwarf_info().iter_CUs():
   a=cu.get_top_DIE().attributes.get('DW_AT_name')
   if a and 'live_bench_20261029' in a.value.decode(errors='replace'):
    name=a.value.decode(errors='replace').replace('\\','/');assert (p.OUT/'nucleo').as_posix() in name,name;units.append(name)
  assert any(n.endswith('current_shunt.c') for n in units)
 def dis(package,name):
  elf=package/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
  return subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d','--disassemble='+name,str(elf)],text=True)
 before=dis(p.BASE,'mic_current_packet');after=dis(p.OUT,'mic_current_packet')
 assert 'cpsid' in before and '<memcpy>' in before
 assert 'cpsid' not in after and 'cpsie' not in after and 'PRIMASK' not in after
 assert '<memcpy>' in after # same exact data copy remains interruptible
 p.write(p.OUT/'verification/old_masked_snapshot_ARM.txt',before)
 p.write(p.OUT/'verification/new_interruptible_snapshot_ARM.txt',after)
 p.write(p.OUT/'verification/old_byte_memcpy_ARM.txt',dis(p.BASE,'memcpy'))
 preserved={}
 for rel in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json'):
  preserved.update(json.loads(p.read(p.BASE/rel)))
 for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
 for dirname in ('powered_FOC_CPU_IRQ_20261030_r1','powered_FOC_CPU_IRQ_20261030_r2','autonomous_before_FOC_r1','autonomous_before_FOC_r2','FOC_CPU_IRQ_trial_preparation_r1'):
  for f in (p.BASE/dirname).rglob('*'):
   if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=sha(f)
 for dirname in ('powered_FOC_CPU_IRQ_20261030_r1','powered_FOC_CPU_IRQ_20261030_r2'):
  folder=p.BASE/dirname
  for rel,h in json.loads(p.read(folder/'saved_files_sha256.json')).items():assert sha(folder/rel)==h
 for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert sha(p.BASE/rel)==h,rel
 p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2)+'\n')
 # Exact same controller and plant-model evidence, explicitly reused, not rerun.
 model=p.BASE/'model_verification/report.json';study=json.loads(p.read(model))
 assert sha(p.OUT/'nucleo/Inc/motor_control.h')==study['actual_c_kernel_sha256']
 p.write(p.OUT/'verification/model_evidence.json',json.dumps(dict(reused_not_rerun=True,
  source=str(model.relative_to(p.ROOT)),sha256=sha(model),controller_byte_identical=True,
  central_passed=4,sensitivity_passed=54,sensitivity_total=60),indent=2)+'\n')
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,f in [('nucleo_2026103004_update_latency.bin',ef.with_suffix('.bin')),
                ('unoq_2026103003_update_latency.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')]:shutil.copy2(f,release/name)
 p.write(p.OUT/'verification/ELF_audit.json',json.dumps(dict(passed=True,source_units=units,
  exact_calculated_profile=True,qualification=128,static_RAM_bytes=ram,
  old_masked_copy_bytes=296,new_current_packet_contains_no_CPSID=True,
  hardware_completion_or_latency_not_measured=True,protection_sources_unchanged=unchanged),indent=2)+'\n')
 source_hashes={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.log'):source_hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(source_hashes,indent=2)+'\n')
 m.update(built=True,installed=False,selftests_passed=True,ARM_blackout_removal_verified=True,
  preserved_files_verified=len(preserved),recorded_invalid_ADC_still_rejected=True,
  hardware_timing_qualification_pending=True,
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print(json.dumps({k:m[k] for k in ('pair','built','installed','preserved_files_verified','ARM_blackout_removal_verified','artifacts')}))
if __name__=='__main__':main()

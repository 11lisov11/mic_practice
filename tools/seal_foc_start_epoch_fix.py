"""Seal the startup fix with exact source, ELF and preserved-capture evidence."""
import hashlib,json,shutil,subprocess
from elftools.elf.elffile import ELFFile
import prepare_foc_start_epoch_fix as p

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
 m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
 for rel in ('verification/selftest.json','verification/startup_schedule.json','nucleo_build_report.json'):
  assert json.loads(p.read(p.OUT/rel))['passed'],rel
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 um=json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
 assert um['firmware_build_id']==p.NEW[0]
 from configure_multi_algorithm import load
 _,raw,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
 elf_path=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 with elf_path.open('rb') as f:
  elf=ELFFile(f);syms={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
  for name in ('fe_fast_cycles','fe_case','fe_fault','fe_trial_done','fe_trial_begin'):
   assert name in syms,name
  def data(name,length):
   s=syms[name];sec=elf.get_section(s['st_shndx']);off=s['st_value']-sec['sh_addr']
   return sec.data()[off:off+length]
  assert data('model',52)==raw
  assert data('qualification',1)==bytes([128])
  units=[]
  for cu in elf.get_dwarf_info().iter_CUs():
   a=cu.get_top_DIE().attributes.get('DW_AT_name')
   if a and 'live_bench_20261029' in a.value.decode(errors='replace'):
    name=a.value.decode(errors='replace').replace('\\','/')
    assert (p.OUT/'nucleo').as_posix() in name,name
    units.append(name)
  assert any(n.endswith('multi_native.c') for n in units)
 p.write(p.OUT/'verification/elf_identity.json',json.dumps(dict(passed=True,
  correct_source_units=units,model_bytes_exact=True,qualification_128=True,
  required_native_symbols_present=True),indent=2))
 # Reuse the existing physics simulation by exact source identity, explicitly.
 # This does not claim another model study or target validation of this fix.
 model_report=p.BASE/'model_verification_final/report.json'
 model=json.loads(p.read(model_report));kernel=p.OUT/'nucleo/Inc/motor_control.h'
 assert sha(kernel)==model['actual_c_kernel_sha256']
 central=[x for x in model['scenarios'] if x['label']=='central']
 assert len(central)==4 and all(x['passed'] for x in central)
 reused=dict(report=str(model_report.relative_to(p.ROOT)),report_sha256=sha(model_report),
  candidate_kernel_sha256=sha(kernel),reused_not_rerun=True,central_passed=4,
  sensitivity_passed=sum(bool(x['passed']) for x in model['scenarios']),sensitivity_total=len(model['scenarios']),
  physical_parameters_and_control_kernel_unchanged=True,hardware_validation=False)
 p.write(p.OUT/'verification/reused_model_evidence.json',json.dumps(reused,indent=2))
 compile(p.read(p.OUT/'web_hmi/server.py'),'server.py','exec')
 r=subprocess.run(['C:/Program Files/nodejs/node.exe','--check',str(p.OUT/'web_hmi/static/app.js')],capture_output=True,text=True)
 p.write(p.OUT/'verification/javascript.log',r.stdout+r.stderr);r.check_returncode()
 old=json.loads(p.read(p.BASE/'verification/preserved_captures_sha256.json'))
 for rel,h in old.items():assert sha(p.ROOT/rel)==h,rel
 preserved=dict(old)
 for folder in ('autonomous_before_first_FOC_r1','first_powered_FOC_5Hz_5s_r1','first_powered_FOC_5Hz_5s_r2'):
  for f in (p.BASE/folder).rglob('*'):
   if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=sha(f)
 # Verify the predecessor application remains untouched; do not rebuild it.
 for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert sha(p.BASE/rel)==h,rel
 p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2))
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,source in [
  ('unoq_2026102961_foc_start_epoch.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'),
  ('nucleo_2026102962_foc_start_epoch.bin',elf_path.with_suffix('.bin'))]:
  shutil.copy2(source,release/name)
 sources={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.log'):
    sources[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(sources,indent=2))
 m.update(built=True,installed=False,selftests_passed=True,
  old_captures_verified=len(old),all_preserved_files=len(preserved),
  target_timing_measured=False,physical_trial_after_fix=False,
  predecessor_sources_unchanged=True,reused_model_evidence=reused,
  native_flash_bytes=elf_path.with_suffix('.bin').stat().st_size,
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2))
 print(json.dumps({k:m[k] for k in ('pair','built','installed','old_captures_verified','all_preserved_files','artifacts')}))

if __name__=='__main__':main()

"""Seal tested calculated-FOC images. Offline, does not program hardware."""
import hashlib,json,shutil,subprocess
from elftools.elf.elffile import ELFFile
import prepare_estimated_foc_trial as p

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
 manifest=json.loads(p.read(p.OUT/'manifest.json'));assert not manifest['installed']
 assert json.loads(p.read(p.OUT/'verification/selftest.json'))['passed']
 assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 from configure_multi_algorithm import load
 _,raw,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
 with (p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf').open('rb') as stream:
  elf=ELFFile(stream);symbols={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
  for name in ('fe_fast_cycles','fe_case','fe_fault','fe_trial_done','fe_trial_begin'):assert name in symbols,name
  symbol=symbols['model'];section=elf.get_section(symbol['st_shndx']);offset=symbol['st_value']-section['sh_addr']
  assert section.data()[offset:offset+52]==raw
  units=[]
  for cu in elf.get_dwarf_info().iter_CUs():
   attr=cu.get_top_DIE().attributes.get('DW_AT_name')
   if attr and 'live_bench_20261029' in attr.value.decode(errors='replace'):
    name=attr.value.decode(errors='replace').replace('\\','/')
    assert (p.OUT/'nucleo').as_posix() in name,name
    units.append(name)
  assert any(n.endswith('multi_native.c') for n in units)
 p.write(p.OUT/'verification/elf_identity.json',json.dumps(dict(passed=True,
  model_bytes_exact=True,correct_package_units=len(units),FOC_symbols_present=True),indent=2))
 # The portable controller and ADC/protection files used by recorded-noise
 # simulation remain unchanged; no need to rerun unrelated research studies.
 model=p.OUT/'model_verification_final'
 r=json.loads(p.read(model/'report.json'))
 assert sha(p.OUT/'nucleo/Inc/motor_control.h')==r['actual_c_kernel_sha256']
 assert all(x['passed'] for x in r['scenarios'] if x['label']=='central')
 compile(p.read(p.OUT/'web_hmi/server.py'),'server.py','exec')
 j=subprocess.run(['C:/Program Files/nodejs/node.exe','--check',str(p.OUT/'web_hmi/static/app.js')],capture_output=True,text=True)
 p.write(p.OUT/'verification/javascript.log',j.stdout+j.stderr);j.check_returncode()
 preserved={}
 for name in ('artifacts/live_bench_20261029/multi_algorithm_r1/hardware_install_r1/preserved_captures_sha256.json',
              'artifacts/live_bench_20261029/standstill_current_noise_r1/verification/preserved_latest_evidence.json'):
  for rel,h in json.loads(p.read(p.ROOT/name)).items():assert sha(p.ROOT/rel)==h,rel;preserved[rel]=h
 p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2))
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,source in [('unoq_2026102951_calculated_foc.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'),
  ('nucleo_2026102952_calculated_foc.bin',p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin')]:
  shutil.copy2(source,release/name)
 sources={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.log'):
    sources[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(sources,indent=2))
 manifest.update(built=True,installed=False,selftests_passed=True,old_captures_unchanged=len(preserved),
  target_timing_measured=False,no_motor_start=True,
  calculated_profile_sha256=sha(model/'profile.json'),
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2));print(json.dumps(manifest))

if __name__=='__main__':main()

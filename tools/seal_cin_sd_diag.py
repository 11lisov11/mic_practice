"""Seal checked 3101/3102 images and retain prior capture identities; no board access."""
import ast,importlib.util,json,sys,subprocess
from pathlib import Path
import prepare_cin_sd_diag as p
from probe_native_programming_state import programmed_hex_image

def main():
 manifest=json.loads(p.read(p.OUT/'manifest.json'));assert not manifest['built'] and not manifest['installed']
 tests=json.loads(p.read(p.OUT/'verification/report.json'));assert tests['passed']
 native=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 native_report=json.loads(p.read(p.OUT/'nucleo_build_report.json'))
 assert native_report['passed'] and native_report['build_id']==p.NEW[1]
 uno=p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'
 ureport=json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
 assert ureport['firmware_build_id']==p.NEW[0]
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 for item in ureport['artifacts']:assert p.sha(p.OUT/'build/uno'/item['file'])==item['sha256'].lower()
 expected,holes=programmed_hex_image(native.with_suffix('.hex'),native.with_suffix('.bin').read_bytes())
 release=p.OUT/'release';release.mkdir(exist_ok=False)
 (release/'nucleo_2026103102_sd_cin.hex').write_bytes(native.with_suffix('.hex').read_bytes())
 (release/'nucleo_2026103102_expected_readback.bin').write_bytes(expected)
 (release/'uno_2026103101_sd_cin.elf-zsk.bin').write_bytes(uno.read_bytes())
 for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert p.sha(p.BASE/rel)==h,rel
 preserved=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
 older=p.BASE/'verification/preserved_captures_sha256.json'
 if older.exists():
  for rel,h in json.loads(p.read(older)).items():
   name=rel.replace('\\','/')
   assert p.sha(p.ROOT/name)==h,name
   preserved[name]=h
 for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
 p.write(p.OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2))
 # Exercise the actually integrated server, including both no-start paths.
 path=p.OUT/'web_hmi/server.py';spec=importlib.util.spec_from_file_location('cin_candidate_hmi',path)
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 assert module.command_guard_check('START',None,None)==(False,'CIN_DIAGNOSTIC_ONLY: motor and service starts disabled')
 assert module.command_guard_check('STOP',None,None)[0]
 assert module.AppState.start_sequence(object())==(False,'CIN_DIAGNOSTIC_ONLY: no motor start',None)
 subprocess.run(['node','--check',str(p.OUT/'web_hmi/static/app.js')],check=True,capture_output=True)
 sources={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts:sources[f.relative_to(p.OUT).as_posix()]=p.sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(sources,indent=2))
 artifacts={f.relative_to(p.OUT).as_posix():p.sha(f) for f in release.iterdir()}
 artifacts['build/uno/UNOQ_MOTOR.ino.elf-zsk.bin']=p.sha(uno)
 for ext in ('.hex','.bin','.elf'):artifacts[native.with_suffix(ext).relative_to(p.OUT).as_posix()]=p.sha(native.with_suffix(ext))
 manifest.update(built=True,host_tests_passed=True,hardware_validated=False,installed=False,
  artifacts=artifacts,sources=len(sources),preserved_files_verified=len(preserved),native_hex_holes=holes,
  verification_sha256=p.sha(p.OUT/'verification/report.json'),
  native_flash_bytes=len(expected),RAM_used_including_reserved_heap_stack=976+27560,
  RAM_unallocated=32768-976-27560,live_CIN_cause_not_yet_measured=True)
 p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2))
 print(json.dumps(dict(built=True,installed=False,pair=p.NEW,source_files=len(sources),preserved_files_verified=len(preserved),hardware_commands=0,RAM_unallocated=manifest['RAM_unallocated'])))
if __name__=='__main__':main()

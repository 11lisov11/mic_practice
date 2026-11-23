"""Seal a tested ADC-publication fix and OFF-only noise diagnostic. No board access."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import prepare_standstill_current_noise as p

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
 m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
 for f in ['noise_selftest/report.json','apex_selftest_r1/report.json',
  'verification/protection_audit.json','recorded_abort_replay/report.json','nucleo_build_report.json']:
  assert json.loads(p.read(p.OUT/f))['passed'],f
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 assert (p.BASE/'nucleo/Inc/identify_core.h').read_bytes()==(p.OUT/'nucleo/Inc/identify_core.h').read_bytes()
 for f in [p.OUT/'web_hmi/server.py',p.ROOT/'tools/collect_idle_adc_noise.py']:
  compile(p.read(f),str(f),'exec')
 r=subprocess.run(['C:/Program Files/nodejs/node.exe','--check',str(p.OUT/'web_hmi/static/app.js')],capture_output=True,text=True)
 p.write(p.OUT/'verification/javascript.log',r.stdout+r.stderr);r.check_returncode()
 latest=json.loads(p.read(p.OUT/'verification/preserved_latest_evidence.json'))
 for f,h in latest.items():assert sha(p.ROOT/f)==h,f
 # All earlier archived captures, plus the latest physical abort, must survive.
 reference=p.ROOT/'artifacts/live_bench_20261029/multi_algorithm_r1/hardware_install_r1/preserved_captures_sha256.json'
 previous=json.loads(p.read(reference))
 for f,h in previous.items():assert sha(Path(f))==h,f
 p.write(p.OUT/'verification/archive_preservation.json',json.dumps(dict(unchanged=True,
  previous_files=len(previous),latest_files=len(latest),reference_sha256=sha(reference)),indent=2))
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,f in [('unoq_2026102939_current_noise.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'),
  ('nucleo_2026102940_current_noise.bin',p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin')]:
  shutil.copy2(f,release/name)
 sources={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.log'):
    sources[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(sources,indent=2))
 m.update(built=True,installed=False,thresholds_changed=False,raw_protection_filter_added=False,
  physical_noise_reduction_verified=False,current_noise_cause_identified=False,
  current_publication_rollover_fixed=True,noise_diagnostic_source='unfiltered OFF-only ADC1/ADC2',
  no_new_pwm_trials=True,hardware_commands=0,archived_capture_files_verified=len(previous)+len(latest),
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2));print(json.dumps(m))

if __name__=='__main__':main()

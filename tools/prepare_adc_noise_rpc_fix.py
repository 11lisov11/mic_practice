"""Repair both Uno command routers; retain the exact installed native image."""
import os
import json
from pathlib import Path
import shutil
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261029/standstill_current_noise_r1'
OUT=ROOT/'artifacts/live_bench_20261029/adc_noise_rpc_fix_r1'
NEW=(2026102941,2026102940)

def main():
 assert not OUT.exists()
 for folder in ('nucleo','libraries','UNOQ_MOTOR','web_hmi'):
  # Immutable native/runtime files are hardlinked and NEVER edited below.
  copy=os.link if folder in ('nucleo','libraries') else shutil.copy2
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 for folder in ('UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026102939','2026102941')
    if n!=s:write(f,n)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 anchor='starts_ci(cmd,"IDENT ") || starts_ci(cmd,"SET ALGORITHM ")'
 assert s.count(anchor)==2
 s=s.replace(anchor,'starts_ci(cmd,"NOISE PAGE ") || '+anchor);write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 s=s.replace('(2026102937,2026102938), (2026102941,2026102940)',
  '(2026102937,2026102938), (2026102939,2026102940), (2026102941,2026102940)');write(f,s)
 f=OUT/'web_hmi/static/index.html';write(f,read(f).replace('2939-current-noise','2941-noise-rpc'))
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.adc_noise_rpc_fix.v1',pair=list(NEW),
  base_pair=[2026102939,2026102940],built=False,installed=False,native_image_changed=False,
  thresholds_changed=False,noise_cause_fully_identified=False,start_commands=0),indent=2))
 print('Prepared Uno2941 / unchanged Nucleo2940; NOISE page dispatch fix only')

if __name__=='__main__':main()

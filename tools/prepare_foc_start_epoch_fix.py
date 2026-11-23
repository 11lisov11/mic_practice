"""Synchronize observer/voltage epochs at the first real PWM control call."""
import json,os,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
from replay_foc_start_timestamps import OLD,FIX
BASE=ROOT/'artifacts/live_bench_20261029/estimated_foc_trial_r5'
OUT=ROOT/'artifacts/live_bench_20261029/foc_start_epoch_fix_r1'
NEW=(2026102961,2026102962)

def main():
 assert not OUT.exists()
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def copy(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='libraries' or (folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full')):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026102951','2026102961').replace('2026102952','2026102962')
    if n!=s:write(f,n)
 f=OUT/'nucleo/Src/multi_native.c';s=read(f);write(f,once(s,OLD,FIX))
 f=OUT/'web_hmi/static/index.html';write(f,read(f).replace('2951-calculated-foc','2961-foc-start-epoch'))
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.foc_start_epoch_fix.v1',
  pair=list(NEW),base_pair=[2026102951,2026102952],built=False,installed=False,
  changed_logic='Reset completed voltage bin epoch and accumulation at first real FOC call',
  current_age_limits_changed=False,observer_deadline_changed=False,
  current_protection_changed=False,raw_adc_or_windows_changed=False,
  current_model_changed=False,native_autostop_seconds=5,experimental_max_hz=5,
  start_commands=0,clear_commands=0),indent=2))
 print('Prepared2961/2962; synchronized startup epoch; no hardware access')

if __name__=='__main__':main()

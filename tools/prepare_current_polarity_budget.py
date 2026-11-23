"""Offline exact saturated-current fast path. No boards or threshold changes."""
import json,os,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
from prepare_cin_sd_diag import sha
BASE=ROOT/'artifacts/live_bench_20261114/observer_voltage_stop_r1'
OUT=ROOT/'artifacts/live_bench_20261114/current_polarity_budget_r1'
NEW=(2026111407,2026111408)

HELPER='''/* Exact saturated branch of clip(current/.05f,-1,1).
 * No reciprocal approximation or fast-math: unsaturated values and NaNs retain
 * the original divide/clip expression. The bounds also make its finite clamps
 * redundant to the compiler without changing the result. */
static inline float ma_current_polarity(float current){
 if(current>=.05f)return 1.f;
 if(current<=-.05f)return -1.f;
 return ma_clip(current/.05f,-1,1);
}
'''


def main():
 assert not OUT.exists(),'Never overwrite firmware or evidence'
 for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=os.path.relpath(src,BASE/folder).split(os.sep)
   if folder=='libraries' or folder=='nucleo' and rel[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026111405',str(NEW[0])).replace('2026111406',str(NEW[1]))
    if n!=s:write(f,n)
 f=OUT/'nucleo/Inc/motor_control.h';s=read(f)
 s=once(s,'static inline int ma_motor_valid(',HELPER+'\nstatic inline int ma_motor_valid(')
 for rel in ('nucleo/Inc/motor_control.h','nucleo/Inc/observer_applied_voltage.h'):
  text=s if rel.endswith('/motor_control.h') else read(OUT/rel)
  for expression in ('ia','(-.5f*ia+.8660254038f*ib)','(-.5f*ia-.8660254038f*ib)'):
   text=once(text,'ma_clip('+expression+'/.05f,-1,1)','ma_current_polarity('+expression+')')
  write(OUT/rel,text)
 preserved=json.loads(read(BASE/'preserved_capture_hashes.json'))
 for f in BASE.rglob('*'):
  if f.is_file() and f.suffix in ('.json','.jsonl','.bin','.log','.txt','.png'):
   preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2))
 m=json.loads(read(BASE/'manifest.json'))
 m.update(pair=list(NEW),base_pair=[2026111405,2026111406],built=False,installed=False,
  hardware_commands=0,START=0,CLEAR=0,ARM=0,RESET=0,thresholds_changed=False,
  target_timing_measured=False,target_timing_measured_OFF=False,OFF_CPU_qualified=False,
  target_timing_requalification_required=True,hardware_validated=False,
  baseline_failed_cycles=4007,CPU_probe_budget_cycles=4000,
  exact_saturated_polarity_fast_path=True,controller_equations_changed=False,
  profiling_work_removed=False,phase_calculation_included_in_CPU_probe=True)
 for key in ('artifacts','source_files','preserved_files_verified','verification_reports','RAM_sections',
  'RAM_allocated','RAM_unallocated','installation_report','idle_timing_report','timing_block','both_readbacks_verified',
  'native_flash_bytes','hex_padding_offsets','host_tests_passed','model_tests_passed'):
  m.pop(key,None)
 write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print('Prepared exact current-polarity optimization offline',NEW)


if __name__=='__main__':main()

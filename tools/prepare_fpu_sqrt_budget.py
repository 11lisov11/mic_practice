"""Prepare exact sqrt backend acceleration offline; never flash/reset/start."""
import json,os,re,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
from prepare_cin_sd_diag import sha
BASE=ROOT/'artifacts/live_bench_20261115/observer_irq_budget_r1'
OUT=ROOT/'artifacts/live_bench_20261115/fpu_sqrt_budget_r1'
NEW=(2026111503,2026111504)


def main():
 assert not OUT.exists()
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
    s=read(f);n=s.replace('2026111501',str(NEW[0])).replace('2026111502',str(NEW[1]))
    if n!=s:write(f,n)
 f=OUT/'nucleo/Src/multi_native.c'
 s=once(read(f),'#include "motor_control.h"','#include "motor_control.h"\n#include "fpu_sqrt_dispatch.h"')
 write(f,s)
 write(OUT/'nucleo/Inc/fpu_sqrt_dispatch.h',read(ROOT/'tools/fpu_sqrt_budget/fpu_sqrt_dispatch.h'))
 # Preserve the linker option in both CubeIDE configurations. It is also added
 # to the reproducible native make recipe by build_fpu_sqrt_budget.py.
 f=OUT/'nucleo/STM32CubeIDE/.cproject';s=read(f)
 pattern=r'(<tool id="com\.st\.stm32cube\.ide\.mcu\.gnu\.managedbuild\.tool\.c\.linker\.[^"]+"[^>]*>)'
 count=[0]
 def opt(m):
  count[0]+=1
  return m[0]+f'\n<option id="com.st.stm32cube.ide.mcu.gnu.managedbuild.tool.c.linker.option.otherflags.1504{count[0]}" name="Other flags" superClass="com.st.stm32cube.ide.mcu.gnu.managedbuild.tool.c.linker.option.otherflags" value="-Wl,--wrap=__ieee754_sqrtf" valueType="string"/>'
 s=re.sub(pattern,opt,s);assert count[0]==2;write(f,s)
 old=json.loads(read(BASE/'manifest.json'))
 keep=('trip_A','ADC_guard_ticks','estimate_limit_ms','fast_budget_cycles','frequency_max_hz',
       'runlimit_ms','peer_reply_timeout_ms','send_cadence_us','reply_guard_us','CPU_probe_budget_cycles',
       'applied_voltage_source_corrected','accepted_reply_lifecycle_corrected',
       'exact_saturated_polarity_fast_path','profiling_work_removed')
 m={k:old[k] for k in keep}
 m.update(pair=list(NEW),base_pair=old['pair'],built=False,installed=False,hardware_commands=0,
          START=0,CLEAR=0,ARM=0,RESET=0,thresholds_changed=False,observer_tuning_changed=False,
          controller_equations_changed=False,OFF_CPU_qualified=False,FOC_start_ready=False,
          target_timing_measured=False,target_timing_measured_OFF=False,
          target_timing_requalification_required=True,hardware_validated=False,
          full_adapter_under_PWM_measured=False,CPU_baseline_cycles=4229,
          FT_wire_schema=3,FT_pages=9,UART_TC_IRQ_order_fixed=True,
          FPU_sqrt_wrap=True,FPU_fast_path='positive normal binary32, FPSCR RNE and FZ0',
          FPU_fallback='original __ieee754_sqrtf for every other input/mode')
 write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 preserved=json.loads(read(BASE/'preserved_capture_hashes.json'))
 for f in BASE.rglob('*'):
  if f.is_file() and f.suffix in ('.json','.jsonl','.bin','.log','.txt','.png','.md'):
   preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2)+'\n')
 print('Prepared offline sqrt dispatch',NEW)


if __name__=='__main__':main()

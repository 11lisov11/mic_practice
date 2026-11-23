"""Measure the real kernel in the actual TIM IRQ, with outputs kept OFF."""
import os,json,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261029/standstill_stack_r1'
OUT=ROOT/'artifacts/live_bench_20261029/standstill_irq_timing_r1'
NEW=(2026102937,2026102938)
def main():
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  assert not (OUT/folder).exists()
  def copy(src,dest):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dest);return dest
   return shutil.copy2(src,dest)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Src','nucleo/Inc','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026102935','2026102937').replace('2026102936','2026102938')
    if s!=n:write(f,n)
 f=OUT/'nucleo/Src/multi_native.c';s=read(f);old=read(ROOT/'tools/motor_commissioning/native_profile_off.inc')
 s=once(s,old,read(ROOT/'tools/motor_commissioning/native_profile_irq.inc'))
 # Main must not serialize temporary CPU state as a real completed measurement.
 s=once(s,'static uint32_t id_profile_cycles;','static uint32_t id_profile_cycles;\nstatic volatile uint8_t id_profile_running;')
 s=once(s,'  mi_native_profile_off();\n  if(mi_native_service())return;',
   '  mi_native_profile_off();\n  if(id_profile_running)return;\n  if(mi_native_service())return;')
 s=once(s,'static volatile uint8_t id_profile_running,id_profile_pending,id_profile_done;',
   'static volatile uint8_t id_profile_pending,id_profile_done;')
 s=once(s,'p[5]=(id_configured?1:0)|(id_state.active?2:0)|(id_state.ready?4:0)|(id_state.done?8:0);',
   'p[5]=(id_configured?1:0)|(!id_profile_running&&id_state.active?2:0)|(!id_profile_running&&id_state.ready?4:0)|(!id_profile_running&&id_state.done?8:0);')
 s=once(s,'p[38]=id_state.fault;','p[38]=id_profile_running?0:id_state.fault;')
 write(f,s)
 f=OUT/'nucleo/Inc/multi_native.h';s=read(f);s=once(s,'void ma_native_service(void);','void ma_native_service(void);\nvoid ma_native_profile_tick(void);');write(f,s)
 f=OUT/'nucleo/Src/mc_tasks.c';s=read(f)
 s=once(s,'  if (0U == LL_TIM_IsEnabledAllOutputs(pwmHandle[M1]->TIMx))\n  {\n    return bMotorNbr;',
   '  if (0U == LL_TIM_IsEnabledAllOutputs(pwmHandle[M1]->TIMx))\n  {\n    ma_native_profile_tick(); /* CPU-only work; never writes PWM. */\n    return bMotorNbr;')
 write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f);s=s.replace('(2026102933,2026102934), (2026102937,2026102938)',
  '(2026102933,2026102934), (2026102935,2026102936), (2026102937,2026102938)');write(f,s)
 f=OUT/'web_hmi/static/index.html';write(f,read(f).replace('2935-stack','2937-irq-timing'))
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.standstill_irq_timing.v1',pair=list(NEW),base_pair=[2026102935,2026102936],
  built=False,installed=False,physical_qualification=False,thresholds_changed=False,adc_guard_changed=False,start_commands=0),indent=2))
 print('Prepared IRQ-context CPU profile; actual live modulation path unchanged')
if __name__=='__main__':main()

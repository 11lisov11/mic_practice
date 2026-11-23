"""Actual native C, IRQ-accounting arithmetic, frozen reasons and wire tests."""
import copy,hashlib,json,shutil,subprocess
import prepare_foc_runtime_fix as p
from audit_production_pwm_filters import function

def compile_run(out,name,code):
 cpp=out/(name+'.cpp');p.write(cpp,code);exe=cpp.with_suffix('.exe')
 r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
  '-Wno-unused-function','-Wno-misleading-indentation','-Wno-missing-field-initializers','-I',str(p.OUT/'nucleo/Inc'),
  '-I',str(p.OUT/'UNOQ_MOTOR'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/(name+'_build.log'),r.stdout+r.stderr);r.check_returncode()
 r=subprocess.run([str(exe)],capture_output=True,text=True)
 p.write(out/(name+'_run.log'),r.stdout+r.stderr);r.check_returncode()
 return r.stdout

def source():
 base=p.read(p.BASE/'verification/native_epoch.cpp')
 pre=base.split('#define MIC_NATIVE_BUILD',1)[0]
 native=p.read(p.OUT/'nucleo/Src/multi_native.c')
 for name in ('ma_native_profile_tick','fe_profile_tick','fe_profile_service'):
  f=function(native,name);native=native.replace(f,f.replace('DWT->CYCCNT','host_profile_clock()'))
 native='\n'.join(l for l in native.splitlines() if not l.startswith(('#include','#pragma')))
 tail=base[base.index('static void NVIC_SetPendingIRQ(int irq){'):].replace('2026102962','2026102972')
 return pre,native,tail

def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True)
 pre,native,tail=source()
 compile_run(out,'native_runtime',pre+native+'\n'+tail)
 tailhead=tail.split('int main(){',1)[0]
 checks=r'''
static void start_case(){
 timer.BDTR=0;cycle.CYCCNT=1000000;selected=MA_FOC;
 fe_complete=1;fe_case=64;fe_fault=0;id_profile_attempted=1;id_profile_running=0;
 fake_bus=320;sample={};sample.zero=sample.valid=1;sample_coherent=1;
 first_fault=0;memset(&ma_first_runtime,0,sizeof(ma_first_runtime));
 assert(ma_native_prepare());timer.BDTR=1;cycle.CYCCNT+=8500000;
 sample.cycles=cycle.CYCCNT;assert(ma_native_fast(5)==0);
}
int main(){
 /* Nested handlers are included once, and wrap arithmetic is modular. */
 ft_irq_meter meter={};ft_irq_token root=ft_irq_enter(&meter,100,1);
 assert(meter.seq==1);auto child=ft_irq_enter(&meter,120,0);
 ft_irq_leave(&meter,child,170);assert(meter.cycles==0);
 ft_irq_leave(&meter,root,200);assert(meter.cycles==100&&meter.roots==1&&meter.seq==2);
 root=ft_irq_enter(&meter,0xfffffff0U,1);ft_irq_leave(&meter,root,0x20);
 assert(meter.cycles==148&&meter.roots==2&&meter.seq==4);
 ft_perf stats={};ft_clock a={0xfffffff0U,0xffffffe0U,0xffffffffU,1};
 ft_clock b={0x50,0x10,1,1};ft_measure(&stats,a,b);
 assert(stats.wall==96&&stats.irq==48&&stats.cpu_upper==48&&stats.roots==2);
 b.irq=0x200;ft_measure(&stats,a,b);assert(stats.errors==1&&stats.cpu_upper==stats.wall);
 /* Snapshot is bounded even if called from a deliberately odd test meter. */
 mic_foc_irq_meter.seq=1;auto invalid=ma_clock_snapshot();assert(!invalid.valid);
 mic_foc_irq_meter.seq=0;
 unsigned reasons=0;
 for(unsigned why:{FT_NO_SAMPLE,FT_ADC_INVALID,FT_ADC_AGE,FT_ESTIMATE_AGE,FT_OBSERVER_DT}){
  start_case();cycle.CYCCNT+=180000;sample.cycles=cycle.CYCCNT;
  if(why==FT_NO_SAMPLE){sample_coherent=0;cached_sample.valid=0;}
  if(why==FT_ADC_INVALID)sample.valid=0;
  if(why==FT_ADC_AGE)sample.cycles-=SystemCoreClock*3U/16000U;
  if(why==FT_ESTIMATE_AGE)cycle.CYCCNT+=180000,sample.cycles=cycle.CYCCNT;
  if(why==FT_OBSERVER_DT){bin_cycles=estimate_cycles+SystemCoreClock*3U/1000U;cycle.CYCCNT=bin_cycles;sample.cycles=cycle.CYCCNT;ma_native_service();}
  else assert(ma_native_fast(5)==MC_SW_ERROR);
  assert(run_fault==MA_STALE&&ma_first_runtime.state==2&&ma_first_runtime.word[0]==why);
  ft_first_fault keep=ma_first_runtime;
  ma_fail_at(MA_CURRENT,FT_CONTROL,0,&sample,0,0,0);
  assert(memcmp(&keep,&ma_first_runtime,sizeof(keep))==0);++reasons;
 }
 /* Real measured-bin cadence can be serviced before a wall-time 1ms gate. */
 start_case();bin_cycles=estimate_cycles+159375U;cycle.CYCCNT=bin_cycles+100;
 sample.cycles=cycle.CYCCNT;ma_native_service();
 assert(!run_fault&&observer.steps==1&&estimate_cycles==bin_cycles);
 /* Telemetry validates every CRC, page, peer and freshness condition. */
 ft_receiver receiver={};uint8_t packet[UV3_FRAME];
 for(unsigned page=0;page<4;++page){ma_timing_diag(packet,2026102972,page);assert(ft_receive(&receiver,packet,2026102972,true,100));}
 assert(ft_fresh(&receiver,true,100));
 packet[10]^=1;assert(!ft_receive(&receiver,packet,2026102972,true,100));
 ma_timing_diag(packet,2026102972,0);assert(!ft_receive(&receiver,packet,2026102962,true,100));
 assert(!ft_receive(&receiver,packet,2026102972,false,100));
 packet[4]=4;uv3_seal(packet);assert(!ft_receive(&receiver,packet,2026102972,true,100));
 ma_timing_diag(packet,2026102972,0);packet[5]=1;uv3_seal(packet);
 assert(ft_receive(&receiver,packet,2026102972,true,200)&&receiver.mask==1);
 assert(!ft_fresh(&receiver,true,200));
 printf("{\"fault_reasons_checked\":%u,\"nested_irq_wrap_and_wire\":true}\n",reasons);
}
'''
 compile_run(out,'runtime_reasons','#include <cstdio>\n#include "foc_timing_wire.h"\n'+pre+native+'\n'+tailhead+checks)
 # Current/SD/local-stop geometry and the actual model/controller are unchanged.
 unchanged=[]
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
  for f in (p.OUT/folder).rglob('*'):
   if not f.is_file() or f.suffix not in ('.c','.h','.ino'):continue
   rel=f.relative_to(p.OUT);old=p.BASE/rel
   if not old.exists():continue
   expected=p.read(old).replace('2026102961','2026102971').replace('2026102962','2026102972')
   if p.read(f)==expected:unchanged.append(rel.as_posix())
 must=['nucleo/Src/current_shunt.c','nucleo/Inc/motor_control.h','nucleo/Inc/foc_experiment.h',
  'nucleo/Inc/current_adc_window_plan.h','nucleo/Inc/current_adc_deadline.h','nucleo/Inc/local_stop.h']
 assert all(n in unchanged for n in must)
 for name in ('uno_rearm_break_irq','uno_clear_frame_is_safe','uno_handle_valid_frame'):
  before=function(p.read(p.BASE/'nucleo/Src/main.c'),name)
  after=function(p.read(p.OUT/'nucleo/Src/main.c'),name)
  assert before==after,name
 report=dict(passed=True,hardware_commands=0,start_commands=0,clear_commands=0,
  exact_native_adapter_regressions=True,native_autostop_5s_and_wrap=True,
  nested_IRQ_accounting_and_counter_wrap=True,bounded_snapshot=True,
  first_fault_reasons_tested=5,first_fault_immutable=True,
  CRC_wrong_peer_stale_and_mixed_page_wire_checks=True,
  protections_and_physics_unchanged=must,other_unchanged_application_files=unchanged)
 p.write(out/'selftest.json',json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if not isinstance(v,list)}))

if __name__=='__main__':main()

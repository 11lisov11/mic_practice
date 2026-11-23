"""Actual ADC-manager simulation, safety expiry and captured current replay."""
import json,subprocess,ast
import prepare_foc_regular_adc_fix as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function
def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
 src=p.read(p.OUT/'nucleo/Src/regular_conversion_manager.c')
 helpers=src[src.index('static RegConv_t *rcm_pending;'):src.index('/* Private function prototypes')]
 code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#define __DMB() __asm__ volatile("":::"memory")
#define MC_SW_ERROR 128
#define LL_ADC_SAMPLINGTIME_47CYCLES_5 47
#define LL_ADC_REG_RANK_1 1
#define __LL_ADC_DECIMAL_NB_TO_CHANNEL(c) (c)
#define RCM_MAX_CONV 4
struct ADC_TypeDef{unsigned channel,data,eoc,ongoing,finish;};
static ADC_TypeDef adc;static ADC_TypeDef*ADC1=&adc;
static int TIM1,enabled,window_ok=1;static unsigned starts;
static struct{uint32_t CYCCNT;}clock_;static auto DWT=&clock_;
static uint32_t SystemCoreClock=170000000;
struct RegConv_t{ADC_TypeDef*regADC;uint32_t samplingTime;uint8_t channel;uint16_t data;uint8_t id;};
static RegConv_t*RCM_handle_array[RCM_MAX_CONV];static uint8_t RCM_conversion_nb=2;
static unsigned LL_TIM_IsEnabledAllOutputs(int){return enabled;}
static int mic_current_regular_window(){return window_ok;}
static unsigned LL_ADC_IsActiveFlag_EOC(ADC_TypeDef*a){
 if(a->ongoing&&(int32_t)(DWT->CYCCNT-a->finish)>=0){a->eoc=1;a->ongoing=0;a->data=a->channel*1234;}
 if(!enabled&&a->ongoing)DWT->CYCCNT+=16;
 return a->eoc;
}
static unsigned LL_ADC_REG_ReadConversionData12L(ADC_TypeDef*a){a->eoc=0;return a->data;}
static void LL_ADC_ClearFlag_EOC(ADC_TypeDef*a){a->eoc=0;}
static void LL_ADC_REG_SetSequencerRanks(ADC_TypeDef*a,int,unsigned ch){assert(!a->ongoing);a->channel=ch;}
static void LL_ADC_REG_StartConversion(ADC_TypeDef*a){assert(!a->ongoing);a->ongoing=1;a->finish=DWT->CYCCNT+240;starts++;}
static unsigned LL_ADC_REG_IsConversionOngoing(ADC_TypeDef*a){LL_ADC_IsActiveFlag_EOC(a);return a->ongoing;}
'''
 code+=helpers+'\n'+function(src,'RCM_ExecRegularConv')
 code+=r'''
int main(){
 RegConv_t bus={ADC1,47,2,0,0},temp={ADC1,47,8,0,1};
 RCM_handle_array[0]=&bus;RCM_handle_array[1]=&temp;
 clock_.CYCCNT=1000;
 assert(RCM_ExecRegularConv(&bus)==2468);assert(RCM_ExecRegularConv(&temp)==9872);
 enabled=1;unsigned n=starts;
 for(unsigned frame=0;frame<80000;++frame){
  clock_.CYCCNT+=10625;
  assert(RCM_CurrentEpoch());
  // completion is owned by ADC tail, not by preempting TIM1/SysTick.
  auto stamp=rcm_stamp[0];auto pending=rcm_pending;
  if(frame%8==0){unsigned count=starts;auto value=RCM_ExecRegularConv(&bus);
   assert(value==2468&&starts==count&&rcm_stamp[0]==stamp&&rcm_pending==pending);
   assert(RCM_ExecRegularConv(&temp)==9872);}
  RCM_ServiceAfterInjected();assert(RCM_CurrentFault()==0);
 }
 assert(starts==n+80000);
 // An unsafe timer slot never starts another regular conversion.
 clock_.CYCCNT+=10625;window_ok=0;n=starts;RCM_ServiceAfterInjected();assert(starts==n);
 clock_.CYCCNT+=170000;assert(!RCM_CurrentEpoch()&&RCM_CurrentFault()==128);
 // OFF acquisition primes caches again, but does not clear the motor's MCI latch.
 enabled=0;assert(RCM_ExecRegularConv(&bus)==2468);assert(RCM_ExecRegularConv(&temp)==9872);
 enabled=1;window_ok=1;clock_.CYCCNT+=10625;assert(RCM_CurrentEpoch());RCM_ServiceAfterInjected();
 adc.finish=clock_.CYCCNT+1000000;clock_.CYCCNT+=10625;
 RCM_ServiceAfterInjected();assert(RCM_CurrentFault()==128); // missing EOC
 // Modular timestamp arithmetic across cycle-counter wrap.
 adc.ongoing=0;adc.eoc=1;rcm_pending=nullptr;rcm_fault=0;rcm_stamp[0]=rcm_stamp[1]=0xfffffff0U;
 clock_.CYCCNT=0x100;assert(RCM_CurrentEpoch());
 temp.samplingTime=100;assert(!RCM_CurrentEpoch());
 puts("actual manager:80000frames, cache-only RUN, expiry, lost EOC, unsupported timing and wrap OK");
}
'''
 common.compile_run(out,'regular_manager',code)
 # Actual timing predicate: no starts near apex, UEV or on the up half.
 window=function(p.read(p.OUT/'nucleo/Src/current_shunt.c'),'mic_current_regular_window')
 pre=r'''
#include <cassert>
#include <cstdint>
struct Timer{uint32_t CNT,CR1,ARR;};static Timer tim;static Timer*TIM1=&tim;
#define TIM_CR1_DIR 16
'''
 checks=r'''
int main(){tim.ARR=5312;
 for(unsigned down=0;down<2;++down)for(unsigned cnt=0;cnt<=5312;++cnt){
  tim.CR1=down?16:0;tim.CNT=cnt;int yes=mic_current_regular_window();
  assert(yes==(down&&cnt>1024&&cnt<4800));
  if(yes){assert(cnt>240+128);assert(5312-cnt>148+128);}
 }
}
'''
 common.compile_run(out,'regular_window',pre+window+checks)
 # Exercise actual high-frequency stop integration, including a safety-cache fault.
 tree=ast.parse(p.read(p.ROOT/'tools/test_foc_runtime_paths.py'))
 literals={}
 for node in ast.walk(tree):
  if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
   for target in node.targets:
    if isinstance(target,ast.Name):literals.setdefault(target.id,node.value.value)
 pre=literals['pre']+'\nstatic int health=1;enum{MC_SW_ERROR=128};static int RCM_CurrentEpoch(){return health;}\n'
 checks=literals['checks'];pos=checks.rfind('}')
 checks=checks[:pos]+'''ret=0;enabled=1;health=0;TSK_HighFrequencyTask();assert(!enabled&&faults==2);
'''+checks[pos:]
 # The original stub checks that the reported fault equals ret.
 pre=pre.replace('assert(f==ret);','assert(f==ret||f==128);')
 common.compile_run(out,'safety_fault_stops_outputs',pre+function(p.read(p.OUT/'nucleo/Src/mc_tasks.c'),'TSK_HighFrequencyTask')+checks)
 # Captured spike remains a trip. No averaging, rejection or new current limit.
 replay=p.read(p.BASE/'powered_FOC_CPU_IRQ_20261030_r2/current_trip_replay.cpp')
 result=common.compile_run(out,'recorded_current_trip',replay)
 rc,ia,ib,norm,trip=map(float,result.split());assert rc==2 and norm>trip and abs(trip-1.35)<1e-6
 for rel in ('motor_control.h','current_core.h','current_adc_window_plan.h','current_adc_deadline.h','foc_experiment.h','local_stop.h'):
  assert (p.OUT/'nucleo/Inc'/rel).read_bytes()==(p.BASE/'nucleo/Inc'/rel).read_bytes(),rel
 old=p.read(p.BASE/'nucleo/Src/current_shunt.c');new=p.read(p.OUT/'nucleo/Src/current_shunt.c')
 for name in ('mic_current_adc_irq','ma_publish_current','mic_current_packet','mic_current_update_epoch'):
  assert function(old,name)==function(new,name),name
 tasks=p.read(p.OUT/'nucleo/Src/mc_tasks.c')
 assert tasks.count('CodeReturn |= RCM_CurrentFault();')==2
 assert 'if(returnValue==MC_NO_ERROR&&!RCM_CurrentEpoch())returnValue=MC_SW_ERROR;' in tasks
 assert not any(x in helpers for x in ('__disable_irq','PRIMASK','while('))
 capture=json.loads(p.read(p.BASE/'powered_FOC_CPU_IRQ_20261030_r2/ADC_peak_decoded.json'))
 rows=capture['samples'];previous=rows[9];bad=rows[10]
 observations=dict(raw_delta_adc1=bad['raw_adc'][0]-previous['raw_adc'][0],
  raw_delta_adc2=bad['raw_adc'][1]-previous['raw_adc'][1],
  EOC_regular_rows=[r['sequence'] for r in rows if r['adc_isr'][0]&4],
  EOC_does_not_always_mean_spike=True,regular_start_time_and_channel_not_recorded=True,
  physical_current_or_ADC_error_cannot_be_uniquely_decided=True,
  MCU_revision='X from existing CubeProgrammer log',
  excluded_errata=['ES0431 2.5.8 onlyZ','ES0431 2.5.10 onlyY','2.5.9 needs>1ms; here62.5us',
   '2.5.11 ADC1/2 asyncDIV1 same clock excluded'],
  source='https://www.st.com/resource/en/errata_sheet/es0431-stm32g431xx441xx-device-errata-stmicroelectronics.pdf')
 report=dict(passed=True,hardware_commands=0,simulated_5s_only=True,simulated_frames=80000,
  timer_policy_cases=10626,recorded_trip_preserved=True,trip_current_A=trip,
  stale_and_missing_safety_data_stops=True,physical_5s_not_proven=True,observations=observations)
 p.write(out/'selftest.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()

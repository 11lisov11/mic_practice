"""Actual C preemption/schedule/fault record, wire and HMI tests; no boards."""
import json, subprocess, ast
import prepare_foc_cache_snapshot_fix as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function


def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
 src=p.read(p.OUT/'nucleo/Src/regular_conversion_manager.c')
 helpers=src[src.index('static RegConv_t *rcm_pending;'):src.index('/* Private function prototypes')]
 original=function(p.read(p.BASE/'nucleo/Src/regular_conversion_manager.c'),'RCM_ExecRegularConv').replace('RCM_ExecRegularConv(','legacy_ExecRegularConv(',1)
 native=p.read(p.OUT/'nucleo/Src/multi_native.c')
 pre=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
static uint32_t host_now=1000;
static volatile uint32_t*hook_stamp;
static unsigned mode,barrier_n,barrier_at;
static void interrupt_publish(){*hook_stamp=host_now+64;host_now+=128;}
static void host_barrier(){
 __asm__ volatile("":::"memory");
 if(barrier_at&&++barrier_n==barrier_at){barrier_at=0;interrupt_publish();}
}
#define __DMB() host_barrier()
#include "foc_timing_core.h"
#include "foc_timing_wire.h"
static ft_first_fault ma_first_runtime;
static ft_perf ma_perf;
static uint8_t ma_perf_off=0;
static void ma_put(uint8_t*p,uint32_t v){memcpy(p,&v,4);}
struct Counter{
 operator uint32_t()const{
  auto saved=host_now;
  if(mode==1||mode==3){interrupt_publish();if(mode==1)mode=0;}
  return saved;
 }
 Counter&operator=(uint32_t v){host_now=v;return*this;}
 Counter&operator+=(uint32_t v){host_now+=v;return*this;}
};
static struct{Counter CYCCNT;}clock_;static auto DWT=&clock_;
static uint32_t SystemCoreClock=170000000;
#define MC_SW_ERROR 128
#define LL_ADC_SAMPLINGTIME_47CYCLES_5 47
#define LL_ADC_REG_RANK_1 1
#define __LL_ADC_DECIMAL_NB_TO_CHANNEL(c) (c)
#define RCM_MAX_CONV 4
struct ADC_TypeDef{unsigned channel,data,eoc,ongoing,finish,ISR,CR,SQR1;};
static ADC_TypeDef adc;static auto ADC1=&adc;
struct Timer{uint32_t CNT,CR1;};static Timer timer={4000,16};static auto TIM1=&timer;
static int enabled,window_ok=1;static unsigned starts;
struct RegConv_t{ADC_TypeDef*regADC;uint32_t samplingTime;uint8_t channel;uint16_t data;uint8_t id;};
static RegConv_t*RCM_handle_array[RCM_MAX_CONV];static uint8_t RCM_conversion_nb=2;
static unsigned LL_TIM_IsEnabledAllOutputs(Timer*){return enabled;}
static unsigned __get_IPSR(){return 15;}
static int mic_current_regular_window(){return window_ok;}
static unsigned LL_ADC_IsActiveFlag_EOC(ADC_TypeDef*a){
 if(a->ongoing&&(int32_t)(host_now-a->finish)>=0){a->eoc=1;a->ongoing=0;a->data=(a->channel*123)<<4;}
 if(!enabled&&a->ongoing)host_now+=16;
 return a->eoc;
}
static unsigned LL_ADC_REG_ReadConversionData12L(ADC_TypeDef*a){a->eoc=0;return a->data;}
static void LL_ADC_ClearFlag_EOC(ADC_TypeDef*a){a->eoc=0;}
static void LL_ADC_REG_SetSequencerRanks(ADC_TypeDef*a,int,unsigned ch){assert(!a->ongoing);a->channel=ch;}
static void LL_ADC_REG_StartConversion(ADC_TypeDef*a){assert(!a->ongoing);a->ongoing=1;a->finish=host_now+240;++starts;}
static unsigned LL_ADC_REG_IsConversionOngoing(ADC_TypeDef*a){LL_ADC_IsActiveFlag_EOC(a);return a->ongoing;}
'''
 checks=r'''
static void reset_case(){
 mode=barrier_at=barrier_n=0;host_now=1000000;adc={};rcm_fault=0;rcm_pending=nullptr;enabled=1;
 memset(&ma_first_runtime,0,sizeof(ma_first_runtime));window_ok=1;
 rcm_stamp[0]=rcm_stamp[1]=host_now-200;rcm_valid[0]=rcm_valid[1]=1;
 hook_stamp=&rcm_stamp[0];
}
static void reason(unsigned want){
 assert(rcm_fault==128&&ma_first_runtime.state==2);
 assert(ma_first_runtime.word[0]==FT_REGULAR_ADC&&ma_first_runtime.word[1]==want);
}
int main(){
 RegConv_t bus={ADC1,47,2,3936,0},temp={ADC1,47,8,15744,1};
 RCM_handle_array[0]=&bus;RCM_handle_array[1]=&temp;
 reset_case();mode=1;legacy_ExecRegularConv(&bus);assert(rcm_fault==128);
 reset_case();mode=1;assert(RCM_ExecRegularConv(&bus)==3936&&rcm_fault==0);
 for(unsigned at:{1U,2U}){
  reset_case();barrier_at=at;assert(RCM_ExecRegularConv(&bus)==3936&&rcm_fault==0);
 }
 reset_case();mode=3;RCM_ExecRegularConv(&bus);mode=0;reason(RCF_CONTENTION);
 reset_case();rcm_valid[0]=0;RCM_ExecRegularConv(&bus);reason(RCF_INVALID);
 reset_case();temp.samplingTime=100;assert(!RCM_CurrentEpoch());reason(RCF_CONFIG);temp.samplingTime=47;
 reset_case();bus.id=9;RCM_ExecRegularConv(&bus);reason(RCF_HANDLE);bus.id=0;
 reset_case();rcm_pending=&bus;adc.ongoing=1;adc.finish=host_now+1000000;
 RCM_ServiceAfterInjected();reason(RCF_NO_EOC);
 reset_case();adc.ongoing=1;adc.finish=host_now+1000000;RCM_ServiceAfterInjected();reason(RCF_BUSY);
 for(unsigned age:{169999U,170000U,170001U}){
  reset_case();rcm_stamp[0]=host_now-age;RCM_ExecRegularConv(&bus);
  if(age<170000)assert(!rcm_fault);else reason(RCF_EXPIRED);
 }
 // The first record is immutable across another failure and OFF recovery.
 auto saved=ma_first_runtime;rcm_fail(RCF_BUSY,1,host_now,rcm_stamp[1]);
 assert(memcmp(&saved,&ma_first_runtime,sizeof(saved))==0);
 enabled=0;assert(RCM_ExecRegularConv(&bus)==3936&&RCM_ExecRegularConv(&temp)==15744);
 assert(!rcm_fault&&memcmp(&saved,&ma_first_runtime,sizeof(saved))==0);
 uint8_t packet[UV3_FRAME];ft_receiver receiver={};
 for(unsigned page=0;page<4;++page){ma_timing_diag(packet,2026103008,page);assert(ft_receive(&receiver,packet,2026103008,true,100));}
 assert(ft_fresh(&receiver,true,100)&&receiver.words[14]==9&&receiver.words[15]==3);
 packet[10]^=1;assert(!ft_receive(&receiver,packet,2026103008,true,100));
 ma_timing_diag(packet,2026103008,0);assert(!ft_receive(&receiver,packet,2026103006,true,100));
 FILE*f=fopen("cache_wire_words.txt","w");assert(f);
 for(auto v:receiver.words)fprintf(f,"%u ",v);fclose(f);
 reset_case();host_now=0x100;rcm_stamp[0]=rcm_stamp[1]=0xfffffff0U;
 assert(RCM_CurrentEpoch());
 reset_case();enabled=0;RCM_ExecRegularConv(&bus);RCM_ExecRegularConv(&temp);enabled=1;
 auto before=starts;
 for(unsigned frame=0;frame<80000;++frame){
  host_now+=10625;assert(RCM_CurrentEpoch());
  if(frame%8==0){auto count=starts;assert(RCM_ExecRegularConv(&bus)==3936);
   assert(RCM_ExecRegularConv(&temp)==15744&&starts==count);}
  RCM_ServiceAfterInjected();assert(!rcm_fault);
 }
 assert(starts==before+80000);
 puts("actual C: legacy race trips; three preemption boundaries fixed; seven fault reasons, immutable record, CRC/peer, expiry1ms, wrap,80000frames OK");
}
'''
 code=pre+function(native,'ma_native_regular_fault')+function(native,'ma_timing_diag')+helpers+function(src,'RCM_ExecRegularConv')+original+checks
 # The test process uses a relative output filename, in a controlled cwd.
 before=__import__('os').getcwd()
 try:
  __import__('os').chdir(out)
  result=common.compile_run(out,'cache_manager',code)
 finally:__import__('os').chdir(before)
 words=list(map(int,p.read(out/'cache_wire_words.txt').split()))
 server=p.read(p.OUT/'web_hmi/server.py');scope={}
 start=server.index('def foc_runtime_status(kv):');end=server.index('\ndef sd_live_status',start)
 exec(server[start:end],scope);decode=scope['foc_runtime_status']
 kv={'foc_runtime_valid':'1','foc_runtime_flags':'1',**{'foc_runtime_w'+str(i):str(v) for i,v in enumerate(words)}}
 decoded=decode(kv)['foc_runtime'];assert decoded['available']
 assert decoded['first_fault']['regular_adc']['reason_code']==3
 assert decoded['first_fault']['algorithm_fault']==0
 for reason in range(1,8):
  k=dict(kv);k['foc_runtime_w15']=str(reason)
  d=decode(k)['foc_runtime'];assert d['available'] and d['first_fault']['regular_adc']['reason_code']==reason
 bad=dict(kv);bad['foc_runtime_w15']='8';assert not decode(bad)['foc_runtime']['available']
 old=dict(kv);old['foc_runtime_w14']='4';assert decode(old)['foc_runtime']['first_fault']['reason_code']==4
 compile(server,'server.py','exec')
 js=function(p.read(p.OUT/'web_hmi/static/app.js'),'mcFaultSummary')
 js_test="const assert=require('assert');\n"+js+"\nconst data="+json.dumps(dict(mc_fault_current_mask=128,foc_runtime=decoded))+";\nassert.strictEqual(mcFaultSummary(data,5),data.foc_runtime.first_fault.reason_ru);\n"
 p.write(out/'banner.js',js_test)
 subprocess.run(['node',str(out/'banner.js')],check=True,capture_output=True)
 subprocess.run(['node','--check',str(p.OUT/'web_hmi/static/app.js')],check=True,capture_output=True)
 # Original production stop path, with actual RCM health returning a fault.
 tree=ast.parse(p.read(p.ROOT/'tools/test_foc_runtime_paths.py'));literals={}
 for n in ast.walk(tree):
  if isinstance(n,ast.Assign) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str):
   for target in n.targets:
    if isinstance(target,ast.Name):literals.setdefault(target.id,n.value.value)
 a=literals['pre'].replace('assert(f==ret);','assert(f==ret||f==128);')+'\nstatic int health=1;enum{MC_SW_ERROR=128};static int RCM_CurrentEpoch(){return health;}\n'
 b=literals['checks'];pos=b.rfind('}');b=b[:pos]+'ret=0;enabled=1;health=0;TSK_HighFrequencyTask();assert(!enabled&&faults==2);\n'+b[pos:]
 common.compile_run(out,'health_stop',a+function(p.read(p.OUT/'nucleo/Src/mc_tasks.c'),'TSK_HighFrequencyTask')+b)
 for rel in ('motor_control.h','foc_experiment.h','current_core.h','current_adc_deadline.h','current_adc_window_plan.h','local_stop.h'):
  assert (p.OUT/'nucleo/Inc'/rel).read_bytes()==(p.BASE/'nucleo/Inc'/rel).read_bytes(),rel
 report=dict(passed=True,hardware_commands=0,frames_simulated=80000,physical_PWM_runs=0,
  actual_legacy_race_reproduced=True,three_preemption_boundaries_tested=True,seven_exact_reasons=True,
  first_fault_survives_OFF_and_later_faults=True,wire_CRC_and_peer_validated=True,
  actual_health_fault_switches_PWM_OFF=True,cache_expiry_ms=1,trip_A=1.35,ADC_guard_ticks=2048,
  HMI_reason_and_banner_verified=True,result=result.strip())
 p.write(out/'selftest.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()

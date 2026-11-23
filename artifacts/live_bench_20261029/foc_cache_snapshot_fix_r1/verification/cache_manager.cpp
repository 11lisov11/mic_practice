
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
void ma_native_regular_fault(const uint32_t*words){
 uint32_t expected=0;
 if(!__atomic_compare_exchange_n(&ma_first_runtime.state,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return;
 for(unsigned i=0;i<14;++i)ma_first_runtime.word[i]=words[i];
 __DMB();__atomic_store_n(&ma_first_runtime.state,2,__ATOMIC_RELEASE);
}void ma_timing_diag(uint8_t*p,uint32_t build,unsigned page){
 uint32_t words[7]={0};page%=4;
 unsigned complete=__atomic_load_n(&ma_first_runtime.state,__ATOMIC_ACQUIRE)==2;
 if(page==0){
  words[0]=ma_perf.wall;words[1]=ma_perf.irq;words[2]=ma_perf.cpu_upper;words[3]=ma_perf.roots;
  words[4]=ma_perf.max_wall;words[5]=ma_perf.max_irq;words[6]=ma_perf.max_cpu;
 }else if(page==1){
  words[0]=ma_perf.queue;words[1]=ma_perf.adc_age;words[2]=ma_perf.result_age;
  words[3]=ma_perf.max_queue;words[4]=ma_perf.max_result;words[5]=ma_perf.steps;words[6]=ma_perf.errors;
 }else if(complete)memcpy(words,ma_first_runtime.word+(page-2)*7,sizeof(words));
 memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xE8;p[3]=1;
 p[4]=(uint8_t)page;p[5]=(uint8_t)(complete|(ma_perf_off?2U:0U));ma_put(p+6,build);
 for(unsigned i=0;i<7;++i)ma_put(p+10+4*i,words[i]);
 uv3_seal(p);
}static RegConv_t *rcm_pending;
static uint8_t rcm_next;
static volatile uint8_t rcm_valid[RCM_MAX_CONV];
static volatile uint32_t rcm_stamp[RCM_MAX_CONV];
static volatile uint16_t rcm_fault;
enum {RCF_CONFIG=1,RCF_INVALID=2,RCF_EXPIRED=3,RCF_CONTENTION=4,
      RCF_NO_EOC=5,RCF_BUSY=6,RCF_HANDLE=7};
static void rcm_fail(unsigned reason,unsigned id,uint32_t now,uint32_t stamp){
 rcm_fault=MC_SW_ERROR; /* existing safety stop, before any diagnostics */
 uint32_t words[14]={FT_REGULAR_ADC,reason,now,stamp,id,now-stamp,
  TIM1->CNT,TIM1->CR1,ADC1->ISR,ADC1->CR,ADC1->SQR1,
  rcm_pending?rcm_pending->id:UINT32_MAX,
  (id<RCM_conversion_nb?rcm_valid[id]:0U)|
   (LL_TIM_IsEnabledAllOutputs(TIM1)?2U:0U),__get_IPSR()};
 /* ISR/CR/SQR are read-only observations here; DR is never touched. */
 ma_native_regular_fault(words);
}
static int rcm_fresh(unsigned id){
 uint32_t stamp=0,now=0;
 for(unsigned retry=0;retry<3;++retry){
  uint32_t valid=rcm_valid[id];stamp=rcm_stamp[id];__DMB();
  now=DWT->CYCCNT;__DMB();
  if(stamp!=rcm_stamp[id])continue;
  if(!valid){rcm_fail(RCF_INVALID,id,now,stamp);return 0;}
  if((uint32_t)(now-stamp)>=SystemCoreClock/1000U){
   rcm_fail(RCF_EXPIRED,id,now,stamp);return 0;
  }
  return 1;
 }
 rcm_fail(RCF_CONTENTION,id,now,stamp);return 0;
}
static int rcm_complete(void){
 if(!rcm_pending)return 1;
 if(!LL_ADC_IsActiveFlag_EOC(rcm_pending->regADC))return 0;
 rcm_pending->data=LL_ADC_REG_ReadConversionData12L(rcm_pending->regADC);
 rcm_stamp[rcm_pending->id]=DWT->CYCCNT;__DMB();rcm_valid[rcm_pending->id]=1;
 rcm_pending=NULL;return 1;
}
uint16_t RCM_CurrentFault(void){return rcm_fault;}
int RCM_CurrentEpoch(void){
 if(!LL_TIM_IsEnabledAllOutputs(TIM1))return 1;
 if(rcm_fault)return 0;
 for(unsigned i=0;i<RCM_conversion_nb;++i){
  RegConv_t*c=RCM_handle_array[i];
  if(c->regADC!=ADC1||c->samplingTime!=LL_ADC_SAMPLINGTIME_47CYCLES_5){
   rcm_fail(RCF_CONFIG,i,DWT->CYCCNT,rcm_stamp[i]);return 0;
  }
  if(!rcm_fresh(i))return 0;
 }
 return 1;
}
void RCM_ServiceAfterInjected(void){
 if(!LL_TIM_IsEnabledAllOutputs(TIM1)||rcm_fault)return;
 if(!rcm_complete()){
  unsigned id=rcm_pending->id;rcm_fail(RCF_NO_EOC,id,DWT->CYCCNT,rcm_stamp[id]);return;
 }
 if(!RCM_conversion_nb||!mic_current_regular_window())return;
 RegConv_t*c=RCM_handle_array[rcm_next];
 if(LL_ADC_REG_IsConversionOngoing(c->regADC)){
  rcm_fail(RCF_BUSY,c->id,DWT->CYCCNT,rcm_stamp[c->id]);return;
 }
 LL_ADC_REG_SetSequencerRanks(c->regADC,LL_ADC_REG_RANK_1,__LL_ADC_DECIMAL_NB_TO_CHANNEL(c->channel));
 (void)LL_ADC_REG_ReadConversionData12L(c->regADC);LL_ADC_ClearFlag_EOC(c->regADC);
 rcm_pending=c;__DMB();LL_ADC_REG_StartConversion(c->regADC);
 rcm_next=(uint8_t)((rcm_next+1U)%RCM_conversion_nb);
}

uint16_t RCM_ExecRegularConv(RegConv_t *regConv)
{
  uint16_t result;
  if(regConv&&LL_TIM_IsEnabledAllOutputs(TIM1)){
    unsigned id=regConv->id;
    if(id>=RCM_conversion_nb||RCM_handle_array[id]!=regConv)
      rcm_fail(RCF_HANDLE,id,DWT->CYCCNT,0);
    else (void)rcm_fresh(id);
    return regConv->data;
  }
  /* A RUN conversion may finish after STOP; consume it before changing SQR. */
  while(!rcm_complete()){} /* OFF only; same blocking convention as original */

#ifdef NULL_PTR_CHECK_REG_CON_MNG
  if (MC_NULL == regConv)
  {
    result = 0U;
  }
  else
  {
#endif

  LL_ADC_REG_SetSequencerRanks(regConv->regADC,
                               LL_ADC_REG_RANK_1,
                               __LL_ADC_DECIMAL_NB_TO_CHANNEL(regConv->channel));

  (void)LL_ADC_REG_ReadConversionData12L(regConv->regADC);

  LL_ADC_ClearFlag_EOC(regConv->regADC);
  LL_ADC_REG_StartConversion(regConv->regADC);

  while (LL_ADC_IsActiveFlag_EOC(regConv->regADC) == 0U )

  {
    /* wait for end of conversion */
  }

  /* Reading of ADC Converted Value */
  result = LL_ADC_REG_ReadConversionData12L(regConv->regADC);
  regConv->data=result;rcm_stamp[regConv->id]=DWT->CYCCNT;
  __DMB();rcm_valid[regConv->id]=1;rcm_fault=0;

#ifdef NULL_PTR_CHECK_REG_CON_MNG
  }
#endif
  return result;

}uint16_t legacy_ExecRegularConv(RegConv_t *regConv)
{
  uint16_t result;
  if(regConv&&LL_TIM_IsEnabledAllOutputs(TIM1)){
    unsigned id=regConv->id;
    if(id>=RCM_conversion_nb||RCM_handle_array[id]!=regConv||!rcm_valid[id]||
       (uint32_t)(DWT->CYCCNT-rcm_stamp[id])>=SystemCoreClock/1000U)rcm_fault=MC_SW_ERROR;
    return regConv->data;
  }
  /* A RUN conversion may finish after STOP; consume it before changing SQR. */
  while(!rcm_complete()){} /* OFF only; same blocking convention as original */

#ifdef NULL_PTR_CHECK_REG_CON_MNG
  if (MC_NULL == regConv)
  {
    result = 0U;
  }
  else
  {
#endif

  LL_ADC_REG_SetSequencerRanks(regConv->regADC,
                               LL_ADC_REG_RANK_1,
                               __LL_ADC_DECIMAL_NB_TO_CHANNEL(regConv->channel));

  (void)LL_ADC_REG_ReadConversionData12L(regConv->regADC);

  LL_ADC_ClearFlag_EOC(regConv->regADC);
  LL_ADC_REG_StartConversion(regConv->regADC);

  while (LL_ADC_IsActiveFlag_EOC(regConv->regADC) == 0U )

  {
    /* wait for end of conversion */
  }

  /* Reading of ADC Converted Value */
  result = LL_ADC_REG_ReadConversionData12L(regConv->regADC);
  regConv->data=result;rcm_stamp[regConv->id]=DWT->CYCCNT;
  __DMB();rcm_valid[regConv->id]=1;rcm_fault=0;

#ifdef NULL_PTR_CHECK_REG_CON_MNG
  }
#endif
  return result;

}
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


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
static RegConv_t *rcm_pending;
static uint8_t rcm_next,rcm_valid[RCM_MAX_CONV];
static uint32_t rcm_stamp[RCM_MAX_CONV];
static volatile uint16_t rcm_fault;
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
 /* Missing conversion completion or stale safety feedback fails closed.
  * The original safety period is0.5ms; maximum cache age here is1ms. */
 for(unsigned i=0;i<RCM_conversion_nb;++i){
  RegConv_t*c=RCM_handle_array[i];
  if(c->regADC!=ADC1||c->samplingTime!=LL_ADC_SAMPLINGTIME_47CYCLES_5||
     !rcm_valid[i]||(uint32_t)(DWT->CYCCNT-rcm_stamp[i])>=SystemCoreClock/1000U){
    rcm_fault=MC_SW_ERROR;return 0;
  }
 }
 return 1;
}
void RCM_ServiceAfterInjected(void){
 if(!LL_TIM_IsEnabledAllOutputs(TIM1)||rcm_fault)return;
 if(!rcm_complete()){rcm_fault=MC_SW_ERROR;return;}
 if(!RCM_conversion_nb||!mic_current_regular_window())return;
 RegConv_t*c=RCM_handle_array[rcm_next];
 if(LL_ADC_REG_IsConversionOngoing(c->regADC)){rcm_fault=MC_SW_ERROR;return;}
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

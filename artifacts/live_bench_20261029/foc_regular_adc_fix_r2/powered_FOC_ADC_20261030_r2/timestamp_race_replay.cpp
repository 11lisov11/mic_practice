
#include <cassert>
#include <cstdint>
#include <cstdio>
#define __DMB() __asm__ volatile("":::"memory")
#define MC_SW_ERROR 128
#define LL_ADC_SAMPLINGTIME_47CYCLES_5 4
#define LL_ADC_REG_RANK_1 1
#define __LL_ADC_DECIMAL_NB_TO_CHANNEL(c) (c)
#define RCM_MAX_CONV 4
static uint32_t clock_now=1000000,*interrupt_stamp;
static bool inject;
struct CounterRead{
 operator uint32_t()const{
  uint32_t saved=clock_now;
  // Exact ARM interleaving: load CYCCNT, higher-priority ADC IRQ publishes
  // a newer stamp, resume SysTick and load that stamp.
  if(inject){inject=false;*interrupt_stamp=saved+64;clock_now=saved+128;}
  return saved;
 }
};
static struct{CounterRead CYCCNT;}clock_;static auto DWT=&clock_;
static uint32_t SystemCoreClock=170000000;
struct ADC_TypeDef{};static ADC_TypeDef adc;static auto ADC1=&adc;
struct RegConv_t{ADC_TypeDef*regADC;uint32_t samplingTime;uint8_t channel;uint16_t data;uint8_t id;};
static RegConv_t*RCM_handle_array[RCM_MAX_CONV];static uint8_t RCM_conversion_nb=1;
static int TIM1;
static int LL_TIM_IsEnabledAllOutputs(int){return 1;}
static int LL_ADC_IsActiveFlag_EOC(ADC_TypeDef*){return 1;}
static int LL_ADC_REG_IsConversionOngoing(ADC_TypeDef*){return 0;}
static uint16_t LL_ADC_REG_ReadConversionData12L(ADC_TypeDef*){return 3200;}
static void LL_ADC_ClearFlag_EOC(ADC_TypeDef*){}
static void LL_ADC_REG_SetSequencerRanks(ADC_TypeDef*,int,unsigned){}
static void LL_ADC_REG_StartConversion(ADC_TypeDef*){}
static int mic_current_regular_window(){return 1;}

#include <initializer_list>
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
// Candidate only: bounded coherent read, same1ms expiry, no IRQ masking.
static bool rcm_cache_fresh(unsigned id){
 for(unsigned n=0;n<3;++n){
  uint32_t stamp=*(volatile uint32_t*)&rcm_stamp[id];__DMB();
  uint32_t now=DWT->CYCCNT;__DMB();
  if(stamp==*(volatile uint32_t*)&rcm_stamp[id])
   return (uint32_t)(now-stamp)<SystemCoreClock/1000U;
 }
 return false;
}
uint16_t candidate_ExecRegularConv(RegConv_t *regConv)
{
  uint16_t result;
  if(regConv&&LL_TIM_IsEnabledAllOutputs(TIM1)){
    unsigned id=regConv->id;
    if(id>=RCM_conversion_nb||RCM_handle_array[id]!=regConv||!rcm_valid[id]||
       !rcm_cache_fresh(id))rcm_fault=MC_SW_ERROR;
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
 RegConv_t c={ADC1,4,2,3200,0};RCM_handle_array[0]=&c;
 rcm_valid[0]=1;interrupt_stamp=&rcm_stamp[0];
 rcm_stamp[0]=clock_now-200;inject=true;
 assert(RCM_ExecRegularConv(&c)==3200);
 assert(rcm_fault==128); // old code rejects a cache just refreshed byADC
 uint32_t apparent_age=(uint32_t)(1000000U-1000064U);
 rcm_fault=0;clock_now=1000000;rcm_stamp[0]=clock_now-200;inject=true;
 assert(candidate_ExecRegularConv(&c)==3200&&rcm_fault==0);
 // Expired data is still rejected, exactly at the original1ms boundary.
 for(unsigned age: {169999U,170000U,170001U}){
  clock_now=1000000;rcm_stamp[0]=clock_now-age;rcm_fault=0;
  candidate_ExecRegularConv(&c);assert((rcm_fault==128)==(age>=170000));
 }
 clock_now=0x100;rcm_stamp[0]=0xfffffff0U;rcm_fault=0;
 candidate_ExecRegularConv(&c);assert(rcm_fault==0);
 printf("old_false_trip=128 apparent_age=%u fixed_coherent_read=OK expiry1ms=unchanged wrap=OK\n",apparent_age);
}

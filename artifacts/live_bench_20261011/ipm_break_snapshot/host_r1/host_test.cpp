
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#define __weak
#define TIM_SR_BIF (1U << 7)
#define TIM_SR_B2IF (1U << 8)
#define MC_DP_FAULT 0x400
#define MC_NO_FAULTS 0
#define MC_OVER_VOLT 2
#define MC_OVER_CURR 1
struct TIM_TypeDef { uint32_t SR, DIER, BDTR, CNT, ARR, CCR1, CCR2, CCR3; } timer;
struct { uint32_t IDR; } gpio;
#define TIM1 (&timer)
#define GPIOA (&gpio)
void __DMB() {}
#include "first_break_snapshot.h"
volatile mic_break_snapshot_t mic_first_break;
volatile uint32_t mic_break_irq_count;
volatile mic_break_context_t mic_break_context[2];
volatile uint32_t mic_break_context_index, mic_break_context_valid;
struct PWMC_Handle_t { bool OverVoltageFlag, OverCurrentFlag, driverProtectionFlag, BrakeActionLock; uint8_t Motor; };
struct { PWMC_Handle_t _Super; } PWM_Handle_M1;
unsigned off_calls, scheduler_calls, cases;
uint32_t clock_ms;
bool held_low;
uint32_t HAL_GetTick() { return clock_ms; }
bool LL_TIM_IsActiveFlag_BRK(TIM_TypeDef *t) { return (t->SR & TIM_SR_BIF) != 0; }
bool LL_TIM_IsActiveFlag_BRK2(TIM_TypeDef *t) { return (t->SR & TIM_SR_B2IF) != 0; }
void LL_TIM_ClearFlag_BRK(TIM_TypeDef *t) { if (!held_low) t->SR &= ~TIM_SR_BIF; }
void LL_TIM_ClearFlag_BRK2(TIM_TypeDef *t) { if (!held_low) t->SR &= ~TIM_SR_B2IF; }
void LL_TIM_DisableIT_BRK(TIM_TypeDef *t) { t->DIER &= ~(1U << 7); }
void PWMC_SwitchOffPWM(PWMC_Handle_t *) { ++off_calls; timer.BDTR &= ~(1U << 15); }
void MC_Scheduler() { ++scheduler_calls; }
void reset() {
 mic_first_break = {}; mic_break_irq_count=0; mic_break_context[0]={};
 mic_break_context[1]={}; mic_break_context_index=0; mic_break_context_valid=0;
 PWM_Handle_M1={}; off_calls=scheduler_calls=0; held_low=false; clock_ms=1234;
 timer={0,1U<<7,(1U<<12)|(1U<<15),37,4000,500,1500,2500}; gpio.IDR=0;
}
__weak void *PWMC_DP_Handler(PWMC_Handle_t *pHandle)
{
  void *tempPointer; //cstat !MISRAC2012-Rule-8.13
#ifdef NULL_PTR_CHECK_PWR_CUR_FDB
  if (MC_NULL == pHandle)
  {
    tempPointer = MC_NULL;
  }
  else
  {
#endif
    PWMC_SwitchOffPWM(pHandle);
    pHandle->driverProtectionFlag = true;
    tempPointer = &(pHandle->Motor);
#ifdef NULL_PTR_CHECK_PWR_CUR_FDB
  }
#endif
  return (tempPointer);
}
__weak uint16_t PWMC_IsFaultOccurred(PWMC_Handle_t *pHandle)
{
  uint16_t retVal = MC_NO_FAULTS;

  if (true == pHandle->OverVoltageFlag)
  {
    retVal = MC_OVER_VOLT;
    pHandle->OverVoltageFlag = false;
  }
  else
  {
    /* Nothing to do */
  }

  if (true == pHandle->OverCurrentFlag)
  {
    retVal |= MC_OVER_CURR;
    pHandle->OverCurrentFlag = false;
  }
  else
  {
    /* Nothing to do */
  }

  if (true == pHandle->driverProtectionFlag)
  {
    retVal |= MC_DP_FAULT;
    pHandle->driverProtectionFlag = false;
  }
  else
  {
    /* Nothing to do */
  }

  return (retVal);
}
void TIMx_BRK_M1_IRQHandler(void)
{
  /* USER CODE BEGIN TIMx_BRK_M1_IRQn 0 */

  /* USER CODE END TIMx_BRK_M1_IRQn 0 */
  mic_break_capture_first(HAL_GetTick());
  /* BIF cannot clear while the break level is active. Mask only its IRQ;
     hardware BKE remains enabled. A clean CLEAR rearms BIE in main.c. */
  if (LL_TIM_IsActiveFlag_BRK(TIM1) || LL_TIM_IsActiveFlag_BRK2(TIM1))
  {
    LL_TIM_DisableIT_BRK(TIM1);
  }
  if (LL_TIM_IsActiveFlag_BRK(TIM1))
  {
    LL_TIM_ClearFlag_BRK(TIM1);
    /* IPM SD reports driver protection, not DC-bus overvoltage. */
    PWMC_DP_Handler(&PWM_Handle_M1._Super);
  }
  if (LL_TIM_IsActiveFlag_BRK2(TIM1))
  {
    LL_TIM_ClearFlag_BRK2(TIM1);
    PWMC_DP_Handler(&PWM_Handle_M1._Super);
  }
  /* Systick is not executed due low priority so is necessary to call MC_Scheduler here.*/
  MC_Scheduler();

  /* USER CODE BEGIN TIMx_BRK_M1_IRQn 1 */

  /* USER CODE END TIMx_BRK_M1_IRQn 1 */
}

int main(int argc, char **argv) {
 static_assert(sizeof(mic_break_snapshot_t)==88, "RAM ABI");
 for (unsigned flags=0; flags<4; ++flags) {
  reset(); timer.SR=((flags&1)?TIM_SR_BIF:0)|((flags&2)?TIM_SR_B2IF:0);
  const uint32_t original_sr=timer.SR;
  TIMx_BRK_M1_IRQHandler();
  assert(scheduler_calls==1 && timer.SR==0 && (timer.BDTR & (1U<<12)));
  assert(off_calls==((flags&1U)+((flags>>1U)&1U)));
  if (!flags) {
   assert(mic_first_break.magic==0 && mic_break_irq_count==0);
   assert(timer.BDTR & (1U<<15)); assert(timer.DIER & (1U<<7));
  } else {
   assert(mic_first_break.magic==MIC_BREAK_MAGIC && mic_break_irq_count==1);
   assert(mic_first_break.schema==1 && mic_first_break.bytes==88);
   assert(mic_first_break.tim_sr==original_sr);
   assert(mic_first_break.tim_dier==(1U<<7));
   assert(mic_first_break.tim_bdtr==((1U<<12)|(1U<<15)));
   assert(mic_first_break.tick_ms==1234 && mic_first_break.tim_cnt==37);
   assert(mic_first_break.tim_arr==4000 && mic_first_break.tim_ccr1==500);
   assert(mic_first_break.tim_ccr2==1500 && mic_first_break.tim_ccr3==2500);
   assert(mic_first_break.context_valid==0);
   assert(!(timer.BDTR&(1U<<15)) && !(timer.DIER&(1U<<7)));
   assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_DP_FAULT);
  }
  ++cases;
 }
 reset(); mic_break_context_t a={1200,-17,6,0,0,321,-50,99};
 mic_break_publish_context(&a);
 timer.SR=TIM_SR_BIF; gpio.IDR=1U<<6; timer.BDTR&=~(1U<<15);
 TIMx_BRK_M1_IRQHandler();
 assert(mic_first_break.context_valid==1 && mic_first_break.gpioa_idr==(1U<<6));
 assert(mic_first_break.context.reference_speed_unit==-17);
 assert(mic_first_break.context.temperature_deci_c==-50);
 assert(mic_first_break.context.tick_ms==1200 && mic_first_break.context.command_sequence==99);
 assert(!(mic_first_break.tim_bdtr&(1U<<15))); ++cases;
 mic_break_snapshot_t saved=mic_first_break;
 mic_break_context_t b={1235,100,7,0x400,0x400,320,520,100};
 mic_break_publish_context(&b); timer.SR=TIM_SR_B2IF; clock_ms=1300;
 TIMx_BRK_M1_IRQHandler();
 mic_break_snapshot_t repeated=mic_first_break;
 assert(std::memcmp(&saved,&repeated,sizeof(saved))==0 && mic_break_irq_count==2); ++cases;
 mic_break_irq_count=UINT32_MAX; TIMx_BRK_M1_IRQHandler(); // no active flag
 assert(mic_break_irq_count==UINT32_MAX); timer.SR=TIM_SR_BIF;
 TIMx_BRK_M1_IRQHandler(); assert(mic_break_irq_count==UINT32_MAX); ++cases;
 reset(); held_low=true; timer.SR=TIM_SR_BIF;
 for (unsigned i=0;i<1000;++i) if(timer.DIER&(1U<<7)) TIMx_BRK_M1_IRQHandler();
 assert(off_calls==1 && scheduler_calls==1 && mic_break_irq_count==1);
 assert(timer.SR==TIM_SR_BIF && !(timer.DIER&(1U<<7)) && (timer.BDTR&(1U<<12))); ++cases;
 // A preempted publisher has written the inactive bank but not published it.
 reset(); mic_break_publish_context(&a);
 mic_break_context[mic_break_context_index^1U]=b;
 timer.SR=TIM_SR_BIF; TIMx_BRK_M1_IRQHandler();
 assert(mic_first_break.context.command_sequence==99); ++cases;
 reset(); mic_break_publish_context(&b); timer.SR=TIM_SR_BIF;
 TIMx_BRK_M1_IRQHandler();
 assert(mic_first_break.context.command_sequence==100); ++cases;
 if (argc==2) {
  FILE *f=std::fopen(argv[1],"wb"); assert(f);
  mic_break_snapshot_t fixture=mic_first_break;
  assert(std::fwrite(&fixture,1,sizeof(fixture),f)==sizeof(fixture)); std::fclose(f);
 }
 std::printf("%u host IRQ/snapshot cases passed\n",cases);
}


#include <cassert>
#include <cstdint>
#include <cstdio>
#define __weak
struct TIM_TypeDef { uint32_t flags; uint32_t moe; bool bie, level; } timer;
#define TIM1 (&timer)
struct PWMC_Handle_t {
 bool OverVoltageFlag, OverCurrentFlag, driverProtectionFlag, BrakeActionLock;
 uint8_t Motor;
};
struct { PWMC_Handle_t _Super; } PWM_Handle_M1;
unsigned off_calls, ovp_calls, scheduler_calls;
bool LL_TIM_IsActiveFlag_BRK(TIM_TypeDef *t) { return (t->flags & 1) != 0; }
bool LL_TIM_IsActiveFlag_BRK2(TIM_TypeDef *t) { return (t->flags & 2) != 0; }
void LL_TIM_ClearFlag_BRK(TIM_TypeDef *t) { if (!t->level) t->flags &= ~1U; }
void LL_TIM_ClearFlag_BRK2(TIM_TypeDef *t) { if (!t->level) t->flags &= ~2U; }
void LL_TIM_DisableIT_BRK(TIM_TypeDef *t) { t->bie = false; }
void PWMC_SwitchOffPWM(PWMC_Handle_t *) { ++off_calls; timer.moe = 0; }
void PWMC_OVP_Handler(PWMC_Handle_t *p, TIM_TypeDef *) {
 ++ovp_calls; p->OverVoltageFlag = true; p->BrakeActionLock = true;
}
void MC_Scheduler() { ++scheduler_calls; }

#define MC_NO_FAULTS ((uint16_t)0x0000)
#define MC_OVER_VOLT ((uint16_t)0x0002)
#define MC_OVER_CURR ((uint16_t)0x0040)
#define MC_DP_FAULT ((uint16_t)0x0400)
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
int main() {
 for (unsigned flags=0; flags<4; ++flags) {
  PWM_Handle_M1 = {}; timer = {flags, 1, true, false};
  off_calls=ovp_calls=scheduler_calls=0;
  TIMx_BRK_M1_IRQHandler();
  assert(timer.flags==0 && ovp_calls==0 && scheduler_calls==1);
  assert(timer.bie == (flags==0));
  assert(!PWM_Handle_M1._Super.BrakeActionLock);
  assert(!PWM_Handle_M1._Super.OverVoltageFlag);
  if (flags) {
   assert(timer.moe==0 && off_calls==((flags&1U)+((flags>>1U)&1U)));
   assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_DP_FAULT);
   assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_NO_FAULTS);
  } else {
   assert(timer.moe==1 && off_calls==0);
   assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_NO_FAULTS);
  }
 }
 PWM_Handle_M1={}; timer={1,1,true,true}; off_calls=ovp_calls=scheduler_calls=0;
 for (unsigned tick=0; tick<1000; ++tick) {
  if (timer.bie && timer.flags) TIMx_BRK_M1_IRQHandler();
 }
 assert(!timer.bie && timer.flags==1 && timer.moe==0 && off_calls==1 && scheduler_calls==1);
 assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_DP_FAULT);
 timer.level=false;
 assert(!timer.bie && timer.moe==0);
 std::puts("4 SD IRQ combinations and sustained-level interrupt starvation regression passed");
}

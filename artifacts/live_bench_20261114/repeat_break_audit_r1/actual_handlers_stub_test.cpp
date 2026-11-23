
#include <cstdint>
#include <cassert>
#include <cstdio>
#define MIC_FOC_IRQ_SCOPE
#define MC_NO_FAULTS 0
#define MC_OVER_VOLT 2
#define MC_OVER_CURR 1
#define MC_DP_FAULT 1024
#define GPIO_PIN_6 64
#define GPIO_PIN_SET 1
struct TIM_TypeDef {uint32_t SR=0; bool MOE=false; bool BIE=true;};
TIM_TypeDef timer; TIM_TypeDef* TIM1=&timer; void* GPIOA=nullptr;
bool pin_high=true,hardware_break_active=false;
struct PWMC_Handle_t {bool driverProtectionFlag=false,OverVoltageFlag=false,OverCurrentFlag=false;int Motor=0;};
struct {PWMC_Handle_t _Super;} PWM_Handle_M1;
unsigned captures=0,schedulers=0;
void PWMC_SwitchOffPWM(PWMC_Handle_t*){timer.MOE=false;}
uint32_t HAL_GetTick(){return 0;}
int HAL_GPIO_ReadPin(void*,int){return pin_high?1:0;}
bool LL_TIM_IsEnabledAllOutputs(TIM_TypeDef*t){return t->MOE;}
void LL_TIM_ClearFlag_BRK(TIM_TypeDef*t){if(!hardware_break_active)t->SR&=~128U;}
void LL_TIM_ClearFlag_BRK2(TIM_TypeDef*t){t->SR&=~256U;}
bool LL_TIM_IsActiveFlag_BRK(TIM_TypeDef*t){return t->SR&128U;}
bool LL_TIM_IsActiveFlag_BRK2(TIM_TypeDef*t){return t->SR&256U;}
void LL_TIM_EnableIT_BRK(TIM_TypeDef*t){t->BIE=true;}
void LL_TIM_DisableIT_BRK(TIM_TypeDef*t){t->BIE=false;}
void mic_break_capture_first(uint32_t){if(timer.SR&384U)++captures;}
void MC_Scheduler(){++schedulers;}
void *PWMC_DP_Handler(PWMC_Handle_t *pHandle)
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
uint16_t PWMC_IsFaultOccurred(PWMC_Handle_t *pHandle)
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
bool uno_rearm_break_irq(void) {
  if (LL_TIM_IsEnabledAllOutputs(TIM1) ||
      HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_6) != GPIO_PIN_SET) return false;
  LL_TIM_ClearFlag_BRK(TIM1);
  LL_TIM_ClearFlag_BRK2(TIM1);
  if (LL_TIM_IsActiveFlag_BRK(TIM1) || LL_TIM_IsActiveFlag_BRK2(TIM1)) return false;
  LL_TIM_EnableIT_BRK(TIM1);
  return true;
}
void TIMx_BRK_M1_IRQHandler(void)
{
  MIC_FOC_IRQ_SCOPE;
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

void reset(){timer={};timer.BIE=true;PWM_Handle_M1._Super={};pin_high=true;hardware_break_active=false;captures=0;schedulers=0;}
int main(){
 reset();TIMx_BRK_M1_IRQHandler();assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==0&&timer.BIE&&captures==0);puts("PASS stale NVIC/vector with no BIF creates no DP fault");
 reset();timer.SR=128;TIMx_BRK_M1_IRQHandler();assert(!timer.BIE&&timer.SR==0&&PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==1024);puts("PASS new BIF with SD already HIGH creates DP fault and masks BIE");
 assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==0);puts("PASS driverProtectionFlag consumed once");
 assert(uno_rearm_break_irq()&&timer.BIE);TIMx_BRK_M1_IRQHandler();assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==0&&timer.BIE);puts("PASS rearm followed by stale interrupt does not recreate old fault");
 timer.SR=128;TIMx_BRK_M1_IRQHandler();assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==1024&&!timer.BIE);puts("PASS later BIF recreates DP latch without PWM or commands");
 reset();timer.SR=128;assert(uno_rearm_break_irq()&&timer.SR==0&&timer.BIE);TIMx_BRK_M1_IRQHandler();assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==0);puts("PASS rearm clears stale BIF before enabling BIE");
 reset();pin_high=false;timer.BIE=false;hardware_break_active=true;timer.SR=128;assert(!uno_rearm_break_irq()&&!timer.BIE);puts("PASS active SD LOW prevents rearm");
 reset();timer.MOE=true;assert(!uno_rearm_break_irq());puts("PASS enabled outputs prevent rearm");
 reset();timer.SR=256;TIMx_BRK_M1_IRQHandler();assert(!timer.BIE&&PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==1024);puts("PASS B2IF follows separate checked fault path");
}

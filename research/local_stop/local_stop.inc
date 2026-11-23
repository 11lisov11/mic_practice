#include "stm32g4xx_ll_exti.h"
#include "local_stop.h"

volatile uint32_t mic_local_stop_latched;
extern uint8_t bMCBootCompleted;

static bool mic_local_button_pending(void) {
  /* MB1367 B1 connects B_USER to VDD; R26 pulls the released input LOW. */
  return HAL_GPIO_ReadPin(Start_Stop_GPIO_Port, Start_Stop_Pin) == GPIO_PIN_SET ||
         LL_EXTI_IsActiveFlag_0_31(LL_EXTI_LINE_13);
}

bool mic_local_stop_blocked(void) {
  if (mic_local_button_pending()) mic_local_stop_latched = 1U;
  return mic_local_stop_latched != 0U;
}

/* Strong override of the MCSDK weak callback. No UART or RPC dependency. */
void UI_HandleStartStopButton_cb(void) {
  mic_local_stop_latched = 1U;
  LL_TIM_DisableAllOutputs(TIM1);
  if (bMCBootCompleted != 0U) (void)MC_StopMotor1();
}

void mic_local_stop_enable_outputs(TIM_TypeDef *timer) {
  /* Only the MOE publication is atomic; BKIN remains hardware-active. */
  const uint32_t mask = __get_PRIMASK();
  __disable_irq();
  if (mic_local_stop_blocked()) LL_TIM_DisableAllOutputs(timer);
  else LL_TIM_EnableAllOutputs(timer);
  __set_PRIMASK(mask);
}

bool mic_local_stop_clear(void) {
  const uint32_t mask = __get_PRIMASK();
  __disable_irq();
  const bool allowed = !mic_local_button_pending() &&
      !LL_TIM_IsEnabledAllOutputs(TIM1) && MC_GetSTMStateMotor1() == IDLE &&
      MC_GetCurrentFaultsMotor1() == MC_NO_FAULTS &&
      MC_GetOccurredFaultsMotor1() == MC_NO_FAULTS;
  if (allowed) mic_local_stop_latched = 0U;
  __set_PRIMASK(mask);
  return allowed;
}

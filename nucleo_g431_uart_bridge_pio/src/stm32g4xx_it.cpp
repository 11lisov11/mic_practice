#include "stm32g4xx_hal.h"

#include "motor_backend.h"

extern UART_HandleTypeDef huart1;

extern "C" void USART1_IRQHandler(void) {
  HAL_UART_IRQHandler(&huart1);
}

extern "C" void TIM1_UP_TIM16_IRQHandler(void) {
  motor_backend_control_irq_handler();
}

extern "C" void SysTick_Handler(void) {
  HAL_IncTick();
  HAL_SYSTICK_IRQHandler();
}

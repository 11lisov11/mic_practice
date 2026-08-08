#include "stm32g4xx_hal.h"

extern UART_HandleTypeDef huart1;

extern "C" void USART1_IRQHandler(void) {
  HAL_UART_IRQHandler(&huart1);
}

extern "C" void SysTick_Handler(void) {
  HAL_IncTick();
  HAL_SYSTICK_IRQHandler();
}

#include "stm32f1xx_hal.h"
#include "config.h"
#if LINK_USE_SPI
extern SPI_HandleTypeDef hspi1;
extern "C" void SPI1_IRQHandler(void) {
  HAL_SPI_IRQHandler(&hspi1);
}
#else
#include "uart_link.h"
extern "C" void USART2_IRQHandler(void) {
  uart_link_isr();
}
#endif

extern "C" void SysTick_Handler(void) {
  HAL_IncTick();
  HAL_SYSTICK_IRQHandler();
}

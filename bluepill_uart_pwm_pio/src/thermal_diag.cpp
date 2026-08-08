#include "stm32f1xx_hal.h"

#ifndef THERMAL_DIAG_UART
#define THERMAL_DIAG_UART 0
#endif

#define DIAG_LED_PORT GPIOC
#define DIAG_LED_PIN GPIO_PIN_13

#if THERMAL_DIAG_UART
static UART_HandleTypeDef s_uart;
#endif

static void system_clock_config(void);
static void gpio_safe_init(void);

static void led_set(bool on) {
  HAL_GPIO_WritePin(DIAG_LED_PORT, DIAG_LED_PIN, on ? GPIO_PIN_RESET : GPIO_PIN_SET);
}

#if THERMAL_DIAG_UART
extern "C" void HAL_UART_MspInit(UART_HandleTypeDef *huart) {
  if (huart->Instance != USART2) {
    return;
  }
  __HAL_RCC_USART2_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {0};
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  gpio.Pin = GPIO_PIN_2;
  gpio.Mode = GPIO_MODE_AF_PP;
  HAL_GPIO_Init(GPIOA, &gpio);

  gpio.Pin = GPIO_PIN_3;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOA, &gpio);
}

static void uart_init(void) {
  s_uart.Instance = USART2;
  s_uart.Init.BaudRate = 115200;
  s_uart.Init.WordLength = UART_WORDLENGTH_8B;
  s_uart.Init.StopBits = UART_STOPBITS_1;
  s_uart.Init.Parity = UART_PARITY_NONE;
  s_uart.Init.Mode = UART_MODE_TX_RX;
  s_uart.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  s_uart.Init.OverSampling = UART_OVERSAMPLING_16;
  (void)HAL_UART_Init(&s_uart);
}
#endif

int main(void) {
  HAL_Init();
  system_clock_config();
  gpio_safe_init();
#if THERMAL_DIAG_UART
  uart_init();
  static const uint8_t banner[] = "BLUEPILL_THERMAL_DIAG_UART\r\n";
#endif

  uint32_t last_cycle_ms = 0;
  while (true) {
    const uint32_t now_ms = HAL_GetTick();
    if ((uint32_t)(now_ms - last_cycle_ms) >= 1000U) {
      last_cycle_ms = now_ms;
      led_set(true);
#if THERMAL_DIAG_UART
      (void)HAL_UART_Transmit(&s_uart, const_cast<uint8_t *>(banner), sizeof(banner) - 1U, 20U);
#endif
      HAL_Delay(50U);
      led_set(false);
    }
  }
}

static void gpio_safe_init(void) {
  __HAL_RCC_AFIO_CLK_ENABLE();
  __HAL_AFIO_REMAP_SWJ_NOJTAG();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();

  // All application pins are high-impedance. PA13/PA14 remain assigned to SWD.
  GPIO_InitTypeDef analog = {0};
  analog.Mode = GPIO_MODE_ANALOG;
  analog.Pull = GPIO_NOPULL;
  analog.Pin = 0x9FFFU;
  HAL_GPIO_Init(GPIOA, &analog);
  analog.Pin = GPIO_PIN_All;
  HAL_GPIO_Init(GPIOB, &analog);
  analog.Pin = GPIO_PIN_14 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOC, &analog);

  GPIO_InitTypeDef led = {0};
  led.Pin = DIAG_LED_PIN;
  led.Mode = GPIO_MODE_OUTPUT_PP;
  led.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(DIAG_LED_PORT, &led);
  led_set(false);
}

static void system_clock_config(void) {
  RCC_OscInitTypeDef osc = {0};
  osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  osc.HSIState = RCC_HSI_ON;
  osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  osc.PLL.PLLState = RCC_PLL_OFF;
  (void)HAL_RCC_OscConfig(&osc);

  RCC_ClkInitTypeDef clock = {0};
  clock.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                    RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clock.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clock.APB1CLKDivider = RCC_HCLK_DIV1;
  clock.APB2CLKDivider = RCC_HCLK_DIV1;
  (void)HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_0);
}

extern "C" void SysTick_Handler(void) {
  HAL_IncTick();
  HAL_SYSTICK_IRQHandler();
}

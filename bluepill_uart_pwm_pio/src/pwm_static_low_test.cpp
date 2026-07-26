#include "config.h"
#include "stm32f1xx_hal.h"

// Diagnostic-only firmware: no TIM1, no UART protocol, no PWM generation.
// It proves whether the STM32 pins can physically hold all IPM logic inputs LOW.

static constexpr uint16_t PWM_A_PINS = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10;
static constexpr uint16_t PWM_B_PINS = GPIO_PIN_13 | GPIO_PIN_14 | GPIO_PIN_15;

static void SystemClock_Config(void);

extern "C" void SysTick_Handler(void) {
  HAL_IncTick();
}

static void enable_port_clk(GPIO_TypeDef *port) {
  if (port == GPIOA) __HAL_RCC_GPIOA_CLK_ENABLE();
  if (port == GPIOB) __HAL_RCC_GPIOB_CLK_ENABLE();
  if (port == GPIOC) __HAL_RCC_GPIOC_CLK_ENABLE();
}

static void em_stop_shutdown(bool active) {
  GPIO_PinState st = (active == (BRAKE_ACTIVE_STATE != 0)) ? GPIO_PIN_SET : GPIO_PIN_RESET;
  HAL_GPIO_WritePin(EM_STOP_GPIO_PORT, EM_STOP_GPIO_PIN, st);
}

static void force_all_static_low(void) {
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_AFIO_CLK_ENABLE();
  __HAL_AFIO_REMAP_SWJ_NOJTAG();

  HAL_GPIO_WritePin(GPIOA, PWM_A_PINS, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOB, PWM_B_PINS, GPIO_PIN_RESET);

  GPIO_InitTypeDef gpio = {0};
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;

  gpio.Pin = PWM_A_PINS;
  HAL_GPIO_Init(GPIOA, &gpio);

  gpio.Pin = PWM_B_PINS;
  HAL_GPIO_Init(GPIOB, &gpio);

  HAL_GPIO_WritePin(GPIOA, PWM_A_PINS, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOB, PWM_B_PINS, GPIO_PIN_RESET);
}

static void init_safe_outputs(void) {
  enable_port_clk(EM_STOP_GPIO_PORT);
  __HAL_RCC_GPIOC_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = EM_STOP_GPIO_PIN;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(EM_STOP_GPIO_PORT, &gpio);
  em_stop_shutdown(true);

  // Blue Pill LED PC13, active low. Blink slowly to show this diagnostic is running.
  gpio.Pin = GPIO_PIN_13;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &gpio);
  HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_SET);
}

int main(void) {
  HAL_Init();
  force_all_static_low();
  SystemClock_Config();
  init_safe_outputs();
  force_all_static_low();

  uint32_t last_blink_ms = HAL_GetTick();
  bool led_on = false;
  while (1) {
    force_all_static_low();
    em_stop_shutdown(true);
    const uint32_t now = HAL_GetTick();
    if ((now - last_blink_ms) >= 1000U) {
      last_blink_ms = now;
      led_on = !led_on;
      HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, led_on ? GPIO_PIN_RESET : GPIO_PIN_SET);
    }
  }
}

static void SystemClock_Config(void) {
  RCC_OscInitTypeDef osc = {0};
  RCC_ClkInitTypeDef clk = {0};

  osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  osc.HSEState = RCC_HSE_ON;
  osc.HSIState = RCC_HSI_ON;
  osc.PLL.PLLState = RCC_PLL_ON;
  osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  osc.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    osc.HSEState = RCC_HSE_OFF;
    osc.HSIState = RCC_HSI_ON;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSI_DIV2;
    osc.PLL.PLLMUL = RCC_PLL_MUL16;
    HAL_RCC_OscConfig(&osc);
  }

  clk.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                  RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clk.APB1CLKDivider = RCC_HCLK_DIV2;
  clk.APB2CLKDivider = RCC_HCLK_DIV1;
  HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_2);
}

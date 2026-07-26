#include "config.h"
#include "pwm_tim1.h"
#include "stm32f1xx_hal.h"

static void SystemClock_Config(void);

extern "C" void SysTick_Handler(void) {
  HAL_IncTick();
}

static void em_stop_shutdown(bool active) {
  GPIO_PinState st = (active == (BRAKE_ACTIVE_STATE != 0)) ? GPIO_PIN_SET : GPIO_PIN_RESET;
  HAL_GPIO_WritePin(EM_STOP_GPIO_PORT, EM_STOP_GPIO_PIN, st);
}

static void init_safe_gpio(void) {
  if (EM_STOP_GPIO_PORT == GPIOA) __HAL_RCC_GPIOA_CLK_ENABLE();
  if (EM_STOP_GPIO_PORT == GPIOB) __HAL_RCC_GPIOB_CLK_ENABLE();
  if (EM_STOP_GPIO_PORT == GPIOC) __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = EM_STOP_GPIO_PIN;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(EM_STOP_GPIO_PORT, &gpio);
  em_stop_shutdown(true);

  gpio.Pin = GPIO_PIN_13;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &gpio);
  HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_SET);
}

int main(void) {
  HAL_Init();
  pwm_force_safe_gpio();
  SystemClock_Config();
  init_safe_gpio();
  pwm_force_safe_gpio();
  pwm_tim1_init();
  pwm_safe_idle();

  while (1) {
    // Keep IPM shutdown asserted; only the logic PWM pins toggle for Saleae.
    em_stop_shutdown(true);
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_SET);
    pwm_safe_idle();
    HAL_Delay(700);

    pwm_apply_diag();  // CH1/2/3 = 10/20/30%, complementary outputs include deadtime.
    pwm_outputs_enable(true);
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_RESET);
    HAL_Delay(2000);
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

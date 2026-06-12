#include "stm32f1xx_hal.h"

// MIC_AI precharge relay driver input: PB4 -> resistor -> transistor base.
// Blue Pill LED PC13 is active-low and mirrors relay state.
static constexpr uint16_t RELAY_PIN = GPIO_PIN_4;
static constexpr uint16_t LED_PIN = GPIO_PIN_13;

static void SystemClock_Config(void);

static void set_relay(bool on) {
  HAL_GPIO_WritePin(GPIOB, RELAY_PIN, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOC, LED_PIN, on ? GPIO_PIN_RESET : GPIO_PIN_SET);
}

extern "C" void SysTick_Handler(void) {
  HAL_IncTick();
}

int main(void) {
  HAL_Init();
  SystemClock_Config();

  __HAL_RCC_AFIO_CLK_ENABLE();
  // PB4 is JTAG NJTRST by default. Keep SWD active, but release PB3/PB4 GPIOs.
  __HAL_AFIO_REMAP_SWJ_NOJTAG();

  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = RELAY_PIN;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &gpio);

  gpio.Pin = LED_PIN;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &gpio);

  set_relay(false);
  HAL_Delay(1000);

  while (1) {
    set_relay(true);
    HAL_Delay(700);
    set_relay(false);
    HAL_Delay(700);
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

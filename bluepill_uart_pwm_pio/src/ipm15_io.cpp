#include "ipm15_io.h"

#include <math.h>

#include "config.h"
#include "stm32f1xx_hal.h"

#if USE_BRAKE_PWM
static TIM_HandleTypeDef s_htim4;
static uint32_t s_brake_arr = 0;
#endif

static uint32_t timer4_clock_hz(void) {
  uint32_t pclk = HAL_RCC_GetPCLK1Freq();
  if ((RCC->CFGR & RCC_CFGR_PPRE1) != RCC_CFGR_PPRE1_DIV1) {
    pclk *= 2U;
  }
  return pclk;
}

static void gpio_out_init(GPIO_TypeDef *port, uint16_t pin) {
  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = pin;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(port, &gpio);
}

static void gpio_analog_init(GPIO_TypeDef *port, uint16_t pin) {
  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = pin;
  gpio.Mode = GPIO_MODE_ANALOG;
  HAL_GPIO_Init(port, &gpio);
}

void ipm15_io_init(void) {
  if (UNUSED_STEVAL_J2_21_PORT == GPIOA || PFC_SYNC_PORT == GPIOA || PRECHARGE_RELAY_PORT == GPIOA ||
      BRAKE_PWM_PORT == GPIOA) {
    __HAL_RCC_GPIOA_CLK_ENABLE();
  }
  if (UNUSED_STEVAL_J2_21_PORT == GPIOB || PFC_SYNC_PORT == GPIOB || PRECHARGE_RELAY_PORT == GPIOB ||
      BRAKE_PWM_PORT == GPIOB) {
    __HAL_RCC_GPIOB_CLK_ENABLE();
  }

  gpio_analog_init(UNUSED_STEVAL_J2_21_PORT, UNUSED_STEVAL_J2_21_PIN);
  gpio_out_init(PFC_SYNC_PORT, PFC_SYNC_PIN);
#if USE_PRECHARGE_RELAY
  gpio_out_init(PRECHARGE_RELAY_PORT, PRECHARGE_RELAY_PIN);
#else
  gpio_analog_init(PRECHARGE_RELAY_PORT, PRECHARGE_RELAY_PIN);
#endif

  ipm15_set_pfc_sync(false);
  ipm15_set_precharge_relay(false);

#if USE_BRAKE_PWM
  __HAL_RCC_TIM4_CLK_ENABLE();
  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = BRAKE_PWM_PIN;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(BRAKE_PWM_PORT, &gpio);

  uint32_t tim_clk = timer4_clock_hz();
  uint32_t period = (tim_clk / BRAKE_PWM_FREQ_HZ);
  if (period > 0) period -= 1U;

  s_htim4.Instance = TIM4;
  s_htim4.Init.Prescaler = 0;
  s_htim4.Init.CounterMode = TIM_COUNTERMODE_UP;
  s_htim4.Init.Period = period;
  s_htim4.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  s_htim4.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  HAL_TIM_PWM_Init(&s_htim4);

  TIM_OC_InitTypeDef oc = {0};
  oc.OCMode = TIM_OCMODE_PWM1;
  oc.Pulse = 0;
  oc.OCPolarity = TIM_OCPOLARITY_HIGH;
  oc.OCFastMode = TIM_OCFAST_DISABLE;
  HAL_TIM_PWM_ConfigChannel(&s_htim4, &oc, TIM_CHANNEL_4);
  __HAL_TIM_ENABLE_OCxPRELOAD(&s_htim4, TIM_CHANNEL_4);
  HAL_TIM_PWM_Start(&s_htim4, TIM_CHANNEL_4);
  s_brake_arr = period;
  ipm15_set_brake_pwm(0.0f);
#else
  gpio_out_init(BRAKE_PWM_PORT, BRAKE_PWM_PIN);
  HAL_GPIO_WritePin(BRAKE_PWM_PORT, BRAKE_PWM_PIN, GPIO_PIN_RESET);
#endif
}

void ipm15_set_pfc_sync(bool on) {
  bool active = on ? true : false;
  GPIO_PinState st = (active == (PFC_SYNC_ACTIVE_STATE != 0)) ? GPIO_PIN_SET : GPIO_PIN_RESET;
  HAL_GPIO_WritePin(PFC_SYNC_PORT, PFC_SYNC_PIN, st);
}

void ipm15_set_precharge_relay(bool on) {
#if USE_PRECHARGE_RELAY
  bool active = on ? true : false;
  GPIO_PinState st = (active == (PRECHARGE_RELAY_ACTIVE_STATE != 0)) ? GPIO_PIN_SET : GPIO_PIN_RESET;
  HAL_GPIO_WritePin(PRECHARGE_RELAY_PORT, PRECHARGE_RELAY_PIN, st);
#else
  (void)on;
#endif
}

bool ipm15_precharge_relay_pin_active(void) {
#if USE_PRECHARGE_RELAY
  const GPIO_PinState state = HAL_GPIO_ReadPin(PRECHARGE_RELAY_PORT, PRECHARGE_RELAY_PIN);
  return (state == GPIO_PIN_SET) == (PRECHARGE_RELAY_ACTIVE_STATE != 0);
#else
  return false;
#endif
}

void ipm15_set_brake_pwm(float duty) {
#if USE_BRAKE_PWM
  if (duty < 0.0f) duty = 0.0f;
  if (duty > 1.0f) duty = 1.0f;
  uint32_t ccr = (uint32_t)((s_brake_arr + 1U) * duty);
  __HAL_TIM_SET_COMPARE(&s_htim4, TIM_CHANNEL_4, ccr);
#else
  (void)duty;
#endif
}

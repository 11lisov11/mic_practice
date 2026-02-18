#include "pwm_tim1.h"

#include "config.h"
#include "stm32f1xx_hal.h"

TIM_HandleTypeDef htim1;
static uint32_t s_pwm_arr = 0;

static uint32_t timer_clock_hz(void) {
  uint32_t pclk = HAL_RCC_GetPCLK2Freq();
  if ((RCC->CFGR & RCC_CFGR_PPRE2) != RCC_CFGR_PPRE2_DIV1) {
    pclk *= 2U;
  }
  return pclk;
}

static uint32_t clamp_percent(uint32_t pct) {
  if (pct < PWM_MIN_PERCENT) return PWM_MIN_PERCENT;
  if (pct > PWM_MAX_PERCENT) return PWM_MAX_PERCENT;
  return pct;
}

static uint32_t q15_to_ccr(uint16_t q15) {
  uint32_t pct = (uint32_t)q15 * 100U / 32767U;
  pct = clamp_percent(pct);
  return (s_pwm_arr + 1U) * pct / 100U;
}

void pwm_tim1_init(void) {
  __HAL_RCC_TIM1_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_AFIO_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {0};
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;

  gpio.Pin = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10;
  HAL_GPIO_Init(GPIOA, &gpio);

  gpio.Pin = GPIO_PIN_13 | GPIO_PIN_14 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOB, &gpio);

  uint32_t tim_clk = timer_clock_hz();
  uint32_t period = (tim_clk / PWM_FREQ_HZ);
  if (period > 0) {
    period -= 1U;
  }

  htim1.Instance = TIM1;
  htim1.Init.Prescaler = 0;
  htim1.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim1.Init.Period = period;
  htim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim1.Init.RepetitionCounter = 0;
  htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  HAL_TIM_PWM_Init(&htim1);

  TIM_OC_InitTypeDef oc = {0};
  oc.OCMode = TIM_OCMODE_PWM1;
  oc.Pulse = 0;
  oc.OCPolarity = TIM_OCPOLARITY_HIGH;
  oc.OCNPolarity = TIM_OCNPOLARITY_HIGH;
  oc.OCFastMode = TIM_OCFAST_DISABLE;
  oc.OCIdleState = TIM_OCIDLESTATE_RESET;
  oc.OCNIdleState = TIM_OCNIDLESTATE_RESET;

  HAL_TIM_PWM_ConfigChannel(&htim1, &oc, TIM_CHANNEL_1);
  HAL_TIM_PWM_ConfigChannel(&htim1, &oc, TIM_CHANNEL_2);
  HAL_TIM_PWM_ConfigChannel(&htim1, &oc, TIM_CHANNEL_3);

  __HAL_TIM_ENABLE_OCxPRELOAD(&htim1, TIM_CHANNEL_1);
  __HAL_TIM_ENABLE_OCxPRELOAD(&htim1, TIM_CHANNEL_2);
  __HAL_TIM_ENABLE_OCxPRELOAD(&htim1, TIM_CHANNEL_3);

  TIM_MasterConfigTypeDef master = {0};
  master.MasterOutputTrigger = TIM_TRGO_UPDATE;
  master.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  HAL_TIMEx_MasterConfigSynchronization(&htim1, &master);

  TIM_BreakDeadTimeConfigTypeDef bd = {0};
  bd.OffStateRunMode = TIM_OSSR_DISABLE;
  bd.OffStateIDLEMode = TIM_OSSI_DISABLE;
  bd.LockLevel = TIM_LOCKLEVEL_OFF;
  bd.BreakState = USE_TIM1_BKIN ? TIM_BREAK_ENABLE : TIM_BREAK_DISABLE;
  if (USE_TIM1_BKIN) {
#if BKIN_ACTIVE_LOW
    bd.BreakPolarity = TIM_BREAKPOLARITY_LOW;
#else
    bd.BreakPolarity = TIM_BREAKPOLARITY_HIGH;
#endif
  } else {
    bd.BreakPolarity = TIM_BREAKPOLARITY_HIGH;
  }
  bd.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;

  uint32_t dt_ticks = (PWM_DEADTIME_NS * tim_clk + 999999999UL) / 1000000000UL;
  if (dt_ticks > 127U) {
    dt_ticks = 127U;
  }
  bd.DeadTime = (uint8_t)dt_ticks;
  HAL_TIMEx_ConfigBreakDeadTime(&htim1, &bd);

  HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);
  HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_2);
  HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_3);
  HAL_TIMEx_PWMN_Start(&htim1, TIM_CHANNEL_1);
  HAL_TIMEx_PWMN_Start(&htim1, TIM_CHANNEL_2);
  HAL_TIMEx_PWMN_Start(&htim1, TIM_CHANNEL_3);

  s_pwm_arr = period;
  pwm_all_off();
  pwm_outputs_enable(false);
}

void pwm_outputs_enable(bool enable) {
  if (enable) {
    __HAL_TIM_MOE_ENABLE(&htim1);
  } else {
    __HAL_TIM_MOE_DISABLE(&htim1);
  }
}

void pwm_set_duty_q15(uint16_t du, uint16_t dv, uint16_t dw) {
  __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, q15_to_ccr(du));
  __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, q15_to_ccr(dv));
  __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, q15_to_ccr(dw));
}

void pwm_apply_diag(void) {
  uint32_t c1 = (s_pwm_arr + 1U) * 10U / 100U;
  uint32_t c2 = (s_pwm_arr + 1U) * 20U / 100U;
  uint32_t c3 = (s_pwm_arr + 1U) * 30U / 100U;
  __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, c1);
  __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, c2);
  __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, c3);
}

void pwm_all_off(void) {
  __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, 0);
  __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 0);
  __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, 0);
}

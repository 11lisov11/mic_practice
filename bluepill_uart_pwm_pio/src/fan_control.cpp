#include "fan_control.h"

#include "config.h"
#include "stm32f1xx_hal.h"

#if USE_FAN_PWM
static TIM_HandleTypeDef s_htim2;
static uint32_t s_fan_arr = 0;
static uint16_t s_fan_duty_q15 = 0;
#endif

#if USE_FAN_TACH
static bool s_tach_prev_level = true;
static bool s_tach_prev_valid = false;
static uint32_t s_tach_edges = 0;
static uint32_t s_tach_last_sample_ms = 0;
static uint16_t s_tach_rpm = 0;
#endif

#if USE_FAN_PWM
static uint32_t timer2_clock_hz(void) {
  uint32_t pclk = HAL_RCC_GetPCLK1Freq();
  if ((RCC->CFGR & RCC_CFGR_PPRE1) != RCC_CFGR_PPRE1_DIV1) {
    pclk *= 2U;
  }
  return pclk;
}
#endif

static void enable_gpio_clk(GPIO_TypeDef *port) {
  if (port == GPIOA) __HAL_RCC_GPIOA_CLK_ENABLE();
  if (port == GPIOB) __HAL_RCC_GPIOB_CLK_ENABLE();
  if (port == GPIOC) __HAL_RCC_GPIOC_CLK_ENABLE();
}

void fan_control_init(void) {
#if USE_FAN_PWM
  enable_gpio_clk(FAN_PWM_PORT);
  __HAL_RCC_AFIO_CLK_ENABLE();
  __HAL_RCC_TIM2_CLK_ENABLE();

#if defined(__HAL_AFIO_REMAP_TIM2_PARTIAL_1)
  // TIM2_CH2 moves to PB3. PB3 is also JTAG JTDO; re-assert SWJ_NOJTAG
  // after the TIM2 remap so later AFIO writes cannot re-capture PB3/PB4.
  __HAL_AFIO_REMAP_TIM2_PARTIAL_1();
  __HAL_AFIO_REMAP_SWJ_NOJTAG();
#endif

  GPIO_InitTypeDef pwm = {0};
  pwm.Pin = FAN_PWM_PIN;
  pwm.Mode = GPIO_MODE_AF_PP;
  pwm.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(FAN_PWM_PORT, &pwm);

  uint32_t tim_clk = timer2_clock_hz();
  uint32_t period = tim_clk / FAN_PWM_FREQ_HZ;
  if (period > 0U) period -= 1U;

  s_htim2.Instance = TIM2;
  s_htim2.Init.Prescaler = 0;
  s_htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  s_htim2.Init.Period = period;
  s_htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  s_htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  HAL_TIM_PWM_Init(&s_htim2);

  TIM_OC_InitTypeDef oc = {0};
  oc.OCMode = TIM_OCMODE_PWM1;
  oc.Pulse = 0;
  oc.OCPolarity = FAN_PWM_ACTIVE_HIGH ? TIM_OCPOLARITY_HIGH : TIM_OCPOLARITY_LOW;
  oc.OCFastMode = TIM_OCFAST_DISABLE;
  HAL_TIM_PWM_ConfigChannel(&s_htim2, &oc, TIM_CHANNEL_2);
  __HAL_TIM_ENABLE_OCxPRELOAD(&s_htim2, TIM_CHANNEL_2);
  HAL_TIM_PWM_Start(&s_htim2, TIM_CHANNEL_2);
  s_fan_arr = period;
  fan_control_set_pwm_q15(0);
#else
  // Do not drive the unfinished fan stage while control is disabled.
  enable_gpio_clk(FAN_PWM_PORT);
  GPIO_InitTypeDef pwm = {0};
  pwm.Pin = FAN_PWM_PIN;
  pwm.Mode = GPIO_MODE_ANALOG;
  HAL_GPIO_Init(FAN_PWM_PORT, &pwm);
#endif

#if USE_FAN_TACH
  enable_gpio_clk(FAN_TACH_PORT);
  GPIO_InitTypeDef tach = {0};
  tach.Pin = FAN_TACH_PIN;
  tach.Mode = GPIO_MODE_INPUT;
  tach.Pull = FAN_TACH_PULL;
  HAL_GPIO_Init(FAN_TACH_PORT, &tach);
  s_tach_prev_level = HAL_GPIO_ReadPin(FAN_TACH_PORT, FAN_TACH_PIN) == GPIO_PIN_SET;
  s_tach_prev_valid = true;
  s_tach_last_sample_ms = HAL_GetTick();
#else
  enable_gpio_clk(FAN_TACH_PORT);
  GPIO_InitTypeDef tach = {0};
  tach.Pin = FAN_TACH_PIN;
  tach.Mode = GPIO_MODE_ANALOG;
  HAL_GPIO_Init(FAN_TACH_PORT, &tach);
#endif
}

void fan_control_tick(void) {
#if USE_FAN_TACH
  const bool level = HAL_GPIO_ReadPin(FAN_TACH_PORT, FAN_TACH_PIN) == GPIO_PIN_SET;
  if (!s_tach_prev_valid) {
    s_tach_prev_level = level;
    s_tach_prev_valid = true;
  } else if (s_tach_prev_level && !level) {
    s_tach_edges++;
  }
  s_tach_prev_level = level;

  const uint32_t now = HAL_GetTick();
  const uint32_t dt_ms = now - s_tach_last_sample_ms;
  if (dt_ms >= FAN_TACH_SAMPLE_MS) {
    uint32_t rpm = 0;
    if (FAN_TACH_PULSES_PER_REV > 0U && dt_ms > 0U) {
      rpm = (s_tach_edges * 60000U) / ((uint32_t)FAN_TACH_PULSES_PER_REV * dt_ms);
    }
    if (rpm > 65535U) rpm = 65535U;
    s_tach_rpm = (uint16_t)rpm;
    s_tach_edges = 0;
    s_tach_last_sample_ms = now;
  }
#endif
}

void fan_control_set_pwm_q15(uint16_t duty_q15) {
#if USE_FAN_PWM
  if (duty_q15 > 32767U) duty_q15 = 32767U;
  s_fan_duty_q15 = duty_q15;
  uint32_t ccr = ((s_fan_arr + 1U) * (uint32_t)duty_q15) / 32767U;
  __HAL_TIM_SET_COMPARE(&s_htim2, TIM_CHANNEL_2, ccr);
#else
  (void)duty_q15;
#endif
}

uint16_t fan_control_duty_q15(void) {
#if USE_FAN_PWM
  return s_fan_duty_q15;
#else
  return 0;
#endif
}

uint16_t fan_control_rpm(void) {
#if USE_FAN_TACH
  return s_tach_rpm;
#else
  return 0;
#endif
}

uint8_t fan_control_reply_duty_q8(void) {
  return (uint8_t)(((uint32_t)fan_control_duty_q15() * 255U) / 32767U);
}

uint8_t fan_control_reply_tach_x30(void) {
  uint32_t v = (uint32_t)fan_control_rpm() / FAN_TACH_RPM_REPLY_STEP;
  if (v > 255U) v = 255U;
  return (uint8_t)v;
}

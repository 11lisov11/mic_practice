#include "motor_backend.h"

#include <string.h>

#include "config.h"
#include "motor_bench_policy.h"
#include "motor_pwm_math.h"
#include "proto.h"
#include "stm32g4xx_hal.h"

#if MIC_MOTOR_BACKEND_PWM_BENCH

static TIM_HandleTypeDef s_tim1;
static ADC_HandleTypeDef s_adc1;
static motor_backend_status_t s_status;
static uint32_t s_pwm_arr;
static uint32_t s_last_adc_ms;
static bool s_adc_ready;

static constexpr uint32_t PWM_CCER_ENABLE_MASK =
    TIM_CCER_CC1E | TIM_CCER_CC1NE | TIM_CCER_CC2E |
    TIM_CCER_CC2NE | TIM_CCER_CC3E | TIM_CCER_CC3NE;

static void em_stop_assert(void) {
  HAL_GPIO_WritePin(MOTOR_EM_STOP_PORT, MOTOR_EM_STOP_PIN, MOTOR_EM_STOP_SAFE_STATE);
}

static void pwm_gpio_force_low(void) {
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10,
                    GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0 | GPIO_PIN_1, GPIO_PIN_RESET);

  GPIO_InitTypeDef gpio = {};
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_PULLDOWN;
  gpio.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  gpio.Pin = GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10;
  HAL_GPIO_Init(GPIOA, &gpio);
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1;
  HAL_GPIO_Init(GPIOB, &gpio);

  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10,
                    GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0 | GPIO_PIN_1, GPIO_PIN_RESET);
}

static void pwm_gpio_config_af(void) {
  GPIO_InitTypeDef gpio = {};
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_PULLDOWN;
  gpio.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  gpio.Alternate = GPIO_AF6_TIM1;
  gpio.Pin = GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10;
  HAL_GPIO_Init(GPIOA, &gpio);
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1;
  HAL_GPIO_Init(GPIOB, &gpio);
}

static void pwm_peripheral_stop(void) {
  __HAL_TIM_MOE_DISABLE(&s_tim1);
  TIM1->CCER &= ~PWM_CCER_ENABLE_MASK;
  __HAL_TIM_DISABLE(&s_tim1);
}

static bool timer_init(void) {
  __HAL_RCC_TIM1_CLK_ENABLE();
  pwm_peripheral_stop();
  pwm_gpio_force_low();

  s_pwm_arr = motor_pwm_center_aligned_arr(HAL_RCC_GetPCLK2Freq(), MOTOR_BENCH_PWM_FREQ_HZ);
  if (s_pwm_arr == 0U) {
    return false;
  }

  s_tim1.Instance = TIM1;
  s_tim1.Init.Prescaler = 0U;
  s_tim1.Init.CounterMode = TIM_COUNTERMODE_CENTERALIGNED1;
  s_tim1.Init.Period = s_pwm_arr;
  s_tim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  s_tim1.Init.RepetitionCounter = 0U;
  s_tim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  if (HAL_TIM_PWM_Init(&s_tim1) != HAL_OK) {
    return false;
  }

  TIM_OC_InitTypeDef oc = {};
  oc.OCMode = TIM_OCMODE_PWM1;
  oc.Pulse = motor_pwm_q15_to_compare(MOTOR_BENCH_DUTY_Q15, s_pwm_arr);
  oc.OCPolarity = TIM_OCPOLARITY_HIGH;
  oc.OCNPolarity = TIM_OCNPOLARITY_HIGH;
  oc.OCFastMode = TIM_OCFAST_DISABLE;
  oc.OCIdleState = TIM_OCIDLESTATE_RESET;
  oc.OCNIdleState = TIM_OCNIDLESTATE_RESET;
  if (HAL_TIM_PWM_ConfigChannel(&s_tim1, &oc, TIM_CHANNEL_1) != HAL_OK ||
      HAL_TIM_PWM_ConfigChannel(&s_tim1, &oc, TIM_CHANNEL_2) != HAL_OK ||
      HAL_TIM_PWM_ConfigChannel(&s_tim1, &oc, TIM_CHANNEL_3) != HAL_OK) {
    return false;
  }

  TIM_BreakDeadTimeConfigTypeDef bd = {};
  bd.OffStateRunMode = TIM_OSSR_DISABLE;
  bd.OffStateIDLEMode = TIM_OSSI_DISABLE;
  bd.LockLevel = TIM_LOCKLEVEL_OFF;
  const uint64_t requested_ticks =
      ((uint64_t)MOTOR_BENCH_DEADTIME_NS * HAL_RCC_GetPCLK2Freq() + 999999999ULL) /
      1000000000ULL;
  bd.DeadTime = motor_pwm_encode_deadtime_ticks((uint32_t)requested_ticks);
  bd.BreakState = TIM_BREAK_DISABLE;
  bd.BreakPolarity = TIM_BREAKPOLARITY_LOW;
  bd.BreakFilter = 0U;
  bd.BreakAFMode = TIM_BREAK_AFMODE_INPUT;
  bd.Break2State = TIM_BREAK2_DISABLE;
  bd.Break2Polarity = TIM_BREAK2POLARITY_LOW;
  bd.Break2Filter = 0U;
  bd.Break2AFMode = TIM_BREAK2_AFMODE_INPUT;
  bd.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;
  if (HAL_TIMEx_ConfigBreakDeadTime(&s_tim1, &bd) != HAL_OK) {
    return false;
  }

  TIM1->CCER &= ~PWM_CCER_ENABLE_MASK;
  __HAL_TIM_MOE_DISABLE(&s_tim1);
  return true;
}

static bool adc_add_channel(uint32_t channel, uint32_t rank) {
  ADC_ChannelConfTypeDef cfg = {};
  cfg.Channel = channel;
  cfg.Rank = rank;
  cfg.SamplingTime = ADC_SAMPLETIME_47CYCLES_5;
  cfg.SingleDiff = ADC_SINGLE_ENDED;
  cfg.OffsetNumber = ADC_OFFSET_NONE;
  cfg.Offset = 0U;
  return HAL_ADC_ConfigChannel(&s_adc1, &cfg) == HAL_OK;
}

static bool adc_init(void) {
  __HAL_RCC_ADC12_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {};
  gpio.Mode = GPIO_MODE_ANALOG;
  gpio.Pull = GPIO_NOPULL;
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1;
  HAL_GPIO_Init(GPIOA, &gpio);
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2;
  HAL_GPIO_Init(GPIOC, &gpio);

  s_adc1.Instance = ADC1;
  s_adc1.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;
  s_adc1.Init.Resolution = ADC_RESOLUTION_12B;
  s_adc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  s_adc1.Init.GainCompensation = 0U;
  s_adc1.Init.ScanConvMode = ADC_SCAN_ENABLE;
  s_adc1.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  s_adc1.Init.LowPowerAutoWait = DISABLE;
  s_adc1.Init.ContinuousConvMode = DISABLE;
  s_adc1.Init.NbrOfConversion = 5U;
  s_adc1.Init.DiscontinuousConvMode = DISABLE;
  s_adc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  s_adc1.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
  s_adc1.Init.DMAContinuousRequests = DISABLE;
  s_adc1.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
  s_adc1.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&s_adc1) != HAL_OK) {
    return false;
  }
  if (!adc_add_channel(ADC_CHANNEL_1, ADC_REGULAR_RANK_1) ||
      !adc_add_channel(ADC_CHANNEL_7, ADC_REGULAR_RANK_2) ||
      !adc_add_channel(ADC_CHANNEL_6, ADC_REGULAR_RANK_3) ||
      !adc_add_channel(ADC_CHANNEL_2, ADC_REGULAR_RANK_4) ||
      !adc_add_channel(ADC_CHANNEL_8, ADC_REGULAR_RANK_5)) {
    return false;
  }
  return HAL_ADCEx_Calibration_Start(&s_adc1, ADC_SINGLE_ENDED) == HAL_OK;
}

static void adc_sample(void) {
  uint16_t values[5] = {};
  if (HAL_ADC_Start(&s_adc1) != HAL_OK) {
    return;
  }
  for (uint32_t i = 0U; i < 5U; ++i) {
    if (HAL_ADC_PollForConversion(&s_adc1, 1U) != HAL_OK) {
      (void)HAL_ADC_Stop(&s_adc1);
      return;
    }
    values[i] = (uint16_t)HAL_ADC_GetValue(&s_adc1);
  }
  (void)HAL_ADC_Stop(&s_adc1);
  s_status.phase_a_raw = values[0];
  s_status.phase_b_raw = values[1];
  s_status.phase_c_raw = values[2];
  s_status.vbus_raw = values[3];
  s_status.temperature_raw = values[4];
}

void motor_backend_init(void) {
  memset(&s_status, 0, sizeof(s_status));
  __HAL_RCC_GPIOA_CLK_ENABLE();
  HAL_GPIO_WritePin(MOTOR_EM_STOP_PORT, MOTOR_EM_STOP_PIN, MOTOR_EM_STOP_SAFE_STATE);
  GPIO_InitTypeDef em_stop = {};
  em_stop.Pin = MOTOR_EM_STOP_PIN;
  em_stop.Mode = GPIO_MODE_OUTPUT_PP;
  em_stop.Pull = GPIO_PULLDOWN;
  em_stop.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(MOTOR_EM_STOP_PORT, &em_stop);
  em_stop_assert();

  const bool timer_ready = timer_init();
  s_adc_ready = adc_init();
  s_status.ready = timer_ready && s_adc_ready;
  s_status.fault_code = s_status.ready ? FAULT_OK : FAULT_INTERNAL;
  motor_backend_force_stop();
}

void motor_backend_tick(void) {
  em_stop_assert();
  const uint32_t now_ms = HAL_GetTick();
  if (s_adc_ready && (uint32_t)(now_ms - s_last_adc_ms) >= MOTOR_BENCH_ADC_SAMPLE_MS) {
    s_last_adc_ms = now_ms;
    adc_sample();
  }
}

void motor_backend_force_stop(void) {
  pwm_peripheral_stop();
  pwm_gpio_force_low();
  em_stop_assert();
  s_status.enabled = false;
  s_status.pwm_active = false;
  s_status.shutdown_released = false;
}

bool motor_backend_clear_fault(void) {
  motor_backend_force_stop();
  if (!s_status.ready) {
    s_status.fault_code = FAULT_INTERNAL;
    return false;
  }
  s_status.fault_code = FAULT_OK;
  return true;
}

bool motor_backend_apply_command(const uint8_t *cmd, uint8_t *fault_code) {
  if (!motor_bench_command_allowed(cmd, s_status.ready)) {
    motor_backend_force_stop();
    s_status.fault_code = FAULT_INTERNAL;
    if (fault_code != nullptr) *fault_code = FAULT_INTERNAL;
    return false;
  }

  const uint32_t compare = motor_pwm_q15_to_compare(MOTOR_BENCH_DUTY_Q15, s_pwm_arr);
  __HAL_TIM_SET_COMPARE(&s_tim1, TIM_CHANNEL_1, compare);
  __HAL_TIM_SET_COMPARE(&s_tim1, TIM_CHANNEL_2, compare);
  __HAL_TIM_SET_COMPARE(&s_tim1, TIM_CHANNEL_3, compare);
  TIM1->EGR = TIM_EGR_UG;
  pwm_gpio_config_af();
  __HAL_TIM_ENABLE(&s_tim1);
  TIM1->CCER |= PWM_CCER_ENABLE_MASK;
  __HAL_TIM_MOE_ENABLE(&s_tim1);

  em_stop_assert();
  s_status.enabled = true;
  s_status.pwm_active = true;
  s_status.shutdown_released = false;
  s_status.fault_code = FAULT_OK;
  if (fault_code != nullptr) *fault_code = FAULT_OK;
  return true;
}

void motor_backend_get_status(motor_backend_status_t *status) {
  if (status != nullptr) {
    *status = s_status;
  }
}

#endif

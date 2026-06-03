#include "adc_currents.h"

#include <math.h>

#include "config.h"
#include "stm32f1xx_hal.h"

static ADC_HandleTypeDef s_hadc1;
static volatile uint16_t s_raw_ia = 0;
static volatile uint16_t s_raw_ib = 0;
static volatile uint16_t s_raw_ic = 0;
static volatile uint16_t s_raw_vbus = 0;
static volatile uint16_t s_raw_heatsink = 0;
static volatile bool s_heatsink_valid = false;
static volatile uint16_t s_raw_phase_a = 0;
static volatile uint16_t s_raw_phase_b = 0;
static volatile uint16_t s_raw_phase_c_virtual = PHASE_MEAS_CENTER_RAW;
static volatile bool s_phase_measure_valid = false;

static uint16_t s_off_ia = 2048;
static uint16_t s_off_ib = 2048;
static uint16_t s_off_ic = 2048;

static uint32_t adc_vbus_channel(void) {
#if LINK_USE_SPI
  return ADC_CHANNEL_3; // VBUS PA3
#else
  return ADC_CHANNEL_5; // VBUS PA5
#endif
}

static uint16_t clamp_adc_raw_i32(int32_t value) {
  if (value < 0) return 0;
  if (value > 4095) return 4095;
  return (uint16_t)value;
}

static bool adc_sample_regular(uint32_t channel, uint32_t sample_time, uint16_t *raw) {
  ADC_ChannelConfTypeDef cfg = {0};
  cfg.Channel = channel;
  cfg.Rank = ADC_REGULAR_RANK_1;
  cfg.SamplingTime = sample_time;

  if (HAL_ADC_ConfigChannel(&s_hadc1, &cfg) != HAL_OK) {
    return false;
  }
  if (HAL_ADC_Start(&s_hadc1) != HAL_OK) {
    return false;
  }
  if (HAL_ADC_PollForConversion(&s_hadc1, 2) != HAL_OK) {
    HAL_ADC_Stop(&s_hadc1);
    return false;
  }
  const uint16_t value = (uint16_t)HAL_ADC_GetValue(&s_hadc1);
  HAL_ADC_Stop(&s_hadc1);
  if (raw) {
    *raw = value;
  }
  return true;
}

static void adc_gpio_init(void) {
  __HAL_RCC_GPIOA_CLK_ENABLE();
#if USE_PHASE_MEAS || USE_HEATSINK_TEMP
  __HAL_RCC_GPIOB_CLK_ENABLE();
#endif
  GPIO_InitTypeDef gpio = {0};
  gpio.Mode = GPIO_MODE_ANALOG;
#if LINK_USE_SPI
  // SPI1 uses PA4..PA7 so keep them digital.
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_3;
#else
  // UART uses PA2/PA3 so keep them digital.
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_4 | GPIO_PIN_5;
#endif
#if USE_PHASE_MEAS
  gpio.Pin |= PHASE_MEAS_A_PIN | PHASE_MEAS_B_PIN;
#endif
  HAL_GPIO_Init(GPIOA, &gpio);
#if USE_PHASE_MEAS
#if !USE_HEATSINK_TEMP
  gpio.Pin = PHASE_MEAS_C_PIN;
  HAL_GPIO_Init(GPIOB, &gpio);
#endif
#endif
#if USE_HEATSINK_TEMP
  gpio.Pin = HEATSINK_TEMP_PIN;
  HAL_GPIO_Init(HEATSINK_TEMP_PORT, &gpio);
#endif
}

static void adc_injected_config(uint32_t trigger) {
  ADC_InjectionConfTypeDef inj = {0};
  inj.InjectedSamplingTime = ADC_SAMPLETIME_28CYCLES_5;
  inj.InjectedNbrOfConversion = 4;
  inj.AutoInjectedConv = DISABLE;
  inj.InjectedDiscontinuousConvMode = DISABLE;
  inj.ExternalTrigInjecConv = trigger;
  inj.InjectedOffset = 0;

  inj.InjectedRank = ADC_INJECTED_RANK_1;
  inj.InjectedChannel = ADC_CHANNEL_0; // IA PA0
  HAL_ADCEx_InjectedConfigChannel(&s_hadc1, &inj);

  inj.InjectedRank = ADC_INJECTED_RANK_2;
  inj.InjectedChannel = ADC_CHANNEL_1; // IB PA1
  HAL_ADCEx_InjectedConfigChannel(&s_hadc1, &inj);

  inj.InjectedRank = ADC_INJECTED_RANK_3;
#if LINK_USE_SPI
  inj.InjectedChannel = ADC_CHANNEL_2; // IC PA2
#else
  inj.InjectedChannel = ADC_CHANNEL_4; // IC PA4
#endif
  HAL_ADCEx_InjectedConfigChannel(&s_hadc1, &inj);

  inj.InjectedRank = ADC_INJECTED_RANK_4;
  inj.InjectedChannel = adc_vbus_channel();
  HAL_ADCEx_InjectedConfigChannel(&s_hadc1, &inj);
}

static void adc_calibrate_offsets(uint16_t samples) {
  uint32_t sum_a = 0;
  uint32_t sum_b = 0;
  uint32_t sum_c = 0;

  adc_injected_config(ADC_INJECTED_SOFTWARE_START);
  for (uint16_t i = 0; i < samples; ++i) {
    HAL_ADCEx_InjectedStart(&s_hadc1);
    HAL_ADCEx_InjectedPollForConversion(&s_hadc1, 10);
    sum_a += HAL_ADCEx_InjectedGetValue(&s_hadc1, ADC_INJECTED_RANK_1);
    sum_b += HAL_ADCEx_InjectedGetValue(&s_hadc1, ADC_INJECTED_RANK_2);
    sum_c += HAL_ADCEx_InjectedGetValue(&s_hadc1, ADC_INJECTED_RANK_3);
  }

  s_off_ia = (uint16_t)(sum_a / samples);
  s_off_ib = (uint16_t)(sum_b / samples);
  s_off_ic = (uint16_t)(sum_c / samples);
}

void adc_currents_init(void) {
  __HAL_RCC_ADC1_CLK_ENABLE();
  adc_gpio_init();

  s_hadc1.Instance = ADC1;
  s_hadc1.Init.ScanConvMode = ADC_SCAN_ENABLE;
  s_hadc1.Init.ContinuousConvMode = DISABLE;
  s_hadc1.Init.DiscontinuousConvMode = DISABLE;
  s_hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  s_hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  s_hadc1.Init.NbrOfConversion = 1;
  HAL_ADC_Init(&s_hadc1);

  HAL_ADCEx_Calibration_Start(&s_hadc1);
  adc_calibrate_offsets(ADC_CALIB_SAMPLES);

  adc_injected_config(ADC_EXTERNALTRIGINJECCONV_T1_TRGO);
  HAL_ADCEx_InjectedStart_IT(&s_hadc1);
}

extern "C" void HAL_ADCEx_InjectedConvCpltCallback(ADC_HandleTypeDef *hadc) {
  if (hadc->Instance != ADC1) return;
  s_raw_ia = HAL_ADCEx_InjectedGetValue(hadc, ADC_INJECTED_RANK_1);
  s_raw_ib = HAL_ADCEx_InjectedGetValue(hadc, ADC_INJECTED_RANK_2);
  s_raw_ic = HAL_ADCEx_InjectedGetValue(hadc, ADC_INJECTED_RANK_3);
  s_raw_vbus = HAL_ADCEx_InjectedGetValue(hadc, ADC_INJECTED_RANK_4);
}

void adc_currents_get(float *ia, float *ib, float *ic, float *vbus) {
  uint16_t a = s_raw_ia;
  uint16_t b = s_raw_ib;
  uint16_t c = s_raw_ic;
  uint16_t v = s_raw_vbus;

  float fa = ((int32_t)a - (int32_t)s_off_ia) * ADC_I_SCALE;
  float fb = ((int32_t)b - (int32_t)s_off_ib) * ADC_I_SCALE;
  float fc = ((int32_t)c - (int32_t)s_off_ic) * ADC_I_SCALE;
  float fv = (float)v * ADC_VBUS_SCALE;

  if (ia) *ia = fa;
  if (ib) *ib = fb;
  if (ic) *ic = fc;
  if (vbus) *vbus = fv;
}

uint16_t adc_vbus_raw(void) {
  return s_raw_vbus;
}

bool adc_vbus_sample_software(uint16_t *raw) {
  uint16_t value = 0;
  if (!adc_sample_regular(adc_vbus_channel(), ADC_SAMPLETIME_28CYCLES_5, &value)) {
    return false;
  }
  s_raw_vbus = value;
  if (raw) {
    *raw = value;
  }
  return true;
}

bool adc_heatsink_sample_software(uint16_t *raw) {
#if USE_HEATSINK_TEMP
  uint16_t value = 0;
  if (!adc_sample_regular(HEATSINK_TEMP_ADC_CHANNEL, ADC_SAMPLETIME_239CYCLES_5, &value)) {
    s_heatsink_valid = false;
    return false;
  }
  s_raw_heatsink = value;
  s_heatsink_valid = true;
  if (raw) {
    *raw = value;
  }
  return true;
#else
  if (raw) {
    *raw = 0;
  }
  return false;
#endif
}

uint16_t adc_heatsink_raw(void) {
  return s_raw_heatsink;
}

bool adc_heatsink_get(float *voltage, float *temp_c) {
#if USE_HEATSINK_TEMP
  if (!s_heatsink_valid) {
    return false;
  }
  const uint16_t raw = s_raw_heatsink;
  const float v = ((float)raw * HEATSINK_TEMP_VREF) / 4095.0f;
  if (voltage) {
    *voltage = v;
  }

  if (temp_c) {
    *temp_c = 0.0f;
    if (raw == 0U || raw >= 4095U || v <= 0.001f || v >= (HEATSINK_TEMP_VREF - 0.001f)) {
      return false;
    }
    const float r_ntc = HEATSINK_TEMP_PULLUP_OHM * v / (HEATSINK_TEMP_VREF - v);
    if (r_ntc <= 0.0f || !isfinite(r_ntc)) {
      return false;
    }
    const float t25_k = 298.15f;
    const float inv_t = (1.0f / t25_k) + (logf(r_ntc / HEATSINK_TEMP_NTC_R25_OHM) / HEATSINK_TEMP_NTC_BETA_K);
    if (inv_t <= 0.0f || !isfinite(inv_t)) {
      return false;
    }
    *temp_c = (1.0f / inv_t) - 273.15f;
  }
  return true;
#else
  if (voltage) {
    *voltage = 0.0f;
  }
  if (temp_c) {
    *temp_c = 0.0f;
  }
  return false;
#endif
}

bool adc_heatsink_fault_active(void) {
#if USE_HEATSINK_TEMP && HEATSINK_TEMP_PROTECTION_ENABLE
  if (!s_heatsink_valid) {
    return false;
  }
  const uint16_t raw = s_raw_heatsink;
  if (raw >= HEATSINK_TEMP_OPEN_RAW) {
    return true;
  }
  float temp_c = 0.0f;
  if (!adc_heatsink_get(nullptr, &temp_c)) {
    return false;
  }
  return temp_c >= HEATSINK_TEMP_TRIP_C;
#else
  return false;
#endif
}

bool adc_phase_measure_sample_software(uint16_t *raw_a, uint16_t *raw_b, uint16_t *raw_c_virtual) {
#if USE_PHASE_MEAS
  uint16_t a = 0;
  uint16_t b = 0;
  if (!adc_sample_regular(ADC_CHANNEL_6, ADC_SAMPLETIME_239CYCLES_5, &a)) {
    s_phase_measure_valid = false;
    return false;
  }
  if (!adc_sample_regular(ADC_CHANNEL_7, ADC_SAMPLETIME_239CYCLES_5, &b)) {
    s_phase_measure_valid = false;
    return false;
  }
  const int32_t c = (3L * (int32_t)PHASE_MEAS_CENTER_RAW) - (int32_t)a - (int32_t)b;
  const uint16_t c_virtual = clamp_adc_raw_i32(c);

  s_raw_phase_a = a;
  s_raw_phase_b = b;
  s_raw_phase_c_virtual = c_virtual;
  s_phase_measure_valid = true;

  if (raw_a) *raw_a = a;
  if (raw_b) *raw_b = b;
  if (raw_c_virtual) *raw_c_virtual = c_virtual;
  return true;
#else
  if (raw_a) *raw_a = 0;
  if (raw_b) *raw_b = 0;
  if (raw_c_virtual) *raw_c_virtual = PHASE_MEAS_CENTER_RAW;
  return false;
#endif
}

void adc_phase_measure_raw(uint16_t *raw_a, uint16_t *raw_b, uint16_t *raw_c_virtual) {
  if (raw_a) *raw_a = s_raw_phase_a;
  if (raw_b) *raw_b = s_raw_phase_b;
  if (raw_c_virtual) *raw_c_virtual = s_raw_phase_c_virtual;
}

bool adc_phase_measure_valid(void) {
  return s_phase_measure_valid;
}

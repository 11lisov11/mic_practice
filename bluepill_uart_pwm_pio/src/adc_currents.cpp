#include "adc_currents.h"

#include "config.h"
#include "stm32f1xx_hal.h"

static ADC_HandleTypeDef s_hadc1;
static volatile uint16_t s_raw_ia = 0;
static volatile uint16_t s_raw_ib = 0;
static volatile uint16_t s_raw_ic = 0;
static volatile uint16_t s_raw_vbus = 0;

static uint16_t s_off_ia = 2048;
static uint16_t s_off_ib = 2048;
static uint16_t s_off_ic = 2048;

static void adc_gpio_init(void) {
  __HAL_RCC_GPIOA_CLK_ENABLE();
#if USE_PHASE_MEAS
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
  gpio.Pin = PHASE_MEAS_C_PIN;
  HAL_GPIO_Init(GPIOB, &gpio);
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
#if LINK_USE_SPI
  inj.InjectedChannel = ADC_CHANNEL_3; // VBUS PA3
#else
  inj.InjectedChannel = ADC_CHANNEL_5; // VBUS PA5
#endif
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

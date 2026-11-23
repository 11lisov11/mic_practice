#ifndef MIC_ADC_DEADLINE_H
#define MIC_ADC_DEADLINE_H
#include <stdint.h>

enum { MIC_ADC_PUBLISH_MARGIN_TICKS=2048U };

/* RCR=1 is initialized before CEN, so UEV is at the bottom, not the apex.
 * Permit JEOS in either half of THAT epoch, but leave >12us to its next UEV.
 * No forced update, PWM duty change or shortened analog settling guard. */
static inline int mic_adc_publish_in_time(uint32_t arr,uint32_t count,
    uint32_t down,uint32_t trigger) {
  if(arr<=MIC_ADC_PUBLISH_MARGIN_TICKS || arr>65535U || count>arr || trigger>=arr)return 0;
  uint32_t phase=down?2U*arr-count:count;
  return phase>=trigger && phase<2U*arr-MIC_ADC_PUBLISH_MARGIN_TICKS;
}
static inline int mic_adc_bottom_update(uint32_t arr,uint32_t count,uint32_t down) {
  return arr>MIC_ADC_PUBLISH_MARGIN_TICKS && count<MIC_ADC_PUBLISH_MARGIN_TICKS && !down;
}
#endif

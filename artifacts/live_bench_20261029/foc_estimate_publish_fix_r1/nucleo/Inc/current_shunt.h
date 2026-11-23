#ifndef MIC_CURRENT_SHUNT_H
#define MIC_CURRENT_SHUNT_H
#include <stdint.h>
void mic_current_init(void);
void mic_current_adc_irq(void);
uint8_t mic_current_packet(uint8_t *packet,uint8_t detail,uint32_t build);
void mic_current_update_epoch(void);
uint8_t mic_current_regular_window(void);
uint8_t mic_current_peak_packet(uint8_t *packet,uint8_t page,uint32_t build);
uint8_t mic_zero_packet(uint8_t *packet,uint32_t build);
uint8_t mic_current_noise_packet(uint8_t*,uint8_t,uint32_t);
#endif

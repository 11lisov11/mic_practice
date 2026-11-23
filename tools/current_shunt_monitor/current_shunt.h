#ifndef MIC_CURRENT_SHUNT_H
#define MIC_CURRENT_SHUNT_H
#include <stdint.h>
void mic_current_init(void);
void mic_current_adc_irq(void);
void mic_current_packet(uint8_t *packet,uint8_t detail,uint32_t build);
#endif

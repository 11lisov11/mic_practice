#ifndef MIC_NUCLEO_ENCODER_H
#define MIC_NUCLEO_ENCODER_H
#include <stdint.h>
void mic_encoder_init(void);
void mic_encoder_poll(void);
void mic_encoder_packet(uint8_t *packet,uint32_t fw);
#endif

#ifndef MIC_NUCLEO_ENCODER_H
#define MIC_NUCLEO_ENCODER_H
#include <stdint.h>
#include <stdbool.h>
void mic_encoder_init(void);
void mic_encoder_poll(void);
void mic_encoder_packet(uint8_t *packet,uint32_t fw);
bool mic_encoder_fault_packet(uint8_t*,unsigned,unsigned);
void mic_encoder_health_snapshot(uint32_t*);
bool mic_encoder_release_packet(uint8_t*,unsigned,unsigned);
#endif

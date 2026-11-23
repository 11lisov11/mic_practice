#ifndef MIC_NO_SWITCH_DIAG_H
#define MIC_NO_SWITCH_DIAG_H
#include <stdint.h>
#include <stdbool.h>
void mic_load_prepare_pins(void);
void mic_load_init(void);
void mic_load_poll(void);
void mic_load_tim_update(void);
void mic_load_medium_update(void);
bool mic_load_active(void);
void mic_load_adc_enter(uint32_t cycles);
void mic_load_adc_exit(uint32_t cycles,uint32_t good);
void mic_encoder_load_snapshot(uint32_t *words);
uint32_t mic_current_load_quality(void);
#endif

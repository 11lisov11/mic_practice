#pragma once

#include <stdbool.h>
#include <stdint.h>

void adc_currents_init(void);
void adc_currents_get(float *ia, float *ib, float *ic, float *vbus);
bool adc_vbus_sample_software(uint16_t *raw);
uint16_t adc_vbus_raw(void);

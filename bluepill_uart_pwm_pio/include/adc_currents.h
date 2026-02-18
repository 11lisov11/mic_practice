#pragma once

#include <stdint.h>

void adc_currents_init(void);
void adc_currents_get(float *ia, float *ib, float *ic, float *vbus);

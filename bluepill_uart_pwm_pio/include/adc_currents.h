#pragma once

#include <stdbool.h>
#include <stdint.h>

void adc_currents_init(void);
void adc_currents_get(float *ia, float *ib, float *ic, float *vbus);
bool adc_vbus_sample_software(uint16_t *raw);
uint16_t adc_vbus_raw(void);
bool adc_heatsink_sample_software(uint16_t *raw);
uint16_t adc_heatsink_raw(void);
bool adc_heatsink_get(float *voltage, float *temp_c);
bool adc_heatsink_fault_active(void);
bool adc_phase_measure_sample_software(uint16_t *raw_a, uint16_t *raw_b, uint16_t *raw_c_virtual);
void adc_phase_measure_raw(uint16_t *raw_a, uint16_t *raw_b, uint16_t *raw_c_virtual);
bool adc_phase_measure_valid(void);

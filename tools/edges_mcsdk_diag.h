#ifndef MIC_EDGES_MCSDK_DIAG_H
#define MIC_EDGES_MCSDK_DIAG_H
#include <stdint.h>
void mic_motor_backend_init(void);
void mic_edges_io_init(void);
void mic_edges_adc_enter(void);
void mic_edges_adc_exit(void);
uint32_t mic_edges_guard(void);
void mic_edges_observe_safety(void);
void mic_pin_force_abort(uint32_t reason);
uint32_t mic_edges_adc_all(void);
uint32_t mic_edges_adc_run(void);
uint32_t mic_edges_adc_bad(void);
uint32_t mic_edges_adc_max_cost(void);
uint32_t mic_edges_backend_flags(void);
#endif

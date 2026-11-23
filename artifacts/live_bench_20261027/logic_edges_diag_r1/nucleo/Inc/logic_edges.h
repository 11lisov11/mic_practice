#ifndef MIC_LOGIC_EDGES_H
#define MIC_LOGIC_EDGES_H
#include <stdint.h>
#include <stdbool.h>
/* Auxiliary TIM8 only. Original six motor pins/TIM1 must remain inhibited. */
void mic_edges_init(void);
uint32_t mic_edges_guard(void);
void mic_edges_begin(void);
bool mic_edges_update(uint32_t elapsed,uint32_t hz);
void mic_edges_stop(bool fault);
void mic_encoder_load_counters(uint32_t *reads,uint32_t *errors);
extern volatile uint32_t mic_logic_edge_report[12];
#endif

#ifndef MIC_LOCAL_STOP_H
#define MIC_LOCAL_STOP_H

#include <stdbool.h>
#include <stdint.h>

extern volatile uint32_t mic_local_stop_latched;
bool mic_local_stop_blocked(void);
bool mic_local_stop_clear(void);
void mic_local_stop_enable_outputs(TIM_TypeDef *timer);

#endif

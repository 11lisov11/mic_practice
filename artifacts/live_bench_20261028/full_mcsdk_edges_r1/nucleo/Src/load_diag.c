#include "load_diag.h"
bool mic_load_active(void){return false;}
void mic_load_tim_update(void){}
void mic_load_medium_update(void){}
void mic_load_adc_enter(uint32_t now){(void)now;}
void mic_load_adc_exit(uint32_t now,uint32_t good){(void)now;(void)good;}

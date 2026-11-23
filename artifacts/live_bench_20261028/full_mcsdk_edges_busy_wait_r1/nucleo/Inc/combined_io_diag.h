#ifndef MIC_COMBINED_IO_DIAG_H
#define MIC_COMBINED_IO_DIAG_H
#include <stdint.h>
void mic_io_init(void);
void mic_io_poll(void);
uint32_t mic_io_guard(void);
void mic_io_adc_enter(void);
void mic_io_adc_exit(void);
void mic_io_uart_snapshot(uint32_t *words);
#endif

#ifndef MIC_FULL_MCSDK_DIAG_H
#define MIC_FULL_MCSDK_DIAG_H
#include <stdint.h>
extern volatile uint32_t mic_full_fixture_denials;
void mic_full_task(unsigned index);
void mic_full_command(uint8_t flags,uint8_t mode);
void mic_full_init(void);
void mic_full_publish(void);
uint32_t mic_full_guard(void);
#endif

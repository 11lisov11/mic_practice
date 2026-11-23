#ifndef MIC_PIN_PWM_DIAG_H
#define MIC_PIN_PWM_DIAG_H
#include <stdint.h>
#include <stdbool.h>
bool mic_pin_active(void);
void mic_pin_init(void);
void mic_pin_poll(void);
void mic_pin_irq(void);
void mic_pin_break(void);
#endif

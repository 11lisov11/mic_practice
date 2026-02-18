#pragma once

#include <stdbool.h>
#include <stdint.h>

void pwm_tim1_init(void);
void pwm_set_duty_q15(uint16_t du, uint16_t dv, uint16_t dw);
void pwm_apply_diag(void);
void pwm_outputs_enable(bool enable);
void pwm_all_off(void);

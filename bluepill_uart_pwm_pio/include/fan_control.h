#pragma once

#include <stdint.h>

void fan_control_init(void);
void fan_control_tick(void);
void fan_control_set_pwm_q15(uint16_t duty_q15);
uint16_t fan_control_duty_q15(void);
uint16_t fan_control_rpm(void);
uint8_t fan_control_reply_duty_q8(void);
uint8_t fan_control_reply_tach_x30(void);

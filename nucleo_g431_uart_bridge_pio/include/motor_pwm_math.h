#pragma once

#include <stdint.h>

uint32_t motor_pwm_center_aligned_arr(uint32_t timer_clock_hz, uint32_t pwm_hz);
uint8_t motor_pwm_encode_deadtime_ticks(uint32_t ticks);
uint32_t motor_pwm_decode_deadtime_ticks(uint8_t encoded);
uint32_t motor_pwm_q15_to_compare(uint16_t q15, uint32_t arr);

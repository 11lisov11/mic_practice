#include "motor_pwm_math.h"

uint32_t motor_pwm_center_aligned_arr(uint32_t timer_clock_hz, uint32_t pwm_hz) {
  if (timer_clock_hz == 0U || pwm_hz == 0U) {
    return 0U;
  }
  const uint32_t counts = timer_clock_hz / (2U * pwm_hz);
  return counts > 0U ? counts - 1U : 0U;
}

uint8_t motor_pwm_encode_deadtime_ticks(uint32_t ticks) {
  if (ticks <= 127U) {
    return (uint8_t)ticks;
  }
  if (ticks <= 254U) {
    uint32_t scaled = (ticks + 1U) / 2U;
    if (scaled < 64U) scaled = 64U;
    if (scaled > 127U) scaled = 127U;
    return (uint8_t)(0x80U | (scaled - 64U));
  }
  if (ticks <= 504U) {
    uint32_t scaled = (ticks + 7U) / 8U;
    if (scaled < 32U) scaled = 32U;
    if (scaled > 63U) scaled = 63U;
    return (uint8_t)(0xC0U | (scaled - 32U));
  }
  if (ticks > 1008U) ticks = 1008U;
  uint32_t scaled = (ticks + 15U) / 16U;
  if (scaled < 32U) scaled = 32U;
  if (scaled > 63U) scaled = 63U;
  return (uint8_t)(0xE0U | (scaled - 32U));
}

uint32_t motor_pwm_decode_deadtime_ticks(uint8_t encoded) {
  if ((encoded & 0x80U) == 0U) {
    return encoded;
  }
  if ((encoded & 0xC0U) == 0x80U) {
    return (64U + (encoded & 0x3FU)) * 2U;
  }
  if ((encoded & 0xE0U) == 0xC0U) {
    return (32U + (encoded & 0x1FU)) * 8U;
  }
  return (32U + (encoded & 0x1FU)) * 16U;
}

uint32_t motor_pwm_q15_to_compare(uint16_t q15, uint32_t arr) {
  if (q15 > 32767U) q15 = 32767U;
  return ((uint64_t)(arr + 1U) * q15) / 32767U;
}
